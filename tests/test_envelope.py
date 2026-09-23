"""Envelopes — declaring failure that HTTP 200 hides.

This is the framework-level answer to a whole class of API, not one vendor's
quirk: Slack's `ok: false`, GraphQL's `errors` array, and the `{"status": "error"}`
family all report failure in the body while the status line says success.
"""

from __future__ import annotations

from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import (
    APIError,
    CredentialError,
    Envelope,
    Path,
    Query,
    Tool,
    api_key_tool_factory,
    oauth_tool_factory,
)
from charter.auth import StaticTokenProvider
from charter.types.envelope import GRAPHQL_ENVELOPE

BASE = "https://api.example.com/"

SLACKISH = Envelope(
    ok_field="ok",
    error_field="error",
    credential_errors={"invalid_auth"},
    detail_fields=("needed",),
)


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
        api_key_headers={"x-api-key": "k"},
    )
    base.update(kw)
    return Tool(**base)


# -----------------------------------------------------
# The declaration itself
# -----------------------------------------------------


def test_an_envelope_must_be_able_to_detect_failure():
    with pytest.raises(ValueError, match="ok_field"):
        Envelope()


def test_success_flag_shape():
    assert SLACKISH.failed({"ok": False, "error": "nope"}) is True
    assert SLACKISH.failed({"ok": True, "data": 1}) is False


def test_absent_flag_is_not_a_failure():
    """A response that simply omits the field is not evidence of failure."""
    assert SLACKISH.failed({"data": 1}) is False


def test_non_dict_payloads_are_never_failures():
    for payload in ([], "text", None, 3):
        assert SLACKISH.failed(payload) is False


def test_value_matching_shape():
    env = Envelope(ok_field="status", ok_value="ok", error_field="message")
    assert env.failed({"status": "error", "message": "bad"}) is True
    assert env.failed({"status": "ok"}) is False


def test_error_collection_shape_graphql():
    assert GRAPHQL_ENVELOPE.failed({"data": {"x": 1}}) is False
    assert GRAPHQL_ENVELOPE.failed({"data": None, "errors": []}) is False
    assert GRAPHQL_ENVELOPE.failed({"errors": [{"message": "boom"}]}) is True


def test_graphql_message_is_extracted_from_the_first_error():
    with pytest.raises(APIError, match="Cannot query field"):
        GRAPHQL_ENVELOPE.raise_for_payload({"errors": [{"message": "Cannot query field"}]})


def test_credential_errors_raise_credential_error():
    with pytest.raises(CredentialError) as excinfo:
        SLACKISH.raise_for_payload({"ok": False, "error": "invalid_auth"}, provider="slack")
    assert excinfo.value.provider == "slack"
    assert excinfo.value.status_code == 401


def test_other_errors_raise_api_error_recording_the_real_status():
    """It really was a 200. Recording that is the useful part."""
    with pytest.raises(APIError) as excinfo:
        SLACKISH.raise_for_payload({"ok": False, "error": "channel_not_found"})
    assert excinfo.value.status_code == 200
    assert "channel_not_found" in str(excinfo.value)


def test_detail_fields_are_appended():
    with pytest.raises(CredentialError, match="chat:write"):
        SLACKISH.raise_for_payload({"ok": False, "error": "invalid_auth", "needed": "chat:write"})


def test_empty_detail_fields_are_not_appended():
    """An empty detail adds nothing to the message. (The raw body excerpt still
    carries it — that is the point of an excerpt.)"""
    with pytest.raises(APIError) as excinfo:
        SLACKISH.raise_for_payload({"ok": False, "error": "x", "needed": ""})
    assert excinfo.value.message == "the API rejected the call: x"


def test_a_missing_error_code_still_raises():
    with pytest.raises(APIError, match="unknown_error"):
        Envelope(ok_field="ok").raise_for_payload({"ok": False})


def test_envelope_is_hashable_and_comparable():
    """It is a declaration — plain data that can be shared and compared."""
    assert Envelope(ok_field="ok") == Envelope(ok_field="ok")
    assert len({Envelope(ok_field="ok"), Envelope(ok_field="ok")}) == 1


# -----------------------------------------------------
# Enforced by the runtime, not by the tool author
# -----------------------------------------------------


@respx.mock
async def test_without_an_envelope_a_200_is_taken_at_face_value():
    """The default is unchanged — envelopes are opt-in per API."""
    respx.get(f"{BASE}v1/x").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "nope"})
    )
    assert await _tool().ainvoke() == {"ok": False, "error": "nope"}


@respx.mock
async def test_the_runtime_applies_the_envelope_with_no_response_handler():
    """The bug this fixes: an author who adds a tool and forgets the guard."""
    respx.get(f"{BASE}v1/x").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "channel_not_found"})
    )
    with pytest.raises(APIError, match="channel_not_found"):
        await _tool(envelope=SLACKISH).ainvoke()


@respx.mock
async def test_response_handlers_never_see_a_failed_payload():
    """Trimming a failure is nonsense; the envelope raises before the handler runs."""
    seen = []

    async def handler(response):
        seen.append(response)
        return response

    respx.get(f"{BASE}v1/x").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "boom"})
    )
    with pytest.raises(APIError):
        await _tool(envelope=SLACKISH, response_handler=handler).ainvoke()
    assert seen == []


@respx.mock
async def test_a_success_still_reaches_the_response_handler():
    async def handler(response):
        return {"trimmed": response["data"]}

    respx.get(f"{BASE}v1/x").mock(
        return_value=httpx.Response(200, json={"ok": True, "data": [1, 2]})
    )
    result = await _tool(envelope=SLACKISH, response_handler=handler).ainvoke()
    assert result == {"trimmed": [1, 2]}


@respx.mock
async def test_http_errors_still_win_over_the_envelope():
    """A real 4xx is still a 4xx; the envelope is for the 200 case."""
    respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(429, text="slow down"))
    with pytest.raises(APIError) as excinfo:
        await _tool(envelope=SLACKISH).ainvoke()
    assert excinfo.value.status_code == 429


@respx.mock
async def test_non_json_success_is_untouched_by_the_envelope():
    respx.get(f"{BASE}v1/x").mock(
        return_value=httpx.Response(200, text="plain", headers={"content-type": "text/plain"})
    )
    assert await _tool(envelope=SLACKISH).ainvoke() == {"raw": "plain"}


@respx.mock
async def test_204_is_untouched_by_the_envelope():
    respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(204))
    assert await _tool(envelope=SLACKISH).ainvoke() == {}


# -----------------------------------------------------
# Declared once on a factory
# -----------------------------------------------------


def test_api_key_factory_propagates_the_envelope_to_every_tool():
    factory = api_key_tool_factory(
        pack="envelope", base_url=BASE, api_key_headers={"x-api-key": "k"}, envelope=SLACKISH
    )
    tools = [
        factory(name=f"t{i}", args_schema=Args, method="GET", url_template="v1/{thing}")
        for i in range(3)
    ]
    assert all(t.envelope is SLACKISH for t in tools)


def test_oauth_factory_propagates_the_envelope_to_every_tool():
    factory = oauth_tool_factory(
        pack="envelope",
        base_url=BASE,
        provider="p",
        credential_provider=StaticTokenProvider("t"),
        envelope=SLACKISH,
    )
    tool = factory(name="t", args_schema=Args, method="GET", url_template="v1/{thing}")
    assert tool.envelope is SLACKISH


def test_a_single_endpoint_can_override_the_factory_envelope():
    factory = api_key_tool_factory(
        pack="envelope", base_url=BASE, api_key_headers={"x-api-key": "k"}, envelope=SLACKISH
    )
    odd = factory(
        name="odd",
        args_schema=Args,
        method="GET",
        url_template="v1/{thing}",
        envelope_override=GRAPHQL_ENVELOPE,
    )
    assert odd.envelope is GRAPHQL_ENVELOPE


def test_factories_default_to_no_envelope():
    factory = api_key_tool_factory(
        pack="envelope", base_url=BASE, api_key_headers={"x-api-key": "k"}
    )
    assert (
        factory(name="t", args_schema=Args, method="GET", url_template="v1/{thing}").envelope
        is None
    )


@respx.mock
async def test_a_graphql_style_api_needs_one_line():
    """The generality claim, exercised: same mechanism, different convention."""
    factory = api_key_tool_factory(
        pack="envelope",
        base_url=BASE,
        api_key_headers={"x-api-key": "k"},
        envelope=GRAPHQL_ENVELOPE,
    )
    tool = factory(name="gql", args_schema=Args, method="GET", url_template="v1/{thing}")

    respx.get(f"{BASE}v1/x").mock(
        return_value=httpx.Response(
            200, json={"data": None, "errors": [{"message": "Unknown field 'foo'"}]}
        )
    )
    with pytest.raises(APIError, match="Unknown field"):
        await tool.ainvoke()


# -----------------------------------------------------
# Paths and wildcards
#
# The root-level envelope catches a document the server would not run. It does
# not catch a mutation the server ran and then declined — that failure sits
# inside the payload, under the operation's name. Reaching it needs a path, and
# the operation name differs per tool, so the path needs a wildcard.
#
# Without this the check goes back into each mutation's response handler: opt-in
# per tool, duplicated per pack, and wrong the first time someone adds a tool
# without remembering. That is the boilerplate `Envelope` exists to delete.
# -----------------------------------------------------


NESTED_OK = Envelope(errors_field="errors", ok_field="data.*.success")
NESTED_ERRORS = Envelope(errors_field=("errors", "data.*.userErrors"))


def test_a_nested_success_flag_is_reached_through_a_wildcard():
    declined = {"data": {"issueCreate": {"success": False, "issue": None}}}
    assert NESTED_OK.failed(declined) is True

    with pytest.raises(APIError, match="data.issueCreate.success is false"):
        NESTED_OK.raise_for_payload(declined)


def test_the_message_names_the_operation_that_was_declined():
    """The resolved path is the useful half — it says which write failed."""
    code, message = NESTED_OK.describe({"data": {"commentCreate": {"success": False}}})
    assert code == "data.commentCreate.success is false"
    assert "commentCreate" in message


def test_a_successful_nested_mutation_is_not_a_failure():
    assert NESTED_OK.failed({"data": {"issueCreate": {"success": True}}}) is False


def test_a_payload_with_no_flag_anywhere_is_not_a_failure():
    """A query has no `success`; the wildcard matches nothing, and silence is not no."""
    assert NESTED_OK.failed({"data": {"issues": {"nodes": []}}}) is False
    assert NESTED_OK.failed({"data": {}}) is False
    assert NESTED_OK.failed({}) is False


def test_the_root_errors_array_still_works_alongside_a_nested_flag():
    assert NESTED_OK.failed({"errors": [{"message": "bad document"}]}) is True


def test_several_error_paths_can_be_declared_at_once():
    assert NESTED_ERRORS.failed({"errors": [{"message": "bad document"}]}) is True
    assert (
        NESTED_ERRORS.failed({"data": {"productCreate": {"userErrors": [{"message": "taken"}]}}})
        is True
    )


def test_an_empty_nested_error_list_is_a_success():
    """Shopify returns userErrors on every mutation; empty means it worked."""
    assert NESTED_ERRORS.failed({"data": {"productCreate": {"userErrors": []}}}) is False


def test_a_user_error_message_keeps_the_field_path_shopify_names():
    payload = {
        "data": {
            "productCreate": {
                "userErrors": [{"field": ["handle"], "message": "Handle has been taken"}]
            }
        }
    }
    code, _ = NESTED_ERRORS.describe(payload)
    assert code == "handle: Handle has been taken"


def test_several_user_errors_are_summarised_rather_than_dumped():
    payload = {
        "data": {
            "productCreate": {
                "userErrors": [
                    {"field": ["a"], "message": "one"},
                    {"field": ["b"], "message": "two"},
                    {"field": ["c"], "message": "three"},
                    {"field": ["d"], "message": "four"},
                ]
            }
        }
    }
    code, _ = NESTED_ERRORS.describe(payload)
    assert "one" in code and "three" in code
    assert "(+1 more)" in code


def test_a_wildcard_does_not_descend_past_the_level_it_names():
    """`data.*.success` is one level, not a recursive search."""
    deep = {"data": {"a": {"b": {"success": False}}}}
    assert NESTED_OK.failed(deep) is False


def test_a_single_segment_path_behaves_exactly_as_before():
    """The Slack case must be untouched by any of this."""
    slack = Envelope(ok_field="ok", error_field="error")
    assert slack.failed({"ok": False, "error": "channel_not_found"}) is True
    assert slack.failed({"ok": True}) is False
    code, _ = slack.describe({"ok": False, "error": "channel_not_found"})
    assert code == "channel_not_found"


def test_an_error_collection_is_checked_before_a_success_flag():
    """A document-level problem is more fundamental than a payload flag."""
    both = {
        "errors": [{"message": "partial failure"}],
        "data": {"issueCreate": {"success": False}},
    }
    code, _ = NESTED_OK.describe(both)
    assert code == "partial failure"


def test_detail_fields_are_paths_not_root_keys():
    """`detail_fields` was the one field on Envelope that was not a path.

    Every other field name — ok_field, error_field, errors_field — goes through
    `_collect`, so it can be dotted and can carry `*`. `detail_fields` read the
    root of the payload directly, which made the class docstring's "every field
    name is a path" true of four fields out of five, and put a nested detail
    (a GraphQL `extensions.code`, exactly where a declined mutation puts one)
    out of reach.
    """
    nested = Envelope(
        errors_field="errors",
        detail_fields=("extensions.code", "meta.*.hint"),
    )
    payload = {
        "errors": [{"message": "declined"}],
        "extensions": {"code": "RATE_LIMITED"},
        "meta": {"first": {"hint": "retry in 30s"}},
    }

    with pytest.raises(APIError) as excinfo:
        nested.raise_for_payload(payload)

    message = str(excinfo.value)
    assert "extensions.code: RATE_LIMITED" in message
    assert "meta.first.hint: retry in 30s" in message


def test_a_root_level_detail_field_still_reads_as_its_bare_key():
    """Slack declares `needed`, and the message must not become `needed: needed`."""
    with pytest.raises(CredentialError) as excinfo:
        SLACKISH.raise_for_payload({"ok": False, "error": "invalid_auth", "needed": "chat:write"})
    assert "needed: chat:write" in str(excinfo.value)


def test_a_detail_path_that_matches_nothing_adds_nothing():
    absent = Envelope(errors_field="errors", detail_fields=("extensions.code",))
    with pytest.raises(APIError) as excinfo:
        absent.raise_for_payload({"errors": [{"message": "boom"}]})
    assert "extensions" not in str(excinfo.value)
