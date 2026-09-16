"""
What the agent made, so the guard lets it be unmade.

The guard restricts destructive calls to fixtures the seed created. That rule is
right for the account's real data and wrong for anything the agent produced
during the run: an event it inserted thirty seconds ago is unambiguously safe for
it to delete, and refusing that turns a mistake the agent had already noticed
into permanent state.

Measured. On `sheet_to_calendar` a run wrote three events at the wrong offset,
recognised it, called ``events_delete`` on all three, was refused all three
times, and recreated them correctly — leaving six events where three were
expected, and failing a task it had in fact recovered from. The rule is the same
on every arm, but its cost is not: it is paid only by an agent that tries to
clean up after itself.

So an id that comes back from a creating call is recorded as owned, and the
guard's ``owns`` check then covers it. Ownership is still never assumed: a call
that did not create the thing does not grant it, and nothing here widens what
may be touched beyond what this run itself made.
"""

from __future__ import annotations

import json
import re
from typing import Any

from charter_harness.context import run_context

__all__ = ["record_charter_creation", "record_raw_creation", "CHARTER_CREATORS", "RAW_CREATORS"]

# (pack, charter tool) -> the kind of thing it creates.
#
# Only kinds the guard actually gates need an entry. Gmail threads are absent
# because the agent cannot create one — both ways of sending are withheld — and
# GitHub and Slack are gated on repository and channel rather than on ownership.
CHARTER_CREATORS: dict[tuple[str, str], str] = {
    ("gcalendar", "events_insert"): "gcalendar.event",
}

# (pack, method, path regex) -> the same, for the raw arm, which reaches the
# identical endpoints through a hand-built request.
RAW_CREATORS: list[tuple[str, str, re.Pattern[str], str]] = [
    ("gcalendar", "POST", re.compile(r"^calendar/v3/calendars/[^/]+/events$"), "gcalendar.event"),
]


def _identifier(result: Any) -> str | None:
    """The created object's id, from whatever shape the call returned.

    The Charter arm hands back a decoded object; the raw arm hands back the text
    it showed the model, which may have been truncated. A response that cannot be
    read simply grants nothing — the guard then refuses a delete it would have
    allowed, which is the safe direction to fail.
    """
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return None
    if isinstance(result, dict):
        value = result.get("id")
        if isinstance(value, (str, int)):
            return str(value)
    return None


def record_charter_creation(pack: str | None, tool: str, result: Any) -> None:
    """Record an id the Charter arm just created."""
    kind = CHARTER_CREATORS.get((pack or "", tool))
    if kind is None:
        return
    identifier = _identifier(result)
    if identifier:
        run_context().own(kind, identifier)


def record_raw_creation(pack: str, method: str, path: str, result: Any) -> None:
    """Record an id the raw arm just created."""
    for owner_pack, owner_method, pattern, kind in RAW_CREATORS:
        if pack == owner_pack and method == owner_method and pattern.match(path):
            identifier = _identifier(result)
            if identifier:
                run_context().own(kind, identifier)
            return
