"""τ²-bench's retail tools, served as an HTTP API and declared with Charter.

The server is an ``httpx.MockTransport`` over the domain's own ``RetailTools``:
each route calls the domain's own tool on the episode's database, so a Charter
call changes exactly what a stock call would, and τ²-bench's evaluator replays the
trajectory unchanged. The body the server returns is the text the stock
environment would have handed the model, so on a call that reaches the API the
two arms read the same bytes. Nothing is reimplemented.

Two declarations of the same API, built from the stock tools so they cannot drift
from them: every field keeps its name, type and description, and every tool its
description.

- :func:`plain_tools`: no rule beyond the types.
- :func:`ruled_tools`: adds the three rules in ``RULES.md``, written before any
  task was read. They read the conversation at call time, through
  :data:`SESSION`, which the environment sets before each call.
"""

from __future__ import annotations

import contextvars
import json
import re
from dataclasses import dataclass, field
from typing import Annotated, Any

import httpx
from charter import Body, Query, Tool, api_key_tool_factory
from pydantic import AfterValidator, BaseModel, Field, create_model, model_validator
from tau2.environment.environment import Environment

BASE_URL = "http://retail.local/"

# RULES.md, rule 1: what may run before anyone is authenticated.
LOOKUPS = {"find_user_id_by_email", "find_user_id_by_name_zip"}
OPEN = LOOKUPS | {"list_all_product_types", "calculate", "transfer_to_human_agents"}
# RULES.md, rule 3: what changes the account.
WRITES = {
    "cancel_pending_order",
    "modify_pending_order_address",
    "modify_pending_order_items",
    "modify_pending_order_payment",
    "modify_user_address",
    "return_delivered_order_items",
    "exchange_delivered_order_items",
}


# -----------------------------------------------------------------------------
# The session the rules read
# -----------------------------------------------------------------------------


@dataclass
class Session:
    """What the host knows when a call arrives: who was authenticated, what was said.

    ``user_id`` is the first id a lookup returned. The policy allows one user per
    conversation, so a later lookup of somebody else does not replace it.
    """

    owners: dict[str, str]  # order id -> user id, from the episode's database
    user_id: str | None = None
    last_user_message: str = ""
    refusals: list[dict[str, Any]] = field(default_factory=list)

    def heard(self, text: str) -> None:
        self.last_user_message = text


SESSION: contextvars.ContextVar[Session] = contextvars.ContextVar("retail_session")


def is_yes(text: str) -> bool:
    """RULES.md, rule 3: lowercased and stripped of punctuation, it is or begins with yes."""
    words = re.sub(r"[^\w\s]", " ", text.lower()).split()
    return bool(words) and words[0] == "yes"


def _own_user(value: str) -> str:
    """Rule 2, for a user id."""
    session = SESSION.get()
    if session.user_id is not None and value != session.user_id:
        raise ValueError(
            "This is not the user authenticated in this conversation. You can only act "
            "for that user."
        )
    return value


def _own_order(value: str) -> str:
    """Rule 2, for an order id. An order that does not exist is the API's to report."""
    session = SESSION.get()
    owner = session.owners.get(value)
    if session.user_id is not None and owner is not None and owner != session.user_id:
        raise ValueError(
            "This order belongs to a different user than the one authenticated in this "
            "conversation. You can only act for that user."
        )
    return value


def _ruled_base(name: str) -> type[BaseModel]:
    """Rules 1 and 3, which are about the call rather than any one field."""

    class Ruled(BaseModel):
        @model_validator(mode="after")
        def _conversation(self) -> Ruled:
            session = SESSION.get()
            if name not in OPEN and session.user_id is None:
                raise ValueError(
                    "No user has been authenticated in this conversation. Find their user "
                    "id by email, or by name and zip code, before anything else."
                )
            if name in WRITES and not is_yes(session.last_user_message):
                raise ValueError(
                    "This changes the user's account, and the user's last message is not "
                    "an explicit yes. List the action's details and ask them to confirm "
                    "with yes."
                )
            return self

    return Ruled


# -----------------------------------------------------------------------------
# The server
# -----------------------------------------------------------------------------


def transport(env: Environment, sent: dict[str, Any] | None = None) -> httpx.MockTransport:
    """An HTTP API over one episode's ``RetailTools``: ``/{tool}``, GET for reads.

    ``sent``, when given, receives the arguments each request carried.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        name = request.url.path.strip("/")
        if not env.tools.has_tool(name):
            return httpx.Response(404, json={"error": f"no route /{name}"})
        kwargs: dict[str, Any] = dict(request.url.params)
        if request.content:
            kwargs.update(json.loads(request.content))
        if sent is not None:
            sent["args"] = dict(kwargs)
        try:
            result = env.tools.use_tool(tool_name=name, **kwargs)
        except Exception as exc:  # the stock environment's own catch
            return httpx.Response(400, json={"error": str(exc)})
        return httpx.Response(200, json={"result": Environment.to_json_str(result)})

    return httpx.MockTransport(handle)


async def _unwrap(body: dict[str, Any]) -> Any:
    return body["result"]


# -----------------------------------------------------------------------------
# The declarations, field for field from the stock tools
# -----------------------------------------------------------------------------


def _model(stock: Any, read: bool, ruled: bool) -> type[BaseModel]:
    marker = Query() if read else Body()
    fields: dict[str, Any] = {}
    for fname, info in stock.params.model_fields.items():
        rules = []
        if ruled and fname == "user_id":
            rules.append(AfterValidator(_own_user))
        if ruled and fname == "order_id":
            rules.append(AfterValidator(_own_order))
        fields[fname] = (
            Annotated[(info.annotation, marker, *rules)],
            Field(description=info.description),
        )
    base = _ruled_base(stock.name) if ruled else BaseModel
    camel = "".join(part.title() for part in stock.name.split("_"))
    return create_model(camel, __base__=base, **fields)


def _tools(env: Environment, ruled: bool) -> list[Tool]:
    retail = api_key_tool_factory(
        pack="retail",
        base_url=BASE_URL,
        api_key_headers={"X-Retail-Session": "tau2"},
        # The domain's names are snake_case and so is this API, both ways.
        query_case="snake",
        body_case="snake",
    )
    tools = []
    for stock in env.get_tools():
        read = env.tools.tool_type(stock.name).value == "read"
        tools.append(
            retail(
                name=stock.name,
                method="GET" if read else "POST",
                url_template=stock.name,
                args_schema=_model(stock, read, ruled),
                description=stock.openai_schema["function"]["description"],
                response_handler=_unwrap,
            )
        )
    return tools


def plain_tools(env: Environment) -> list[Tool]:
    return _tools(env, ruled=False)


def ruled_tools(env: Environment) -> list[Tool]:
    return _tools(env, ruled=True)
