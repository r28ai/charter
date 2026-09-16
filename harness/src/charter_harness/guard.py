"""
The guard: the one approval policy every arm runs under.

The harness drives real accounts. Most of what a scenario asks for is reversible
or namespaced, and the account owner has said the rest is acceptable — with three
exceptions the guard makes mechanical rather than hoped for:

1. **Nothing is ever sent from the mailbox.** Neither ``gmail.messages_send``
   nor ``gmail.drafts_send`` is in the Charter arm's tool set, and the raw arm
   may not POST to either path. Gmail has two ways to send and a rule naming
   only one of them is a rule against half of sending.
2. **GitHub writes stay inside sandbox repositories.** Any non-GET call must
   target ``<GITHUB_OWNER>/harness-*``. Existing repositories are read-only.
3. **Deletes and channel writes stay on what this run made.** A calendar event
   or a mail thread may only be deleted if this run created it — the seed, or
   the agent itself; a Slack write may only go to the harness channel. The
   mailbox holds real correspondence, and ``threads.delete`` is permanent rather
   than a move to the bin.

   The agent's own creations count, and that is not a loosening. Restricted to
   seeded fixtures, the rule refused an agent deleting an event it had inserted
   moments earlier: one ``sheet_to_calendar`` run wrote three events at the wrong
   offset, noticed, was refused all three deletes, and recreated them correctly,
   leaving six where three were expected. It failed a task it had already
   recovered from. The rule is the same on every arm but the cost is not — it
   falls only on an agent that cleans up after itself. See
   :mod:`charter_harness.arms.ownership`.

And one rule that is about the comparison rather than safety: **the raw arm may
only reach the endpoints the Charter arm has tools for.** The allow-list is
compiled from the same pack tools the raw tool's description was derived from,
so "same endpoints on both arms" is enforced, not asserted.

A rejected call is reported to the model with the reason (Inspect's ``reject``
decision) and counted in the ledger. The decision function is pure so the rules
can be unit-tested offline without an eval running.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from re import Pattern
from typing import Any

from inspect_ai.approval import Approval, ApprovalPolicy, Approver, approver
from inspect_ai.model import ChatMessage
from inspect_ai.tool import ToolCall, ToolCallView

from charter_harness.arms.ledger import ledger
from charter_harness.arms.raw_arm import GRAPHQL_PACKS, endpoints_for, normalise_path
from charter_harness.context import RunContext, run_context

__all__ = ["GuardContext", "decide", "harness_guard", "guard_policy", "SANDBOX_REPO"]


@dataclass
class GuardContext:
    """The slice of the run the guard reasons about — a plain value, so tests can
    build one without an Inspect store behind it."""

    arm: str
    tool_index: Mapping[str, Sequence[str]] = field(default_factory=dict)
    owned: Mapping[str, Sequence[str]] = field(default_factory=dict)
    github_owner: str = ""

    def owns(self, kind: str, identifier: Any) -> bool:
        return str(identifier) in set(self.owned.get(kind, []))

    @classmethod
    def from_run(cls, ctx: RunContext) -> GuardContext:
        return cls(
            arm=ctx.arm,
            tool_index=dict(ctx.tool_index),
            owned=dict(ctx.owned),
            github_owner=ctx.github_owner,
        )

SANDBOX_REPO: Pattern[str] = re.compile(r"^harness-[A-Za-z0-9._-]+$")

# Both of Gmail's ways to send. `messages_send` posts a new message and
# `drafts_send` posts an existing draft; they reach the same recipients, so a
# rule naming only the first is a rule against half of sending.
GMAIL_SEND_TOOLS = frozenset({"messages_send", "drafts_send"})

# Destroying mail the seed did not create. `threads_delete` is permanent — not a
# move to the bin — and the mailbox holds real correspondence.
GMAIL_THREAD_DESTROY = frozenset({"threads_delete", "threads_trash"})

GITHUB_WRITE_TOOLS = {"issues_create", "issues_update", "issues_create_comment", "pulls_create"}
SLACK_WRITE_TOOLS = {"chat_post_message", "chat_update", "chat_delete", "reactions_add"}
SLACK_WRITE_PATHS = {"chat.postMessage", "chat.update", "chat.delete", "reactions.add"}

_GCAL_DELETE = re.compile(r"^calendar/v3/calendars/[^/]+/events/([^/?#]+)$")
_GMAIL_THREAD = re.compile(r"^gmail/v1/users/[^/]+/threads/([^/?#]+?)(?:/trash)?$")
_GITHUB_REPO = re.compile(r"^repos/([^/]+)/([^/]+)(?:/|$)")

_ENDPOINT_CACHE: dict[str, list[tuple[str, Pattern[str]]]] = {}


def _endpoint_patterns(pack: str) -> list[tuple[str, Pattern[str]]]:
    if pack not in _ENDPOINT_CACHE:
        _ENDPOINT_CACHE[pack] = [(ep.method, ep.regex) for ep in endpoints_for(pack)]
    return _ENDPOINT_CACHE[pack]


def _sandbox_repo(owner: Any, repo: Any, ctx: GuardContext) -> str | None:
    if ctx.github_owner and str(owner).lower() != ctx.github_owner.lower():
        return f"GitHub writes are limited to repositories under {ctx.github_owner}; got {owner!r}."
    if not SANDBOX_REPO.match(str(repo)):
        return f"GitHub writes are limited to sandbox repositories named harness-*; got {repo!r}."
    return None


def _slack_channel_ok(channel: Any, ctx: GuardContext) -> str | None:
    allowed = set(ctx.owned.get("slack.channel", []))
    if not allowed:
        return "Slack writes are disabled for this run (no harness channel recorded)."
    value = str(channel or "").lstrip("#")
    if value in allowed or f"#{value}" in allowed:
        return None
    return f"Slack writes are limited to the harness channel; got {channel!r}."


def _charter_decision(pack: str, tool: str, args: Mapping[str, Any], ctx: GuardContext) -> str | None:
    if pack == "gmail" and tool in GMAIL_SEND_TOOLS:
        return "Sending email is not permitted in this environment."
    if pack == "github" and tool in GITHUB_WRITE_TOOLS:
        return _sandbox_repo(args.get("owner"), args.get("repo"), ctx)
    if pack == "gmail" and tool in GMAIL_THREAD_DESTROY:
        if not ctx.owns("gmail.thread", args.get("id")):
            return "Only mail threads created for this task may be deleted or trashed."
    if pack == "gcalendar" and tool == "events_delete":
        if not ctx.owns("gcalendar.event", args.get("eventId")):
            return "Only events created for this task may be deleted."
    if pack == "slack" and tool in SLACK_WRITE_TOOLS:
        return _slack_channel_ok(args.get("channel"), ctx)
    return None


def _raw_decision(pack: str, args: Mapping[str, Any], ctx: GuardContext) -> str | None:
    if pack in GRAPHQL_PACKS:
        return None

    method = str(args.get("method", "GET")).upper()
    # normalise_path strips any scheme+host the model pasted, so the guard
    # compares the same bare path the raw tool will send.
    path = normalise_path(str(args.get("path", "")), "")

    if not any(m == method and rx.match(path) for m, rx in _endpoint_patterns(pack)):
        return (
            f"{method} {path} is not an available endpoint for {pack}; see the tool description "
            "for the endpoints you can call."
        )

    if pack == "github" and method != "GET":
        match = _GITHUB_REPO.match(path)
        if not match:
            return "GitHub writes must target a repository path."
        return _sandbox_repo(match.group(1), match.group(2), ctx)

    if pack == "gmail" and (method == "DELETE" or path.endswith("/trash")):
        match = _GMAIL_THREAD.match(path)
        if match and not ctx.owns("gmail.thread", match.group(1)):
            return "Only mail threads created for this task may be deleted or trashed."

    if pack == "gcalendar" and method == "DELETE":
        match = _GCAL_DELETE.match(path)
        if not match or not ctx.owns("gcalendar.event", match.group(1)):
            return "Only events created for this task may be deleted."

    if pack == "slack" and method == "POST" and path in SLACK_WRITE_PATHS:
        body = args.get("body") or {}
        return _slack_channel_ok(body.get("channel") if isinstance(body, dict) else None, ctx)

    return None


def decide(function: str, arguments: Mapping[str, Any], ctx: GuardContext) -> str | None:
    """The reason a call is rejected, or ``None`` to approve it."""
    entry = ctx.tool_index.get(function)
    if entry is None:
        # A tool the arm did not register (the submit tool, for instance).
        return None
    pack, charter_tool = entry
    if ctx.arm == "raw":
        return _raw_decision(pack, arguments, ctx)
    return _charter_decision(pack, charter_tool, arguments, ctx)


@approver(name="harness_guard")
def harness_guard() -> Approver:
    async def approve(
        message: str,
        call: ToolCall,
        view: ToolCallView,
        history: Sequence[ChatMessage],
    ) -> Approval:
        ctx = GuardContext.from_run(run_context())
        reason = decide(call.function, call.arguments or {}, ctx)
        if reason is None:
            return Approval(decision="approve")
        led = ledger()
        led.guard_rejections = led.guard_rejections + [
            {"tool": call.function, "arguments": call.arguments, "reason": reason}
        ]
        return Approval(decision="reject", explanation=f"Rejected by the environment: {reason}")

    return approve


def guard_policy() -> list[ApprovalPolicy]:
    """The policy for a task: every tool call passes through the guard."""
    return [ApprovalPolicy(approver=harness_guard(), tools="*")]
