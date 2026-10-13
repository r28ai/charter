"""A connection that fails, drops or times out is a NetworkError, wherever it happens.

Every adapter catches CharterError and turns it into a tool result. An httpx
exception escaping a call passed all of them, so a network blip ended the agent
instead of the call — seen live against Microsoft Graph, from the API call and
from the token refresh in front of it. These pin each place Charter sends a
request: the tool's call, a redirect hop, the token endpoint, the code exchange
and a revocation.
"""

from __future__ import annotations

from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import CharterError, NetworkError, Path, Query, Tool, oauth_tool_factory
from charter.auth import OAuth2Client, OAuth2Flow, OAuth2Server, Revocation, revoke_token
from charter.types.transport import network_error

BASE = "https://api.example.com/"
TOKEN_URL = "https://oauth2.example.com/token"
REVOKE_URL = "https://oauth2.example.com/revoke"


class GetThing(BaseModel):
    thing_id: Annotated[str, Path()]
    units: Annotated[Optional[str], Query()] = None


def _tool(**overrides) -> Tool:
    kwargs = dict(
        name="things_get",
        description="Get a thing.",
        method="GET",
        url_template="v1/things/{thing_id}",
        args_schema=GetThing,
        base_url=BASE,
        api_key_headers={"x-api-key": "k"},
    )
    kwargs.update(overrides)
    return Tool(**kwargs)


@pytest.mark.parametrize(
    ("failure", "may_have_taken_effect"),
    [
        (httpx.ConnectTimeout("connect timed out"), False),
        (httpx.ConnectError("All connection attempts failed"), False),
        (httpx.PoolTimeout(""), False),
        (httpx.ReadTimeout(""), True),
        (httpx.WriteTimeout(""), True),
        (httpx.RemoteProtocolError("Server disconnected"), True),
        (httpx.ReadError("Connection reset by peer"), True),
    ],
)
@respx.mock
async def test_a_transport_failure_is_a_network_error(failure, may_have_taken_effect):
    respx.get(f"{BASE}v1/things/t1").mock(side_effect=failure)

    with pytest.raises(NetworkError) as raised:
        await _tool().ainvoke(thing_id="t1")

    error = raised.value
    assert isinstance(error, CharterError)
    assert error.__cause__ is failure
    assert error.host == "api.example.com"
    assert error.may_have_taken_effect is may_have_taken_effect
    assert "not a problem with the arguments" in str(error)


@respx.mock
async def test_a_connection_that_never_opened_says_nothing_changed():
    respx.get(f"{BASE}v1/things/t1").mock(side_effect=httpx.ConnectTimeout(""))

    with pytest.raises(NetworkError) as raised:
        await _tool().ainvoke(thing_id="t1")

    assert str(raised.value).startswith("Could not reach api.example.com (timed out connecting).")
    assert "never sent, so nothing changed" in str(raised.value)


@respx.mock
async def test_a_timeout_after_sending_warns_the_call_may_have_taken_effect():
    """A model that repeats a send after a read timeout can send it twice."""
    respx.get(f"{BASE}v1/things/t1").mock(side_effect=httpx.ReadTimeout(""))

    with pytest.raises(NetworkError) as raised:
        await _tool().ainvoke(thing_id="t1")

    assert "may have reached the server and taken effect" in str(raised.value)
    assert "check before repeating" in str(raised.value)


@respx.mock
async def test_the_url_kept_on_the_error_has_no_query_string():
    respx.get(f"{BASE}v1/things/t1").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(NetworkError) as raised:
        await _tool().ainvoke(thing_id="t1", units="metric")

    assert raised.value.url == f"{BASE}v1/things/t1"


@respx.mock
async def test_a_redirect_hop_that_fails_is_a_network_error_too():
    respx.get(f"{BASE}v1/things/t1").mock(
        return_value=httpx.Response(302, headers={"Location": "https://cdn.example.net/t1"})
    )
    respx.get("https://cdn.example.net/t1").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(NetworkError) as raised:
        await _tool(follow_redirects=True).ainvoke(thing_id="t1")

    assert raised.value.host == "cdn.example.net"


# -----------------------------------------------------
# The requests in front of the tool's own
# -----------------------------------------------------


def _client() -> OAuth2Client:
    return OAuth2Client(
        OAuth2Server(token_endpoint=TOKEN_URL),
        client_id="cid",
        client_secret="s3cr3t-client",
        refresh_token="rt-1",
    )


@respx.mock
async def test_an_unreachable_token_endpoint_names_the_authorization_server():
    """The model must not be told the API was down when it was never contacted."""
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectTimeout(""))
    api = respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={}))
    tool = oauth_tool_factory(
        pack="things", base_url=BASE, provider="example", credential_provider=_client()
    )(name="things_get", args_schema=GetThing, method="GET", url_template="v1/things/{thing_id}")

    with pytest.raises(NetworkError) as raised:
        await tool.ainvoke(thing_id="t1")

    assert raised.value.host == "oauth2.example.com"
    assert "while getting an access token" in str(raised.value)
    assert not api.called


@respx.mock
async def test_a_failed_token_request_does_not_put_the_secret_in_the_error():
    respx.post(TOKEN_URL).mock(side_effect=httpx.ReadTimeout(""))

    with pytest.raises(NetworkError) as raised:
        await _client().get_credentials("example")

    assert "s3cr3t-client" not in str(raised.value)
    assert "rt-1" not in str(raised.value)


@respx.mock
async def test_an_unreachable_token_endpoint_during_the_code_exchange():
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("refused"))
    flow = OAuth2Flow(
        OAuth2Server(
            token_endpoint=TOKEN_URL, authorization_endpoint="https://oauth2.example.com/auth"
        ),
        client_id="cid",
        client_secret="s3cr3t-client",
        redirect_uri="https://app.example.com/callback",
    )

    with pytest.raises(NetworkError) as raised:
        await flow.exchange("code-1", code_verifier="v" * 43)

    assert "while exchanging the authorization code" in str(raised.value)


@respx.mock
async def test_an_unreachable_revocation_endpoint():
    respx.post(REVOKE_URL).mock(side_effect=httpx.ConnectTimeout(""))
    server = OAuth2Server(token_endpoint=TOKEN_URL, revocation=Revocation(REVOKE_URL))

    with pytest.raises(NetworkError) as raised:
        await revoke_token(server, refresh_token="rt-1", client_id="cid", client_secret="s")

    assert "while revoking the grant" in str(raised.value)


# -----------------------------------------------------
# The translation itself
# -----------------------------------------------------


def test_a_failure_httpx_adds_later_is_assumed_to_have_been_sent():
    """Unknown means unknown: assuming nothing happened is the unsafe guess."""

    class NewFailure(httpx.TransportError):
        pass

    error = network_error(NewFailure("new"), f"{BASE}v1/things/t1")
    assert error.may_have_taken_effect is True
    assert "NewFailure" in str(error)


def test_the_detail_httpx_gives_is_kept_but_bounded():
    error = network_error(httpx.ConnectError("x" * 5000), f"{BASE}v1/things/t1")
    assert "could not connect: xxx" in str(error)
    assert len(str(error)) < 600


def test_a_network_error_survives_pickling():
    """Hosts that run tools in a process pool get the error, not a TypeError."""
    import pickle

    error = network_error(httpx.ConnectTimeout(""), f"{BASE}v1/things/t1")
    copy = pickle.loads(pickle.dumps(error))
    assert str(copy) == str(error)
    assert copy.may_have_taken_effect is False
    assert copy.host == "api.example.com"
