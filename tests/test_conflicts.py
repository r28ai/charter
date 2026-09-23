"""
The exclusion rules a pack declares, read back.

`ConflictsWith` puts each rule on the field it is about, which is the right place
to declare one and the wrong place to read the set of them. The list form it
replaced was better at exactly this — eight names in one block — so the report
has to give that back, reconstructed from the declarations the runtime enforces
rather than maintained beside them.
"""

from __future__ import annotations

from typing import Annotated, Optional

import pytest
from pydantic import BaseModel, Field

from charter import ConflictsWith, Query, WireName, conflict_map, format_conflicts
from charter.factories import api_key_tool_factory
from charter.packs import gcalendar, gmail


def _tool(schema):
    factory = api_key_tool_factory(base_url="https://x.test/", pack="t", api_key_headers={"k": "v"})
    return factory(
        name="listing", args_schema=schema, method="GET", url_template="go", description="d"
    )


class _Listing(BaseModel):
    sync_token: Annotated[Optional[str], Field(None), Query()]
    i_cal_uid: Annotated[
        Optional[str],
        Field(None),
        Query(),
        WireName("iCalUID"),
        ConflictsWith("sync_token", reason="Continue the sync or start a new query."),
    ]
    time_min: Annotated[Optional[str], Field(None), Query(), ConflictsWith("sync_token")]
    harmless: Annotated[Optional[str], Field(None), Query()]


def test_the_map_reports_each_rule_with_both_halves_named_as_the_api_names_them():
    report = conflict_map([_tool(_Listing)])
    rules = {r["field"]: r for r in report["t__listing"]}
    assert set(rules) == {"i_cal_uid", "time_min"}
    assert rules["i_cal_uid"]["api_name"] == "iCalUID"
    assert rules["i_cal_uid"]["excludes"] == [
        {"field": "sync_token", "api_name": "syncToken", "declared": True}
    ]
    assert rules["i_cal_uid"]["reason"].startswith("Continue the sync")


def test_a_tool_with_no_rules_is_absent():
    assert conflict_map(gmail.TOOLS) == {}
    assert format_conflicts(gmail.TOOLS) == "no exclusion rules declared"


def test_the_rendering_groups_by_what_is_excluded():
    """The question is "what does syncToken refuse", not "what does iCalUID
    refuse" — one line per rule with its parameters beside it, which is the shape
    the hand-kept list had and the markers took away."""
    rendered = format_conflicts([_tool(_Listing)])
    assert "syncToken refuses 2:" in rendered
    assert "- iCalUID" in rendered and "- timeMin" in rendered
    assert "why: Continue the sync" in rendered


def test_a_rule_that_can_never_fire_is_reported():
    """A conflict may name a field the schema does not declare, and then it
    silently never fires. Surfaced rather than resolved: this is the defect the
    report exists to find."""

    class Broken(BaseModel):
        a: Annotated[Optional[str], Field(None), Query(), ConflictsWith("typo_not_a_field")]

    report = conflict_map([_tool(Broken)])
    assert report["t__listing"][0]["excludes"][0]["declared"] is False
    assert "NOT A FIELD OF THIS SCHEMA" in format_conflicts([_tool(Broken)])


def test_the_shipped_calendar_rules_read_back_whole():
    """Ten declarations across two tools, and the documentation says four rules —
    two exclusions here and two "may not be False" that stay validators."""
    report = conflict_map(gcalendar.TOOLS)
    assert set(report) == {"gcalendar__events_list", "gcalendar__calendar_list_list"}
    assert len(report["gcalendar__events_list"]) == 8
    assert len(report["gcalendar__calendar_list_list"]) == 2
    assert all(
        e["api_name"] == "syncToken"
        for rules in report.values()
        for r in rules
        for e in r["excludes"]
    )


def test_a_surface_of_several_packs_keeps_every_rule():
    """The sibling artifact had the same defect, latent rather than firing.

    `conflict_map` keyed on the bare name too. Only three shipped tools declare
    a conflict, so nothing collided yet and nothing would have said so when it
    did. Keyed and guarded the same way now, because the two maps make the same
    promise to the same reader.
    """
    from charter import report_key
    from charter.packs import gcalendar, gdrive, notion

    tools = [*gcalendar.TOOLS, *gdrive.TOOLS, *notion.TOOLS]
    report = conflict_map(tools)
    assert set(report) <= {report_key(t) for t in tools}
    assert "gcalendar__events_list" in report


def test_two_tools_that_would_share_a_row_raise_rather_than_overwrite():
    from charter.types.errors import DeclarationError

    factory = api_key_tool_factory(
        pack="conflicts", base_url="https://x.test/", api_key_headers={"k": "v"}
    )
    pair = [
        factory(name="dup", args_schema=_Listing, method="GET", url_template="go", description="d")
        for _ in range(2)
    ]
    with pytest.raises(DeclarationError, match="Two tools report under 'conflicts__dup'"):
        conflict_map(pair)
