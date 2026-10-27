"""The airline integration, offline: rules, the after-the-fact count, the wire, and limits.

Everything here is synthetic. The database is three airports, five flights and two
users made up for these tests, and no τ²-bench task is read: the rules were
written before any task was, and a test built from one would be a test tuned on one.

    .venv/bin/python -m pytest tests
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import airline_api as A  # noqa: E402
import resume  # noqa: E402
import run  # noqa: E402
from tau2.data_model.message import (  # noqa: E402
    AssistantMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau2.data_model.tasks import Task, UserScenario  # noqa: E402
from tau2.domains.airline.data_model import FlightDB  # noqa: E402
from tau2.domains.airline.environment import get_environment  # noqa: E402

NOW = "2024-05-15T15:00:00"


def _available(price: int = 100) -> dict[str, Any]:
    return {
        "status": "available",
        "available_seats": {"basic_economy": 9, "economy": 9, "business": 9},
        "prices": {"basic_economy": price, "economy": price * 2, "business": price * 5},
    }


def _flight(number: str, origin: str, destination: str, dep: str, dates: dict) -> dict:
    return {
        "flight_number": number,
        "origin": origin,
        "destination": destination,
        "scheduled_departure_time_est": dep,
        "scheduled_arrival_time_est": "23:00:00",
        "dates": dates,
    }


def _leg(number: str, origin: str, destination: str, date: str) -> dict:
    return {
        "flight_number": number,
        "origin": origin,
        "destination": destination,
        "date": date,
        "price": 200,
    }


def _user(uid: str, membership: str, methods: dict, reservations: list[str]) -> dict:
    return {
        "user_id": uid,
        "name": {"first_name": "Test", "last_name": uid},
        "address": {
            "address1": "1 Test St",
            "city": "Testville",
            "country": "USA",
            "state": "TS",
            "zip": "00000",
        },
        "email": f"{uid}@example.test",
        "dob": "1990-01-01",
        "payment_methods": methods,
        "saved_passengers": [],
        "membership": membership,
        "reservations": reservations,
    }


def _reservation(rid: str, uid: str, **kw: Any) -> dict:
    base = {
        "reservation_id": rid,
        "user_id": uid,
        "origin": "AAA",
        "destination": "BBB",
        "flight_type": "one_way",
        "cabin": "economy",
        "flights": [_leg("TST100", "AAA", "BBB", "2024-05-20")],
        "passengers": [{"first_name": "P", "last_name": "One", "dob": "1990-01-01"}],
        "payment_history": [{"payment_id": "credit_card_1", "amount": 200}],
        "created_at": "2024-05-01T10:00:00",
        "total_baggages": 0,
        "nonfree_baggages": 0,
        "insurance": "no",
    }
    return {**base, **kw}


TWO = [
    {"first_name": "P", "last_name": "One", "dob": "1990-01-01"},
    {"first_name": "P", "last_name": "Two", "dob": "1991-01-01"},
]


def synthetic_db() -> FlightDB:
    landed = {"status": "landed", "actual_departure_time_est": "x", "actual_arrival_time_est": "y"}
    delayed = {
        "status": "delayed",
        "estimated_departure_time_est": "x",
        "estimated_arrival_time_est": "y",
    }
    return FlightDB.model_validate(
        {
            "flights": {
                "TST100": _flight(
                    "TST100",
                    "AAA",
                    "BBB",
                    "08:00:00",
                    {"2024-05-20": _available(), "2024-05-14": landed},
                ),
                "TST101": _flight("TST101", "BBB", "AAA", "12:00:00", {"2024-05-25": _available()}),
                "TST102": _flight("TST102", "AAA", "CCC", "09:00:00", {"2024-05-20": _available()}),
                "TST103": _flight(
                    "TST103", "AAA", "BBB", "07:00:00", {"2024-05-18": {"status": "cancelled"}}
                ),
                "TST104": _flight("TST104", "BBB", "AAA", "06:00:00", {"2024-05-22": delayed}),
            },
            "users": {
                "ada_test_1": _user(
                    "ada_test_1",
                    "regular",
                    {
                        "credit_card_1": {
                            "source": "credit_card",
                            "id": "credit_card_1",
                            "brand": "visa",
                            "last_four": "1111",
                        },
                        "credit_card_2": {
                            "source": "credit_card",
                            "id": "credit_card_2",
                            "brand": "visa",
                            "last_four": "2222",
                        },
                        "gift_card_1": {"source": "gift_card", "id": "gift_card_1", "amount": 5000},
                        "certificate_1": {
                            "source": "certificate",
                            "id": "certificate_1",
                            "amount": 100,
                        },
                    },
                    ["RES001", "RES002", "RES003", "RES006"],
                ),
                "bo_test_2": _user(
                    "bo_test_2",
                    "gold",
                    {
                        "credit_card_3": {
                            "source": "credit_card",
                            "id": "credit_card_3",
                            "brand": "visa",
                            "last_four": "3333",
                        }
                    },
                    ["RES004", "RES005"],
                ),
            },
            "reservations": {
                # basic economy, old, uninsured: not cancellable, flights fixed
                "RES001": _reservation("RES001", "ada_test_1", cabin="basic_economy"),
                # round trip, insured, two passengers, two bags
                "RES002": _reservation(
                    "RES002",
                    "ada_test_1",
                    flight_type="round_trip",
                    flights=[
                        _leg("TST100", "AAA", "BBB", "2024-05-20"),
                        _leg("TST101", "BBB", "AAA", "2024-05-25"),
                    ],
                    passengers=TWO,
                    total_baggages=2,
                    insurance="yes",
                ),
                # already flown
                "RES003": _reservation(
                    "RES003", "ada_test_1", flights=[_leg("TST100", "AAA", "BBB", "2024-05-14")]
                ),
                # booked six hours ago
                "RES006": _reservation("RES006", "ada_test_1", created_at="2024-05-15T09:00:00"),
                # gold member, a flight the airline cancelled, two passengers
                "RES004": _reservation(
                    "RES004",
                    "bo_test_2",
                    flights=[_leg("TST103", "AAA", "BBB", "2024-05-18")],
                    passengers=TWO,
                ),
                # gold member, a delayed flight
                "RES005": _reservation(
                    "RES005",
                    "bo_test_2",
                    origin="BBB",
                    destination="AAA",
                    flights=[_leg("TST104", "BBB", "AAA", "2024-05-22")],
                ),
            },
        }
    )


@pytest.fixture
def db() -> FlightDB:
    return synthetic_db()


def rules(
    name: str, args: dict, db: FlightDB, said: list[str] | None = None, changed=None
) -> list[int]:
    said = (
        ["my user id is ada_test_1, and bo_test_2 is my partner's", "yes"] if said is None else said
    )
    return [n for n, _ in A.check(name, args, db, db, said, changed or set(), NOW)]


# -----------------------------------------------------------------------------
# The rules, one at a time
# -----------------------------------------------------------------------------


def test_rule_1_the_user_must_have_given_the_id(db: FlightDB) -> None:
    assert rules("get_user_details", {"user_id": "ada_test_1"}, db, said=["hello"]) == [1]
    assert rules("get_user_details", {"user_id": "ada_test_1"}, db, said=["I'm ADA_TEST_1"]) == []
    # a longer id that contains it is not it
    assert rules("get_user_details", {"user_id": "ada_test_1"}, db, said=["ada_test_12"]) == [1]
    # a reservation acts for its owner
    assert rules(
        "get_reservation_details", {"reservation_id": "res004"}, db, said=["ada_test_1"]
    ) == [1]
    assert (
        rules("get_reservation_details", {"reservation_id": "RES001"}, db, said=["ada_test_1"])
        == []
    )
    # a reservation that does not exist is the API's to report
    assert rules("get_reservation_details", {"reservation_id": "NOPE"}, db, said=[]) == []
    # searches name no user
    assert (
        rules(
            "search_direct_flight",
            {"origin": "AAA", "destination": "BBB", "date": "2024-05-20"},
            db,
            said=[],
        )
        == []
    )


@pytest.mark.parametrize(
    "text",
    [
        "Yes",
        "yes please",
        "Yeah, go ahead.",
        "Sure, do it",
        "OK",
        "okay.",
        "That's correct.",
        "Please proceed with the cancellation",
        "Go ahead",
        "Confirmed!",
        "I said yes earlier",
    ],
)
def test_rule_2_agreement_in_ordinary_words(text: str) -> None:
    assert A.is_yes(text)


@pytest.mark.parametrize(
    "text",
    [
        "No",
        "No, wait",
        "I'm not sure",
        "Can you check the price first?",
        "",
        "great, thanks",
        "yesterday works",
    ],
)
def test_rule_2_what_is_not_agreement(text: str) -> None:
    assert not A.is_yes(text)


def test_rule_2_every_write_needs_the_yes(db: FlightDB) -> None:
    said = ["my user id is ada_test_1", "hmm, let me think"]
    assert 2 in rules("cancel_reservation", {"reservation_id": "RES002"}, db, said=said)
    assert 2 in rules("send_certificate", {"user_id": "ada_test_1", "amount": 100}, db, said=said)
    assert 2 not in rules("get_user_details", {"user_id": "ada_test_1"}, db, said=said)


def _booking(**kw: Any) -> dict:
    base = {
        "user_id": "ada_test_1",
        "origin": "AAA",
        "destination": "BBB",
        "flight_type": "one_way",
        "cabin": "economy",
        "flights": [{"flight_number": "TST100", "date": "2024-05-20"}],
        "passengers": TWO,
        "payment_methods": [{"payment_id": "credit_card_1", "amount": 400}],
        "total_baggages": 0,
        "nonfree_baggages": 0,
        "insurance": "no",
    }
    return {**base, **kw}


def test_rules_3_4_5_on_a_booking(db: FlightDB) -> None:
    assert rules("book_reservation", _booking(), db) == []
    assert rules("book_reservation", _booking(passengers=TWO * 3), db) == [3]
    two_cards = [
        {"payment_id": "credit_card_1", "amount": 200},
        {"payment_id": "credit_card_2", "amount": 200},
    ]
    assert rules("book_reservation", _booking(payment_methods=two_cards), db) == [4]
    three_gift_cards = [{"payment_id": "gift_card_1", "amount": 100}] * 3
    assert rules("book_reservation", _booking(payment_methods=three_gift_cards), db) == []
    # a regular member's economy passengers get one free bag each: 3 bags for 2 is 1 paid
    assert rules("book_reservation", _booking(total_baggages=3, nonfree_baggages=0), db) == [5]
    assert rules("book_reservation", _booking(total_baggages=3, nonfree_baggages=1), db) == []
    # charging for a free bag is not refused: the per-passenger reading may allow it
    assert rules("book_reservation", _booking(total_baggages=2, nonfree_baggages=1), db) == []


def test_rules_5_6_on_bags(db: FlightDB) -> None:
    def bags(total: int, nonfree: int) -> list[int]:
        args = {
            "reservation_id": "RES002",
            "total_baggages": total,
            "nonfree_baggages": nonfree,
            "payment_id": "credit_card_1",
        }
        return rules("update_reservation_baggages", args, db)

    assert bags(3, 1) == []
    assert bags(3, 0) == [5]
    assert bags(1, 0) == [6]


def _change(rid: str, cabin: str, *flights: tuple[str, str]) -> dict:
    return {
        "reservation_id": rid,
        "cabin": cabin,
        "flights": [{"flight_number": n, "date": d} for n, d in flights],
        "payment_id": "credit_card_1",
    }


def test_rules_7_8_9_on_changing_flights(db: FlightDB) -> None:
    # basic economy: a new flight is refused, a cabin change on the same flights is not
    assert rules(
        "update_reservation_flights",
        _change("RES001", "basic_economy", ("TST102", "2024-05-20")),
        db,
    ) == [7, 8]
    assert (
        rules(
            "update_reservation_flights", _change("RES001", "economy", ("tst100", "2024-05-20")), db
        )
        == []
    )
    # a round trip listed return first is still the same trip
    assert (
        rules(
            "update_reservation_flights",
            _change("RES002", "economy", ("TST101", "2024-05-25"), ("TST100", "2024-05-20")),
            db,
        )
        == []
    )
    # dropping the return changes the trip type
    assert rules(
        "update_reservation_flights", _change("RES002", "economy", ("TST100", "2024-05-20")), db
    ) == [8]
    # a flown reservation keeps its cabin
    assert rules(
        "update_reservation_flights", _change("RES003", "business", ("TST100", "2024-05-14")), db
    ) == [9]
    assert (
        rules(
            "update_reservation_flights", _change("RES003", "economy", ("TST100", "2024-05-14")), db
        )
        == []
    )


def test_rule_10_on_cancelling(db: FlightDB) -> None:
    def cancel(rid: str) -> list[int]:
        return rules("cancel_reservation", {"reservation_id": rid}, db)

    assert cancel("RES001") == [10]  # old, basic economy, uninsured
    assert cancel("RES002") == []  # insured
    assert cancel("RES003") == [10]  # flown
    assert cancel("RES006") == []  # booked within 24 hours
    assert cancel("RES004") == []  # the airline cancelled a flight


def test_rule_11_on_certificates(db: FlightDB) -> None:
    def cert(uid: str, amount: int, changed: set[str] | None = None) -> list[int]:
        return rules("send_certificate", {"user_id": uid, "amount": amount}, db, changed=changed)

    assert cert("bo_test_2", 200) == []  # gold, cancelled flight, two passengers
    assert cert("bo_test_2", 100) == [11]  # wrong amount
    assert cert("bo_test_2", 50) == [11]  # delayed, but not yet changed or cancelled
    assert cert("bo_test_2", 50, changed={"RES005"}) == []
    assert cert("ada_test_1", 100) == [11]  # regular, and nothing cancelled


# -----------------------------------------------------------------------------
# The count after the fact, on a synthetic conversation
# -----------------------------------------------------------------------------


def _call(
    i: int, name: str, args: dict, *, rejected: bool = False, content: str = "{}"
) -> list[Any]:
    tc = ToolCall(id=f"c{i}", name=name, arguments=args, requestor="assistant")
    tm = ToolMessage(
        id=f"c{i}",
        role="tool",
        content=content,
        requestor="assistant",
        error=rejected,
        execution_status="rejected" if rejected else "executed",
    )
    return [AssistantMessage(role="assistant", tool_calls=[tc]), tm]


class _Task:
    initial_state = None


def _bags(rid: str, total: int, nonfree: int) -> dict:
    return {
        "reservation_id": rid,
        "total_baggages": total,
        "nonfree_baggages": nonfree,
        "payment_id": "credit_card_1",
    }


def test_broken_rules_counts_what_ran_and_replays_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(A, "get_environment", lambda: get_environment(db=synthetic_db()))
    trajectory = [
        AssistantMessage(role="assistant", content="Hi! How can I help?"),
        UserMessage(role="user", content="Cancel RES001 please"),
        *_call(1, "get_reservation_details", {"reservation_id": "RES001"}),
        UserMessage(role="user", content="I'm ada_test_1. Just do it"),
        # refused by an orchestrator: neither counted nor replayed
        *_call(2, "cancel_reservation", {"reservation_id": "RES006"}, rejected=True),
        *_call(3, "cancel_reservation", {"reservation_id": "RES001"}),
        UserMessage(role="user", content="yes"),
        *_call(
            4, "update_reservation_flights", _change("RES002", "economy", ("TST100", "2024-05-20"))
        ),
        *_call(5, "update_reservation_baggages", _bags("RES002", 3, 1)),
        # 2 bags is what RES002 started with, so only the replay of call 5 makes this a removal
        *_call(6, "update_reservation_baggages", _bags("RES002", 2, 1)),
    ]
    broken = A.broken_rules(trajectory, _Task())
    assert [(b["tool"], b["rules"]) for b in broken] == [
        ("get_reservation_details", [1]),
        ("cancel_reservation", [2, 10]),
        ("update_reservation_flights", [8]),
        ("update_reservation_baggages", [6]),
    ]


def test_broken_rules_sees_the_change_a_call_made(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 11's "already changed or cancelled" comes from the replayed calls."""
    monkeypatch.setattr(A, "get_environment", lambda: get_environment(db=synthetic_db()))
    said = UserMessage(role="user", content="bo_test_2 here. yes")
    before = [said, *_call(1, "send_certificate", {"user_id": "bo_test_2", "amount": 50})]
    after = [
        said,
        *_call(1, "cancel_reservation", {"reservation_id": "RES005"}),
        said,
        *_call(2, "send_certificate", {"user_id": "bo_test_2", "amount": 50}),
    ]
    assert [b["rules"] for b in A.broken_rules(before, _Task())] == [[11]]
    # the cancellation itself breaks rule 10 (not insured, not business, not recent)
    assert [b["rules"] for b in A.broken_rules(after, _Task())] == [[10]]


# -----------------------------------------------------------------------------
# The Charter arm: what it refuses, and what it sends
# -----------------------------------------------------------------------------


def _charter(ruled: bool) -> run.CharterEnv:
    return run.CharterEnv(get_environment(db=synthetic_db()), ruled=ruled)


def _tc(name: str, args: dict, i: int = 1) -> ToolCall:
    return ToolCall(id=f"t{i}", name=name, arguments=args, requestor="assistant")


def _camel(args: dict) -> dict:
    """What the model sends: Charter publishes camelCase names, nested ones too."""
    from pydantic.alias_generators import to_camel

    def walk(v: Any) -> Any:
        if isinstance(v, dict):
            return {to_camel(k): walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v

    return walk(args)


CALLS = [
    ("get_user_details", {"user_id": "ada_test_1"}),
    ("get_reservation_details", {"reservation_id": "RES002"}),
    ("get_reservation_details", {"reservation_id": "NOPE00"}),  # an error, as text
    ("search_direct_flight", {"origin": "AAA", "destination": "BBB", "date": "2024-05-20"}),
    ("search_onestop_flight", {"origin": "AAA", "destination": "BBB", "date": "2024-05-20"}),
    ("get_flight_status", {"flight_number": "TST104", "date": "2024-05-22"}),
    ("list_all_airports", {}),
    ("calculate", {"expression": "2 * (3 + 4)"}),
    (
        "book_reservation",
        _booking(
            total_baggages=3,
            nonfree_baggages=1,
            payment_methods=[{"payment_id": "credit_card_1", "amount": 450}],
        ),
    ),
    ("book_reservation", _booking()),  # an error: the payment does not add up
    (
        "update_reservation_baggages",
        {
            "reservation_id": "RES002",
            "total_baggages": 3,
            "nonfree_baggages": 1,
            "payment_id": "gift_card_1",
        },
    ),
    (
        "update_reservation_flights",
        _change("RES002", "business", ("TST100", "2024-05-20"), ("TST101", "2024-05-25")),
    ),
    (
        "update_reservation_passengers",
        {"reservation_id": "RES002", "passengers": list(reversed(TWO))},
    ),
    ("cancel_reservation", {"reservation_id": "RES006"}),
    ("send_certificate", {"user_id": "bo_test_2", "amount": 200}),
    ("transfer_to_human_agents", {"summary": "wants a human"}),
]


def test_a_call_through_charter_reads_and_changes_what_a_stock_call_does() -> None:
    stock = get_environment(db=synthetic_db())
    plain = _charter(ruled=False)
    for i, (name, args) in enumerate(CALLS):
        want = stock.get_response(_tc(name, args, i))
        got = plain.get_response(_tc(name, _camel(args), i))
        assert (got.content, got.error) == (want.content, want.error), name
        assert got.execution_status == "executed"
    assert plain.get_db_hash() == stock.get_db_hash()


def test_the_ruled_arm_refuses_before_anything_is_sent() -> None:
    env = _charter(ruled=True)
    before = env.tools.db.get_hash()
    env.session.heard("hi, I want to cancel RES001")
    msg = _tc("cancel_reservation", {"reservationId": "RES001"})
    reply = env.get_response(msg)
    assert reply.execution_status == "rejected" and reply.error
    assert env.tools.db.get_hash() == before
    assert env.session.refusals[-1]["rules"] == [1, 2, 10]
    # a refused call keeps the model's arguments, in the domain's names
    assert msg.arguments == {"reservation_id": "RES001"}


def test_the_ruled_arm_follows_what_the_conversation_changed() -> None:
    env = _charter(ruled=True)
    env.session.heard("I'm bo_test_2, my flight was delayed so cancel RES005")
    env.session.heard("yes")
    refused = env.get_response(_tc("cancel_reservation", {"reservationId": "RES005"}))
    assert refused.execution_status == "rejected"  # not insured, not business, not recent
    assert env.session.refusals[-1]["rules"] == [10]
    env.session.heard("ok then I'd like a certificate, yes")
    # RES005 has not been changed, so its $50 is refused; RES004's $200 is not
    assert env.get_response(_tc("send_certificate", {"userId": "bo_test_2", "amount": 50})).error
    good = env.get_response(_tc("send_certificate", {"userId": "bo_test_2", "amount": 200}))
    assert good.execution_status == "executed" and not good.error
    # once a call has changed RES005, the $50 is allowed
    env.session.heard("yes, add a bag to RES005")
    bag = {
        "reservationId": "RES005",
        "totalBaggages": 1,
        "nonfreeBaggages": 0,
        "paymentId": "credit_card_3",
    }
    assert env.get_response(_tc("update_reservation_baggages", bag)).execution_status == "executed"
    assert env.session.changed == {"RES005"}
    env.session.heard("yes")
    late = env.get_response(_tc("send_certificate", {"userId": "bo_test_2", "amount": 50}))
    assert late.execution_status == "executed" and not late.error


def test_the_schema_says_five_passengers_and_the_refusal_is_rule_3() -> None:
    env = _charter(ruled=True)
    schema = env.charter["book_reservation"].to_json_schema()["parameters"]
    assert schema["properties"]["passengers"]["maxItems"] == 5
    env.session.heard("ada_test_1, yes")
    reply = env.get_response(_tc("book_reservation", _camel(_booking(passengers=TWO * 3))))
    assert reply.execution_status == "rejected"
    assert env.session.refusals[-1]["rules"] == [3]


def test_both_arms_count_the_same_way() -> None:
    """What the ruled arm refuses at call time is what broken_rules finds after the fact."""
    said = ["I am ada_test_1", "Sure thing"]
    for name, args in CALLS:
        db = synthetic_db()
        expected = [n for n, _ in A.check(name, args, db, db, said, set(), NOW)]
        env = _charter(ruled=True)
        for s in said:
            env.session.heard(s)
        reply = env.get_response(_tc(name, _camel(args)))
        refused = env.session.refusals[-1]["rules"] if reply.execution_status == "rejected" else []
        assert refused == expected, name


# -----------------------------------------------------------------------------
# A subscription limit in the middle of a conversation
# -----------------------------------------------------------------------------


# A task with no grading criteria, which τ²-bench scores 1.0: what is tested is
# whether the episode is recorded, not what it scores.
SYNTHETIC_TASK = Task(
    id="synthetic", user_scenario=UserScenario(instructions="You need help with a booking.")
)


class FakeModels:
    """An OpenAI-style endpoint for both the agent and the customer.

    The customer asks for help until the agent (a request with tools) has answered
    twice, then says goodbye, so every conversation needs two agent turns. After
    ``limit_after`` agent requests, every agent request gets the 402 that
    bench/claude_provider.py sends when the subscription is out.
    """

    ASK = "Could you tell me more?"
    LIMIT = {
        "error": {
            "message": "claude subscription limit: You've hit your session limit · resets 5:40am",
            "type": "insufficient_quota",
        }
    }

    def __init__(self, limit_after: int | None) -> None:
        self.limit_after = limit_after
        self.agent_calls = 0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                status, reply = fake.answer(body)
                data = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def answer(self, body: dict) -> tuple[int, dict]:
        if body.get("tools"):
            self.agent_calls += 1
            if self.limit_after is not None and self.agent_calls > self.limit_after:
                return 402, self.LIMIT
            text = self.ASK
        else:
            asked = sum(m.get("content") == self.ASK for m in body.get("messages", []))
            text = "Thanks, that's all. ###STOP###" if asked >= 2 else "I need help with a booking."
        return 200, {
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": body.get("model"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def make(limit_after: int | None) -> FakeModels:
        fake = FakeModels(limit_after)
        monkeypatch.setitem(run.MODELS, "fake", "openai/fake")
        monkeypatch.setitem(
            run.LOCAL, "fake", {"api_base": fake.url, "api_key": "local", "num_retries": 0}
        )
        monkeypatch.setattr(run, "USER_MODEL", "fake")
        monkeypatch.setattr(run, "OUT_DIR", tmp_path)
        monkeypatch.setitem(run.TASKS, "airline", lambda split: [SYNTHETIC_TASK])
        return fake

    return make


def _main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--model",
            "fake",
            "--domain",
            "airline",
            "--split",
            "base",
            "--tasks",
            "0",
            *argv,
        ],
    )
    try:
        run.main()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def test_a_limit_mid_conversation_stops_the_run_and_writes_nothing(
    fake_run, monkeypatch, tmp_path
) -> None:
    fake = fake_run(limit_after=1)  # the first episode's second agent turn hits the limit
    code = _main(
        monkeypatch,
        "--arms",
        "stock,charter_rules",
        "--trials",
        "1",
        "--workers",
        "1",
        "--out",
        "t",
    )
    assert code == 3
    assert fake.agent_calls == 2  # mid-conversation, and the second episode never started
    out = tmp_path / "t" / "fake.jsonl"
    assert not out.exists() or out.read_text() == ""

    # The limit lifts; the same command finishes, and a third run has nothing to do.
    fake.limit_after = None
    assert (
        _main(
            monkeypatch,
            "--arms",
            "stock,charter_rules",
            "--trials",
            "1",
            "--workers",
            "1",
            "--out",
            "t",
        )
        == 0
    )
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert sorted((r["domain"], r["arm"], r["trial"]) for r in rows) == [
        ("airline", "charter_rules", 0),
        ("airline", "stock", 0),
    ]
    assert all(r.get("error") is None and r["reward"] is not None for r in rows)
    assert _main(monkeypatch, "--arms", "stock,charter_rules", "--trials", "1", "--out", "t") == 0
    assert len(out.read_text().splitlines()) == 2


def test_resume_keys_on_the_domain(fake_run, monkeypatch, tmp_path) -> None:
    """A retail row with the same arm, task and trial is not this airline episode."""
    fake_run(limit_after=None)
    task_id = SYNTHETIC_TASK.id
    out = tmp_path / "t" / "fake.jsonl"
    out.parent.mkdir(parents=True)
    # an old row, from before rows named their domain: it is retail
    out.write_text(json.dumps({"arm": "stock", "task": task_id, "trial": 0, "reward": 1.0}) + "\n")
    assert _main(monkeypatch, "--arms", "stock", "--trials", "1", "--out", "t") == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [r.get("domain", "retail") for r in rows] == ["retail", "airline"]


# -----------------------------------------------------------------------------
# The wrapper
# -----------------------------------------------------------------------------


def test_reset_times_are_read_from_the_limit_message() -> None:
    from datetime import datetime

    now = datetime(2026, 10, 25, 3, 0)
    assert resume.reset_time("You've hit your session limit · resets 5:40am", now) == datetime(
        2026, 10, 25, 5, 40
    )
    assert resume.reset_time("limit · resets 2am", now) == datetime(2026, 10, 26, 2, 0)
    assert resume.reset_time("resets 1:15pm (Europe/Paris)", now) == datetime(2026, 10, 25, 13, 15)
    assert resume.reset_time("resets Oct 27, 9am", now) == datetime(2026, 10, 27, 9, 0)
    assert resume.reset_time("usage limit reached", now) is None
    # what the CLI said on 2026-10-25
    weekly = "You've hit your weekly limit · resets Oct 26, 10pm (Europe/Paris)"
    assert resume.reset_time(weekly, now) == datetime(2026, 10, 26, 22, 0)
    session = "You've hit your session limit · resets 9:30am (Europe/Paris)"
    assert resume.reset_time(session, now) == datetime(2026, 10, 25, 9, 30)


@pytest.mark.parametrize(
    "said",
    [
        "You've hit your session limit · resets 5:40am",
        "You've hit your session limit · resets 9:30am (Europe/Paris)",
        "You've hit your weekly limit · resets Oct 26, 10pm (Europe/Paris)",
        "You've hit your monthly limit",
    ],
)
def test_the_provider_knows_a_limit_when_it_sees_one(said: str) -> None:
    """A limit read as an ordinary error is retried, recorded and rerun, not waited out."""
    sys.path.insert(0, str(HERE.parent))
    import claude_provider

    assert claude_provider._is_limit(said)
    assert not claude_provider._is_limit("claude -p failed: API Error: 500 Internal server error")


def test_the_wrapper_waits_until_the_provider_answers(tmp_path: Path) -> None:
    fake = FakeModels(limit_after=None)
    refusals = iter([True, True, False])
    answer = fake.answer
    fake.answer = lambda body: (402, FakeModels.LIMIT) if next(refusals) else answer(body)  # type: ignore[method-assign]
    log = resume.Log(tmp_path / "resume.log")
    resume.wait_for_provider("usage limit", fake.url, every=0.05, log=log)
    lines = (tmp_path / "resume.log").read_text().splitlines()
    assert [line.split(" ", 1)[1].split(":")[0] for line in lines] == [
        "waiting",
        "still refused",
        "still refused",
        "provider answers again (HTTP 200)",
    ]
