"""
Stripe — fifty-nine tools over the Stripe API.

    from charter.packs import stripe

    stripe.configure(api_key="sk_test_...")
    await stripe.customers_create.ainvoke(email="ada@example.com", name="Ada Lovelace")

``configure()`` is optional if ``$STRIPE_API_KEY`` is set. Prefer a
`restricted key <https://docs.stripe.com/keys/restricted-api-keys>`_ scoped to
what the agent actually needs.

Stripe is the pack that exercises the wire contract hardest:

**Form-encoded, not JSON.** Stripe speaks
``application/x-www-form-urlencoded`` with bracket notation, in both directions.
``body_format="form"`` and ``query_format="bracket"`` say so once, and a nested
schema serialises the way Stripe expects —
``line_items[0][price]=price_x&line_items[0][quantity]=2``.

**Its cursor is derived, not returned.** Where Slack and Google hand back an
opaque token, Stripe's ``starting_after`` takes the *last object's id*. The
pagination declaration reads ``data[-1].id`` for exactly that.

**No envelope.** Unlike Slack, Stripe uses real HTTP status codes and puts the
detail in ``error.message``, which the runtime already understands. Nothing to
declare — worth saying out loud, because the right amount of configuration for a
well-behaved API is none.

**The API version is pinned.** Stripe otherwise serves each account its own
default version, set in a dashboard this library cannot see — so the same code
answers differently for two callers, and a schema written against one of them is
right by luck. :data:`API_VERSION` goes out as ``Stripe-Version`` on every
request, which makes this pack's behaviour a property of this file. The
alternative is not "the latest version"; it is "whichever version the account
was created under", and Stripe moves fields between major releases:
``current_period_start`` and ``current_period_end`` left the Subscription object
for its items, and the handler that reads them had to move with it.

**Idempotency and Connect go through the per-call header channel.** Both are
values the host application decides, never the model, so they are passed at the
call site rather than declared on the tool::

    key = f"refund-{order_id}"        # yours, and stable across your retries
    await stripe.refunds_create.ainvoke(
        {"charge": charge_id}, headers={"Idempotency-Key": key}
    )

    await stripe.balance_retrieve.ainvoke(
        headers={"Stripe-Account": "acct_1032D82eZvKYlo2C"}
    )

Charter never mints the idempotency key. A key generated per call would defeat the
purpose — the point is that your retry sends the same one — and Charter does not own
retries, so it does not own the key.

Known limit, named rather than hidden:

* **Coverage is the documented core, not the whole API.** Stripe's parameter
  surface is enormous — ``checkout.sessions.create`` alone has ~50 parameters with
  deep nesting. These schemas model the commonly-used subset, exactly, rather than
  claiming completeness badly.
"""

from __future__ import annotations

from charter.factories import api_key_tool_factory
from charter.packs._config import DeferredApiKeyHeaders, api_key_headers
from charter.packs.stripe.response_handlers import (
    trim_accounts,
    trim_application_fees,
    trim_balance,
    trim_balance_transactions,
    trim_charges,
    trim_checkout_sessions,
    trim_customers,
    trim_disputes,
    trim_invoice_items,
    trim_invoices,
    trim_line_items,
    trim_payment_intents,
    trim_payment_methods,
    trim_payouts,
    trim_prices,
    trim_products,
    trim_refunds,
    trim_subscriptions,
    trim_transfers,
)
from charter.packs.stripe.types import (
    AccountsListRequest,
    AccountsRetrieveRequest,
    ApplicationFeesListRequest,
    BalanceRetrieveRequest,
    BalanceTransactionsListRequest,
    ChargesListRequest,
    ChargesRetrieveRequest,
    CheckoutSessionsCreateRequest,
    CheckoutSessionsLineItemsRequest,
    CheckoutSessionsListRequest,
    CheckoutSessionsRetrieveRequest,
    CustomerPaymentMethodRetrieveRequest,
    CustomerPaymentMethodsListRequest,
    CustomersCreateRequest,
    CustomersListRequest,
    CustomersRetrieveRequest,
    CustomersUpdateRequest,
    DisputesCloseRequest,
    DisputesListRequest,
    DisputesRetrieveRequest,
    DisputesUpdateRequest,
    InvoiceItemsCreateRequest,
    InvoiceItemsDeleteRequest,
    InvoiceItemsListRequest,
    InvoiceItemsUpdateRequest,
    InvoicesCreateRequest,
    InvoicesFinalizeRequest,
    InvoicesListRequest,
    InvoicesMarkUncollectibleRequest,
    InvoicesRetrieveRequest,
    InvoicesSendRequest,
    InvoicesUpdateRequest,
    InvoicesVoidRequest,
    PaymentIntentsCancelRequest,
    PaymentIntentsCaptureRequest,
    PaymentIntentsCreateRequest,
    PaymentIntentsListRequest,
    PaymentIntentsRetrieveRequest,
    PaymentMethodsAttachRequest,
    PaymentMethodsDetachRequest,
    PaymentMethodsListRequest,
    PaymentMethodsRetrieveRequest,
    PayoutsListRequest,
    PayoutsRetrieveRequest,
    PricesCreateRequest,
    PricesListRequest,
    PricesUpdateRequest,
    ProductsCreateRequest,
    ProductsListRequest,
    ProductsUpdateRequest,
    RefundsCreateRequest,
    RefundsListRequest,
    RefundsRetrieveRequest,
    SubscriptionsCancelRequest,
    SubscriptionsCreateRequest,
    SubscriptionsListRequest,
    SubscriptionsUpdateRequest,
    TransfersListRequest,
    TransfersRetrieveRequest,
)
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://api.stripe.com/"
QUOTA_DOC_URL = "https://docs.stripe.com/rate-limits"

# The Stripe release these schemas and handlers were written against. Stripe
# names major releases and dates every one; an unpinned request uses the
# account's own default instead, which is a property of the account rather than
# of this code. https://docs.stripe.com/api/versioning
API_VERSION = "2026-08-26.dahlia"

# Sent verbatim on every request, alongside the key the caller configures.
STRIPE_HEADERS = {"Stripe-Version": API_VERSION}

# Stripe's cursor is the id of the last object in the page, not a token it hands
# back. https://docs.stripe.com/api/pagination
STRIPE_PAGINATION = Pagination(
    cursor_field="data[-1].id",
    cursor_param="starting_after",
    more_field="has_more",
)

_headers: DeferredApiKeyHeaders = api_key_headers(
    "stripe",
    {"Authorization": "Bearer CHARTER_UNCONFIGURED"},
    "Authorization",
    "STRIPE_API_KEY",
)


def configure(api_key: str) -> None:
    """Supply the Stripe secret or restricted key for this pack's tools."""
    _headers.configure(api_key)


_stripe = api_key_tool_factory(
    pack="stripe",
    base_url=BASE_URL,
    api_key_headers=_headers,
    # Stripe is snake_case natively, and form-encoded in both directions.
    body_case="snake",
    query_case="snake",
    body_format="form",
    query_format="bracket",
    # Pagination is a property of a list endpoint, not of the API: declaring it
    # on the factory labels every retrieve and write with a cursor parameter
    # they do not accept. It is declared per tool below.
    quota_doc_url=QUOTA_DOC_URL,
    static_headers=STRIPE_HEADERS,
)

# ---------- customers ----------

customers_list = _stripe(
    name="customers_list",
    args_schema=CustomersListRequest,
    method="GET",
    url_template="v1/customers",
    description="List customers, most recently created first. Filter by email to find one.",
    action_label="Lists Stripe customers.",
    response_handler=trim_customers,
    pagination_override=STRIPE_PAGINATION,
)

customers_retrieve = _stripe(
    name="customers_retrieve",
    args_schema=CustomersRetrieveRequest,
    method="GET",
    url_template="v1/customers/{customer}",
    description="Retrieve a single customer by ID.",
    action_label="Looks up a Stripe customer.",
    response_handler=trim_customers,
)

customers_create = _stripe(
    name="customers_create",
    args_schema=CustomersCreateRequest,
    method="POST",
    url_template="v1/customers",
    description="Create a customer.",
    action_label="Creates a Stripe customer.",
    response_handler=trim_customers,
)

customers_update = _stripe(
    name="customers_update",
    args_schema=CustomersUpdateRequest,
    method="POST",
    url_template="v1/customers/{customer}",
    description="Update a customer. Parameters not provided are left unchanged.",
    action_label="Updates a Stripe customer.",
    response_handler=trim_customers,
)

# ---------- payments ----------

payment_intents_list = _stripe(
    name="payment_intents_list",
    args_schema=PaymentIntentsListRequest,
    method="GET",
    url_template="v1/payment_intents",
    description="List PaymentIntents, most recently created first.",
    action_label="Lists Stripe payments.",
    response_handler=trim_payment_intents,
    pagination_override=STRIPE_PAGINATION,
)

payment_intents_retrieve = _stripe(
    name="payment_intents_retrieve",
    args_schema=PaymentIntentsRetrieveRequest,
    method="GET",
    url_template="v1/payment_intents/{payment_intent}",
    description="Retrieve a single PaymentIntent by ID.",
    action_label="Looks up a Stripe payment.",
    response_handler=trim_payment_intents,
)

charges_list = _stripe(
    name="charges_list",
    args_schema=ChargesListRequest,
    method="GET",
    url_template="v1/charges",
    description="List charges, most recently created first.",
    action_label="Lists Stripe charges.",
    response_handler=trim_charges,
    pagination_override=STRIPE_PAGINATION,
)

refunds_create = _stripe(
    name="refunds_create",
    args_schema=RefundsCreateRequest,
    method="POST",
    url_template="v1/refunds",
    description=(
        "Refund a charge. Provide either `charge` or `payment_intent`. Omit `amount` "
        "to refund the full sum."
    ),
    action_label="Issues a Stripe refund.",
    response_handler=trim_refunds,
)

refunds_list = _stripe(
    name="refunds_list",
    args_schema=RefundsListRequest,
    method="GET",
    url_template="v1/refunds",
    description=(
        "List refunds, most recently created first. Filter by charge or payment "
        "intent. Stripe has no status filter here, so check `status` on the results."
    ),
    action_label="Lists Stripe refunds.",
    pagination_override=STRIPE_PAGINATION,
    response_handler=trim_refunds,
)

refunds_retrieve = _stripe(
    name="refunds_retrieve",
    args_schema=RefundsRetrieveRequest,
    method="GET",
    url_template="v1/refunds/{refund}",
    description="Retrieve a single refund by ID, including its current status.",
    action_label="Looks up a Stripe refund.",
    response_handler=trim_refunds,
)

# ---------- catalog and billing ----------

products_list = _stripe(
    name="products_list",
    args_schema=ProductsListRequest,
    method="GET",
    url_template="v1/products",
    description="List products in the catalog.",
    action_label="Lists Stripe products.",
    pagination_override=STRIPE_PAGINATION,
    response_handler=trim_products,
)

prices_list = _stripe(
    name="prices_list",
    args_schema=PricesListRequest,
    method="GET",
    url_template="v1/prices",
    description="List prices. Filter by product to find what a product costs.",
    action_label="Lists Stripe prices.",
    response_handler=trim_prices,
    pagination_override=STRIPE_PAGINATION,
)

subscriptions_list = _stripe(
    name="subscriptions_list",
    args_schema=SubscriptionsListRequest,
    method="GET",
    url_template="v1/subscriptions",
    description="List subscriptions. Filter by customer or status.",
    action_label="Lists Stripe subscriptions.",
    response_handler=trim_subscriptions,
    pagination_override=STRIPE_PAGINATION,
)

subscriptions_create = _stripe(
    name="subscriptions_create",
    args_schema=SubscriptionsCreateRequest,
    method="POST",
    url_template="v1/subscriptions",
    description=(
        "Subscribe a customer to one or more prices. `items` is required. If the "
        "first payment fails the subscription is still created, with status "
        "'incomplete'."
    ),
    action_label="Creates a Stripe subscription.",
    response_handler=trim_subscriptions,
)

subscriptions_update = _stripe(
    name="subscriptions_update",
    args_schema=SubscriptionsUpdateRequest,
    method="POST",
    url_template="v1/subscriptions/{subscription}",
    description=(
        "Update a subscription. Parameters not provided are left unchanged. To "
        "change an item send its `id`; omitting the `id` adds a new item instead."
    ),
    action_label="Updates a Stripe subscription.",
    response_handler=trim_subscriptions,
)

subscriptions_cancel = _stripe(
    name="subscriptions_cancel",
    args_schema=SubscriptionsCancelRequest,
    method="DELETE",
    url_template="v1/subscriptions/{subscription}",
    description=(
        "Cancel a subscription immediately. To stop it at the end of the period "
        "instead, update it with `cancel_at_period_end` rather than cancelling here."
    ),
    action_label="Cancels a Stripe subscription.",
    response_handler=trim_subscriptions,
)

# ---------- invoices ----------

invoices_list = _stripe(
    name="invoices_list", args_schema=InvoicesListRequest, method="GET",
    url_template="v1/invoices",
    description="List invoices, most recently created first. Filter by customer, subscription, status or collection method.",
    action_label="Lists Stripe invoices.",
    response_handler=trim_invoices, pagination_override=STRIPE_PAGINATION,
)

invoices_retrieve = _stripe(
    name="invoices_retrieve", args_schema=InvoicesRetrieveRequest, method="GET",
    url_template="v1/invoices/{invoice}",
    description="Retrieve a single invoice by ID.",
    action_label="Looks up a Stripe invoice.", response_handler=trim_invoices,
)

invoices_create = _stripe(
    name="invoices_create", args_schema=InvoicesCreateRequest, method="POST",
    url_template="v1/invoices",
    description=(
        "Create a draft invoice for a customer. It bills nothing until finalised, so "
        "this is the safe half of invoicing."
    ),
    action_label="Creates a draft Stripe invoice.", response_handler=trim_invoices,
)

invoices_update = _stripe(
    name="invoices_update", args_schema=InvoicesUpdateRequest, method="POST",
    url_template="v1/invoices/{invoice}",
    description=(
        "Update an invoice. Parameters not provided are left unchanged. Monetary "
        "values and the collection method stop being editable once it is finalised."
    ),
    action_label="Updates a Stripe invoice.", response_handler=trim_invoices,
)

invoices_finalize = _stripe(
    name="invoices_finalize", args_schema=InvoicesFinalizeRequest, method="POST",
    url_template="v1/invoices/{invoice}/finalize",
    description=(
        "Finalise a draft invoice, making it open and payable. The amounts stop being "
        "editable at this point."
    ),
    action_label="Finalises a Stripe invoice.", response_handler=trim_invoices,
)

invoices_send = _stripe(
    name="invoices_send", args_schema=InvoicesSendRequest, method="POST",
    url_template="v1/invoices/{invoice}/send",
    description=(
        "Email an invoice to the customer outside the normal schedule. Test mode "
        "sends nothing but still emits the event."
    ),
    action_label="Emails a Stripe invoice to the customer.", response_handler=trim_invoices,
)

invoices_void = _stripe(
    name="invoices_void", args_schema=InvoicesVoidRequest, method="POST",
    url_template="v1/invoices/{invoice}/void",
    description=(
        "Void a finalised invoice. This cannot be undone: correcting it afterwards "
        "means issuing another invoice or a credit note."
    ),
    action_label="Voids a Stripe invoice. This cannot be undone.",
    response_handler=trim_invoices,
)

invoices_mark_uncollectible = _stripe(
    name="invoices_mark_uncollectible", args_schema=InvoicesMarkUncollectibleRequest,
    method="POST", url_template="v1/invoices/{invoice}/mark_uncollectible",
    description=(
        "Record an invoice as bad debt. It refunds nothing and cancels nothing; it "
        "marks the invoice for accounting."
    ),
    action_label="Marks a Stripe invoice uncollectible.", response_handler=trim_invoices,
)

# ---------- payment methods ----------

payment_methods_list = _stripe(
    name="payment_methods_list", args_schema=PaymentMethodsListRequest, method="GET",
    url_template="v1/payment_methods",
    description="List payment methods. Without a type, every type except 'custom' is returned.",
    action_label="Lists Stripe payment methods.",
    response_handler=trim_payment_methods, pagination_override=STRIPE_PAGINATION,
)

payment_methods_retrieve = _stripe(
    name="payment_methods_retrieve", args_schema=PaymentMethodsRetrieveRequest,
    method="GET", url_template="v1/payment_methods/{payment_method}",
    description="Retrieve a payment method by ID.",
    action_label="Looks up a Stripe payment method.", response_handler=trim_payment_methods,
)

payment_methods_attach = _stripe(
    name="payment_methods_attach", args_schema=PaymentMethodsAttachRequest,
    method="POST", url_template="v1/payment_methods/{payment_method}/attach",
    description="Attach a payment method to a customer so it can be charged later.",
    action_label="Attaches a payment method to a Stripe customer.",
    response_handler=trim_payment_methods,
)

payment_methods_detach = _stripe(
    name="payment_methods_detach", args_schema=PaymentMethodsDetachRequest,
    method="POST", url_template="v1/payment_methods/{payment_method}/detach",
    description=(
        "Detach a payment method from its customer. This is permanent: it can no "
        "longer be charged and cannot be reattached."
    ),
    action_label="Detaches a payment method. This cannot be undone.",
    response_handler=trim_payment_methods,
)

customer_payment_methods_list = _stripe(
    name="customer_payment_methods_list", args_schema=CustomerPaymentMethodsListRequest,
    method="GET", url_template="v1/customers/{customer}/payment_methods",
    description="List the payment methods attached to one customer.",
    action_label="Lists a Stripe customer's payment methods.",
    response_handler=trim_payment_methods, pagination_override=STRIPE_PAGINATION,
)

customer_payment_method_retrieve = _stripe(
    name="customer_payment_method_retrieve",
    args_schema=CustomerPaymentMethodRetrieveRequest, method="GET",
    url_template="v1/customers/{customer}/payment_methods/{payment_method}",
    description="Retrieve one payment method belonging to a customer.",
    action_label="Looks up a Stripe customer's payment method.",
    response_handler=trim_payment_methods,
)

# ---------- disputes ----------

disputes_list = _stripe(
    name="disputes_list", args_schema=DisputesListRequest, method="GET",
    url_template="v1/disputes",
    description=(
        "List disputes, most recently created first. Stripe has no status filter "
        "here, so check `status` on the results."
    ),
    action_label="Lists Stripe disputes.",
    response_handler=trim_disputes, pagination_override=STRIPE_PAGINATION,
)

disputes_retrieve = _stripe(
    name="disputes_retrieve", args_schema=DisputesRetrieveRequest, method="GET",
    url_template="v1/disputes/{dispute}",
    description=(
        "Retrieve a dispute by ID. `evidence_details.due_by` is the deadline; "
        "evidence submitted after it is wasted."
    ),
    action_label="Looks up a Stripe dispute.", response_handler=trim_disputes,
)

disputes_update = _stripe(
    name="disputes_update", args_schema=DisputesUpdateRequest, method="POST",
    url_template="v1/disputes/{dispute}",
    description=(
        "Add evidence to a dispute. Writing any evidence field submits every evidence "
        "field to the bank unless `submit` is false, and submission cannot be undone. "
        "Set `submit` to false to stage it for review first."
    ),
    action_label="Submits dispute evidence to the bank.", response_handler=trim_disputes,
)

disputes_close = _stripe(
    name="disputes_close", args_schema=DisputesCloseRequest, method="POST",
    url_template="v1/disputes/{dispute}/close",
    description=(
        "Concede a dispute. The status becomes 'lost', the customer keeps the money, "
        "and it cannot be reopened. Use this only when giving up deliberately."
    ),
    action_label="Concedes a Stripe dispute and forfeits the money. This cannot be undone.",
    response_handler=trim_disputes,
)

# ---------- connect and money movement ----------

accounts_list = _stripe(
    name="accounts_list", args_schema=AccountsListRequest, method="GET",
    url_template="v1/accounts",
    description="List the connected accounts on this platform. Empty if you are not a platform.",
    action_label="Lists Stripe connected accounts.",
    response_handler=trim_accounts, pagination_override=STRIPE_PAGINATION,
)

accounts_retrieve = _stripe(
    name="accounts_retrieve", args_schema=AccountsRetrieveRequest, method="GET",
    url_template="v1/accounts/{account}",
    description="Retrieve a connected account by ID.",
    action_label="Looks up a Stripe connected account.", response_handler=trim_accounts,
)

transfers_list = _stripe(
    name="transfers_list", args_schema=TransfersListRequest, method="GET",
    url_template="v1/transfers",
    description="List transfers to connected accounts, most recently created first.",
    action_label="Lists Stripe transfers.",
    response_handler=trim_transfers, pagination_override=STRIPE_PAGINATION,
)

transfers_retrieve = _stripe(
    name="transfers_retrieve", args_schema=TransfersRetrieveRequest, method="GET",
    url_template="v1/transfers/{transfer}",
    description="Retrieve a transfer by ID.",
    action_label="Looks up a Stripe transfer.", response_handler=trim_transfers,
)

payouts_list = _stripe(
    name="payouts_list", args_schema=PayoutsListRequest, method="GET",
    url_template="v1/payouts",
    description="List payouts to your own bank account or card, most recently created first.",
    action_label="Lists Stripe payouts.",
    response_handler=trim_payouts, pagination_override=STRIPE_PAGINATION,
)

payouts_retrieve = _stripe(
    name="payouts_retrieve", args_schema=PayoutsRetrieveRequest, method="GET",
    url_template="v1/payouts/{payout}",
    description="Retrieve a payout by ID.",
    action_label="Looks up a Stripe payout.", response_handler=trim_payouts,
)

application_fees_list = _stripe(
    name="application_fees_list", args_schema=ApplicationFeesListRequest, method="GET",
    url_template="v1/application_fees",
    description="List the platform fees collected from connected accounts.",
    action_label="Lists Stripe application fees.",
    response_handler=trim_application_fees, pagination_override=STRIPE_PAGINATION,
)

balance_transactions_list = _stripe(
    name="balance_transactions_list", args_schema=BalanceTransactionsListRequest,
    method="GET", url_template="v1/balance_transactions",
    description=(
        "List every movement across the Stripe balance: charges, refunds, fees and "
        "payouts. For accounting, `reporting_category` on each result groups them "
        "better than `type` does."
    ),
    action_label="Lists Stripe balance transactions.",
    response_handler=trim_balance_transactions, pagination_override=STRIPE_PAGINATION,
)


# ---------- checkout ----------

checkout_sessions_create = _stripe(
    name="checkout_sessions_create",
    args_schema=CheckoutSessionsCreateRequest,
    method="POST",
    url_template="v1/checkout/sessions",
    description=(
        "Create a Checkout Session and get a hosted payment URL. Pass `line_items` "
        "with price IDs and quantities, `mode='payment'` for one-time or "
        "`mode='subscription'` for recurring."
    ),
    action_label="Creates a Stripe checkout link.",
    response_handler=trim_checkout_sessions,
)

# ---------- invoice items ----------

invoice_items_create = _stripe(
    name="invoice_items_create", args_schema=InvoiceItemsCreateRequest, method="POST",
    url_template="v1/invoiceitems",
    description=(
        "Add a line to an invoice. Name an existing price as `pricing.price`, or give "
        "an `amount` directly. Without `invoice` the line waits for the customer's "
        "next subscription invoice."
    ),
    action_label="Adds a line to a Stripe invoice.", response_handler=trim_invoice_items,
)

invoice_items_list = _stripe(
    name="invoice_items_list", args_schema=InvoiceItemsListRequest, method="GET",
    url_template="v1/invoiceitems",
    description="List invoice lines. `pending` finds lines not yet on any invoice.",
    action_label="Lists Stripe invoice lines.",
    response_handler=trim_invoice_items, pagination_override=STRIPE_PAGINATION,
)

invoice_items_update = _stripe(
    name="invoice_items_update", args_schema=InvoiceItemsUpdateRequest, method="POST",
    url_template="v1/invoiceitems/{invoiceitem}",
    description=(
        "Update an invoice line. A line cannot be moved to another customer or "
        "another invoice; its `frozen_fields` lists what has stopped being editable."
    ),
    action_label="Updates a Stripe invoice line.", response_handler=trim_invoice_items,
)

invoice_items_delete = _stripe(
    name="invoice_items_delete", args_schema=InvoiceItemsDeleteRequest, method="DELETE",
    url_template="v1/invoiceitems/{invoiceitem}",
    description="Remove an invoice line, while it is unattached or its invoice is a draft.",
    action_label="Deletes a Stripe invoice line.",
)

# ---------- reading a checkout back ----------

checkout_sessions_retrieve = _stripe(
    name="checkout_sessions_retrieve", args_schema=CheckoutSessionsRetrieveRequest,
    method="GET", url_template="v1/checkout/sessions/{session}",
    description=(
        "Retrieve a checkout session. Check `payment_status` as well as `status`: a "
        "complete session has finished, which is not the same as having been paid."
    ),
    action_label="Looks up a Stripe checkout session.",
    response_handler=trim_checkout_sessions,
)

checkout_sessions_list = _stripe(
    name="checkout_sessions_list", args_schema=CheckoutSessionsListRequest, method="GET",
    url_template="v1/checkout/sessions",
    description=(
        "List checkout sessions. Stripe has no payment_status filter, so find paid "
        "ones by reading the results."
    ),
    action_label="Lists Stripe checkout sessions.",
    response_handler=trim_checkout_sessions, pagination_override=STRIPE_PAGINATION,
)

checkout_sessions_line_items = _stripe(
    name="checkout_sessions_line_items", args_schema=CheckoutSessionsLineItemsRequest,
    method="GET", url_template="v1/checkout/sessions/{session}/line_items",
    description="List what a checkout session sold, with amounts and quantities.",
    action_label="Lists what a Stripe checkout sold.",
    response_handler=trim_line_items, pagination_override=STRIPE_PAGINATION,
)

# ---------- catalog writes ----------

products_create = _stripe(
    name="products_create", args_schema=ProductsCreateRequest, method="POST",
    url_template="v1/products",
    description="Create a product. Prices attach to it separately.",
    action_label="Creates a Stripe product.", response_handler=trim_products,
)

products_update = _stripe(
    name="products_update", args_schema=ProductsUpdateRequest, method="POST",
    url_template="v1/products/{id}",
    description=(
        "Update a product. `default_price` names an existing price; a price cannot "
        "be created here."
    ),
    action_label="Updates a Stripe product.", response_handler=trim_products,
)

prices_create = _stripe(
    name="prices_create", args_schema=PricesCreateRequest, method="POST",
    url_template="v1/prices",
    description=(
        "Create a price for a product. Include `recurring` for a subscription price, "
        "omit it for a one-off."
    ),
    action_label="Creates a Stripe price.", response_handler=trim_prices,
)

prices_update = _stripe(
    name="prices_update", args_schema=PricesUpdateRequest, method="POST",
    url_template="v1/prices/{price}",
    description=(
        "Update a price's label, metadata or active flag. What it costs cannot be "
        "changed: to reprice, create a new price and set `active` false on this one."
    ),
    action_label="Updates a Stripe price.", response_handler=trim_prices,
)

# ---------- authorising and capturing ----------

payment_intents_create = _stripe(
    name="payment_intents_create", args_schema=PaymentIntentsCreateRequest,
    method="POST", url_template="v1/payment_intents",
    description=(
        "Start a payment. With `capture_method` set to 'manual' this authorises the "
        "card and holds the funds without taking them, to capture once the order "
        "ships."
    ),
    action_label="Creates a Stripe payment.", response_handler=trim_payment_intents,
)

payment_intents_capture = _stripe(
    name="payment_intents_capture", args_schema=PaymentIntentsCaptureRequest,
    method="POST", url_template="v1/payment_intents/{intent}/capture",
    description=(
        "Take funds previously authorised by a manual-capture payment. Capturing "
        "less than the full amount releases the rest."
    ),
    action_label="Captures an authorised Stripe payment.",
    response_handler=trim_payment_intents,
)

payment_intents_cancel = _stripe(
    name="payment_intents_cancel", args_schema=PaymentIntentsCancelRequest,
    method="POST", url_template="v1/payment_intents/{intent}/cancel",
    description="Cancel a payment, releasing any authorised funds back to the customer.",
    action_label="Cancels a Stripe payment.", response_handler=trim_payment_intents,
)

charges_retrieve = _stripe(
    name="charges_retrieve", args_schema=ChargesRetrieveRequest, method="GET",
    url_template="v1/charges/{charge}",
    description="Retrieve a single charge by ID.",
    action_label="Looks up a Stripe charge.", response_handler=trim_charges,
)


# ---------- account ----------

balance_retrieve = _stripe(
    name="balance_retrieve",
    args_schema=BalanceRetrieveRequest,
    method="GET",
    url_template="v1/balance",
    description="Retrieve the current account balance.",
    action_label="Checks the Stripe balance.",
    response_handler=trim_balance,
)

TOOLS: list[Tool] = [
    customers_list,
    customers_retrieve,
    customers_create,
    customers_update,
    payment_intents_list,
    payment_intents_retrieve,
    charges_list,
    refunds_create,
    refunds_list,
    refunds_retrieve,
    products_list,
    prices_list,
    subscriptions_list,
    subscriptions_create,
    subscriptions_update,
    subscriptions_cancel,
    invoices_list,
    invoices_retrieve,
    invoices_create,
    invoices_update,
    invoices_finalize,
    invoices_send,
    invoices_void,
    invoices_mark_uncollectible,
    invoice_items_create,
    invoice_items_list,
    invoice_items_update,
    invoice_items_delete,
    checkout_sessions_retrieve,
    checkout_sessions_list,
    checkout_sessions_line_items,
    products_create,
    products_update,
    prices_create,
    prices_update,
    payment_intents_create,
    payment_intents_capture,
    payment_intents_cancel,
    charges_retrieve,
    payment_methods_list,
    payment_methods_retrieve,
    payment_methods_attach,
    payment_methods_detach,
    customer_payment_methods_list,
    customer_payment_method_retrieve,
    disputes_list,
    disputes_retrieve,
    disputes_update,
    disputes_close,
    accounts_list,
    accounts_retrieve,
    transfers_list,
    transfers_retrieve,
    payouts_list,
    payouts_retrieve,
    application_fees_list,
    balance_transactions_list,
    checkout_sessions_create,
    balance_retrieve,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "QUOTA_DOC_URL",
    "API_VERSION",
    "STRIPE_HEADERS",
    "STRIPE_PAGINATION",
    "customers_list",
    "customers_retrieve",
    "customers_create",
    "customers_update",
    "payment_intents_list",
    "payment_intents_retrieve",
    "charges_list",
    "refunds_create",
    "products_list",
    "prices_list",
    "subscriptions_list",
    "checkout_sessions_create",
    "balance_retrieve",
]
