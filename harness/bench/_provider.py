"""Is the model provider refusing every call because of the account, not this call?

When credits run out mid-run, every later request fails the same way, so a runner
should stop scheduling, keep what it has, and say how to resume. It must never
record such a failure as a result: the agent never ran.

Deliberately narrow, like ``charter_harness.report.provider_outage``: only states
of the account. A 429 or a 5xx is transient and is retried where it happens; a
400 is about the request.
"""

from __future__ import annotations

import re

_ACCOUNT_CODES = (401, 402, 412)
_CODE = re.compile(r"\b(?:Error code: |Client error ')(\d{3})\b")
_WORDS = ("suspended", "spending limit", "insufficient credit", "billing", "quota exceeded")


def out_of_credit(error: object) -> bool:
    """True when ``error`` (an exception or its message) says the account cannot be served."""
    text = str(error or "")
    match = _CODE.search(text)
    if match and int(match.group(1)) in _ACCOUNT_CODES:
        return True
    lowered = text.lower()
    # bench/claude_provider.py, when the Claude subscription it runs on is out of quota.
    # Its 402 reaches some callers (litellm) without the code in the text.
    if "claude subscription limit" in lowered:
        return True
    # Fireworks, through litellm, on 2026-10-24: no status code in the text at all,
    # only "Account ... is suspended, possibly due to reaching the monthly spending
    # limit", and the code PRECONDITION_FAILED.
    if "account" in lowered and "is suspended" in lowered:
        return True
    return any(word in lowered for word in _WORDS) and "403" in text
