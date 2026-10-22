"""Put each rule on its field instead of in the system prompt, and it leaves with the field."""

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter import Body, Gloss, api_key_tool_factory


class CreateRefund(BaseModel):
    charge: Annotated[str, Body()] = Field(description="The identifier of the charge to refund.")
    amount: Annotated[
        Optional[int],
        Body(),
        Gloss("Cents, not dollars: $15.00 is 1500, and 15 is 15 cents."),
    ] = Field(
        None,
        description="A positive integer in the smallest currency unit representing how much "
        "to refund. Defaults to the entire charge.",
    )
    reason: Annotated[
        Optional[Literal["duplicate", "fraudulent", "requested_by_customer"]],
        Body(),
        Gloss("Only fraudulent when the customer says the charge wasn't theirs."),
    ] = Field(None, description="String indicating the reason for the refund.")


stripe = api_key_tool_factory(
    pack="stripe",
    base_url="https://api.stripe.com/",
    api_key_headers={"Authorization": "Bearer sk_test_..."},
    body_format="form",
)
refund = stripe(
    name="refunds_create",
    description="Refund a charge.",
    method="POST",
    url_template="v1/refunds",
    args_schema=CreateRefund,
)

amount = refund.to_json_schema()["parameters"]["properties"]["amount"]
print("the model reads on amount:", amount["description"])
# the model reads on amount: A positive integer in the smallest currency unit representing how
# much to refund. Defaults to the entire charge. Cents, not dollars: $15.00 is 1500, and 15 is
# 15 cents.
#
# Stripe's own words first, then your Gloss, on the field it's about.

refund_in_full = refund.derived(name="refund_in_full", drop={"amount"})
fields_left = list(refund_in_full.to_json_schema()["parameters"]["properties"])
print("cut amount, and its rule leaves too:", fields_left)
# cut amount, and its rule leaves too: ['charge', 'reason']
#
# Written in the system prompt, "amounts are in cents" would stay behind after the cut,
# a rule about a field the model no longer has.
