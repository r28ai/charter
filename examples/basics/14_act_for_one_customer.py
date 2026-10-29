"""Act for one customer: your app says whose account each call is for, and the model can't change it.

httpbin.org stands in for your API: it echoes back the request it received.
"""

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from charter import (
    ContextError,
    FromContext,
    Path,
    Query,
    ToolValidationError,
    api_key_tool_factory,
    format_egress_map,
)

OWNERS = {"ord_1": "cus_42", "ord_2": "cus_7"}  # who owns what, from your database


class GetOrder(BaseModel):
    order_id: Annotated[str, Path()] = Field(description="The order.")
    customer_id: Annotated[str, Query(), FromContext()]  # set by your app, and sent

    @model_validator(mode="after")
    def _their_own(self) -> "GetOrder":
        if OWNERS.get(self.order_id) != self.customer_id:
            raise ValueError("That order belongs to another customer.")
        return self


shop = api_key_tool_factory(
    pack="shop",
    base_url="https://httpbin.org/anything/",
    api_key_headers={"Authorization": "Bearer sk_demo"},
)
get_order = shop(
    name="orders_get",
    description="Get one of the customer's orders.",
    method="GET",
    url_template="v1/orders/{order_id}",
    args_schema=GetOrder,
)

me = {"customer_id": "cus_42"}  # from your session, never from the model

print("sent       ", get_order.invoke({"order_id": "ord_1"}, context=me)["url"])
# sent        https://httpbin.org/anything/v1/orders/ord_1?customer_id=cus_42

try:
    get_order.invoke({"order_id": "ord_2"}, context=me)
except ToolValidationError as refused:
    print("refused    ", refused.errors[0]["msg"])
# refused     Value error, That order belongs to another customer.

try:
    get_order.invoke({"order_id": "ord_1"})
except ContextError as missing:
    print("no context ", f"your app didn't pass {missing.key!r}")
# no context  your app didn't pass 'customer_id'

print(format_egress_map([get_order]))
# shop_orders_get  (GET v1/orders/{order_id})
#   visible to the model (1):
#     + order_id
#   withheld (1):
#     - customer_id  [context] <- context['customer_id']
