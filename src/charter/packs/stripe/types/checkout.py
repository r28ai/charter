"""Request schema for Stripe Checkout Sessions.

The flagship nested-form case: `line_items` becomes
``line_items[0][price]=price_xxx&line_items[0][quantity]=2`` on the wire.

API Reference: https://docs.stripe.com/api/checkout/sessions/create
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Body, Gloss

__all__ = ["CheckoutMode", "UiMode", "LineItem", "CheckoutSessionsCreateRequest"]

CheckoutMode = Literal["payment", "setup", "subscription"]
UiMode = Literal["hosted_page", "embedded_page", "form", "elements"]

# The UI modes Checkout renders inside your own page. All of them refuse the
# redirect URLs, because there is no redirect: the customer never leaves.
# `form` belongs here as much as the other two — verified against the live API,
# which answers 400 "not supported with `ui_mode: form`" for either URL.
_IN_PAGE_UI_MODES = ("embedded_page", "elements", "form")


class LineItem(BaseModel):
    """One item the customer is purchasing.

    API Reference: https://docs.stripe.com/api/checkout/sessions/create
    """

    price: Optional[str] = Field(
        None, description="The ID of the Price object, e.g. 'price_1MotwRLkd...'."
    )
    quantity: Optional[int] = Field(
        None,
        ge=0,
        description="The quantity of the line item being purchased.",
    )


class CheckoutSessionsCreateRequest(BaseModel):
    """Input schema for Stripe `POST /v1/checkout/sessions`.

    API Reference: https://docs.stripe.com/api/checkout/sessions/create
    """

    mode: Annotated[
        CheckoutMode,
        Field(
            ...,
            description=(
                "The mode of the Checkout Session. Pass 'subscription' if the session "
                "includes at least one recurring item, 'payment' for one-time payments, "
                "'setup' to save payment details for later."
            ),
        ),
        Body(),
    ]
    line_items: Annotated[
        Optional[List[LineItem]],
        Field(
            None,
            description=(
                "A list of items the customer is purchasing. Required for 'payment' and "
                "'subscription' mode."
            ),
        ),
        Body(),
    ]
    success_url: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The URL to send customers to when payment or setup is complete. "
                "Required for the default hosted flow, and not allowed if ui_mode is "
                "'embedded_page', 'elements' or 'form'."
            ),
        ),
        Body(),
    ]
    cancel_url: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "If set, Checkout displays a back button and sends customers here if "
                "they cancel."
            ),
        ),
        Body(),
    ]
    customer: Annotated[
        Optional[str],
        Field(None, description="ID of an existing Customer, if one exists."),
        Body(),
    ]
    customer_email: Annotated[
        Optional[str],
        Field(
            None,
            max_length=800,
            description=(
                "Prefills the customer's email. If not provided, customers are asked to "
                "enter it."
            ),
        ),
        Body(),
    ]
    client_reference_id: Annotated[
        Optional[str],
        Field(
            None,
            max_length=200,
            description=(
                "A unique string to reference the Checkout Session — a customer ID, a "
                "cart ID — used to reconcile the session with your own systems."
            ),
        ),
        Body(),
    ]
    currency: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Three-letter ISO currency code, in lowercase. Required in 'setup' mode "
                "when payment_method_types is not set."
            ),
        ),
        Body(),
    ]
    expires_at: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "The Epoch time in seconds at which the session expires. Between 30 "
                "minutes and 24 hours after creation; defaults to 24 hours."
            ),
        ),
        Gloss("Seconds, not milliseconds: 1700000000, not 1700000000000."),
        Body(),
    ]
    allow_promotion_codes: Annotated[
        Optional[bool],
        Field(None, description="Enables user-redeemable promotion codes."),
        Body(),
    ]
    ui_mode: Annotated[
        Optional[UiMode],
        Field(None, description="The UI mode of the session. Defaults to 'hosted_page'."),
        Body(),
    ]
    return_url: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Where to send the customer after they authenticate or cancel. Required "
                "if ui_mode is 'embedded_page', 'elements' or 'form' with "
                "redirect-based methods."
            ),
        ),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the session."),
        Body(),
    ]

    @model_validator(mode="after")
    def _mode_and_ui_mode_agree(self) -> CheckoutSessionsCreateRequest:
        """The three rules Checkout states outright, checked before the round trip.

        Each of these is a 400 with a message the model then has to interpret and
        retry against — and a Checkout Session is usually created in front of a
        waiting customer, so the retry is expensive in a way a background call is
        not.

        Conditions that depend on parameters this schema does not model are left
        to Stripe and named in the field descriptions instead: ``return_url`` is
        required for the in-page modes only when redirect-based payment methods
        are enabled on the session, which is not visible from here.
        """
        if self.mode in ("payment", "subscription") and not self.line_items:
            raise ValueError(
                f"`line_items` is required in '{self.mode}' mode — it is what the "
                "customer is being charged for. Pass price IDs and quantities."
            )
        if self.mode == "setup" and self.currency is None:
            raise ValueError(
                "`currency` is required in 'setup' mode, where there is no line item "
                "to take it from."
            )
        if self.ui_mode in _IN_PAGE_UI_MODES:
            offending = [
                name
                for name in ("success_url", "cancel_url")
                if getattr(self, name) is not None
            ]
            if offending:
                raise ValueError(
                    f"{' and '.join('`' + n + '`' for n in offending)} cannot be set "
                    f"when ui_mode is '{self.ui_mode}': the customer stays on your "
                    "page, so there is nowhere to redirect them. Use `return_url`."
                )
        return self
