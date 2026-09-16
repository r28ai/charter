"""Every documentation link an error can print resolves to something real.

A dead link inside an exception is worse than no link: it reaches someone who is
already stuck, and it is the one kind of broken promise a library selling
determinism cannot afford. Errors carry a slug rather than a URL precisely so
this file can exist — the slugs are enumerable from the source, and each one is
resolved here against the docs tree that ships beside it.

Three kinds of slug, checked three ways:

* **Literal** — ``docs="auth/oauth-flow#refresh-tokens"`` at a raise site, found
  by walking the AST of every module.
* **Per-provider** — the map behind ``provider_docs()``, plus its fallback.
* **Per-pack** — ``docs=f"packs/{self._pack}"``, which no literal scan can see,
  so the packs themselves are the list.

A page counts as resolving when the file exists under ``docs/``; an anchor counts
when a heading on that page would produce it. Anything a raise site can print,
this file can find.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path as FsPath
from typing import Iterator, Set, Tuple

import pytest

import charter
from charter.mcp import PACKS
from charter.types.errors import _PROVIDER_PAGES, provider_docs

SRC = FsPath(charter.__file__).parent
DOCS = FsPath(__file__).resolve().parent.parent / "docs"

# `## \x60name\x60`, `### Heading`, and the frontmatter title: the three things
# Mintlify turns into an anchor on a page.
_HEADING = re.compile(r"^#{2,6}\s+(.+?)\s*$", re.M)


def _source_files() -> list[FsPath]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _literal_slugs() -> Set[Tuple[str, str]]:
    """Every ``docs="..."`` literal in the library, with where it was written.

    An AST walk rather than a registry of constants: the slug reads better at the
    raise site than a name pointing at one, and a walk catches a typo anywhere
    rather than only in the names someone remembered to register.
    """
    found: Set[Tuple[str, str]] = set()
    for path in _source_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "docs" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, str):
                        where = f"{path.relative_to(SRC)}:{keyword.value.lineno}"
                        found.add((keyword.value.value, where))
    return found


def _page_for(slug: str) -> FsPath | None:
    """The file a slug's page part names, or None."""
    page = slug.split("#", 1)[0].rstrip("/")
    # is_file, not exists: `docs/auth` is a directory, and a slug naming one
    # would otherwise pass this check and 404 for the reader.
    for candidate in (DOCS / f"{page}.mdx", DOCS / f"{page}.md", DOCS / page):
        if candidate.is_file():
            return candidate
    return None


def _anchors(page: FsPath) -> Set[str]:
    """The anchors a page offers, as Mintlify slugifies its headings."""
    anchors = set()
    for heading in _HEADING.findall(page.read_text()):
        text = heading.replace("`", "").strip().lower()
        anchors.add(re.sub(r"[^a-z0-9_]+", "-", text).strip("-"))
        anchors.add(re.sub(r"[^a-z0-9]+", "-", text).strip("-"))
    return anchors


def _resolves(slug: str) -> Iterator[str]:
    """Whatever is wrong with ``slug``, or nothing."""
    page = _page_for(slug)
    if page is None:
        yield f"no page under docs/ for {slug!r}"
        return
    if "#" in slug:
        anchor = slug.split("#", 1)[1]
        if anchor not in _anchors(page):
            yield f"{page.name} has no heading producing anchor {anchor!r} (from {slug!r})"


@pytest.fixture
def _pack_credentials_restored():
    """These tests call `configure()`; hand the packs back as they were found."""
    import importlib

    saved = []
    for name in PACKS:
        module = importlib.import_module(f"charter.packs.{name}")
        for attr in ("_credentials", "_headers"):
            holder = getattr(module, attr, None)
            if holder is None:
                continue
            for field in ("_provider", "_api_key", "_shop"):
                if hasattr(holder, field):
                    saved.append((holder, field, getattr(holder, field)))
    try:
        yield
    finally:
        for holder, field, value in saved:
            setattr(holder, field, value)


@pytest.mark.parametrize(
    "pack_name,host,configure,expected",
    [
        ("stripe", "api.stripe.com", {"api_key": "sk_bad"}, "auth/api-key-tool-factory"),
        ("gmail", "gmail.googleapis.com", None, "auth/providers/google"),
    ],
    ids=["api-key pack", "bearer pack"],
)
async def test_a_401_links_to_the_page_for_that_kind_of_credential(
    pack_name, host, configure, expected, _pack_credentials_restored
):
    """The bug this pair exists to prevent, checked where it actually happened.

    A unit test on `provider_docs()` passed while every API-key pack was being
    sent to the OAuth walkthrough, because nothing exercised the path that
    decides which fallback applies. This drives a real 401 through a real pack.
    """
    import importlib

    import httpx
    import respx

    from charter import CredentialError
    from charter.auth import StaticTokenProvider

    pack = importlib.import_module(f"charter.packs.{pack_name}")
    if configure is None:
        pack.configure(credential_provider=StaticTokenProvider("token-that-is-rejected"))
    else:
        pack.configure(**configure)

    with respx.mock:
        respx.route(host=host).mock(
            return_value=httpx.Response(401, json={"error": {"message": "nope"}})
        )
        for tool in pack.TOOLS:
            try:
                await tool.ainvoke()
            except CredentialError as exc:
                assert exc.docs == expected
                assert not list(_resolves(exc.docs))
                return
            except Exception:
                continue  # this tool needs arguments; try the next one
    raise AssertionError(f"no tool on {pack_name} reached the credential path")


def test_every_docs_argument_reaches_a_class_that_accepts_one():
    """A `docs=` on the wrong constructor is a TypeError on an error path.

    Error paths are the least-exercised code in any library, so a slug handed to
    `APIError` or `ToolValidationError` — the two that refuse one by design —
    would sit there until the day something actually failed, and then replace
    the real failure with a TypeError. Checked statically instead.
    """
    import inspect

    from charter.types import errors

    accepts = {
        name: "docs" in inspect.signature(obj.__init__).parameters
        for name, obj in vars(errors).items()
        if isinstance(obj, type) and issubclass(obj, BaseException)
    }
    assert accepts["APIError"] is False and accepts["ToolValidationError"] is False

    misplaced = []
    for path in _source_files():
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            if not any(k.arg == "docs" for k in node.keywords):
                continue
            callee = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if callee in ("__init__", "super"):
                continue
            if not accepts.get(callee, False):
                misplaced.append(f"{path.relative_to(SRC)}:{node.lineno} -> {callee}")
    assert not misplaced, f"docs= passed to something that does not accept it: {misplaced}"


def test_there_are_slugs_to_check():
    """Guard against the scan passing because it found nothing."""
    assert len(_literal_slugs()) >= 1


@pytest.mark.parametrize(
    "slug,where", sorted(_literal_slugs()), ids=lambda v: v if isinstance(v, str) else str(v)
)
def test_every_literal_slug_resolves(slug, where):
    problems = list(_resolves(slug))
    assert not problems, f"{where}: " + "; ".join(problems)


@pytest.mark.parametrize("pack", sorted(PACKS))
def test_every_pack_has_the_page_its_credential_error_links_to(pack):
    """`DeferredCredentialProvider` builds `packs/<pack>` for whichever pack it holds.

    Two raise sites in `packs/_config.py` serve all of them, so the slug is an
    f-string no literal scan can see. The pack list is the list.
    """
    problems = list(_resolves(f"packs/{pack}"))
    assert not problems, f"charter.packs.{pack}: " + "; ".join(problems)


@pytest.mark.parametrize("provider", sorted(_PROVIDER_PAGES))
def test_every_provider_page_in_the_map_exists(provider):
    problems = list(_resolves(_PROVIDER_PAGES[provider]))
    assert not problems, f"provider {provider!r}: " + "; ".join(problems)


@pytest.mark.parametrize("bearer", [True, False])
def test_the_provider_fallback_resolves(bearer):
    """An unmapped provider still lands somewhere, in either credential mode."""
    problems = list(_resolves(provider_docs("a-provider-with-no-page", bearer=bearer)))
    assert not problems, "; ".join(problems)


def test_an_unmapped_provider_does_not_invent_a_page():
    """The lookup is a map on purpose. An f-string here would 404 for eight packs."""
    assert provider_docs("stripe", bearer=False) == "auth/api-key-tool-factory"
    assert provider_docs(None, bearer=True) == "auth/your-own-account"


def test_a_rejected_api_key_is_not_sent_to_the_oauth_page():
    """`auth/your-own-account` tells API-key readers to go elsewhere.

    Its second paragraph names `stripe`, `linear`, `shopify`, `firecrawl` and
    `granola` and sends them to `auth/api-key-tool-factory`. A link that lands
    on a page saying "not for you" is alive and wrong, which is the failure the
    slug mechanism exists to prevent, so the fallback follows the credential
    kind rather than the provider name alone.
    """
    assert provider_docs("", bearer=False) == "auth/api-key-tool-factory"
    assert provider_docs("", bearer=True) == "auth/your-own-account"

    excluded = (DOCS / "auth/your-own-account.mdx").read_text()
    assert "/auth/api-key-tool-factory" in excluded, (
        "the page no longer redirects API-key readers; revisit the fallback"
    )


def test_a_slug_that_does_not_resolve_is_caught():
    """The check is not vacuous: a wrong slug and a wrong anchor both fail."""
    assert list(_resolves("auth/no-such-page"))
    assert list(_resolves("auth/oauth-flow#no-such-anchor"))
    # A directory is not a page: `docs/auth` exists on disk and serves nothing.
    assert (DOCS / "auth").is_dir()
    assert list(_resolves("auth"))


# --- the mechanism itself -----------------------------------------------------


def test_a_slug_renders_into_the_message_and_the_url():
    from charter import CredentialError

    error = CredentialError("no token", provider="google", docs="auth/providers/google")
    assert error.docs_url == "https://docs.r28.ai/charter/auth/providers/google"
    assert str(error) == "[google] no token See https://docs.r28.ai/charter/auth/providers/google"


def test_an_error_without_a_slug_reads_exactly_as_it_did():
    """The link is additive. An error that carries none is unchanged."""
    from charter import APIError, CredentialError, TransformError

    assert str(CredentialError("no token")) == "no token"
    assert str(CredentialError("no token", provider="google")) == "[google] no token"
    assert str(TransformError("boom", field="raw")) == "boom (field: raw)"
    assert str(APIError("nope", status_code=500)) == "HTTP 500 — nope"

    for error in (CredentialError("x"), TransformError("x"), APIError("x", status_code=1)):
        assert error.docs is None
        assert error.docs_url is None


async def test_a_declaration_error_can_arrive_from_a_call_not_only_a_build():
    """The claim the reference makes about where to put a `try`.

    A tool whose schema has an unmarked field builds without complaint: nothing
    inspects the markers until a request is assembled. So a host guarding only
    its declarations lets this escape out of `ainvoke`, which is why the page
    says `except CharterError` rather than "wrap the declaration".
    """
    from typing import Annotated, Optional

    from pydantic import BaseModel

    from charter import CharterError, DeclarationError, Query, api_key_tool_factory

    class Unmarked(BaseModel):
        city: str  # no Path()/Query()/Body()
        units: Annotated[Optional[str], Query()] = None

    factory = api_key_tool_factory(base_url="https://x.test/", api_key_headers={"k": "v"})
    tool = factory(name="t", args_schema=Unmarked, method="GET", url_template="v1")

    with pytest.raises(DeclarationError) as excinfo:
        await tool.ainvoke(city="Tokyo")
    assert "has no Path(), Query() or Body() marker" in str(excinfo.value)
    assert isinstance(excinfo.value, CharterError)

    # The author's own class, not the generated `Unmarked_LLM` variant they
    # would grep their code for and never find.
    assert "'city' on Unmarked " in str(excinfo.value)
    assert "_LLM" not in str(excinfo.value)


def test_a_declaration_error_also_arrives_at_build_time():
    """The other half of the same claim, so neither can be dropped quietly."""
    from charter import DeclarationError, Pagination

    with pytest.raises(DeclarationError):
        Pagination(cursor_field="next", page_param="page")


def test_the_model_facing_error_cannot_be_given_a_link():
    """`ToolValidationError` goes back into the loop as a tool result.

    A URL there is context the model pays for and cannot follow, so the rule is
    enforced by the signature rather than by remembering it at each raise site.
    """
    from charter import ToolValidationError

    with pytest.raises(TypeError):
        ToolValidationError("bad field", docs="reference/markers")  # type: ignore[call-arg]

    error = ToolValidationError("bad field")
    assert error.docs is None
    assert str(error) == "bad field"


async def test_no_link_reaches_a_model_through_a_nested_validator():
    """The path the constructor check misses.

    pydantic quotes a validator's `ValueError` verbatim into its own message,
    and `Value` is a schema type a *model* fills in — so a link on that
    validator surfaces in the tool result handed back to the model. Caught by
    stripping in `ToolValidationError`, not by remembering it per raise site.
    """
    from typing import Annotated

    from pydantic import BaseModel

    from charter import Body, Struct, ToolValidationError, api_key_tool_factory
    from charter.types.errors import DOCS_BASE

    class Args(BaseModel):
        payload: Annotated[Struct, Body(envelop=True)]

    factory = api_key_tool_factory(base_url="https://x.test/", api_key_headers={"k": "v"})
    tool = factory(name="t", args_schema=Args, method="POST", url_template="v1")

    with pytest.raises(ToolValidationError) as excinfo:
        # Two variants set on one Value: rejected by Value's own model_validator.
        await tool.ainvoke(payload={"fields": {"a": {"string_value": "s", "number_value": 1}}})

    assert "Value must have exactly one variant set" in str(excinfo.value)
    assert DOCS_BASE not in str(excinfo.value)
    assert not any(
        DOCS_BASE in str(value)
        for error in excinfo.value.errors
        for value in error.values()
    )


def test_the_langchain_formatter_is_clean_too():
    """`format_validation_error` is wired into LangChain as handle_validation_error.

    That path never constructs a `ToolValidationError`, so stripping only there
    would leave the adapter leaking a link into the agent loop.
    """
    from pydantic import BaseModel, ValidationError

    from charter import Value
    from charter.execution.validation import format_validation_error
    from charter.types.errors import DOCS_BASE

    class Model(BaseModel):
        v: Value

    try:
        Model(v={"string_value": "a", "number_value": 1})
    except ValidationError as exc:
        text = format_validation_error(exc)
    assert "Value must have exactly one variant set" in text
    assert DOCS_BASE not in text


def test_stripping_a_link_leaves_the_sentence_intact():
    """The strip removes the link and nothing else."""
    from charter.types.errors import strip_docs_links

    assert strip_docs_links("no link here") == "no link here"
    assert (
        strip_docs_links("Bad shape. See https://docs.r28.ai/charter/tools/wire-contract#body")
        == "Bad shape."
    )


def test_an_upstream_failure_cannot_be_given_a_link():
    """`APIError` is the API's failure. Charter's docs have nothing to add."""
    from charter import APIError

    with pytest.raises(TypeError):
        APIError("nope", status_code=500, docs="reference/errors")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "build",
    [
        lambda m: __import__("charter").CredentialError(
            m, provider="google", status_code=401, docs="auth/oauth-flow"
        ),
        lambda m: __import__("charter").DeclarationError(m, docs="tools/wire-contract"),
        lambda m: __import__("charter").TransformError(m, transform="t", field="raw"),
        lambda m: __import__("charter").ToolValidationError(m, tool_name="x"),
        lambda m: __import__("charter").APIError(
            m, status_code=429, body="b", url="u", retry_after=3
        ),
    ],
    ids=["credential", "declaration", "transform", "validation", "api"],
)
def test_every_error_survives_a_pickle(build):
    """A host running tools in a process pool or a task queue has to get its error.

    Exception's default pickling replays `cls(*args)`, which is a TypeError for
    any subclass with a required keyword — `APIError` could not cross a process
    boundary at all. Attributes have to come back too, or a `retry_after` the
    server sent is lost exactly where a worker needs it.
    """
    import pickle

    error = build("something went wrong")
    restored = pickle.loads(pickle.dumps(error))

    assert type(restored) is type(error)
    assert str(restored) == str(error)
    assert restored.__dict__ == error.__dict__


def test_the_link_is_reachable_without_parsing_the_message():
    """A host formatting errors elsewhere reads the field, not the string."""
    from charter import CredentialError

    error = CredentialError("no token", docs="auth/oauth-flow")
    assert error.docs == "auth/oauth-flow"
    assert error.args == ("no token",)
