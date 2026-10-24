# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""A grant that does not cover the call raises one error, however the provider says it.

Each refusal below is the shape a provider was seen answering on 2026-10-24, to a
token holding less than the call needs: Google's standard challenge header,
Slack's ``missing_scope`` inside a 200, Linear's sentence, GitHub's 404 beside
two headers, Stripe's restricted-key sentence, Microsoft's bare
``ErrorAccessDenied``.
"""

from __future__ import annotations

import pickle
from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import (
    APIError,
    CredentialError,
    DeclarationError,
    InsufficientScope,
    Path,
    Query,
    Tool,
)
from charter.auth import AnyOf, Kind, ScopeRefusal, StaticTokenProvider, Unavailable

BASE = "https://api.example.com/"
URL = f"{BASE}v1/x"


class Args(BaseModel):
    thing: Annotated[str, Path()] = "x"
    q: Annotated[Optional[str], Query()] = None


def _tool(**kw) -> Tool:
    base = dict(
        name="t",
        method="GET",
        url_template="v1/{thing}",
        args_schema=Args,
        base_url=BASE,
        provider="example",
        credential_provider=StaticTokenProvider("tok"),
    )
    base.update(kw)
    return Tool(**base)


def _challenge(scopes: str) -> dict[str, str]:
    return {
        "www-authenticate": (
            'Bearer realm="https://accounts.example.com/", error="insufficient_scope", '
            f'scope="{scopes}"'
        )
    }


# -----------------------------------------------------
# The standard challenge, which needs no declaration
# -----------------------------------------------------


@respx.mock
async def test_the_standard_challenge_raises_with_the_narrowest_scope_the_tool_lists():
    """Google names legacy aliases and broader scopes first; the declaration decides."""
    respx.get(URL).mock(
        return_value=httpx.Response(
            403,
            headers=_challenge("https://x/full https://x/feed https://x/read https://x/write"),
            json={
                "error": {"code": 403, "message": "Request had insufficient authentication scopes."}
            },
        )
    )
    tool = _tool(scopes=[AnyOf("https://x/read", "https://x/write", "https://x/full")])
    with pytest.raises(InsufficientScope) as excinfo:
        await tool.ainvoke()
    error = excinfo.value
    assert error.needed == ["https://x/read"]
    assert error.accepted == (
        "https://x/full",
        "https://x/feed",
        "https://x/read",
        "https://x/write",
    )
    assert error.status_code == 403
    assert error.token_refused is False
    assert error.provider == "example"
    assert "insufficient authentication scopes" in str(error)
    assert "Add: https://x/read" in str(error)


@respx.mock
async def test_a_tool_that_declares_nothing_gets_the_providers_first_choice():
    respx.get(URL).mock(return_value=httpx.Response(403, headers=_challenge("a b")))
    with pytest.raises(InsufficientScope) as excinfo:
        await _tool().ainvoke()
    assert excinfo.value.needed == ["a"]
    assert excinfo.value.accepted == ("a", "b")


@respx.mock
async def test_another_challenge_on_a_403_is_left_alone():
    respx.get(URL).mock(
        return_value=httpx.Response(
            403, headers={"www-authenticate": 'Bearer error="invalid_token"'}
        )
    )
    with pytest.raises(APIError):
        await _tool().ainvoke()


@respx.mock
async def test_it_is_a_credential_error_and_the_token_is_kept():
    """A host's existing `except CredentialError` keeps working, and nothing refreshes."""
    dropped = []

    class Provider(StaticTokenProvider):
        def invalidate(self, *args, **kwargs):  # pragma: no cover - must not run
            dropped.append(args)

    respx.get(URL).mock(return_value=httpx.Response(403, headers=_challenge("a")))
    with pytest.raises(CredentialError) as excinfo:
        await _tool(credential_provider=Provider("tok")).ainvoke()
    assert isinstance(excinfo.value, InsufficientScope)
    assert dropped == []


@respx.mock
async def test_it_survives_pickling():
    respx.get(URL).mock(return_value=httpx.Response(403, headers=_challenge("a b")))
    with pytest.raises(InsufficientScope) as excinfo:
        await _tool().ainvoke()
    copy = pickle.loads(pickle.dumps(excinfo.value))
    assert (copy.needed, copy.accepted, copy.status_code) == (["a"], ("a", "b"), 403)


# -----------------------------------------------------
# Declared refusals, one per provider shape
# -----------------------------------------------------

SLACK = ScopeRefusal(
    status=200,
    signal=r'"error"\s*:\s*"missing_scope"',
    needed_field="needed",
    alternatives=False,
)
LINEAR = ScopeRefusal(
    status={200, 400}, signal=r"Invalid scope", needed=r"Invalid scope:\s*(.+?)\s+required"
)
GITHUB = ScopeRefusal(
    status={403, 404},
    needed_header="x-accepted-oauth-scopes",
    held_header="x-oauth-scopes",
)
MICROSOFT = ScopeRefusal(status=403, signal=r'"code"\s*:\s*"ErrorAccessDenied"')


@respx.mock
async def test_a_refusal_inside_a_200_raises_before_the_envelope_sees_it():
    respx.get(URL).mock(
        return_value=httpx.Response(
            200, json={"ok": False, "error": "missing_scope", "needed": "chat:write"}
        )
    )
    with pytest.raises(InsufficientScope) as excinfo:
        await _tool(scope_refusals=[SLACK], scopes=["chat:write", "users:read"]).ainvoke()
    assert excinfo.value.needed == ["chat:write"]
    # HTTP's own word for it, as an envelope's permission error has always said.
    assert excinfo.value.status_code == 403


@respx.mock
async def test_a_refusal_naming_nothing_falls_back_to_the_declaration():
    respx.get(URL).mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "missing_scope"})
    )
    with pytest.raises(InsufficientScope) as excinfo:
        await _tool(scope_refusals=[SLACK], scopes=["chat:write", "users:read"]).ainvoke()
    assert excinfo.value.needed == ["chat:write", "users:read"]
    assert "named no scope; t declares chat:write, users:read" in str(excinfo.value)


@respx.mock
async def test_alternatives_named_in_a_sentence_are_ordered_by_the_declaration():
    """Linear lists `write` first; the tool knows `comments:create` is narrower."""
    respx.get(URL).mock(
        return_value=httpx.Response(
            400,
            json={"errors": [{"message": "Invalid scope: `write` or `comments:create` required"}]},
        )
    )
    tool = _tool(scope_refusals=[LINEAR], scopes=[AnyOf("comments:create", "write")])
    with pytest.raises(InsufficientScope) as excinfo:
        await tool.ainvoke()
    assert excinfo.value.needed == ["comments:create"]
    assert excinfo.value.accepted == ("write", "comments:create")


@respx.mock
async def test_a_404_is_a_refusal_only_when_the_token_holds_none_of_what_is_accepted():
    """GitHub hides a private repository behind the same 404 as a missing one."""
    respx.get(URL).mock(
        return_value=httpx.Response(
            404,
            headers={"x-accepted-oauth-scopes": "repo", "x-oauth-scopes": ""},
            json={"message": "Not Found"},
        )
    )
    with pytest.raises(InsufficientScope) as excinfo:
        await _tool(scope_refusals=[GITHUB], scopes=["repo"]).ainvoke()
    assert excinfo.value.needed == ["repo"]
    assert excinfo.value.status_code == 404


@respx.mock
async def test_a_404_the_token_could_have_read_is_the_apis_own():
    respx.get(URL).mock(
        return_value=httpx.Response(
            404,
            headers={"x-accepted-oauth-scopes": "repo", "x-oauth-scopes": "repo, gist"},
            json={"message": "Not Found"},
        )
    )
    with pytest.raises(APIError) as excinfo:
        await _tool(scope_refusals=[GITHUB], scopes=["repo"]).ainvoke()
    assert not isinstance(excinfo.value, CredentialError)
    assert excinfo.value.status_code == 404


@respx.mock
async def test_a_403_that_does_not_match_the_signal_stays_an_api_error():
    respx.get(URL).mock(
        return_value=httpx.Response(403, json={"error": {"code": "ErrorQuotaExceeded"}})
    )
    with pytest.raises(APIError):
        await _tool(scope_refusals=[MICROSOFT], scopes=["Mail.Read"]).ainvoke()


@respx.mock
async def test_a_refusal_for_another_kind_names_that_kinds_permissions():
    key = Kind("restricted_key", provider="example", granted="configured")
    refusal = ScopeRefusal(
        status=403,
        signal=r"does not have the required permissions",
        needed=r"Having the '([^']+)' permission",
        kind=key,
    )
    respx.get(URL).mock(
        return_value=httpx.Response(
            403,
            json={
                "error": {
                    "message": "The provided key 'rk_test_***' does not have the required "
                    "permissions for this endpoint. Having the 'rak_charge_read' permission "
                    "would allow this request to continue."
                }
            },
        )
    )
    tool = _tool(scope_refusals=[refusal], scopes={key: ["rak_charge_read"]})
    with pytest.raises(InsufficientScope) as excinfo:
        await tool.ainvoke()
    assert excinfo.value.needed == ["rak_charge_read"]
    assert excinfo.value.kind is key


@respx.mock
async def test_a_derived_tool_keeps_the_refusals():
    respx.get(URL).mock(
        return_value=httpx.Response(
            200, json={"ok": False, "error": "missing_scope", "needed": "a"}
        )
    )
    narrow = _tool(scope_refusals=[SLACK], scopes=["a"]).derived(name="narrow")
    with pytest.raises(InsufficientScope):
        await narrow.ainvoke()


def test_api_key_factory_and_oauth_factory_both_take_refusals():
    from charter import api_key_tool_factory, oauth_tool_factory

    for build in (
        api_key_tool_factory(BASE, {"x-api-key": "k"}, pack="example", scope_refusals=[SLACK]),
        oauth_tool_factory(
            BASE, "example", StaticTokenProvider("t"), pack="example", scope_refusals=[SLACK]
        ),
    ):
        tool = build(name="t", args_schema=Args, method="GET", url_template="v1/{thing}")
        assert tool.scope_refusals == (SLACK,)


# -----------------------------------------------------
# The declaration
# -----------------------------------------------------


def test_a_refusal_with_nothing_to_tell_it_apart_is_refused():
    with pytest.raises(DeclarationError, match="every"):
        ScopeRefusal(status=403)


def test_a_needed_pattern_must_capture():
    with pytest.raises(DeclarationError, match="group"):
        ScopeRefusal(signal="x", needed=r"Required: \w+")


def test_a_bad_pattern_is_refused_at_declaration():
    with pytest.raises(DeclarationError, match="regular expression"):
        ScopeRefusal(signal="(")


def test_no_status_is_refused():
    with pytest.raises(DeclarationError, match="status"):
        ScopeRefusal(status=set(), signal="x")


# -----------------------------------------------------
# Every pack, with the shape its provider sends
# -----------------------------------------------------


def _configure_all(monkeypatch):
    from charter.packs import github, gmail, linear, notion, outlook, shopify, stripe

    for var in ("SHOPIFY_SHOP", "SHOPIFY_ACCESS_TOKEN", "LINEAR_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    gmail.configure(StaticTokenProvider("ya29.test"))
    github.configure(StaticTokenProvider("ghp_test"))
    linear.configure(api_key="lin_api_test")
    notion.configure(StaticTokenProvider("ntn_test"))
    outlook.configure(StaticTokenProvider("graph-test"))
    shopify.configure(shop="my-store", access_token="shpat_test")
    stripe.configure(api_key="rk_test_123")


def _shopify_api():
    from charter.packs import shopify

    return f"https://my-store.myshopify.com/admin/api/{shopify.API_VERSION}/graphql.json"


PACK_REFUSALS = [
    pytest.param(
        "gmail",
        "labels_list",
        {},
        "GET",
        "https://gmail.googleapis.com/gmail/v1/users/me/labels",
        httpx.Response(
            403,
            headers=_challenge(
                "https://mail.google.com/ https://www.googleapis.com/auth/gmail.labels "
                "https://www.googleapis.com/auth/gmail.readonly"
            ),
            json={
                "error": {"code": 403, "message": "Request had insufficient authentication scopes."}
            },
        ),
        ["https://www.googleapis.com/auth/gmail.labels"],
        None,
        id="google",
    ),
    pytest.param(
        "linear",
        "webhooks_list",
        {},
        "POST",
        "https://api.linear.app/graphql",
        httpx.Response(200, json={"errors": [{"message": "Invalid scope: `admin` required"}]}),
        ["admin"],
        None,
        id="linear-query",
    ),
    pytest.param(
        "shopify",
        "orders_list",
        {},
        "POST",
        None,
        httpx.Response(
            200,
            json={
                "errors": [
                    {
                        "message": "Access denied for orders field. Required access: "
                        "`read_orders` access scope.",
                        "extensions": {"code": "ACCESS_DENIED"},
                    }
                ]
            },
        ),
        ["read_orders"],
        None,
        id="shopify",
    ),
    pytest.param(
        "notion",
        "users_list",
        {},
        "GET",
        "https://api.notion.com/v1/users",
        httpx.Response(
            403,
            json={
                "object": "error",
                "status": 403,
                "code": "restricted_resource",
                "message": "Insufficient permissions for this endpoint.",
            },
        ),
        ["Read user information"],
        None,
        id="notion",
    ),
    pytest.param(
        "outlook",
        "messages_list",
        {},
        "GET",
        "https://graph.microsoft.com/v1.0/me/messages",
        httpx.Response(
            403,
            json={
                "error": {
                    "code": "ErrorAccessDenied",
                    "message": "Access is denied. Check credentials and try again.",
                }
            },
        ),
        ["https://graph.microsoft.com/Mail.Read"],
        None,
        id="outlook",
    ),
    pytest.param(
        "stripe",
        "customers_list",
        {},
        "GET",
        "https://api.stripe.com/v1/customers",
        httpx.Response(
            403,
            json={
                "error": {
                    "message": "The provided key 'rk_test_***123' does not have the required "
                    "permissions for this endpoint on account 'acct_1'. Having the "
                    "'rak_customer_read' permission would allow this request to continue.",
                    "type": "invalid_request_error",
                }
            },
        ),
        ["customer_read"],
        "restricted_key",
        id="stripe",
    ),
    pytest.param(
        "github",
        "repos_get",
        {"owner": "o", "repo": "r"},
        "GET",
        "https://api.github.com/repos/o/r",
        httpx.Response(
            404,
            headers={"x-accepted-oauth-scopes": "repo", "x-oauth-scopes": "read:user"},
            json={"message": "Not Found"},
        ),
        ["repo"],
        None,
        id="github-classic",
    ),
    pytest.param(
        "github",
        "repos_get",
        {"owner": "o", "repo": "r"},
        "GET",
        "https://api.github.com/repos/o/r",
        httpx.Response(
            403,
            headers={"x-accepted-github-permissions": "metadata=read"},
            json={"message": "Resource not accessible by personal access token"},
        ),
        ["metadata=read"],
        "fine_grained",
        id="github-fine-grained",
    ),
]


@respx.mock
@pytest.mark.parametrize(
    ("pack", "name", "args", "method", "url", "response", "needed", "kind"), PACK_REFUSALS
)
async def test_every_pack_raises_insufficient_scope_on_its_providers_refusal(
    monkeypatch, pack, name, args, method, url, response, needed, kind
):
    import importlib

    _configure_all(monkeypatch)
    tool = getattr(importlib.import_module(f"charter.packs.{pack}"), name)
    respx.route(method=method, url=url or _shopify_api()).mock(return_value=response)
    with pytest.raises(InsufficientScope) as excinfo:
        await tool.ainvoke(args)
    error = excinfo.value
    assert error.needed == needed
    assert (error.kind.name if error.kind else None) == kind
    assert error.token_refused is False


@respx.mock
async def test_the_message_names_the_kind_and_an_unavailable_reason():
    """GitHub's notifications to a fine-grained token, and a sentence with no full stop."""
    app = Kind("app", provider="example", granted="configured")
    refusal = ScopeRefusal(status=403, signal=r"Resource not accessible", kind=app)
    respx.get(URL).mock(
        return_value=httpx.Response(403, json={"message": "Resource not accessible by integration"})
    )
    blocked = _tool(scope_refusals=[refusal], scopes={app: [Unavailable("apps cannot read this")]})
    with pytest.raises(InsufficientScope) as excinfo:
        await blocked.ainvoke()
    assert excinfo.value.needed == []
    assert "integration. t cannot run with this credential: apps cannot read this." in str(
        excinfo.value
    )

    allowed = _tool(scope_refusals=[refusal], scopes={app: ["secrets=read"]})
    with pytest.raises(InsufficientScope) as excinfo:
        await allowed.ainvoke()
    assert "t declares secrets=read for example.app." in str(excinfo.value)


@respx.mock
async def test_a_404_without_the_held_header_is_the_apis_own():
    """A fine-grained GitHub token is sent no X-OAuth-Scopes: it holds no scopes
    to compare, so its 404 says nothing about them."""
    respx.get(URL).mock(
        return_value=httpx.Response(
            404, headers={"x-accepted-oauth-scopes": "repo"}, json={"message": "Not Found"}
        )
    )
    with pytest.raises(APIError) as excinfo:
        await _tool(scope_refusals=[GITHUB], scopes=["repo"]).ainvoke()
    assert not isinstance(excinfo.value, CredentialError)
