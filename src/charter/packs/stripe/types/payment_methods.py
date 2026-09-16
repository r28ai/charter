"""Payment methods, and the one enum in this pack that must stay open.

``type`` looks exactly like an enum and is not one. Stripe's own schema marks it
``x-stripeBypassValidation``, the customer-scoped list says in prose that it covers
"all current and future payment method types", and three different value sets are
documented simultaneously: 55 accepted by the list filter, 57 on the object
(``card_present`` and ``interac_present`` are readable but not filterable), and 58 on
the create page (``paypay``, which is absent from the schema entirely). Closing the
Literal at any one of those numbers breaks one of the other two directions, and the
model cannot tell a rejected valid type from a wrong one. So it is a plain string,
with the values named in the description where they help and cost nothing.

API Reference: https://docs.stripe.com/api/payment_methods
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.stripe.types.common import StripeListRequest
from charter.types import Body, Path, Query

__all__ = [
    "AllowRedisplay",
    "PAYMENT_METHOD_TYPES",
    "PaymentMethodsListRequest",
    "PaymentMethodsRetrieveRequest",
    "PaymentMethodsAttachRequest",
    "PaymentMethodsDetachRequest",
    "CustomerPaymentMethodsListRequest",
    "CustomerPaymentMethodRetrieveRequest",
]

AllowRedisplay = Literal["always", "limited", "unspecified"]

# Documented for the description, deliberately not a Literal. See the module
# docstring: Stripe does not validate this field strictly and the set grows.
PAYMENT_METHOD_TYPES = (
    "acss_debit, affirm, afterpay_clearpay, alipay, alma, amazon_pay, au_becs_debit, "
    "bacs_debit, bancontact, billie, bizum, blik, boleto, card, cashapp, crypto, "
    "custom, customer_balance, eps, fpx, giropay, grabpay, ideal, kakao_pay, klarna, "
    "konbini, kr_card, link, mb_way, mobilepay, multibanco, naver_pay, "
    "nz_bank_account, oxxo, p24, pay_by_bank, payco, paynow, paypal, payto, pix, "
    "promptpay, revolut_pay, samsung_pay, satispay, scalapay, sepa_debit, sofort, "
    "sunbit, swish, twint, upi, us_bank_account, wechat_pay, zip"
)

_TYPE_DESCRIPTION = (
    "Only return payment methods of this type. Stripe adds types over time, so this "
    "is not a closed set; documented values are: " + PAYMENT_METHOD_TYPES + "."
)

_REDISPLAY_DESCRIPTION = (
    "Filter by whether the method may be shown to the customer again: 'always', "
    "'limited' (only in a specific context, such as one subscription), or "
    "'unspecified'."
)


class _PaymentMethodId(BaseModel):
    payment_method: Annotated[
        str,
        Field(..., description="The ID of the payment method."),
        Path(),
    ]


class PaymentMethodsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/payment_methods`.

    Without a `type` this returns every type except `custom`; custom payment methods
    appear only when asked for by name.

    API Reference: https://docs.stripe.com/api/payment_methods/list
    """

    type: Annotated[Optional[str], Field(None, description=_TYPE_DESCRIPTION), Query()]
    customer: Annotated[
        Optional[str],
        Field(None, description="Only return payment methods for this customer ID."),
        Query(),
    ]
    allow_redisplay: Annotated[
        Optional[AllowRedisplay],
        Field(None, description=_REDISPLAY_DESCRIPTION),
        Query(),
    ]


class PaymentMethodsRetrieveRequest(_PaymentMethodId):
    """Input schema for Stripe `GET /v1/payment_methods/{payment_method}`.

    For a method attached to a customer, prefer the customer-scoped retrieve.

    API Reference: https://docs.stripe.com/api/payment_methods/retrieve
    """


class PaymentMethodsAttachRequest(_PaymentMethodId):
    """Input schema for Stripe `POST /v1/payment_methods/{payment_method}/attach`.

    Stripe marks `customer` optional because `customer_account` is an alternative
    spelling of the same idea, which this pack does not model. Attaching to nobody
    is not a thing, so here it is required: it is required for every call this tool
    can make.

    API Reference: https://docs.stripe.com/api/payment_methods/attach
    """

    customer: Annotated[
        str,
        Field(..., description="The ID of the customer to attach this method to."),
        Body(),
    ]


class PaymentMethodsDetachRequest(_PaymentMethodId):
    """Input schema for Stripe `POST /v1/payment_methods/{payment_method}/detach`.

    Detaching is permanent. The method can no longer be charged and cannot be
    reattached to a customer.

    API Reference: https://docs.stripe.com/api/payment_methods/detach
    """


class CustomerPaymentMethodsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/customers/{customer}/payment_methods`.

    API Reference: https://docs.stripe.com/api/payment_methods/customer_list
    """

    customer: Annotated[
        str,
        Field(..., description="The ID of the customer whose methods to list."),
        Path(),
    ]
    type: Annotated[Optional[str], Field(None, description=_TYPE_DESCRIPTION), Query()]
    allow_redisplay: Annotated[
        Optional[AllowRedisplay],
        Field(None, description=_REDISPLAY_DESCRIPTION),
        Query(),
    ]


class CustomerPaymentMethodRetrieveRequest(_PaymentMethodId):
    """Input schema for `GET /v1/customers/{customer}/payment_methods/{payment_method}`.

    API Reference: https://docs.stripe.com/api/payment_methods/customer
    """

    customer: Annotated[
        str,
        Field(..., description="The ID of the customer the method belongs to."),
        Path(),
    ]
