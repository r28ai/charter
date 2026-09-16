"""
Stripe response trimming.

Stripe objects are wide. A Customer carries ~20 fields, a PaymentIntent closer to
40, most of them null or infrastructural (`livemode`, `object`, `next_invoice_sequence`,
eight nested settings objects). A list of them is mostly envelope.

These handlers keep the fields an agent can act on and drop the rest. Two
invariants they must preserve, because other things depend on them:

* the ``data`` list and each object's ``id`` — Stripe's cursor is the last
  object's id (``data[-1].id``), so trimming ``id`` away would break pagination;
* ``has_more`` — the paging signal, at the top level and on a subscription's
  nested ``items``, where Stripe truncates at 20 without saying so anywhere else.

Stripe reports errors with real HTTP status codes, so unlike Slack there is no
success flag to check here; the runtime has already raised on a 4xx.

One of these handlers is not a projection. A subscription's billing period used
to be two fields on the subscription; it now lives on each subscription item, so
:func:`trim_subscriptions` reassembles it. See the note there.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

__all__ = [
    "trim_customers",
    "trim_payment_intents",
    "trim_charges",
    "trim_subscriptions",
    "trim_prices",
    "trim_invoices",
    "trim_payment_methods",
    "trim_disputes",
    "trim_accounts",
    "trim_transfers",
    "trim_payouts",
    "trim_application_fees",
    "trim_balance_transactions",
    "trim_checkout_sessions",
    "trim_line_items",
    "trim_products",
    "trim_invoice_items",
    "trim_refunds",
    "trim_balance",
]


def _pick(obj: Dict[str, Any], fields: Sequence[str]) -> Dict[str, Any]:
    """Project one object onto ``fields``, dropping keys that are absent or null.

    ``id`` is always kept: it is the pagination cursor.
    """
    out: Dict[str, Any] = {}
    if obj.get("id") is not None:
        out["id"] = obj["id"]
    for field in fields:
        value = obj.get(field)
        if value not in (None, "", [], {}):
            out[field] = value
    return out


def _list_handler(
    fields: Sequence[str],
    refine: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None,
) -> Callable[[Dict[str, Any]], Any]:
    """Build a handler that trims every object in a Stripe list response.

    The list envelope (``data``, ``has_more``) is preserved so the declared
    pagination keeps working against the trimmed payload.

    ``refine`` is an optional hook receiving ``(raw_object, projected_object)``
    for a field that needs more than a flat copy — a nested object worth keeping
    but not worth keeping whole.
    """

    def one(obj: Dict[str, Any]) -> Dict[str, Any]:
        out = _pick(obj, fields)
        if refine is not None:
            refine(obj, out)
        return out

    async def handler(response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(response, dict):
            return response

        # A retrieve endpoint returns a bare object rather than a list.
        if response.get("object") != "list":
            return one(response)

        data: List[Dict[str, Any]] = [
            one(item) for item in response.get("data") or [] if isinstance(item, dict)
        ]
        out: Dict[str, Any] = {"data": data}
        # Preserve has_more even when False. Stripe's cursor is the last object's
        # id, which is always present, so dropping a False has_more would leave
        # pagination with nothing to stop on.
        if "has_more" in response:
            out["has_more"] = bool(response["has_more"])
        return out

    return handler


_CUSTOMER_FIELDS = (
    "email", "name", "description", "phone", "created", "currency",
    "balance", "delinquent", "metadata",
)
_PAYMENT_INTENT_FIELDS = (
    "amount", "amount_received", "currency", "status", "created", "customer",
    "description", "latest_charge", "payment_method", "metadata",
)
# `amount_captured` beside `amount`, because on a partial capture they differ and
# only the second one is money that moved: a charge authorised at 5000 and
# captured at 4000 reports `amount` 5000 forever. Without it the sum an agent
# reconciles against is the authorisation, not the takings.
_CHARGE_FIELDS = (
    "amount", "amount_captured", "amount_refunded", "currency", "status", "paid",
    "captured", "refunded", "created", "customer", "description", "receipt_url",
    "failure_code", "failure_message", "payment_intent", "metadata",
)
_SUBSCRIPTION_FIELDS = (
    "status", "customer", "created", "cancel_at", "cancel_at_period_end",
    "canceled_at", "ended_at", "trial_end", "currency", "metadata",
)
_PRICE_FIELDS = (
    "product", "active", "currency", "unit_amount", "type", "recurring",
    "nickname", "metadata",
)


def _subscription(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One subscription, with its billing period put back together.

    ``current_period_start`` and ``current_period_end`` were fields on the
    Subscription object until Stripe moved them onto each subscription item,
    where a schedule can differ per item. A projection that keeps asking the
    subscription for them gets nothing and drops them silently, which is how an
    agent ends up reporting a renewal date of "unknown" for an active
    subscription.

    Almost every subscription bills its items on one schedule, so when the items
    agree the period is lifted back to where a reader expects it. When they do
    not, the per-item periods are reported instead and nothing is invented.

    API Reference: https://docs.stripe.com/api/subscriptions/object
    """
    out = _pick(obj, _SUBSCRIPTION_FIELDS)

    items = obj.get("items")
    data = items.get("data") if isinstance(items, dict) else None
    if not isinstance(data, list):
        return out

    periods = set()
    projected: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        price = item.get("price")
        entry: Dict[str, Any] = {}
        if isinstance(price, dict):
            entry["price"] = price.get("id")
            if price.get("unit_amount") is not None:
                entry["unit_amount"] = price["unit_amount"]
        if item.get("quantity") is not None:
            entry["quantity"] = item["quantity"]
        start, end = item.get("current_period_start"), item.get("current_period_end")
        if (start, end) != (None, None):
            periods.add((start, end))
            if start is not None:
                entry["current_period_start"] = start
            if end is not None:
                entry["current_period_end"] = end
        projected.append(entry)

    if len(periods) == 1:
        # One schedule, which is nearly always: lift it to where a reader
        # expects it and stop repeating it on every item.
        start, end = periods.pop()
        for entry in projected:
            entry.pop("current_period_start", None)
            entry.pop("current_period_end", None)
        if start is not None:
            out["current_period_start"] = start
        if end is not None:
            out["current_period_end"] = end

    if projected:
        out["items"] = projected
        # Stripe caps this nested list at 20 and says so in `items.has_more`.
        # The projection above flattens `items` to a bare list, which would drop
        # that flag and leave an agent totalling a subscription from a silently
        # short list. No tool here pages subscription items, so a `False` says
        # nothing actionable and is not carried; a `True` is a warning, and is.
        if isinstance(items, dict) and items.get("has_more"):
            out["items_has_more"] = True

    return out


# Why a failed PaymentIntent keeps more than its status. `status` says the
# payment did not happen; only `last_payment_error` says why, and the difference
# between `try_again_later` and a hard decline is the difference between an agent
# retrying and an agent telling the customer to use another card. The whole error
# object carries a nested payment_method and charge, so it is projected rather
# than copied: `charge` is already on the intent as `latest_charge`.
# https://docs.stripe.com/api/payment_intents/object#payment_intent_object-last_payment_error
_PAYMENT_ERROR_FIELDS = (
    "type", "code", "decline_code", "advice_code", "network_decline_code",
    "message", "param", "doc_url",
)


def _carry_payment_error(obj: Dict[str, Any], out: Dict[str, Any]) -> None:
    """Keep the projected reason a PaymentIntent failed, when there is one."""
    error = obj.get("last_payment_error")
    if not isinstance(error, dict):
        return
    projected = {
        field: error[field]
        for field in _PAYMENT_ERROR_FIELDS
        if error.get(field) not in (None, "")
    }
    if projected:
        out["last_payment_error"] = projected


trim_customers = _list_handler(_CUSTOMER_FIELDS)
trim_payment_intents = _list_handler(_PAYMENT_INTENT_FIELDS, _carry_payment_error)
trim_charges = _list_handler(_CHARGE_FIELDS)
trim_prices = _list_handler(_PRICE_FIELDS)


async def trim_subscriptions(response: Any) -> Any:
    """Trim a subscription or a list of them, keeping the billing period.

    The list envelope (``data``, ``has_more``) is preserved so the declared
    pagination keeps working, exactly as in :func:`_list_handler`.
    """
    if not isinstance(response, dict):
        return response

    if response.get("object") != "list":
        return _subscription(response)

    out: Dict[str, Any] = {
        "data": [
            _subscription(item)
            for item in response.get("data") or []
            if isinstance(item, dict)
        ]
    }
    if "has_more" in response:
        out["has_more"] = bool(response["has_more"])
    return out


_INVOICE_FIELDS = (
    "status", "customer", "subscription", "currency", "total", "amount_due",
    "amount_paid", "amount_remaining", "created", "due_date", "collection_method",
    "auto_advance", "number", "hosted_invoice_url", "invoice_pdf", "description",
    "metadata",
)

# The type-specific hash (card, sepa_debit, ...) is whichever one matches `type`,
# so it cannot be named in a static field list. `_carry_method_detail` copies it.
_PAYMENT_METHOD_FIELDS = ("type", "customer", "created", "billing_details", "allow_redisplay")

_DISPUTE_FIELDS = (
    "amount", "currency", "status", "reason", "created", "charge", "payment_intent",
    "is_charge_refundable", "evidence_details", "metadata",
)
_ACCOUNT_FIELDS = (
    "business_type", "country", "default_currency", "email", "charges_enabled",
    "payouts_enabled", "details_submitted", "created", "type", "metadata",
)
_TRANSFER_FIELDS = (
    "amount", "amount_reversed", "currency", "created", "destination",
    "destination_payment", "reversed", "transfer_group", "description", "metadata",
)
_PAYOUT_FIELDS = (
    "amount", "currency", "status", "arrival_date", "created", "destination",
    "method", "type", "failure_code", "failure_message", "description", "metadata",
)
_APPLICATION_FEE_FIELDS = (
    "amount", "amount_refunded", "currency", "created", "account", "charge",
    "refunded",
)
_BALANCE_TRANSACTION_FIELDS = (
    "amount", "net", "fee", "currency", "created", "available_on", "type",
    "reporting_category", "status", "source", "description",
)


def _carry_method_detail(obj: Dict[str, Any], out: Dict[str, Any]) -> None:
    """Keep the detail hash that matches the payment method's own type.

    A PaymentMethod carries exactly one of ~57 type-specific hashes, named after
    `type`. Listing them all statically would be a list that goes stale every time
    Stripe adds a payment method, so the type names its own hash instead.
    """
    kind = obj.get("type")
    if isinstance(kind, str) and isinstance(obj.get(kind), dict):
        out[kind] = obj[kind]


trim_invoices = _list_handler(_INVOICE_FIELDS)
trim_payment_methods = _list_handler(_PAYMENT_METHOD_FIELDS, _carry_method_detail)
trim_disputes = _list_handler(_DISPUTE_FIELDS)
trim_accounts = _list_handler(_ACCOUNT_FIELDS)
trim_transfers = _list_handler(_TRANSFER_FIELDS)
trim_payouts = _list_handler(_PAYOUT_FIELDS)
trim_application_fees = _list_handler(_APPLICATION_FEE_FIELDS)
trim_balance_transactions = _list_handler(_BALANCE_TRANSACTION_FIELDS)


_CHECKOUT_SESSION_FIELDS = (
    "status", "payment_status", "mode", "url", "customer", "customer_email",
    "amount_total", "amount_subtotal", "currency", "created", "expires_at",
    "payment_intent", "subscription", "invoice", "metadata",
)
_LINE_ITEM_FIELDS = (
    "description", "quantity", "amount_total", "amount_subtotal", "amount_discount",
    "amount_tax", "currency", "price",
)
_PRODUCT_FIELDS = (
    "name", "description", "active", "default_price", "created", "updated", "url",
    "images", "metadata",
)
_INVOICE_ITEM_FIELDS = (
    "amount", "currency", "description", "quantity", "customer", "invoice",
    "subscription", "date", "period", "discountable", "proration", "frozen_fields",
    "metadata",
)

trim_checkout_sessions = _list_handler(_CHECKOUT_SESSION_FIELDS)
trim_line_items = _list_handler(_LINE_ITEM_FIELDS)
trim_products = _list_handler(_PRODUCT_FIELDS)
trim_invoice_items = _list_handler(_INVOICE_ITEM_FIELDS)


# A refund carries `status` *and* `failure_reason`: a refund can come back
# `failed` days after it was created (a closed bank account, a card that no
# longer exists), and the reason is the only field that says which. Both are
# kept for the same reason `_carry_payment_error` exists on charges — a
# projection that keeps the amount and drops why it did not arrive reports a
# refund that never happened as one that did.
_REFUND_FIELDS = (
    "amount", "currency", "status", "reason", "failure_reason", "created",
    "charge", "payment_intent", "receipt_number", "description", "metadata",
)
# Stripe's balance is per-currency and split by how the money arrived, which is
# not a distinction an agent acts on: `available[0].source_types` breaks 4200
# into {card: 4200, bank_account: 0, fpx: 0} and every zero ships anyway.
_BALANCE_BUCKET_FIELDS = ("amount", "currency")

trim_refunds = _list_handler(_REFUND_FIELDS)


def _bucket(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {k: entry[k] for k in _BALANCE_BUCKET_FIELDS if entry.get(k) is not None}


async def trim_balance(response: Any) -> Any:
    """Trim ``GET /v1/balance`` to the amounts, per currency.

    Every bucket Stripe sends is kept — ``available``, ``pending``, and the
    Connect-only ``instant_available``, ``connect_reserved`` and
    ``refund_and_dispute_prefunding`` — because which ones are present is a
    property of the account, and an agent that reads only ``available`` on an
    account with funds in reserve reads the wrong number. What is dropped is
    the ``source_types`` breakdown inside each.
    """
    if not isinstance(response, dict):
        return response

    out: Dict[str, Any] = {}
    for key, value in response.items():
        if key in ("object", "livemode"):
            continue
        if isinstance(value, list):
            out[key] = [_bucket(e) for e in value if isinstance(e, dict)]
    return out
