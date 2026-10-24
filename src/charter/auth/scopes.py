# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""What a tool needs from a grant, and the fewest, narrowest scopes a set of tools needs.

A tool's ``scopes`` is a list of requirements, and a grant runs the tool when it
meets every one. A requirement is a scope, or an :class:`AnyOf`: the scopes a
provider accepts for the same call, narrowest first. Google's
``users.messages.send`` takes ``gmail.send``, ``gmail.compose``, ``gmail.modify``
or the full mailbox, so ``messages_send`` declares all four in that order, and an
agent that only sends asks for ``gmail.send``.

Which scope covers which is never declared. It is read off the requirements:
``gmail.modify`` is accepted wherever ``gmail.readonly`` is, so an agent that
reads and relabels asks for ``gmail.modify`` alone, without a hierarchy table that
would have to be kept in step with the provider.

:func:`scopes_for` starts from every scope any requirement offers and drops them
broadest first, keeping a scope only when something would be left uncovered
without it. The order comes from the declarations themselves: a scope listed
before another in some :class:`AnyOf` is the narrower of the two. The result
depends on which tools are handed in, never on the order they are handed in.

Some providers issue more than one kind of credential, each with its own names:
GitHub's OAuth apps and classic tokens take scopes (``repo``), its GitHub Apps
and fine-grained tokens take permissions (``issues:write``), set where the app is
created. A pack declares each :class:`Kind` once, every tool says what it needs
under each, and ``scopes_for(tools, kind=github.APP)`` answers for that kind. A
tool that cannot run under a kind at all says so with :class:`Unavailable`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional, Union

from charter.types.errors import DeclarationError

if TYPE_CHECKING:
    from charter.tool import Tool

__all__ = [
    "AnyOf",
    "Kind",
    "ScopeRequirement",
    "Unavailable",
    "check_scopes",
    "missing_scopes",
    "scopes_for",
]


class AnyOf:
    """One requirement several scopes can meet, listed narrowest first.

    List only scopes that let the tool do everything its arguments can ask for.
    Google's ``files.get`` also accepts ``drive.file``, but that scope reaches only
    files the app created, so ``files_get`` does not offer it: a grant holding it
    would pass the consent screen and then fail on the user's own files.
    """

    __slots__ = ("options",)
    options: tuple[str, ...]

    def __init__(self, *options: str) -> None:
        if not options:
            raise DeclarationError(
                "AnyOf() needs at least one scope.", docs="reference/oauth#anyof"
            )
        for option in options:
            if not isinstance(option, str) or not option.strip():
                raise DeclarationError(
                    f"AnyOf() takes scope strings; got {option!r}.", docs="reference/oauth#anyof"
                )
        if len(set(options)) != len(options):
            raise DeclarationError(
                f"AnyOf{options!r} names a scope twice.", docs="reference/oauth#anyof"
            )
        object.__setattr__(self, "options", tuple(options))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("AnyOf is immutable")

    def met_by(self, granted: Iterable[str]) -> bool:
        held = set(granted)
        return any(option in held for option in self.options)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, AnyOf) and other.options == self.options

    def __hash__(self) -> int:
        return hash(("AnyOf", self.options))

    def __repr__(self) -> str:
        return "AnyOf(" + ", ".join(repr(o) for o in self.options) + ")"


class Unavailable:
    """A tool that cannot run under one kind of credential, and why.

    GitHub Apps cannot read notifications, so ``notifications_list`` declares
    ``Unavailable("GitHub Apps cannot read notifications")`` for ``github.APP``.
    :func:`scopes_for` refuses a tool set that includes it for that kind, naming
    the tool and the reason, rather than building a grant that cannot run it.
    """

    __slots__ = ("reason",)
    reason: str

    def __init__(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise DeclarationError(
                "Unavailable() needs the reason, in words.", docs="reference/oauth#unavailable"
            )
        object.__setattr__(self, "reason", reason)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Unavailable is immutable")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Unavailable) and other.reason == self.reason

    def __hash__(self) -> int:
        return hash(("Unavailable", self.reason))

    def __repr__(self) -> str:
        return f"Unavailable({self.reason!r})"


ScopeRequirement = Union[str, AnyOf, Unavailable]


@dataclass(frozen=True)
class Kind:
    """One kind of credential a provider issues, with its own permission names.

    ``granted`` says how a credential of this kind gets them: ``"consent"`` when
    the authorization request names them (OAuth scopes), ``"configured"`` when they
    are set where the app or key is created (a GitHub App's permissions, a Stripe
    restricted key's). ``default`` marks the kind a plain list of scopes means.
    Declared once per pack and imported, so a kind is never a string to misspell::

        scopes_for(tools, kind=github.APP)
    """

    name: str
    provider: str
    granted: Literal["consent", "configured"] = "consent"
    default: bool = False
    description: str = field(default="", compare=False)

    def __str__(self) -> str:
        return f"{self.provider}.{self.name}"


def _options(requirement: ScopeRequirement) -> tuple[str, ...]:
    if isinstance(requirement, Unavailable):
        return ()
    return (requirement,) if isinstance(requirement, str) else requirement.options


def check_scopes(scopes: Sequence[object], *, where: str) -> list[ScopeRequirement]:
    """Validate one kind's ``scopes``: each item a scope string, an AnyOf or an Unavailable."""
    if isinstance(scopes, (str, bytes)) or not isinstance(scopes, Sequence):
        raise DeclarationError(
            f"{where}: scopes must be a list of requirements; got {scopes!r}.",
            docs="reference/oauth#anyof",
        )
    out: list[ScopeRequirement] = []
    for item in scopes:
        if isinstance(item, (AnyOf, Unavailable)) or (isinstance(item, str) and item.strip()):
            out.append(item)
            continue
        raise DeclarationError(
            f"{where}: scopes must be scope strings, AnyOf(...) or Unavailable(...); got {item!r}.",
            docs="reference/oauth#anyof",
        )
    return out


@dataclass(frozen=True)
class Scopes:
    """A tool's requirements under each kind of credential its provider issues.

    ``default`` is what a plain list declared, under ``default_kind`` when the pack
    names it; ``kinds`` holds every other kind. Built by :func:`normalize_scopes`
    from whatever a declaration passed, and merged by :func:`merge_scopes`.
    """

    default: tuple[ScopeRequirement, ...] = ()
    default_kind: Optional[Kind] = None
    kinds: Mapping[Kind, tuple[ScopeRequirement, ...]] = field(default_factory=dict)


ScopesDeclaration = Union[
    Sequence[ScopeRequirement], Mapping[Kind, Sequence[ScopeRequirement]], Scopes
]


def normalize_scopes(scopes: Optional[ScopesDeclaration], *, where: str) -> Scopes:
    """A list (the default kind), a mapping of kinds to lists, or a Scopes, as a Scopes."""
    if scopes is None:
        return Scopes()
    if isinstance(scopes, Scopes):
        return scopes
    if isinstance(scopes, Mapping):
        defaults = [k for k in scopes if isinstance(k, Kind) and k.default]
        strays = [k for k in scopes if not isinstance(k, Kind)]
        if strays:
            raise DeclarationError(
                f"{where}: a scopes mapping is keyed by Kind; got {strays[0]!r}. Import the "
                "kind from its pack (github.APP), or pass a plain list for the default.",
                docs="reference/oauth#kind",
            )
        if len(defaults) > 1:
            raise DeclarationError(
                f"{where}: two default kinds, {defaults}.", docs="reference/oauth#kind"
            )
        providers = {k.provider for k in scopes}
        if len(providers) > 1:
            raise DeclarationError(
                f"{where}: kinds of two providers, {sorted(providers)}.",
                docs="reference/oauth#kind",
            )
        default_kind = defaults[0] if defaults else None
        kinds = {
            k: tuple(check_scopes(v, where=f"{where} [{k}]"))
            for k, v in scopes.items()
            if not k.default
        }
        default = tuple(check_scopes(scopes[default_kind], where=where)) if default_kind else ()
        return Scopes(default=default, default_kind=default_kind, kinds=kinds)
    return Scopes(default=tuple(check_scopes(scopes, where=where)))


def merge_scopes(base: Scopes, override: Optional[ScopesDeclaration], *, where: str) -> Scopes:
    """A factory's scopes with one tool's on top: a list replaces the default kind's,
    a mapping replaces the kinds it names and keeps the rest."""
    if override is None:
        return base
    if not isinstance(override, (Mapping, Scopes)):
        return Scopes(
            default=tuple(check_scopes(override, where=where)),
            default_kind=base.default_kind,
            kinds=base.kinds,
        )
    top = normalize_scopes(override, where=where)
    default_kind = top.default_kind or base.default_kind
    if base.default_kind and top.default_kind and base.default_kind != top.default_kind:
        raise DeclarationError(
            f"{where}: default kind {top.default_kind} differs from the factory's {base.default_kind}.",
            docs="reference/oauth#kind",
        )
    default = top.default if top.default_kind else base.default
    return Scopes(default=default, default_kind=default_kind, kinds={**base.kinds, **top.kinds})


def _requirements(tool: Tool, kind: Union[Kind, str, None]) -> Sequence[ScopeRequirement]:
    """What one tool needs under ``kind``; the default kind when ``kind`` is None."""
    if kind is None:
        return tool.scopes
    name = kind.name if isinstance(kind, Kind) else kind
    if isinstance(kind, Kind) and kind.provider != tool.provider:
        raise DeclarationError(
            f"{kind} is a {kind.provider} kind of credential; {tool.name} is a "
            f"{tool.provider} tool. Ask for each provider's tools separately.",
            docs="reference/oauth#kind",
        )
    default_kind = tool.default_kind
    if default_kind is not None and default_kind.name == name:
        return tool.scopes
    for declared, requirements in tool.kind_scopes.items():
        if declared.name == name:
            return requirements
    known = [k.name for k in ([default_kind] if default_kind else []) + list(tool.kind_scopes)]
    raise DeclarationError(
        f"{tool.name} declares nothing for kind {name!r}"
        + (
            f"; it declares {', '.join(repr(k) for k in known)}. Import the kind from "
            f"its pack ({tool.pack or tool.provider}.{known[-1].upper()}) rather than "
            "spelling it."
            if known
            else "; it declares only plain scopes."
        ),
        docs="reference/oauth#kind",
    )


def _kinds_of(tool: Tool) -> list[Kind]:
    return ([tool.default_kind] if tool.default_kind else []) + list(tool.kind_scopes)


def _clauses(tools: Iterable[Tool], kind: Union[Kind, str, None] = None) -> list[tuple[str, ...]]:
    seen: list[tuple[str, ...]] = []
    refused: dict[str, list[str]] = {}
    usable: Optional[list[Kind]] = None
    label = str(kind) if isinstance(kind, Kind) else kind
    for tool in tools:
        if label is None and tool.default_kind is not None:
            label = str(tool.default_kind)
        for requirement in _requirements(tool, kind):
            if isinstance(requirement, Unavailable):
                refused.setdefault(requirement.reason, []).append(tool.name)
                # The kinds every refused tool can run under, to suggest one.
                here = [
                    k
                    for k in _kinds_of(tool)
                    if not any(isinstance(r, Unavailable) for r in _requirements(tool, k))
                ]
                usable = here if usable is None else [k for k in usable if k in here]
                continue
            options = _options(requirement)
            if options not in seen:
                seen.append(options)
    if refused:
        hint = (
            "ask with " + " or ".join(f"kind={k.provider}.{k.name.upper()}" for k in usable)
            if usable
            else "ask for them separately, under another kind"
        )
        raise DeclarationError(
            f"These tools cannot run with a {label or 'default'} credential: "
            + "; ".join(f"{', '.join(names)} ({reason})" for reason, names in refused.items())
            + f". Leave them out, or {hint}.",
            docs="reference/oauth#unavailable",
        )
    return seen


def _narrowest_first(clauses: list[tuple[str, ...]]) -> list[str]:
    """Every scope the clauses offer, ordered so each comes before any listed after it.

    Ties are broken by the scope string, so the order is a function of the set of
    clauses and not of the order they arrived in. Two declarations that disagree
    about which of two scopes is narrower are refused rather than resolved.
    """
    after: dict[str, set[str]] = {}
    before_count: dict[str, int] = {}
    for clause in clauses:
        for scope in clause:
            after.setdefault(scope, set())
            before_count.setdefault(scope, 0)
    for clause in clauses:
        for i, narrower in enumerate(clause):
            for broader in clause[i + 1 :]:
                if broader not in after[narrower]:
                    after[narrower].add(broader)
                    before_count[broader] += 1
    ready = sorted(s for s, n in before_count.items() if n == 0)
    order: list[str] = []
    while ready:
        scope = ready.pop(0)
        order.append(scope)
        for broader in sorted(after[scope]):
            before_count[broader] -= 1
            if before_count[broader] == 0:
                ready.append(broader)
                ready.sort()
    if len(order) != len(before_count):
        stuck = sorted(s for s, n in before_count.items() if n > 0)
        pairs = [(a, b) for a in stuck for b in stuck if a < b and b in after[a] and a in after[b]]
        detail = (
            f" ({pairs[0][0]} and {pairs[0][1]} are each listed before the other)" if pairs else ""
        )
        raise DeclarationError(
            f"These tools disagree about which scopes are narrower{detail}. List every "
            f"AnyOf narrowest first, the same way in each tool. Involved: {stuck}.",
            docs="reference/oauth#anyof",
        )
    return order


def _cover(clauses: list[tuple[str, ...]]) -> list[str]:
    if not clauses:
        return []
    allowed = set(_narrowest_first(clauses))
    for scope in reversed(_narrowest_first(clauses)):
        rest = allowed - {scope}
        if all(any(option in rest for option in clause) for clause in clauses):
            allowed = rest
    # First-seen order, so a consent screen lists scopes the way the tools did.
    out: list[str] = []
    for clause in clauses:
        for option in clause:
            if option in allowed and option not in out:
                out.append(option)
    return out


def scopes_for(tools: Iterable[Tool], kind: Union[Kind, str, None] = None) -> list[str]:
    """The fewest, narrowest scopes an authorization request needs to run these tools.

    ``kind`` asks about another kind of credential than the pack's default:
    ``scopes_for(tools, kind=github.APP)`` is the permissions to set on a GitHub
    App, ``kind=stripe.RESTRICTED_KEY`` the narrowest restricted key.

    Every tool's requirements are met by the result, no scope in it can be dropped
    without leaving one unmet, and among such sets it is the one that avoids the
    broadest scopes first. A tool that declares plain scopes needs each of them, so
    tools declared that way get their union, as before.
    """
    return _cover(_clauses(tools, kind))


def missing_scopes(
    tools: Iterable[Tool], granted: Iterable[str], kind: Union[Kind, str, None] = None
) -> list[str]:
    """What to add to a grant so it runs every one of these tools; empty when it does.

    Compares by requirement rather than by string, so a grant holding
    ``gmail.modify`` runs a tool that asks for ``gmail.readonly`` first. The
    answer is :func:`scopes_for` over the requirements the grant leaves unmet: the
    narrowest scopes that would close the gap.
    """
    held = set(granted)
    unmet = [clause for clause in _clauses(tools, kind) if not any(o in held for o in clause)]
    return _cover(unmet)
