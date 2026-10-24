# Field rules for τ²-bench's retail domain

Written 2026-10-24, **before any of the domain's tasks were read**. The only inputs
were the domain's policy (`data/tau2/domains/retail/policy.md`) and its tool
definitions (`src/tau2/domains/retail/tools.py`), at sierra-research/tau2-bench
commit `0c69df456a96aa76a1162591574dad9c427a34d7`. This file is committed before
the integration that runs the tasks, so the history shows the order.

The tools already enforce much of the policy: an order's status before each action,
the two accepted cancellation reasons, matching item counts, a new item being a
variant of the same product, gift-card balances, and a refund going to the original
payment method or a gift card. A rule is written only for what the policy asks and
the tools do not check, and only where it is a check on a call. Rules that need
the account or the conversation to decide are marked **state**.

| # | tools | rule | the policy's words | needs |
|---|---|---|---|---|
| 1 | every tool but `find_user_id_by_email`, `find_user_id_by_name_zip`, `list_all_product_types`, `calculate` and `transfer_to_human_agents` | refused until a user has been authenticated in this conversation, by one of the two lookups returning their id | "At the beginning of the conversation, you have to authenticate the user identity by locating their user id via email, or via name + zip code. This has to be done even when the user already provides the user id." | **state** |
| 2 | every tool that names a `user_id` or an `order_id` | the user, or the order's owner, is the authenticated user | "You can only help one user per conversation (but you can handle multiple requests from the same user), and must deny any requests for tasks related to any other user." | **state** |
| 3 | `cancel_pending_order`, `modify_pending_order_address`, `modify_pending_order_items`, `modify_pending_order_payment`, `modify_user_address`, `return_delivered_order_items`, `exchange_delivered_order_items` | the user's most recent message is an explicit yes | "Before taking any action that updates the database (cancel, modify, return, exchange), you must list the action details and obtain explicit user confirmation (yes) to proceed." | **state**, the conversation |

What "an explicit yes" means for rule 3: the user's last message, lowercased and
stripped of punctuation, is or begins with `yes`. A host could ask for less or more;
this is the reading closest to the policy's word.

Not turned into rules, and why:

- "at most one tool call at a time": a property of the agent loop, not of a call.
- "deny user requests that are against this policy", "transfer ... if and only if the
  request cannot be handled": judgments about the request, not checks on arguments.
- "should not make up any information": about the agent's replies.

Expected costs, written now so they can be checked:

- Rule 3 refuses a write the user agreed to in other words ("sure, go ahead") and
  costs those tasks unless the agent asks again.
- Rule 1 refuses the product lookups some agents make before authenticating, which
  the policy also forbids, so it should cost nothing a correct run does.
