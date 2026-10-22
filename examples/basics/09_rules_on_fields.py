"""Put each rule on its field instead of in the system prompt, and it leaves with the field."""

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter import Body, Gloss, api_key_tool_factory

SYSTEM_PROMPT = """You handle refunds.
- Stripe amounts are in cents: $15.00 is 1500.
- Only use reason=fraudulent when the customer says the charge wasn't theirs."""


class CreateRefund(BaseModel):
    charge: Annotated[str, Body()] = Field(description="The identifier of the charge to refund.")
    amount: Annotated[
        Optional[int], Body(), Gloss("Cents, not dollars: $15.00 is 1500, and 15 is 15 cents.")
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


def rules_on(tool) -> None:
    """What the model reads on each field after Stripe's own description: the Gloss."""
    for name, field in tool.to_json_schema()["parameters"]["properties"].items():
        stripes = CreateRefund.model_fields[name].description or ""
        if rule := field["description"].removeprefix(stripes).strip():
            print(f"  {name:7} {rule}")


print("before, in the system prompt:")
print(*(f"  {line}" for line in SYSTEM_PROMPT.splitlines()[1:]), sep="\n")
print("\nafter, on each field, right after Stripe's own description:")
rules_on(refund)
print("\ncut amount, and its rule leaves with it:")
rules_on(refund.derived(name="refund_in_full", drop={"amount"}))
print("while the system prompt would still say:", SYSTEM_PROMPT.splitlines()[1][2:])
# before, in the system prompt:
#   - Stripe amounts are in cents: $15.00 is 1500.
#   - Only use reason=fraudulent when the customer says the charge wasn't theirs.
#
# after, on each field, right after Stripe's own description:
#   amount  Cents, not dollars: $15.00 is 1500, and 15 is 15 cents.
#   reason  Only fraudulent when the customer says the charge wasn't theirs.
#
# cut amount, and its rule leaves with it:
#   reason  Only fraudulent when the customer says the charge wasn't theirs.
# while the system prompt would still say: Stripe amounts are in cents: $15.00 is 1500.
