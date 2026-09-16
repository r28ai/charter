"""Stripe, against the real API in test mode.

Test mode charges nothing and the objects are disposable, so this is the one
provider where a full billing lifecycle can be exercised end to end: a customer,
a card, an authorisation, a capture, a refund, an invoice, a subscription.

Every test states its arguments literally. Nothing here asks a model what to send,
which is the point: the question is whether Stripe accepts what the pack declares,
and a model choosing arguments only obscures the answer.

Two tools are deliberately never called. ``disputes_update`` submits evidence to
the bank and ``disputes_close`` concedes the money, and neither can be undone —
in test mode they cost nothing and still teach the suite a habit it must not
have. They are listed here so the gap is a decision rather than an oversight.
"""

from __future__ import annotations

import pytest
from charter.packs import stripe
from charter.types.errors import APIError

pytestmark = pytest.mark.live

# The account this suite runs against declines 4242 with a Radar rule, so a test
# that needs a *charge* uses the Mastercard number. `pm_card_visa` is still fine
# where nothing is charged — attaching, listing, detaching.
CHARGEABLE = "pm_card_mastercard"


async def _customer(world, trash, run_tag: str, *, suffix: str = "") -> str:
    """A throwaway customer, deleted on the way out.

    The pack has no ``customers_delete`` — deleting a customer is not an agent
    action anyone has asked for — so teardown goes through the world client.
    """
    made = await stripe.customers_create.ainvoke(
        {
            "email": f"{run_tag}{suffix}@harness.invalid",
            "name": f"Live check {run_tag}",
            "metadata": {"harness": run_tag},
        }
    )
    customer = made["id"]
    trash.later(lambda: world.stripe.customer_delete(customer))
    return customer


async def _price(trash, run_tag: str, *, amount: int, recurring: dict | None = None) -> str:
    """A product and a price on it, both deactivated on the way out.

    Neither can be deleted once anything references it, which is Stripe's design:
    an archived price keeps its history readable. Deactivating is the whole of
    the cleanup that exists.
    """
    product = await stripe.products_create.ainvoke(
        {"name": f"Live {run_tag}", "metadata": {"harness": run_tag}}
    )
    args: dict = {"product": product["id"], "currency": "usd", "unit_amount": amount}
    if recurring:
        args["recurring"] = recurring
    price = await stripe.prices_create.ainvoke(args)
    trash.later(lambda: stripe.prices_update.ainvoke({"price": price["id"], "active": False}))
    trash.later(lambda: stripe.products_update.ainvoke({"id": product["id"], "active": False}))
    return price["id"]


# -----------------------------------------------------
# The round trip this whole batch existed to close
# -----------------------------------------------------


async def test_an_invoice_can_be_built_and_finalised(needs, world, trash, run_tag):
    """Create an invoice, put a line on it, finalise it, void it.

    Before ``invoice_items_create`` existed the pack could make an invoice and had
    no way to put anything on it, so this is the sequence that was impossible.
    """
    needs("stripe")
    customer = await _customer(world, trash, run_tag)

    # `currency` is stated rather than defaulted: an invoice takes the account's
    # currency, this account's is AUD, and a USD line on it is a 400. The pack
    # offers the field; a test that relied on the default would pass only on an
    # account that happens to be American.
    invoice = await stripe.invoices_create.ainvoke(
        {"customer": customer, "currency": "usd", "description": f"live check {run_tag}"}
    )
    assert invoice["status"] == "draft"

    line = await stripe.invoice_items_create.ainvoke(
        {
            "customer": customer,
            "invoice": invoice["id"],
            "amount": 2500,
            "currency": "usd",
            "description": "One widget",
        }
    )
    assert line["amount"] == 2500

    described = await stripe.invoices_update.ainvoke(
        {"invoice": invoice["id"], "description": f"live check {run_tag}, amended"}
    )
    assert described["description"].endswith("amended")

    # The line is on the invoice, which is the assertion the mocks could not make.
    reread = await stripe.invoices_retrieve.ainvoke({"invoice": invoice["id"]})
    assert reread["amount_due"] == 2500

    finalised = await stripe.invoices_finalize.ainvoke({"invoice": invoice["id"]})
    assert finalised["status"] == "open"

    voided = await stripe.invoices_void.ainvoke({"invoice": invoice["id"]})
    assert voided["status"] == "void"


async def test_an_invoice_can_be_sent_and_written_off(needs, world, trash, run_tag):
    """``invoices_send`` and ``invoices_mark_uncollectible``, the two ends of an
    invoice nobody pays.

    Sending needs ``collection_method='send_invoice'`` and a due date; Stripe
    refuses to email an invoice it is charging a card for. Test mode delivers no
    mail but still runs the whole path.
    """
    needs("stripe")
    customer = await _customer(world, trash, run_tag, suffix="+send")

    invoice = await stripe.invoices_create.ainvoke(
        {
            "customer": customer,
            "currency": "usd",
            "collection_method": "send_invoice",
            "days_until_due": 30,
            "description": f"live send {run_tag}",
        }
    )
    await stripe.invoice_items_create.ainvoke(
        {"customer": customer, "invoice": invoice["id"], "amount": 1900, "currency": "usd"}
    )
    await stripe.invoices_finalize.ainvoke({"invoice": invoice["id"]})

    sent = await stripe.invoices_send.ainvoke({"invoice": invoice["id"]})
    assert sent["status"] == "open"

    written_off = await stripe.invoices_mark_uncollectible.ainvoke({"invoice": invoice["id"]})
    assert written_off["status"] == "uncollectible"

    mine = await stripe.invoices_list.ainvoke({"customer": customer, "limit": 10})
    assert any(i["id"] == invoice["id"] for i in mine["data"])


async def test_a_pending_line_waits_for_an_invoice(needs, world, trash, run_tag):
    """Created without ``invoice``, a line floats until something collects it, and
    the ``pending`` filter is how you find it."""
    needs("stripe")
    customer = await _customer(world, trash, run_tag)

    line = await stripe.invoice_items_create.ainvoke(
        {"customer": customer, "amount": 700, "currency": "usd", "description": "floating"}
    )
    trash.later(lambda: stripe.invoice_items_delete.ainvoke({"invoiceitem": line["id"]}))

    pending = await stripe.invoice_items_list.ainvoke({"customer": customer, "pending": True})
    assert any(item["id"] == line["id"] for item in pending["data"])

    changed = await stripe.invoice_items_update.ainvoke(
        {"invoiceitem": line["id"], "description": "floating, renamed"}
    )
    assert changed["description"] == "floating, renamed"


async def test_a_price_is_named_under_pricing(needs, world, trash, run_tag):
    """The field Stripe moved. ``pricing[price]`` reaches the API; a top-level
    ``price`` would be accepted and ignored, billing nothing.

    The assertion is the amount, not the acceptance: a line that quietly billed
    zero is exactly the failure this is here to catch.
    """
    needs("stripe")
    customer = await _customer(world, trash, run_tag)
    price = await _price(trash, run_tag, amount=1200)

    line = await stripe.invoice_items_create.ainvoke(
        {"customer": customer, "pricing": {"price": price}}
    )
    trash.later(lambda: stripe.invoice_items_delete.ainvoke({"invoiceitem": line["id"]}))
    assert line["amount"] == 1200


# -----------------------------------------------------
# Catalog
# -----------------------------------------------------


async def test_a_product_takes_a_default_price(needs, trash, run_tag):
    """``products_update`` names an existing price; it cannot mint one."""
    needs("stripe")
    product = await stripe.products_create.ainvoke(
        {"name": f"Live catalog {run_tag}", "description": "made by the live check"}
    )
    trash.later(lambda: stripe.products_update.ainvoke({"id": product["id"], "active": False}))

    price = await stripe.prices_create.ainvoke(
        {
            "product": product["id"],
            "currency": "usd",
            "unit_amount": 9900,
            "recurring": {"interval": "month"},
        }
    )
    trash.later(lambda: stripe.prices_update.ainvoke({"price": price["id"], "active": False}))
    assert price["recurring"]["interval"] == "month"

    updated = await stripe.products_update.ainvoke(
        {"id": product["id"], "default_price": price["id"]}
    )
    assert updated["default_price"] == price["id"]

    catalog = await stripe.prices_list.ainvoke({"product": product["id"], "limit": 10})
    assert [p["id"] for p in catalog["data"]] == [price["id"]]


async def test_a_price_cannot_be_repriced(needs, trash, run_tag):
    """The schema offers no amount on update. Confirm Stripe agrees by doing the
    one thing update *can* do, and checking the amount survived it."""
    needs("stripe")
    product = await stripe.products_create.ainvoke({"name": f"Live fixed {run_tag}"})
    trash.later(lambda: stripe.products_update.ainvoke({"id": product["id"], "active": False}))

    price = await stripe.prices_create.ainvoke(
        {"product": product["id"], "currency": "usd", "unit_amount": 500}
    )
    renamed = await stripe.prices_update.ainvoke(
        {"price": price["id"], "nickname": "renamed", "active": False}
    )
    assert renamed["nickname"] == "renamed"
    assert renamed["unit_amount"] == 500


# -----------------------------------------------------
# Checkout, read back
# -----------------------------------------------------


async def test_a_checkout_session_can_be_read_back(needs, trash, run_tag):
    """Creating a session and never being able to see whether it was paid was a
    dead end. ``status`` and ``payment_status`` are both needed to decide."""
    needs("stripe")
    price = await _price(trash, run_tag, amount=4200)

    session = await stripe.checkout_sessions_create.ainvoke(
        {
            "mode": "payment",
            "line_items": [{"price": price, "quantity": 2}],
            "success_url": "https://example.com/ok",
            "cancel_url": "https://example.com/no",
        }
    )

    reread = await stripe.checkout_sessions_retrieve.ainvoke({"session": session["id"]})
    assert reread["status"] == "open"
    assert reread["payment_status"] == "unpaid"
    assert reread["amount_total"] == 8400

    lines = await stripe.checkout_sessions_line_items.ainvoke({"session": session["id"]})
    assert lines["data"][0]["quantity"] == 2
    assert lines["data"][0]["amount_total"] == 8400

    listed = await stripe.checkout_sessions_list.ainvoke({"status": "open", "limit": 100})
    assert any(s["id"] == session["id"] for s in listed["data"])


# -----------------------------------------------------
# Payment intents: authorise, capture, refund
# -----------------------------------------------------


async def _authorised(customer: str, run_tag: str, amount: int = 5000) -> dict:
    """A confirmed, manual-capture PaymentIntent: money held, not taken."""
    return await stripe.payment_intents_create.ainvoke(
        {
            "amount": amount,
            "currency": "usd",
            "customer": customer,
            "payment_method": CHARGEABLE,
            "capture_method": "manual",
            "confirm": True,
            "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
            "description": f"live capture {run_tag}",
            "metadata": {"harness": run_tag},
        }
    )


async def test_a_payment_can_be_confirmed_on_creation(needs, world, trash, run_tag):
    """``confirm`` is the difference between an intent and a payment.

    An agent told to take a payment has no client-side step to hand off to, so an
    intent it cannot confirm is a dead end. Stripe offers the intent whatever the
    dashboard has enabled, some of which redirects, so confirming needs
    ``allow_redirects='never'`` here — or a ``return_url``, which an agent does
    not have.
    """
    needs("stripe")
    customer = await _customer(world, trash, run_tag, suffix="+auto")

    intent = await stripe.payment_intents_create.ainvoke(
        {
            "amount": 1000,
            "currency": "usd",
            "customer": customer,
            "payment_method": CHARGEABLE,
            "confirm": True,
            "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
            "description": f"live auto {run_tag}",
        }
    )
    assert intent["status"] == "succeeded"
    assert intent["amount_received"] == 1000


async def test_an_authorised_payment_is_captured_and_refunded(needs, world, trash, run_tag):
    """Hold the funds, ship, take them — and refund when that goes wrong.

    ``capture_method`` is trimmed out of the response, so nothing here reads it
    back. ``requires_capture`` is the proof it arrived: an automatic intent would
    already say ``succeeded``.
    """
    needs("stripe")
    customer = await _customer(world, trash, run_tag, suffix="+capture")
    authorised = await _authorised(customer, run_tag)
    assert authorised["status"] == "requires_capture"

    # `final_capture` is refused rather than ignored on an intent that does not
    # support multi-capture, which an online card never does — and refused even
    # when set to the value matching the default. The pack's docstring says the
    # field applies "where the payment method supports it"; this is what the
    # other case actually does.
    with pytest.raises(APIError) as refused:
        await stripe.payment_intents_capture.ainvoke(
            {"intent": authorised["id"], "amount_to_capture": 4000, "final_capture": True}
        )
    assert "multi-capture" in refused.value.body

    captured = await stripe.payment_intents_capture.ainvoke(
        {"intent": authorised["id"], "amount_to_capture": 4000}
    )
    assert captured["status"] == "succeeded"
    # Capturing less than authorised releases the rest, which is the only reason
    # amount_to_capture exists and the only way to tell it was honoured.
    assert captured["amount_received"] == 4000

    charge = await stripe.charges_retrieve.ainvoke({"charge": captured["latest_charge"]})
    assert charge["paid"] is True
    # `amount` stays the authorisation and does not move when less than all of it
    # is captured; `amount_captured` is the money. An agent reconciling on the
    # first of those overstates a partial capture by the released remainder.
    assert charge["amount"] == 5000
    assert charge["amount_captured"] == 4000

    refund = await stripe.refunds_create.ainvoke(
        {"charge": charge["id"], "amount": 1500, "reason": "requested_by_customer"}
    )
    assert refund["status"] in {"succeeded", "pending"}

    reread = await stripe.refunds_retrieve.ainvoke({"refund": refund["id"]})
    assert reread["id"] == refund["id"]

    mine = await stripe.refunds_list.ainvoke({"payment_intent": authorised["id"], "limit": 10})
    assert [r["id"] for r in mine["data"]] == [refund["id"]]

    settled = await stripe.charges_retrieve.ainvoke({"charge": charge["id"]})
    assert settled["amount_refunded"] == 1500

    found = await stripe.payment_intents_retrieve.ainvoke({"payment_intent": authorised["id"]})
    assert found["amount_received"] == 4000

    listed = await stripe.payment_intents_list.ainvoke({"customer": customer, "limit": 10})
    assert [p["id"] for p in listed["data"]] == [authorised["id"]]

    charges = await stripe.charges_list.ainvoke({"payment_intent": authorised["id"], "limit": 10})
    assert [c["id"] for c in charges["data"]] == [charge["id"]]


async def test_an_unconfirmed_intent_can_be_cancelled(needs, run_tag):
    """``cancellation_reason`` has four sendable values against the eight the
    object reports, and a schema typed on the object's set would offer values the
    API refuses. ``abandoned`` is one of the four."""
    needs("stripe")
    intent = await stripe.payment_intents_create.ainvoke(
        {"amount": 5000, "currency": "usd", "description": f"live cancel {run_tag}"}
    )
    assert intent["status"] == "requires_payment_method"

    cancelled = await stripe.payment_intents_cancel.ainvoke(
        {"intent": intent["id"], "cancellation_reason": "abandoned"}
    )
    assert cancelled["status"] == "canceled"


# -----------------------------------------------------
# Payment methods
# -----------------------------------------------------


async def test_a_payment_method_attaches_is_read_and_detaches(needs, world, trash, run_tag):
    """``pm_card_visa`` is Stripe's own test payment method. Nothing is charged
    here, so the Radar rule on 4242 never comes into it."""
    needs("stripe")
    customer = await _customer(world, trash, run_tag, suffix="+pm")
    attached = await stripe.payment_methods_attach.ainvoke(
        {"payment_method": "pm_card_visa", "customer": customer}
    )
    assert attached["customer"] == customer

    mine = await stripe.customer_payment_methods_list.ainvoke({"customer": customer})
    assert [pm["id"] for pm in mine["data"]] == [attached["id"]]

    one = await stripe.customer_payment_method_retrieve.ainvoke(
        {"customer": customer, "payment_method": attached["id"]}
    )
    assert one["type"] == "card"
    # The type-named detail hash survives the trim, and only that one.
    assert one["card"]["last4"] == "4242"
    assert "sepa_debit" not in one

    direct = await stripe.payment_methods_retrieve.ainvoke({"payment_method": attached["id"]})
    assert direct["id"] == attached["id"]

    detached = await stripe.payment_methods_detach.ainvoke({"payment_method": attached["id"]})
    assert detached.get("customer") is None


async def test_an_unknown_payment_method_type_is_not_rejected_locally(needs):
    """``type`` is an open set. A closed Literal would reject this before sending,
    and Stripe answers it fine."""
    needs("stripe")
    result = await stripe.payment_methods_list.ainvoke({"type": "sepa_debit", "limit": 1})
    assert "data" in result


# -----------------------------------------------------
# Customers
# -----------------------------------------------------


async def test_a_customer_can_be_read_back_and_edited(needs, world, trash, run_tag):
    needs("stripe")
    customer = await _customer(world, trash, run_tag, suffix="+edit")

    found = await stripe.customers_retrieve.ainvoke({"customer": customer})
    assert found["email"] == f"{run_tag}+edit@harness.invalid"
    assert found["metadata"]["harness"] == run_tag

    updated = await stripe.customers_update.ainvoke(
        {
            "customer": customer,
            "description": "edited by the live check",
            "address": {"line1": "1 Test Street", "city": "Paris", "country": "FR"},
        }
    )
    assert updated["description"] == "edited by the live check"

    by_email = await stripe.customers_list.ainvoke(
        {"email": f"{run_tag}+edit@harness.invalid", "limit": 10}
    )
    assert [c["id"] for c in by_email["data"]] == [customer]


# -----------------------------------------------------
# Subscriptions
# -----------------------------------------------------


async def test_a_subscription_runs_its_lifecycle(needs, world, trash, run_tag):
    """Create, update, cancel. The three tools that turned ``subscriptions_list``
    from a dead end into a lifecycle."""
    needs("stripe")
    customer = await _customer(world, trash, run_tag, suffix="+sub")
    price = await _price(trash, run_tag, amount=1500, recurring={"interval": "month"})
    # A card, so the first invoice is actually paid. Without one the subscription
    # sits at `incomplete` and cancelling it reports `incomplete_expired`, which
    # is a different lifecycle from the one under test.
    card = await world.stripe.http.json(
        "POST", f"v1/payment_methods/{CHARGEABLE}/attach", data={"customer": customer}
    )

    sub = await stripe.subscriptions_create.ainvoke(
        {
            "customer": customer,
            "items": [{"price": price}],
            "default_payment_method": card["id"],
            "description": f"live sub {run_tag}",
        }
    )
    assert sub["status"] == "active"
    # The period Stripe moved onto the items, reassembled by the handler.
    assert sub["current_period_end"] > sub["current_period_start"]

    mine = await stripe.subscriptions_list.ainvoke({"customer": customer, "limit": 10})
    assert [s["id"] for s in mine["data"]] == [sub["id"]]

    ending = await stripe.subscriptions_update.ainvoke(
        {"subscription": sub["id"], "cancel_at_period_end": True}
    )
    assert ending["cancel_at_period_end"] is True

    cancelled = await stripe.subscriptions_cancel.ainvoke(
        {"subscription": sub["id"], "cancellation_details": {"feedback": "other"}}
    )
    assert cancelled["status"] == "canceled"


# -----------------------------------------------------
# Connect and disputes: read-only, and honest about it
# -----------------------------------------------------


async def test_the_connect_reads_answer_on_an_account_with_no_connect(needs):
    """Every Connect tool is a GET, and on a plain account the answer is an empty
    list. That the *call* is accepted is the whole assertion — a platform account
    is not something this suite can conjure."""
    needs("stripe")
    accounts = await stripe.accounts_list.ainvoke({"limit": 1})
    assert "data" in accounts

    if not accounts["data"]:
        pytest.skip("no connected accounts: accounts_retrieve and transfers_retrieve need one")

    one = await stripe.accounts_retrieve.ainvoke({"account": accounts["data"][0]["id"]})
    assert one["id"] == accounts["data"][0]["id"]


async def test_a_dispute_is_readable_when_one_exists(needs):
    """``disputes_update`` and ``disputes_close`` are not exercised anywhere in
    this suite: both are irreversible. The read half is."""
    needs("stripe")
    disputes = await stripe.disputes_list.ainvoke({"limit": 1})
    if not disputes["data"]:
        pytest.skip("this account has no disputes to retrieve")

    one = await stripe.disputes_retrieve.ainvoke({"dispute": disputes["data"][0]["id"]})
    assert one["id"] == disputes["data"][0]["id"]


async def test_a_payout_is_readable_when_one_exists(needs):
    needs("stripe")
    payouts = await stripe.payouts_list.ainvoke({"limit": 1})
    if not payouts["data"]:
        pytest.skip("this account has no payouts to retrieve")

    one = await stripe.payouts_retrieve.ainvoke({"payout": payouts["data"][0]["id"]})
    assert one["id"] == payouts["data"][0]["id"]


async def test_a_transfer_is_readable_when_one_exists(needs):
    needs("stripe")
    transfers = await stripe.transfers_list.ainvoke({"limit": 1})
    if not transfers["data"]:
        pytest.skip("this account has no transfers to retrieve")

    one = await stripe.transfers_retrieve.ainvoke({"transfer": transfers["data"][0]["id"]})
    assert one["id"] == transfers["data"][0]["id"]


# -----------------------------------------------------
# Reads that must not 400
# -----------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("refunds_list", {"limit": 1}),
        ("disputes_list", {"limit": 1}),
        ("accounts_list", {"limit": 1}),
        ("transfers_list", {"limit": 1}),
        ("payouts_list", {"limit": 1}),
        ("application_fees_list", {"limit": 1}),
        ("balance_transactions_list", {"limit": 1}),
        ("invoices_list", {"limit": 1, "status": "draft"}),
        ("invoice_items_list", {"limit": 1}),
        ("products_list", {"limit": 1, "active": True}),
        ("prices_list", {"limit": 1, "active": True}),
        ("subscriptions_list", {"limit": 1, "status": "active"}),
        ("payment_methods_list", {"limit": 1}),
        ("payment_intents_list", {"limit": 1}),
        ("checkout_sessions_list", {"limit": 1}),
        ("customers_list", {"limit": 1}),
        ("charges_list", {"limit": 1}),
        ("balance_retrieve", {}),
    ],
)
async def test_a_read_tool_is_accepted_as_declared(needs, tool_name, args):
    """Every filter and parameter name here is one Stripe could have renamed.

    A mock answers whatever it was told to; only the live API says whether the
    query string is spelled the way it expects.
    """
    needs("stripe")
    result = await getattr(stripe, tool_name).ainvoke(dict(args))
    assert result is not None


async def test_the_created_window_filters_rather_than_erroring(needs):
    """``created`` is the bracketed range object, not a bare integer. Stripe
    accepts ``created=<int>`` too, meaning *exactly* that second, so a wrong
    encoding here returns an empty list rather than an error."""
    needs("stripe")
    recent = await stripe.balance_transactions_list.ainvoke({"created": {"gte": 1}, "limit": 1})
    assert "data" in recent

    impossible = await stripe.balance_transactions_list.ainvoke(
        {"created": {"lt": 1}, "limit": 1}
    )
    assert impossible["data"] == []


async def test_a_payout_status_filter_is_accepted(needs):
    """Four documented values. ``in_transit`` is on the object but not the filter."""
    needs("stripe")
    result = await stripe.payouts_list.ainvoke({"status": "paid", "limit": 1})
    assert "data" in result


async def test_the_derived_cursor_pages_forward(needs):
    """Stripe's cursor is the last object's id, not a token it hands back. If the
    trim ever dropped ``id`` this is the test that would notice."""
    needs("stripe")
    first = await stripe.customers_list.ainvoke({"limit": 1})
    if not first["data"] or not first.get("has_more"):
        pytest.skip("fewer than two customers on this account")

    second = await stripe.customers_list.ainvoke(
        {"limit": 1, "starting_after": first["data"][0]["id"]}
    )
    assert second["data"]
    assert second["data"][0]["id"] != first["data"][0]["id"]


# -----------------------------------------------------
# One runtime rule, and the three tools it used to break
# -----------------------------------------------------


@pytest.mark.parametrize(
    "call,names",
    [
        pytest.param(
            lambda: stripe.payment_methods_attach.ainvoke(
                {"payment_method": "pm_card_visa", "customer": "cus_missing"}
            ),
            "cus_missing",
            id="payment_methods_attach",
        ),
        pytest.param(
            lambda: stripe.payment_intents_cancel.ainvoke(
                {"intent": "pi_missing", "cancellation_reason": "abandoned"}
            ),
            "pi_missing",
            id="payment_intents_cancel_with_a_reason",
        ),
        pytest.param(
            lambda: stripe.invoices_finalize.ainvoke(
                {"invoice": "in_missing", "auto_advance": False}
            ),
            "in_missing",
            id="invoices_finalize_with_auto_advance",
        ),
    ],
)
async def test_a_lone_scalar_body_field_reaches_the_network(needs, call, names):
    """Each of these three sends one scalar to the body and nothing else.

    A lone ``Body()`` field is unwrapped to *become* the request body, which is
    right for a model and impossible for a scalar: form encoding has no
    bare-value form, so these died locally with a DeclarationError before
    anything was sent. ``payment_methods_attach`` takes a required scalar, so it
    could never run at all.

    The ids are deliberately ones Stripe does not have: what is under test is
    whether the request is *built and sent*, so Stripe complaining about the id
    is the pass and a DeclarationError raised before the socket opens is the
    failure. The three are listed rather than summarised so the rule can be
    checked against each shape that used to break it.

    ``attach`` is the sharpest of the three. The id it complains about is the one
    in the *body*, not the path — Stripe could only have read it if the scalar
    arrived under its own name.
    """
    needs("stripe")
    with pytest.raises(APIError) as caught:
        await call()
    assert caught.value.status_code in (400, 404)
    assert names in str(caught.value)
