"""Shared request pieces for the Linear pack.

Three things recur across every domain in Linear's API, so they are declared
once here rather than repeated on forty schemas:

**The comparators.** Linear filters are built from a comparator object per
field — ``{"title": {"containsIgnoreCase": "flake"}}`` — and the same handful of
comparator types are reused for every string, id, number, date and boolean in
the schema. They are modelled in full: a comparator missing an operator the API
accepts rejects a filter the model was right to write, and the model cannot tell
that from Linear refusing it.

**The Relay page arguments.** Every connection in Linear takes the same
``first``/``after`` pair. See :data:`~charter.packs.linear.LINEAR_PAGINATION`
for the cursor that reads them back.

**The priority scale.** An integer on the wire, and meaningless without the
mapping Linear documents for it.

API Reference: https://linear.app/developers/filtering
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

__all__ = [
    "StringComparator",
    "ContentComparator",
    "RelationExistsComparator",
    "EstimateComparator",
    "SlaStatusComparator",
    "CyclePeriodComparator",
    "TeamVisibilityComparator",
    "Day",
    "FrequencyResolutionType",
    "InitiativeTab",
    "ProjectTab",
    "PipelineTab",
    "TeamVisibility",
    "SlaStatus",
    "CyclePeriod",
    "DurationComparator",
    "NullableStringComparator",
    "IdComparator",
    "NumberComparator",
    "NullableNumberComparator",
    "DateComparator",
    "NullableDateComparator",
    "BooleanComparator",
    "PageVariables",
    "Priority",
    "PRIORITY_DESCRIPTION",
    "PaginationOrderBy",
    "SlaDayCountType",
    "ReleasePipelineType",
    "ReleaseStageType",
    "NullableTimelessDateComparator",
    "SubTypeComparator",
    "WorkflowDefinitionIdComparator",
    "SourceMetadataComparator",
    "ReleasePipelineTypeComparator",
    "ReleaseStageTypeComparator",
    "JSONObject",
]


# Linear's priority scale, which is an integer on the wire and meaningless
# without this mapping. The wording is Linear's own: the SDL documents 3 as
# "Medium", not "Normal".
# https://linear.app/developers/filtering
Priority = Literal[0, 1, 2, 3, 4]
PRIORITY_DESCRIPTION = (
    "The priority of the issue. 0 = No priority, 1 = Urgent, 2 = High, "
    "3 = Medium, 4 = Low."
)

PaginationOrderBy = Literal["createdAt", "updatedAt"]
"""Which timestamp a connection is ordered by. Linear orders by ``updatedAt``
when the argument is absent."""

SlaDayCountType = Literal["all", "onlyBusinessDays"]
"""Whether an SLA counts calendar days or business days only."""

Day = Literal[
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]
"""A day of the week, capitalised the way Linear's enum spells it."""

FrequencyResolutionType = Literal["daily", "weekly"]
"""The unit an update-reminder frequency is counted in."""

InitiativeTab = Literal["overview", "projects", "updates"]
"""Which tab of an initiative a favorite points at."""

ProjectTab = Literal["customers", "documents", "issues", "loops", "updates"]
"""Which tab of a project a favorite points at."""

PipelineTab = Literal["releaseNotes", "releases"]
"""Which tab of a release pipeline a favorite points at."""

TeamVisibility = Literal["public", "private", "restricted"]
"""Who can see a team."""

SlaStatus = Literal["Breached", "Completed", "Failed", "HighRisk", "LowRisk", "MediumRisk"]
"""Where an issue stands against its SLA."""

CyclePeriod = Literal["after", "before", "during"]
"""When, relative to a cycle, something happened — for example when an issue
was added to one."""

ReleasePipelineType = Literal["continuous", "scheduled"]
"""How a release pipeline produces releases."""

ReleaseStageType = Literal["canceled", "completed", "planned", "started"]
"""Where a release sits in its pipeline."""

# Linear's JSONObject scalar: string and number values, as attachment metadata
# and similar free-form maps use.
JSONObject = Dict[str, Union[str, int, float]]


class StringComparator(BaseModel):
    """String comparators for a Linear filter.

    Comparators on the same object combine with AND. Every operator Linear's
    ``StringComparator`` accepts is here: a closed subset would reject filters
    the API would have honoured.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[str] = Field(None, description="Equals the given value exactly.")
    neq: Optional[str] = Field(None, description="Does not equal the given value.")
    eq_ignore_case: Optional[str] = Field(
        None, description="Equals the given value, ignoring case."
    )
    neq_ignore_case: Optional[str] = Field(
        None, description="Does not equal the given value, ignoring case."
    )
    # `in` is a Python keyword. The trailing underscore is stripped by the
    # camel-case conversion on the way to the wire, so this arrives as `in`
    # without needing a Pydantic alias — which would collide with the alias
    # machinery the LLM view installs.
    in_: Optional[List[str]] = Field(None, description="Is one of the given values.")
    nin: Optional[List[str]] = Field(None, description="Is not one of the given values.")
    contains: Optional[str] = Field(
        None, description="Contains the given substring, case-sensitively."
    )
    contains_ignore_case: Optional[str] = Field(
        None, description="Contains the given substring, ignoring case."
    )
    contains_ignore_case_and_accent: Optional[str] = Field(
        None,
        description="Contains the given substring, ignoring case and accents.",
    )
    not_contains: Optional[str] = Field(
        None, description="Does not contain the given substring."
    )
    not_contains_ignore_case: Optional[str] = Field(
        None, description="Does not contain the given substring, ignoring case."
    )
    starts_with: Optional[str] = Field(None, description="Starts with the given string.")
    starts_with_ignore_case: Optional[str] = Field(
        None, description="Starts with the given string, ignoring case."
    )
    not_starts_with: Optional[str] = Field(
        None, description="Does not start with the given string."
    )
    ends_with: Optional[str] = Field(None, description="Ends with the given string.")
    not_ends_with: Optional[str] = Field(
        None, description="Does not end with the given string."
    )


class NullableStringComparator(StringComparator):
    """A string comparator for a field that may be null.

    API Reference: https://linear.app/developers/filtering
    """

    null: Optional[bool] = Field(
        None, description="True to match only where the field is null, false where it is set."
    )


class IdComparator(BaseModel):
    """UUID comparators for a Linear filter.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[str] = Field(None, description="Equals the given UUID.")
    neq: Optional[str] = Field(None, description="Does not equal the given UUID.")
    in_: Optional[List[str]] = Field(None, description="Is one of the given UUIDs.")
    nin: Optional[List[str]] = Field(None, description="Is not one of the given UUIDs.")


class NumberComparator(BaseModel):
    """Numeric comparators for a Linear filter.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[float] = Field(None, description="Equals the given value.")
    neq: Optional[float] = Field(None, description="Does not equal the given value.")
    lt: Optional[float] = Field(None, description="Is less than the given value.")
    lte: Optional[float] = Field(
        None, description="Is less than or equal to the given value."
    )
    gt: Optional[float] = Field(None, description="Is greater than the given value.")
    gte: Optional[float] = Field(
        None, description="Is greater than or equal to the given value."
    )
    in_: Optional[List[float]] = Field(None, description="Is one of the given values.")
    nin: Optional[List[float]] = Field(
        None, description="Is not one of the given values."
    )


class NullableNumberComparator(NumberComparator):
    """A numeric comparator for a field that may be null."""

    null: Optional[bool] = Field(
        None, description="True to match only where the field is null, false where it is set."
    )


class DateComparator(BaseModel):
    """Date comparators for a Linear filter.

    Values are ISO 8601 timestamps, such as ``2026-09-13T00:00:00.000Z``.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[str] = Field(None, description="Equals the given date.")
    neq: Optional[str] = Field(None, description="Does not equal the given date.")
    lt: Optional[str] = Field(None, description="Is before the given date.")
    lte: Optional[str] = Field(None, description="Is at or before the given date.")
    gt: Optional[str] = Field(None, description="Is after the given date.")
    gte: Optional[str] = Field(None, description="Is at or after the given date.")
    in_: Optional[List[str]] = Field(None, description="Is one of the given dates.")
    nin: Optional[List[str]] = Field(None, description="Is not one of the given dates.")


class NullableDateComparator(DateComparator):
    """A date comparator for a field that may be null."""

    null: Optional[bool] = Field(
        None, description="True to match only where the field is null, false where it is set."
    )


class BooleanComparator(BaseModel):
    """Boolean comparators for a Linear filter.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[bool] = Field(None, description="Equals the given value.")
    neq: Optional[bool] = Field(None, description="Does not equal the given value.")


class PageVariables(BaseModel):
    """The Relay pagination arguments every Linear connection accepts.

    API Reference: https://linear.app/developers/pagination
    """

    first: Optional[int] = Field(
        default=50,
        ge=1,
        le=250,
        description="How many results to return. Linear returns 50 by default.",
    )
    after: Optional[str] = Field(
        default=None,
        description=(
            "The `endCursor` from the previous page's `pageInfo`, to fetch the "
            "next page."
        ),
    )


class ContentComparator(BaseModel):
    """Substring comparators for a searchable-content field.

    Narrower than :class:`StringComparator`: Linear only offers containment
    here.

    API Reference: https://linear.app/developers/filtering
    """

    contains: Optional[str] = Field(None, description="Contains the given substring.")
    not_contains: Optional[str] = Field(
        None, description="Does not contain the given substring."
    )


class RelationExistsComparator(BaseModel):
    """Whether a relationship exists at all.

    Used for the ``has*Relations`` filters — "is this issue blocked by
    anything?" rather than "which issue blocks it".

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[bool] = Field(None, description="True to match where the relation exists.")
    neq: Optional[bool] = Field(
        None, description="True to match where the relation does not exist."
    )


class EstimateComparator(BaseModel):
    """Comparators for an issue estimate.

    A numeric comparator that also composes: ``and_``/``or_`` take lists of
    plain numeric comparators.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[float] = Field(None, description="Equals the given value.")
    neq: Optional[float] = Field(None, description="Does not equal the given value.")
    lt: Optional[float] = Field(None, description="Is less than the given value.")
    lte: Optional[float] = Field(None, description="Is less than or equal to the given value.")
    gt: Optional[float] = Field(None, description="Is greater than the given value.")
    gte: Optional[float] = Field(None, description="Is greater than or equal to the given value.")
    in_: Optional[List[float]] = Field(None, description="Is one of the given values.")
    nin: Optional[List[float]] = Field(None, description="Is not one of the given values.")
    null: Optional[bool] = Field(
        None, description="True to match only where the estimate is unset."
    )
    and_: Optional[List[NullableNumberComparator]] = Field(
        None, description="Every comparator in this list must match."
    )
    or_: Optional[List[NullableNumberComparator]] = Field(
        None, description="At least one comparator in this list must match."
    )


class SlaStatusComparator(BaseModel):
    """Comparators for an issue's SLA status.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[SlaStatus] = Field(None, description="Equals the given status.")
    neq: Optional[SlaStatus] = Field(None, description="Does not equal the given status.")
    in_: Optional[List[SlaStatus]] = Field(None, description="Is one of the given statuses.")
    nin: Optional[List[SlaStatus]] = Field(
        None, description="Is not one of the given statuses."
    )
    null: Optional[bool] = Field(
        None, description="True to match only where no SLA applies."
    )


class CyclePeriodComparator(BaseModel):
    """Comparators for which cycle period something falls in.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[CyclePeriod] = Field(None, description="Equals the given period.")
    neq: Optional[CyclePeriod] = Field(None, description="Does not equal the given period.")
    in_: Optional[List[CyclePeriod]] = Field(None, description="Is one of the given periods.")
    nin: Optional[List[CyclePeriod]] = Field(
        None, description="Is not one of the given periods."
    )
    null: Optional[bool] = Field(
        None, description="True to match only where there is no such period."
    )


class TeamVisibilityComparator(BaseModel):
    """Comparators for a team's visibility.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[TeamVisibility] = Field(None, description="Equals the given visibility.")
    neq: Optional[TeamVisibility] = Field(
        None, description="Does not equal the given visibility."
    )
    in_: Optional[List[TeamVisibility]] = Field(
        None, description="Is one of the given visibilities."
    )
    nin: Optional[List[TeamVisibility]] = Field(
        None, description="Is not one of the given visibilities."
    )



class NullableTimelessDateComparator(NullableDateComparator):
    """Comparators for a calendar date that may be null.

    Values are ``YYYY-MM-DD`` or a duration such as ``-P2D``. Linear types
    this separately from :class:`NullableDateComparator` (timestamps); the
    operators are the same.

    API Reference: https://linear.app/developers/filtering
    """


class SubTypeComparator(BaseModel):
    """Comparators for a source subtype string that may be null.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[str] = Field(None, description="Equals the given value.")
    neq: Optional[str] = Field(None, description="Does not equal the given value.")
    in_: Optional[List[str]] = Field(None, description="Is one of the given values.")
    nin: Optional[List[str]] = Field(None, description="Is not one of the given values.")
    null: Optional[bool] = Field(
        None, description="True to match only where the subtype is unset."
    )


class WorkflowDefinitionIdComparator(BaseModel):
    """Comparators for the workflow definition that created an issue.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[str] = Field(None, description="Equals the given UUID.")
    neq: Optional[str] = Field(None, description="Does not equal the given UUID.")
    in_: Optional[List[str]] = Field(None, description="Is one of the given UUIDs.")
    nin: Optional[List[str]] = Field(None, description="Is not one of the given UUIDs.")
    null: Optional[bool] = Field(
        None, description="True to match only where no workflow definition applies."
    )


class SourceMetadataComparator(BaseModel):
    """Comparators for how an issue was created — an integration, intake, or not.

    Salesforce-specific metadata is marked ``[INTERNAL]`` in Linear's schema
    and is not modelled.

    API Reference: https://linear.app/developers/filtering
    """

    null: Optional[bool] = Field(
        None,
        description=(
            "When true, matches issues without an external source: issues with "
            "no source metadata and issues created through the API, an OAuth "
            "application, or a loop. When false, matches issues created by an "
            "integration or an intake source such as email."
        ),
    )
    sub_type: Optional[SubTypeComparator] = Field(
        None, description="Comparator for the sub type."
    )
    workflow_definition_id: Optional[WorkflowDefinitionIdComparator] = Field(
        None, description="Comparator for the workflow definition that created the issue."
    )


class ReleasePipelineTypeComparator(BaseModel):
    """Comparators for a release pipeline's type.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[ReleasePipelineType] = Field(None, description="Equals the given type.")
    neq: Optional[ReleasePipelineType] = Field(
        None, description="Does not equal the given type."
    )
    in_: Optional[List[ReleasePipelineType]] = Field(
        None, description="Is one of the given types."
    )
    nin: Optional[List[ReleasePipelineType]] = Field(
        None, description="Is not one of the given types."
    )
    null: Optional[bool] = Field(
        None, description="True to match only where the type is unset."
    )


class ReleaseStageTypeComparator(BaseModel):
    """Comparators for a release stage's type.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[ReleaseStageType] = Field(None, description="Equals the given type.")
    neq: Optional[ReleaseStageType] = Field(
        None, description="Does not equal the given type."
    )
    in_: Optional[List[ReleaseStageType]] = Field(
        None, description="Is one of the given types."
    )
    nin: Optional[List[ReleaseStageType]] = Field(
        None, description="Is not one of the given types."
    )
    null: Optional[bool] = Field(
        None, description="True to match only where the type is unset."
    )


class DurationComparator(BaseModel):
    """Comparators for a measured duration, in seconds.

    Linear derives these from an issue's history — how long it sat in triage,
    how long it took to lead, how long a cycle ran.

    API Reference: https://linear.app/developers/filtering
    """

    eq: Optional[float] = Field(None, description="Equals the given number of seconds.")
    neq: Optional[float] = Field(None, description="Does not equal the given number of seconds.")
    lt: Optional[float] = Field(None, description="Is shorter than the given duration.")
    lte: Optional[float] = Field(None, description="Is at most the given duration.")
    gt: Optional[float] = Field(None, description="Is longer than the given duration.")
    gte: Optional[float] = Field(None, description="Is at least the given duration.")
    in_: Optional[List[float]] = Field(None, description="Is one of the given durations.")
    nin: Optional[List[float]] = Field(None, description="Is not one of the given durations.")
    null: Optional[bool] = Field(
        None, description="True to match only where the duration is unset."
    )


EstimateComparator.model_rebuild()
