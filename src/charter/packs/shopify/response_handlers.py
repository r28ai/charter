"""
Shopify response unwrapping.

Two layers of GraphQL envelope come off here — ``data`` and the operation name —
exactly as in the Linear pack. What is specific to Shopify is money and
mutations.

**Money.** Shopify returns every price as a ``MoneyBag``:
``{"shopMoney": {"amount": "10.00", "currencyCode": "USD"}}``, because a store
can present one currency and settle in another. Two levels of nesting per price,
on every line item of every order, is a lot of envelope for a number. These
handlers flatten the shop-currency side to ``"10.00 USD"``.

**Contact details.** ``Customer.email`` and ``Customer.phone`` are deprecated;
the current fields are ``defaultEmailAddress { emailAddress }`` and
``defaultPhoneNumber { phoneNumber }``. That is an object wrapping one string,
for the two fields most likely to be read on a customer, so it is collapsed back
to ``email`` and ``phone``. The deprecation is Shopify's; the extra nesting does
not have to be the model's problem.

**userErrors.** A Shopify mutation that fails validation returns HTTP 200, no
``errors`` array, and a populated ``userErrors`` list. That is caught, but not
here: it is a fact about the API rather than about any one tool, so it is
declared once as :data:`~charter.packs.shopify.SHOPIFY_ENVELOPE` and enforced by the
runtime on every call. Nothing reaching these handlers has failed.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

__all__ = ["unwrap", "unwrap_mutation", "flatten_wrappers"]

_MONEY_KEYS = ("shopMoney", "presentmentMoney")

# The single-value objects Shopify wraps a customer's contact details in, and
# the scalar key each collapses back to.
_CONTACT_WRAPPERS = {
    "defaultEmailAddress": ("emailAddress", "email"),
    "defaultPhoneNumber": ("phoneNumber", "phone"),
}


def flatten_wrappers(value: Any) -> Any:
    """Collapse the one-value objects Shopify wraps scalars in.

    MoneyBag/MoneyV2 become ``"10.00 USD"``; a customer's
    ``defaultEmailAddress``/``defaultPhoneNumber`` become ``email``/``phone``.
    Walks the whole payload, since both appear at several depths — prices on the
    order, on each line item and on the customer's lifetime spend; contact
    details on a customer both standalone and nested inside an order.
    """
    if isinstance(value, list):
        return [flatten_wrappers(item) for item in value]

    if not isinstance(value, dict):
        return value

    # MoneyV2: {"amount": "10.00", "currencyCode": "USD"}
    if set(value) == {"amount", "currencyCode"}:
        return f"{value['amount']} {value['currencyCode']}"

    # MoneyBag: {"shopMoney": {...}} — keep the shop side, which is the one an
    # operator means when they say what an order was worth.
    for key in _MONEY_KEYS:
        if key in value and len(value) <= len(_MONEY_KEYS):
            return flatten_wrappers(value[key])

    out: Dict[str, Any] = {}
    for key, item in value.items():
        wrapper = _CONTACT_WRAPPERS.get(key)
        if wrapper is not None:
            inner, renamed = wrapper
            # Null when the customer has none, which is a fact worth keeping:
            # the key stays, exactly as the deprecated scalar used to report it.
            out[renamed] = item.get(inner) if isinstance(item, dict) else None
        else:
            out[key] = flatten_wrappers(item)
    return out


def _strip(operation: str, response: Any) -> Any:
    """``{"data": {"<operation>": X}}`` -> ``X``."""
    if not isinstance(response, dict):
        return response
    data = response.get("data")
    if not isinstance(data, dict):
        return response
    if operation not in data:
        return data
    return data[operation]


def unwrap(operation: str) -> Callable[[Any], Any]:
    """Strip the GraphQL envelope and flatten Shopify's one-value wrappers.

    ``pageInfo`` is preserved — it is where the cursor lives, and the pagination
    this pack declares reads it back out of the trimmed payload.
    """

    async def handler(response: Any) -> Any:
        return flatten_wrappers(_strip(operation, response))

    return handler


def unwrap_mutation(operation: str) -> Callable[[Any], Any]:
    """Unwrap a mutation payload and flatten Shopify's one-value wrappers.

    The envelope has already raised on a populated ``userErrors``, so anything
    reaching here succeeded and the now-empty list is noise. A mutation payload
    wraps its result in one more key (``product``, ``customer``); that is
    unwrapped when it is the only thing left.
    """

    async def handler(response: Any) -> Any:
        payload = _strip(operation, response)
        if not isinstance(payload, dict):
            return flatten_wrappers(payload)

        rest = {k: v for k, v in payload.items() if k != "userErrors"}
        if len(rest) == 1:
            rest = next(iter(rest.values()))
        return flatten_wrappers(rest)

    return handler
