"""τ²-bench's airline tools, served as an HTTP API and declared with Charter.

The same construction as :mod:`retail_api`, over the domain's own ``AirlineTools``:
each route calls the stock tool on the episode's database and returns the text the
stock environment would have handed the model, errors included, so τ²-bench's
evaluator replays a Charter trajectory unchanged.

Two declarations of the same API, built from the stock tools so they cannot drift
from them: every field keeps its name, type and description, every nested object
its model, and every tool its description. The one difference from the stock
signatures is that ``List[FlightInfo | dict]`` (and the same for passengers and
payments) is declared ``list[FlightInfo]``: the ``dict`` is how the stock tool
receives raw JSON, and through Charter the model's JSON is validated into the
model and sent on the wire as a dict.

- :func:`plain_tools`: no rule beyond the types.
- :func:`ruled_tools`: adds the eleven rules in ``RULES_AIRLINE.md``, written
  before any task was read. They read the conversation and the database at call
  time, through :data:`SESSION`.

:func:`check` is those rules, and the only copy of them. The ruled tools refuse a
call it flags; :func:`broken_rules` applies it after the fact to every arm's
conversation, stock included, so "broke a rule and ran" is counted the same way
everywhere.
"""

from __future__ import annotations

import contextvars
import re
import types
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Annotated, Any, Union, get_args, get_origin

from charter import Body, Query, Tool, api_key_tool_factory
from pydantic import BaseModel, Field, create_model, model_validator
from retail_api import transport  # noqa: F401 - the same server, over this domain's tools
from tau2.data_model.message import ToolMessage, UserMessage
from tau2.domains.airline.data_model import FlightDB, Reservation
from tau2.domains.airline.environment import get_environment
from tau2.domains.airline.tools import AirlineTools, _resolve_key_folded
from tau2.environment.environment import Environment
from tau2.utils.text_match import fold_for_match

BASE_URL = "http://airline.local/"

# RULES_AIRLINE.md, rule 1: tools that act for a user named in the call...
BY_USER = {"get_user_details", "book_reservation", "send_certificate"}
# ...and tools that act for the owner of the reservation named in the call.
BY_RESERVATION = {
    "get_reservation_details",
    "cancel_reservation",
    "update_reservation_baggages",
    "update_reservation_flights",
    "update_reservation_passengers",
}
# Rule 2: what changes the database.
WRITES = {
    "book_reservation",
    "cancel_reservation",
    "update_reservation_baggages",
    "update_reservation_flights",
    "update_reservation_passengers",
    "send_certificate",
}
# Rule 11: a reservation "this conversation has already changed or cancelled".
CHANGES = WRITES & BY_RESERVATION
RULED = BY_USER | BY_RESERVATION | WRITES

FLOWN = {"landed", "flying"}
FREE_BAGS = {
    "regular": {"basic_economy": 0, "economy": 1, "business": 2},
    "silver": {"basic_economy": 1, "economy": 2, "business": 3},
    "gold": {"basic_economy": 2, "economy": 3, "business": 4},
}
PAYMENT_LIMITS = {"certificate": 1, "credit_card": 1, "gift_card": 3}

# Each refusal begins with its rule's phrase, so a refusal can be read back to it.
MESSAGES = {
    1: "The user has not given this user id in this conversation.",
    2: "This changes the booking database, and the user's last message is not an explicit yes.",
    3: "A reservation can have at most five passengers.",
    4: "A reservation can use at most one travel certificate, one credit card and three "
    "gift cards.",
    5: "Too few non-free bags for the allowance.",
    6: "Checked bags can be added but not removed.",
    7: "Basic economy flights cannot be modified.",
    8: "A change must keep the reservation's origin, destination and trip type.",
    9: "The cabin cannot be changed once a flight in the reservation has been flown.",
    10: "This reservation cannot be cancelled.",
    11: "No reservation of this user qualifies for this certificate.",
}


# -----------------------------------------------------------------------------
# What the host knows when a call arrives
# -----------------------------------------------------------------------------


@dataclass
class Session:
    """The episode's database, as it was and as it is, and what the user has said.

    ``changed`` holds the reservations a call has changed or cancelled (rule 11).
    """

    env: Environment
    start: FlightDB
    said: list[str] = field(default_factory=list)
    changed: set[str] = field(default_factory=set)
    refusals: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def of(cls, env: Environment) -> Session:
        return cls(env=env, start=env.tools.db.model_copy(deep=True))

    def heard(self, text: str) -> None:
        self.said.append(text)

    def restart(self) -> None:
        """The task's initial state has been applied: the conversation starts here."""
        self.start = self.env.tools.db.model_copy(deep=True)

    def ran(self, name: str, args: dict[str, Any]) -> None:
        """A call reached the tools and succeeded."""
        note_change(self.changed, name, args, self.env.tools.db)


SESSION: contextvars.ContextVar[Session] = contextvars.ContextVar("airline_session")


def note_change(changed: set[str], name: str, args: dict[str, Any], db: FlightDB) -> None:
    if name in CHANGES:
        rid = _resolve_key_folded(db.reservations, str(args.get("reservation_id", "")))
        if rid is not None:
            changed.add(rid)


# -----------------------------------------------------------------------------
# The rules
# -----------------------------------------------------------------------------

_AGREE_ANYWHERE = {"yes", "yeah", "yep", "yup"}
_AGREE_FIRST = (
    "sure",
    "ok",
    "okay",
    "correct",
    "confirmed",
    "i confirm",
    "absolutely",
    "definitely",
    "go ahead",
    "please go ahead",
    "proceed",
    "please proceed",
    "thats correct",
    "that is correct",
    "thats right",
    "sounds good",
)


def is_yes(text: str) -> bool:
    """Rule 2's explicit yes, as RULES_AIRLINE.md defines it."""
    words = re.sub(r"[^\w\s]", " ", re.sub(r"['’]", "", text.lower())).split()
    if _AGREE_ANYWHERE & set(words):
        return True
    joined = " ".join(words)
    return any(joined == p or joined.startswith(p + " ") for p in _AGREE_FIRST)


def _given(user_id: str, said: list[str]) -> bool:
    """Rule 1: the id appears in something the user said, ignoring case and accents."""
    wanted = re.escape(fold_for_match(user_id))
    return any(re.search(rf"(?<!\w){wanted}(?!\w)", fold_for_match(t)) for t in said)


def _reservation(db: FlightDB, rid: Any) -> Reservation | None:
    key = _resolve_key_folded(db.reservations, str(rid or ""))
    return db.reservations[key] if key is not None else None


def _status(db: FlightDB, number: str, date: str) -> str | None:
    key = _resolve_key_folded(db.flights, number)
    if key is None or date not in db.flights[key].dates:
        return None
    return db.flights[key].dates[date].status


def _flown(db: FlightDB, r: Reservation) -> bool:
    return any(_status(db, f.flight_number, f.date) in FLOWN for f in r.flights)


def _legs(db: FlightDB, flights: list[Any]) -> list[tuple[str, str]] | None:
    """(origin, destination) per flight in date and departure order; None if one is unknown."""
    legs = []
    for f in flights:
        number = f["flight_number"] if isinstance(f, dict) else f.flight_number
        date = f["date"] if isinstance(f, dict) else f.date
        key = _resolve_key_folded(db.flights, str(number))
        if key is None:
            return None
        flight = db.flights[key]
        legs.append(
            (str(date), flight.scheduled_departure_time_est, flight.origin, flight.destination)
        )
    return [(o, d) for _, _, o, d in sorted(legs)]


def _keeps_trip(legs: list[tuple[str, str]], r: Reservation) -> bool:
    if not legs or legs[0][0] != r.origin:
        return False
    if r.flight_type == "one_way":
        return legs[-1][1] == r.destination
    return legs[-1][1] == r.origin and any(d == r.destination for _, d in legs)


def _free_bags(db: FlightDB, user_id: str, cabin: str, passengers: int) -> int | None:
    key = _resolve_key_folded(db.users, user_id)
    if key is None or cabin not in FREE_BAGS["regular"]:
        return None
    return FREE_BAGS[db.users[key].membership][cabin] * passengers


def check(
    name: str,
    args: dict[str, Any],
    db: FlightDB,
    start: FlightDB,
    said: list[str],
    changed: set[str],
    now: str,
) -> list[tuple[int, str]]:
    """The rules of RULES_AIRLINE.md this call breaks, as ``(rule, message)``.

    ``db`` is the database as the call finds it, ``start`` as the conversation
    found it, ``said`` the user's messages so far and ``changed`` the reservations
    calls have changed or cancelled. Anything the call names that does not exist
    is left to the API to report.
    """
    out: list[tuple[int, str]] = []
    r = _reservation(db, args.get("reservation_id")) if name in BY_RESERVATION else None

    # 1. The user id the call acts for was given by the user.
    acts_for = args.get("user_id") if name in BY_USER else (r.user_id if r else None)
    if acts_for is not None and not _given(str(acts_for), said):
        out.append(
            (
                1,
                MESSAGES[1]
                + " Ask the user for their user id; do not use one found any other way.",
            )
        )

    # 2. An explicit yes.
    if name in WRITES and not (said and is_yes(said[-1])):
        out.append(
            (2, MESSAGES[2] + " List the action's details and ask them to confirm with yes.")
        )

    if name == "book_reservation":
        passengers = args.get("passengers") or []
        user_id = str(args.get("user_id", ""))
        # 3. At most five passengers.
        if len(passengers) > 5:
            out.append((3, MESSAGES[3]))
        # 4. Payment methods by type.
        ukey = _resolve_key_folded(db.users, user_id)
        if ukey is not None:
            methods = db.users[ukey].payment_methods
            used: dict[str, int] = {}
            for p in args.get("payment_methods") or []:
                pid = p.get("payment_id") if isinstance(p, dict) else getattr(p, "payment_id", None)
                if pid in methods:
                    used[methods[pid].source] = used.get(methods[pid].source, 0) + 1
            over = [s for s, n in used.items() if n > PAYMENT_LIMITS.get(s, n)]
            if over:
                out.append(
                    (4, MESSAGES[4] + f" This uses {', '.join(f'{used[s]} {s}' for s in over)}.")
                )
        # 5. The allowance.
        free = _free_bags(db, user_id, str(args.get("cabin")), len(passengers))
        if free is not None:
            out += _bags(args, free)

    if name == "update_reservation_baggages" and r is not None:
        free = _free_bags(db, r.user_id, r.cabin, len(r.passengers))
        if free is not None:
            out += _bags(args, free)
        # 6. Only added.
        total = _int(args.get("total_baggages"))
        if total is not None and total < r.total_baggages:
            out.append((6, MESSAGES[6] + f" The reservation has {r.total_baggages}."))

    if name == "update_reservation_flights" and r is not None:
        new = args.get("flights") or []
        # 7. Basic economy keeps its flights.
        if r.cabin == "basic_economy":

            def key(f: Any) -> tuple[str, str]:
                number = f["flight_number"] if isinstance(f, dict) else f.flight_number
                date = f["date"] if isinstance(f, dict) else f.date
                return (_resolve_key_folded(db.flights, str(number)) or str(number), str(date))

            if sorted(map(key, new)) != sorted(map(key, r.flights)):
                out.append(
                    (
                        7,
                        MESSAGES[7]
                        + " Only the cabin can change, with the reservation's own flights.",
                    )
                )
        # 8. Origin, destination and trip type, unless the booking itself fails the test.
        own, legs = _legs(db, r.flights), _legs(db, new)
        if (
            own is not None
            and legs is not None
            and _keeps_trip(own, r)
            and not _keeps_trip(legs, r)
        ):
            out.append(
                (
                    8,
                    MESSAGES[8] + f" It is {r.flight_type.replace('_', ' ')} from {r.origin} "
                    f"to {r.destination}.",
                )
            )
        # 9. No cabin change once flown.
        if args.get("cabin") != r.cabin and _flown(db, r):
            out.append((9, MESSAGES[9]))

    # 10. Cancellation.
    if name == "cancel_reservation" and r is not None:
        if _flown(db, r):
            out.append(
                (
                    10,
                    MESSAGES[10]
                    + " A flight in it has already been flown; transfer the user to a human agent.",
                )
            )
        else:
            recent = datetime.fromisoformat(now) - datetime.fromisoformat(
                r.created_at
            ) <= timedelta(hours=24)
            airline = any(_status(db, f.flight_number, f.date) == "cancelled" for f in r.flights)
            if not (recent or airline or r.cabin == "business" or r.insurance == "yes"):
                out.append(
                    (
                        10,
                        MESSAGES[10] + " It was not booked within the last 24 hours, none of its "
                        "flights was cancelled by the airline, it is not business, and it has no "
                        "travel insurance.",
                    )
                )

    # 11. Compensation.
    if name == "send_certificate":
        if not _certificate_allowed(
            start, str(args.get("user_id", "")), args.get("amount"), changed
        ):
            out.append(
                (
                    11,
                    MESSAGES[11] + " A certificate is $100 times the passengers of a reservation "
                    "with a cancelled flight, or $50 times the passengers of one with a delayed "
                    "flight once it has been changed or cancelled, and only for a silver or gold "
                    "member, or a reservation with insurance or in business.",
                )
            )
    return out


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None  # the types report it


def _bags(args: dict[str, Any], free: int) -> list[tuple[int, str]]:
    total, nonfree = _int(args.get("total_baggages")), _int(args.get("nonfree_baggages"))
    if total is None or nonfree is None:
        return []
    least = max(0, total - free)
    if nonfree < least:
        return [
            (5, MESSAGES[5] + f" {total} bags with {free} free means at least {least} non-free.")
        ]
    return []


def _certificate_allowed(start: FlightDB, user_id: str, amount: Any, changed: set[str]) -> bool:
    ukey = _resolve_key_folded(start.users, user_id)
    if ukey is None:
        return True  # the API reports the user missing
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return True  # the types report it
    user = start.users[ukey]
    for rid in user.reservations:
        r = start.reservations.get(rid)
        if r is None:
            continue
        if not (
            user.membership in ("silver", "gold") or r.insurance == "yes" or r.cabin == "business"
        ):
            continue
        statuses = {_status(start, f.flight_number, f.date) for f in r.flights}
        n = len(r.passengers)
        if amount == 100 * n and "cancelled" in statuses:
            return True
        if amount == 50 * n and "delayed" in statuses and rid in changed:
            return True
    return False


def refusal_rules(message: str) -> list[int]:
    """The rules a refusal names, by their phrases; ``[]`` for a refusal by the types."""
    rules = [n for n, phrase in MESSAGES.items() if phrase in message]
    if not rules and "at most 5 items" in message:  # rule 3, as the schema's maxItems says it
        rules = [3]
    return rules


# -----------------------------------------------------------------------------
# Rules broken by calls that ran, the same count on every arm
# -----------------------------------------------------------------------------


def broken_rules(trajectory: list[Any], task: Any) -> list[dict[str, Any]]:
    """Each call that reached the tools, succeeded, and broke a rule of RULES_AIRLINE.md.

    The conversation is replayed against a fresh environment the way τ²-bench's
    evaluator replays it, so each call is judged against the database as it found
    it, and the user's messages before it.
    """
    env = get_environment()
    init = task.initial_state
    env.set_state(
        initialization_data=init.initialization_data if init else None,
        initialization_actions=init.initialization_actions if init else None,
        message_history=[],
    )
    start = env.tools.db.model_copy(deep=True)
    now = env.tools._get_datetime()
    said: list[str] = []
    changed: set[str] = set()
    pending: dict[str, Any] = {}
    out: list[dict[str, Any]] = []
    for m in trajectory:
        if isinstance(m, UserMessage) and m.content:
            said.append(m.content)
        for tc in getattr(m, "tool_calls", None) or []:
            pending[tc.id] = tc
        tms = getattr(m, "tool_messages", None) or ([m] if isinstance(m, ToolMessage) else [])
        for tm in tms:
            tc = pending.pop(tm.id, None)
            # What the evaluator's replay skips, and what it applies.
            if tc is None or tm.execution_status == "rejected" or not env._has_tool(tc.name):
                continue
            args = tc.arguments or {}
            ok = not tm.error and tm.execution_status == "executed"
            broke = check(tc.name, args, env.tools.db, start, said, changed, now) if ok else []
            if env._is_mutating_tool(tc.name):
                env.get_response(tc)
            if ok:
                note_change(changed, tc.name, args, env.tools.db)
            if broke:
                out.append(
                    {
                        "tool": tc.name,
                        "rules": [n for n, _ in broke],
                        "user_said": (said[-1] if said else "")[:200],
                    }
                )
    return out


# -----------------------------------------------------------------------------
# The declarations, field for field from the stock tools
# -----------------------------------------------------------------------------


def _ruled_base(name: str) -> type[BaseModel]:
    class Ruled(BaseModel):
        @model_validator(mode="after")
        def _policy(self) -> Ruled:
            session = SESSION.get()
            tools: AirlineTools = session.env.tools
            broke = check(
                name,
                self.model_dump(),
                tools.db,
                session.start,
                session.said,
                session.changed,
                tools._get_datetime(),
            )
            if broke:
                raise ValueError(" ".join(message for _, message in broke))
            return self

    return Ruled


def _declared(annotation: Any) -> Any:
    """``List[X | dict]`` as ``list[X]``; anything else as it is."""
    if get_origin(annotation) is list:
        (item,) = get_args(annotation)
        if get_origin(item) in (Union, types.UnionType):
            members = [a for a in get_args(item) if a is not dict]
            if len(members) == 1:
                return list[members[0]]
    return annotation


def _model(stock: Any, read: bool, ruled: bool) -> type[BaseModel]:
    marker = Query() if read else Body()
    fields: dict[str, Any] = {}
    for fname, info in stock.params.model_fields.items():
        constraint: dict[str, Any] = {}
        if ruled and stock.name == "book_reservation" and fname == "passengers":
            constraint["max_length"] = 5  # rule 3
        fields[fname] = (
            Annotated[_declared(info.annotation), marker],
            Field(description=info.description, **constraint),
        )
    base = _ruled_base(stock.name) if ruled and stock.name in RULED else BaseModel
    camel = "".join(part.title() for part in stock.name.split("_"))
    return create_model(camel, __base__=base, **fields)


async def _unwrap(body: dict[str, Any]) -> Any:
    return body["result"]


def _tools(env: Environment, ruled: bool) -> list[Tool]:
    airline = api_key_tool_factory(
        pack="airline",
        base_url=BASE_URL,
        api_key_headers={"X-Airline-Session": "tau2"},
        # The domain's names are snake_case and so is this API, both ways.
        query_case="snake",
        body_case="snake",
    )
    tools = []
    for stock in env.get_tools():
        read = env.tools.tool_type(stock.name).value == "read"
        tools.append(
            airline(
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
