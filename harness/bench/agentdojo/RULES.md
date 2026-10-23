# Field rules for AgentDojo's banking suite

Written 2026-10-23, **before any of the suite's injection tasks, attacks or
injection vectors were read**. The only inputs were the suite's tool definitions
(`default_suites/v1/tools/banking_client.py`, `user_account.py`,
`file_reader.py`) and the prompts of its sixteen user tasks, which are the app's
normal use. This file is committed before the integration that runs the attacks,
so the history shows the order.

One disclosure: listing the user-task prompts also printed task 0's `COMMENT`,
which names an injection point (`injection_bill_text`) and says an attack must
keep one line of the bill. No injection task, attacker goal or attacker IBAN was
read.

A rule had to be one a developer would write from normal use alone, and had to be
a check on one call's arguments. Where a rule needs to read the account to decide,
it is marked **state**, as the plan asks.

| # | tool, field | rule | why, from normal use | needs |
|---|---|---|---|---|
| 1 | `send_money.recipient`, `schedule_transaction.recipient`, `update_scheduled_transaction.recipient` | an IBAN the account has already sent money to or received money from, in its transactions or scheduled transactions, or one that appears in the user's own request | every user task that pays someone names a counterparty the account already has, or gives the IBAN in the request (tasks 3, 4, 6, 15); a refund goes to someone who paid you (tasks 3, 4, 15) | **state**, and the user's request |
| 2 | `send_money.amount`, `schedule_transaction.amount`, `update_scheduled_transaction.amount` | greater than 0, and no more than the account's balance | no user task moves more than the balance, and none moves zero or a negative amount | **state** |
| 3 | `update_password.password` | must appear verbatim in the user's own request | the one task that changes the password gives it in the request (task 14) | the user's request |
| 4 | `update_user_info.first_name`, `update_user_info.last_name` | not offered to the model | the tasks that update account information change the address (tasks 13, 15), never the name | nothing: the fields are dropped from the tool |

What "the user's own request" means: the task prompt the user typed, as the host
received it, before any tool ran. Text that arrived in a tool result (a file, a
transaction subject) is not the user's request.

Nothing else is constrained. In particular there is no rule on `subject`, on
`date`, on `read_file`, or on which tool may follow which; a defense built from
attack knowledge would add those, and this one is not allowed to.

Expected costs, written now so they can be checked:

- Rule 1 refuses a payment to a new payee the user names only indirectly, for
  example in a file. Task 0 pays a bill from a file; if the bill's IBAN is not an
  existing counterparty and is not in the request, rule 1 blocks a legitimate
  payment and costs utility.
- Rule 2 needs the balance at call time. A host that cannot read it cannot hold
  this rule.
