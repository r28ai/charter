# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Data sources — the schema of a table, and the grammar for querying it.

A database is a container; a *data source* is a table inside it, and that is
where the columns live and where rows are queried from. Three object graphs sit
here:

* **Property configurations** — the twenty-six kinds of column a data source can
  have, which is what ``properties`` means on create and update.
* **Filters** — Notion's query grammar: a condition per property type, composed
  with ``and`` and ``or``. Both of those are Python keywords, so the fields are
  spelled ``and_`` and ``or_`` and carry an ``alias`` plus a serializer that puts
  the API's own spelling on the wire.
* **Sorts** — by a property, or by one of the two timestamps.

API Reference: https://developers.notion.com/reference/data-source
"""

from __future__ import annotations

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_serializer, model_validator

from charter.packs.notion.types.common import SelectColor, exactly_one_of

__all__ = [
    "RelativeDate",
    "EmptyCondition",
    "TextCondition",
    "NumberCondition",
    "CheckboxCondition",
    "DateCondition",
    "SelectCondition",
    "MultiSelectCondition",
    "PeopleCondition",
    "RelationCondition",
    "ExistenceCondition",
    "FormulaCondition",
    "RollupSubCondition",
    "RollupCondition",
    "VerificationCondition",
    "Filter",
    "Sort",
    "SelectOption",
    "StatusOption",
    "PropertyConfiguration",
    "PropertyUpdate",
]


RELATIVE_DATES = (
    "Also accepts one of Notion's relative values: `today`, `tomorrow`, "
    "`yesterday`, `one_week_ago`, `one_week_from_now`, `one_month_ago`, "
    "`one_month_from_now`."
)

RelativeDate = Literal[
    "today",
    "tomorrow",
    "yesterday",
    "one_week_ago",
    "one_week_from_now",
    "one_month_ago",
    "one_month_from_now",
]
"""A date expressed relative to now, accepted anywhere a filter takes a date."""


# Declared at module level, not as class attributes. A private tuple in a model
# body does not survive onto the LLM view ``create_llm_schema`` generates, and
# the validators below are carried there — so reading one off ``self`` raises
# AttributeError on exactly the input the rule exists to check.
_CONDITIONS = (
    "title",
    "rich_text",
    "url",
    "email",
    "phone_number",
    "number",
    "unique_id",
    "checkbox",
    "select",
    "status",
    "multi_select",
    "date",
    "created_time",
    "last_edited_time",
    "people",
    "created_by",
    "last_edited_by",
    "files",
    "relation",
    "formula",
    "rollup",
    "verification",
)

_PROPERTY_TYPES = (
    "title",
    "rich_text",
    "number",
    "select",
    "multi_select",
    "status",
    "date",
    "people",
    "files",
    "checkbox",
    "url",
    "email",
    "phone_number",
    "formula",
    "relation",
    "rollup",
    "created_time",
    "created_by",
    "last_edited_time",
    "last_edited_by",
    "last_visited_time",
    "unique_id",
    "verification",
    "button",
    "location",
    "place",
)


class EmptyCondition(BaseModel):
    """A condition that needs no argument, such as ``past_week``.

    Send an empty object: Notion reads the key, not the value.

    API Reference: https://developers.notion.com/reference/post-database-query-filter
    """


# -----------------------------------------------------
# Conditions, one shape per property type
# -----------------------------------------------------


class ExistenceCondition(BaseModel):
    """Whether a property has any value at all.

    Available on every filterable type; it is the whole of the ``files`` filter.

    API Reference: https://developers.notion.com/reference/post-database-query-filter
    """

    is_empty: Optional[Literal[True]] = Field(
        None, description="Whether the property value is empty. Only `true` is accepted."
    )
    is_not_empty: Optional[Literal[True]] = Field(
        None,
        description="Whether the property value is not empty. Only `true` is accepted.",
    )


class TextCondition(ExistenceCondition):
    """Conditions on a text-valued property.

    Used by ``title``, ``rich_text``, ``url``, ``email`` and ``phone_number``.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#rich-text
    """

    equals: Optional[str] = Field(None, description="The exact string to match.")
    does_not_equal: Optional[str] = Field(None, description="The exact string to exclude.")
    contains: Optional[str] = Field(None, description="A substring the value must contain.")
    does_not_contain: Optional[str] = Field(
        None, description="A substring the value must not contain."
    )
    starts_with: Optional[str] = Field(None, description="A prefix the value must have.")
    ends_with: Optional[str] = Field(None, description="A suffix the value must have.")


class NumberCondition(ExistenceCondition):
    """Conditions on a number-valued property.

    Used by ``number`` and by ``unique_id``.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#number
    """

    equals: Optional[float] = Field(None, description="The number to match.")
    does_not_equal: Optional[float] = Field(None, description="The number to exclude.")
    greater_than: Optional[float] = Field(None, description="An exclusive lower bound.")
    less_than: Optional[float] = Field(None, description="An exclusive upper bound.")
    greater_than_or_equal_to: Optional[float] = Field(None, description="An inclusive lower bound.")
    less_than_or_equal_to: Optional[float] = Field(None, description="An inclusive upper bound.")


class CheckboxCondition(BaseModel):
    """Conditions on a checkbox property.

    A checkbox is always either checked or not, so it has no emptiness check.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#checkbox
    """

    equals: Optional[bool] = Field(None, description="Whether the checkbox is checked.")
    does_not_equal: Optional[bool] = Field(
        None, description="Whether the checkbox is not in this state."
    )


class DateCondition(ExistenceCondition):
    """Conditions on a date-valued property.

    Used by ``date``, ``created_time`` and ``last_edited_time``. The six
    period conditions take an empty object.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#date
    """

    equals: Optional[str] = Field(None, description=f"An ISO 8601 date to match. {RELATIVE_DATES}")
    before: Optional[str] = Field(
        None, description=f"An ISO 8601 date the value must precede. {RELATIVE_DATES}"
    )
    after: Optional[str] = Field(
        None, description=f"An ISO 8601 date the value must follow. {RELATIVE_DATES}"
    )
    on_or_before: Optional[str] = Field(
        None, description=f"An ISO 8601 date the value must not follow. {RELATIVE_DATES}"
    )
    on_or_after: Optional[str] = Field(
        None, description=f"An ISO 8601 date the value must not precede. {RELATIVE_DATES}"
    )
    this_week: Optional[EmptyCondition] = Field(
        None, description="Whether the date is in the current week. Send an empty object."
    )
    past_week: Optional[EmptyCondition] = Field(
        None, description="Whether the date is in the past week. Send an empty object."
    )
    past_month: Optional[EmptyCondition] = Field(
        None, description="Whether the date is in the past month. Send an empty object."
    )
    past_year: Optional[EmptyCondition] = Field(
        None, description="Whether the date is in the past year. Send an empty object."
    )
    next_week: Optional[EmptyCondition] = Field(
        None, description="Whether the date is in the next week. Send an empty object."
    )
    next_month: Optional[EmptyCondition] = Field(
        None, description="Whether the date is in the next month. Send an empty object."
    )
    next_year: Optional[EmptyCondition] = Field(
        None, description="Whether the date is in the next year. Send an empty object."
    )


class SelectCondition(ExistenceCondition):
    """Conditions on a select or status property.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#select
    """

    equals: Optional[Union[str, List[str]]] = Field(
        None,
        description=("The option name to match. A list matches any of several options."),
    )
    does_not_equal: Optional[Union[str, List[str]]] = Field(
        None, description="The option name to exclude. A list excludes several."
    )


class MultiSelectCondition(ExistenceCondition):
    """Conditions on a multi-select property.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#multi-select
    """

    contains: Optional[Union[str, List[str]]] = Field(
        None, description="An option the value must include."
    )
    does_not_contain: Optional[Union[str, List[str]]] = Field(
        None, description="An option the value must not include."
    )


class PeopleCondition(ExistenceCondition):
    """Conditions on a people property.

    Used by ``people``, ``created_by`` and ``last_edited_by``.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#people
    """

    contains: Optional[str] = Field(
        None,
        description=(
            "The ID of a user the value must include. The literal `me` stands for "
            "the user the token acts as."
        ),
    )
    does_not_contain: Optional[str] = Field(
        None,
        description=("The ID of a user the value must not include. `me` is accepted here too."),
    )


class RelationCondition(ExistenceCondition):
    """Conditions on a relation property.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#relation
    """

    contains: Optional[str] = Field(None, description="The ID of a page the relation must include.")
    does_not_contain: Optional[str] = Field(
        None, description="The ID of a page the relation must not include."
    )


class FormulaCondition(BaseModel):
    """Conditions on a formula property, applied to the formula's result.

    Which field to use depends on what the formula returns.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#formula
    """

    string: Optional[TextCondition] = Field(
        None, description="Applied when the formula returns a string."
    )
    checkbox: Optional[CheckboxCondition] = Field(
        None, description="Applied when the formula returns a boolean."
    )
    number: Optional[NumberCondition] = Field(
        None, description="Applied when the formula returns a number."
    )
    date: Optional[DateCondition] = Field(
        None, description="Applied when the formula returns a date."
    )


class RollupSubCondition(BaseModel):
    """A condition applied to each value a rollup gathers.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#rollup
    """

    rich_text: Optional[TextCondition] = Field(None, description="A text condition.")
    number: Optional[NumberCondition] = Field(None, description="A number condition.")
    checkbox: Optional[CheckboxCondition] = Field(None, description="A checkbox condition.")
    select: Optional[SelectCondition] = Field(None, description="A select condition.")
    multi_select: Optional[MultiSelectCondition] = Field(
        None, description="A multi-select condition."
    )
    status: Optional[SelectCondition] = Field(None, description="A status condition.")
    relation: Optional[RelationCondition] = Field(None, description="A relation condition.")
    date: Optional[DateCondition] = Field(None, description="A date condition.")
    people: Optional[PeopleCondition] = Field(None, description="A people condition.")
    files: Optional[ExistenceCondition] = Field(None, description="A files condition.")


class RollupCondition(BaseModel):
    """Conditions on a rollup property.

    ``any``, ``none`` and ``every`` quantify over the gathered values; ``date``
    and ``number`` apply to a rollup that aggregates to a single value.

    API Reference: https://developers.notion.com/reference/post-database-query-filter#rollup
    """

    any: Optional[RollupSubCondition] = Field(
        None, description="Matches when at least one gathered value matches."
    )
    none: Optional[RollupSubCondition] = Field(
        None, description="Matches when no gathered value matches."
    )
    every: Optional[RollupSubCondition] = Field(
        None, description="Matches when every gathered value matches."
    )
    date: Optional[DateCondition] = Field(
        None, description="Applied when the rollup aggregates to a date."
    )
    number: Optional[NumberCondition] = Field(
        None, description="Applied when the rollup aggregates to a number."
    )


class VerificationCondition(BaseModel):
    """Conditions on a verification property, for pages in a wiki database.

    API Reference: https://developers.notion.com/reference/post-database-query-filter
    """

    status: Literal["verified", "expired", "none"] = Field(
        ..., description="The verification status to match."
    )


# -----------------------------------------------------
# The filter itself
# -----------------------------------------------------


class Filter(BaseModel):
    """Which rows a query returns.

    A filter is one of three things, and the validator below holds it to exactly
    one:

    * a **compound** — ``and_`` or ``or_``, each a list of filters. Notion allows
      two levels of nesting.
    * a **property filter** — ``property`` naming the column, plus the condition
      field for that column's type.
    * a **timestamp filter** — ``timestamp`` naming ``created_time`` or
      ``last_edited_time``, plus the matching date condition.

    ``and_`` and ``or_`` go out as ``and`` and ``or``: both are Python keywords,
    so the field carries the API's spelling as an ``alias`` and a serializer puts
    it on the wire. A ``WireName`` cannot reach this far — key conversion applies
    per-field markers at the top level of a body, and a filter is nested inside
    one.

    API Reference: https://developers.notion.com/reference/post-database-query-filter
    """

    and_: Optional[List[Filter]] = Field(
        None,
        alias="and",
        max_length=100,
        description="Filters that must all match. Nests at most two levels deep.",
    )
    or_: Optional[List[Filter]] = Field(
        None,
        alias="or",
        max_length=100,
        description="Filters of which at least one must match. Nests at most two levels deep.",
    )

    property: Optional[str] = Field(
        None,
        description="The name or ID of the property to filter on. Required for a property filter.",
    )
    timestamp: Optional[Literal["created_time", "last_edited_time"]] = Field(
        None,
        description=(
            "Filter on when the page was created or last edited rather than on one "
            "of its properties."
        ),
    )
    type: Optional[str] = Field(None, description="The type of the property being filtered on.")

    title: Optional[TextCondition] = Field(None, description="A condition on the title.")
    rich_text: Optional[TextCondition] = Field(None, description="A condition on a text property.")
    url: Optional[TextCondition] = Field(None, description="A condition on a URL property.")
    email: Optional[TextCondition] = Field(None, description="A condition on an email property.")
    phone_number: Optional[TextCondition] = Field(
        None, description="A condition on a phone number property."
    )
    number: Optional[NumberCondition] = Field(None, description="A condition on a number property.")
    unique_id: Optional[NumberCondition] = Field(
        None, description="A condition on the auto-incrementing ID."
    )
    checkbox: Optional[CheckboxCondition] = Field(
        None, description="A condition on a checkbox property."
    )
    select: Optional[SelectCondition] = Field(None, description="A condition on a select property.")
    status: Optional[SelectCondition] = Field(None, description="A condition on a status property.")
    multi_select: Optional[MultiSelectCondition] = Field(
        None, description="A condition on a multi-select property."
    )
    date: Optional[DateCondition] = Field(None, description="A condition on a date property.")
    created_time: Optional[DateCondition] = Field(
        None, description="A condition on when the page was created."
    )
    last_edited_time: Optional[DateCondition] = Field(
        None, description="A condition on when the page was last edited."
    )
    people: Optional[PeopleCondition] = Field(None, description="A condition on a people property.")
    created_by: Optional[PeopleCondition] = Field(
        None, description="A condition on who created the page."
    )
    last_edited_by: Optional[PeopleCondition] = Field(
        None, description="A condition on who last edited the page."
    )
    files: Optional[ExistenceCondition] = Field(
        None, description="A condition on whether a files property has any file."
    )
    relation: Optional[RelationCondition] = Field(
        None, description="A condition on a relation property."
    )
    formula: Optional[FormulaCondition] = Field(
        None, description="A condition on a formula's result."
    )
    rollup: Optional[RollupCondition] = Field(None, description="A condition on a rollup's value.")
    verification: Optional[VerificationCondition] = Field(
        None, description="A condition on a wiki page's verification status."
    )

    @model_validator(mode="after")
    def _one_shape(self):
        compound = [n for n in ("and_", "or_") if getattr(self, n, None) is not None]
        conditions = [n for n in _CONDITIONS if getattr(self, n, None) is not None]
        if compound and conditions:
            raise ValueError(
                "a filter is either a compound (`and`/`or`) or a single condition, "
                "not both — wrap the condition in the list instead"
            )
        if len(compound) > 1:
            raise ValueError("a filter takes `and` or `or`, not both")
        if compound:
            return self
        if len(conditions) > 1:
            raise ValueError(
                f"a property filter carries one condition, got {', '.join(conditions)} "
                f"— combine them under `and`"
            )
        if not conditions:
            raise ValueError(
                "a filter needs either `and`/`or`, or a property condition such as "
                "`{'property': 'Status', 'status': {'equals': 'Done'}}`"
            )
        if self.timestamp is None and self.property is None:
            raise ValueError(
                f"a `{conditions[0]}` condition needs `property` naming the column it applies to"
            )
        return self

    @model_serializer(mode="wrap")
    def _keywords_on_the_wire(self, handler: Any) -> Any:
        """Send ``and``/``or``, which Python will not let a field be called.

        Carried onto the LLM view by ``_carry_validators``, which is the
        instance the runtime actually dumps.
        """
        data = handler(self)
        if "and_" in data:
            data["and"] = data.pop("and_")
        if "or_" in data:
            data["or"] = data.pop("or_")
        return data


class Sort(BaseModel):
    """How to order the rows a query returns.

    Sort by a property, or by one of the two timestamps — one or the other.

    API Reference: https://developers.notion.com/reference/post-database-query-sort
    """

    property: Optional[str] = Field(None, description="The name or ID of the property to sort by.")
    timestamp: Optional[Literal["created_time", "last_edited_time"]] = Field(
        None, description="Sort by when the page was created or last edited."
    )
    direction: Literal["ascending", "descending"] = Field(
        ..., description="Whether to sort ascending or descending."
    )

    @model_validator(mode="after")
    def _one_key(self):
        if (self.property is None) == (self.timestamp is None):
            raise ValueError("a sort takes exactly one of `property` or `timestamp`")
        return self


# -----------------------------------------------------
# The column schema
# -----------------------------------------------------


class SelectOption(BaseModel):
    """One option of a select or multi-select column.

    API Reference: https://developers.notion.com/reference/property-object#select
    """

    name: Optional[str] = Field(
        None, description="The name of the option, as it appears in Notion."
    )
    id: Optional[str] = Field(
        None, description="The ID of an existing option, when updating it rather than adding one."
    )
    color: Optional[SelectColor] = Field(None, description="The color of the option.")
    description: Optional[str] = Field(None, description="The description of the option.")

    @model_validator(mode="after")
    def _identified(self):
        if self.name is None and self.id is None:
            raise ValueError("an option needs either `name` or `id`")
        return self


class StatusOption(SelectOption):
    """One option of a status column, which also belongs to a group.

    API Reference: https://developers.notion.com/reference/property-object#status
    """

    group: Optional[Literal["To-do", "In progress", "Complete"]] = Field(
        None, description="Which of the three status groups this option belongs to."
    )


class SelectConfig(BaseModel):
    """The options of a select or multi-select column.

    API Reference: https://developers.notion.com/reference/property-object#select
    """

    options: Optional[List[SelectOption]] = Field(
        None, max_length=100, description="The available options."
    )


class StatusConfig(BaseModel):
    """The options of a status column.

    API Reference: https://developers.notion.com/reference/property-object#status
    """

    options: Optional[List[StatusOption]] = Field(
        None, max_length=100, description="The available options."
    )


class NumberConfig(BaseModel):
    """How a number column is displayed.

    API Reference: https://developers.notion.com/reference/property-object#number
    """

    format: Optional[str] = Field(
        None,
        description=(
            "How the number is formatted — `number`, `number_with_commas`, "
            "`percent`, `dollar`, `euro`, `pound`, `yen` and the other currency "
            "codes Notion supports. The API declares this an open string rather "
            "than a fixed set, so a format added later is accepted."
        ),
    )


class FormulaConfig(BaseModel):
    """The expression a formula column evaluates.

    API Reference: https://developers.notion.com/reference/property-object#formula
    """

    expression: Optional[str] = Field(
        None, description="The formula, in Notion's formula language."
    )


class SinglePropertyRelation(BaseModel):
    """A relation that does not show up on the related data source."""


class DualPropertyRelation(BaseModel):
    """A relation mirrored by a property on the related data source.

    API Reference: https://developers.notion.com/reference/property-object#relation
    """

    synced_property_id: Optional[str] = Field(
        None, description="The ID of the mirrored property on the related data source."
    )
    synced_property_name: Optional[str] = Field(
        None, description="The name of the mirrored property on the related data source."
    )


class RelationConfig(BaseModel):
    """Which data source a relation column points at, and whether it is mirrored.

    API Reference: https://developers.notion.com/reference/property-object#relation
    """

    data_source_id: str = Field(
        ..., description="The ID of the data source the relation points at."
    )
    type: Optional[Literal["single_property", "dual_property"]] = Field(
        None, description="Whether the relation is mirrored on the other data source."
    )
    single_property: Optional[SinglePropertyRelation] = Field(
        None,
        description=(
            "A one-way relation, which adds no property to the related data source. "
            "Send an empty object."
        ),
    )
    dual_property: Optional[DualPropertyRelation] = Field(
        None,
        description="A two-way relation, mirrored by a property on the related data source.",
    )

    @model_validator(mode="after")
    def _one_kind(self):
        return exactly_one_of(self, "type", ("single_property", "dual_property"))


class RollupConfig(BaseModel):
    """What a rollup column gathers and how it aggregates it.

    Name the relation and the property either both by name or both by ID.

    API Reference: https://developers.notion.com/reference/property-object#rollup
    """

    function: str = Field(
        ...,
        description=(
            "How the gathered values are aggregated: `count`, `count_values`, "
            "`empty`, `not_empty`, `unique`, `show_unique`, `percent_empty`, "
            "`percent_not_empty`, `sum`, `average`, `median`, `min`, `max`, "
            "`range`, `earliest_date`, `latest_date`, `date_range`, `checked`, "
            "`unchecked`, `percent_checked`, `percent_unchecked`, "
            "`count_per_group`, `percent_per_group` or `show_original`."
        ),
    )
    relation_property_name: Optional[str] = Field(
        None, description="The name of the relation column to follow."
    )
    relation_property_id: Optional[str] = Field(
        None, description="The ID of the relation column to follow."
    )
    rollup_property_name: Optional[str] = Field(
        None, description="The name of the property to gather from the related pages."
    )
    rollup_property_id: Optional[str] = Field(
        None, description="The ID of the property to gather from the related pages."
    )


class UniqueIdConfig(BaseModel):
    """The prefix shown before an auto-incrementing ID.

    API Reference: https://developers.notion.com/reference/property-object#unique-id
    """

    prefix: Optional[str] = Field(
        None, description="The prefix, for example `RC` to produce `RC-1`. Null for none."
    )


class EmptyConfig(BaseModel):
    """A column type with nothing to configure.

    Most types are like this: the type is the whole configuration. Send an
    empty object.

    API Reference: https://developers.notion.com/reference/property-object
    """


class PropertyConfiguration(BaseModel):
    """One column of a data source.

    Exactly one of the type fields is set, and it decides the column's type.
    Most types take an empty object — the type *is* the configuration.

    API Reference: https://developers.notion.com/reference/property-object
    """

    type: Optional[str] = Field(
        None,
        description=(
            "The type of the column. Returned on a read; on a write Notion infers "
            "it from whichever configuration field below is set."
        ),
    )
    description: Optional[str] = Field(
        None, max_length=280, description="The description of the property."
    )

    title: Optional[EmptyConfig] = Field(
        None,
        description=(
            "The title column. Every data source has exactly one, and it cannot be "
            "deleted. Send an empty object."
        ),
    )
    rich_text: Optional[EmptyConfig] = Field(
        None, description="A text column. Send an empty object."
    )
    number: Optional[NumberConfig] = Field(None, description="A number column.")
    select: Optional[SelectConfig] = Field(None, description="A single-choice column.")
    multi_select: Optional[SelectConfig] = Field(None, description="A multiple-choice column.")
    status: Optional[StatusConfig] = Field(
        None, description="A status column, whose options belong to three groups."
    )
    date: Optional[EmptyConfig] = Field(None, description="A date column. Send an empty object.")
    people: Optional[EmptyConfig] = Field(
        None, description="A people column. Send an empty object."
    )
    files: Optional[EmptyConfig] = Field(None, description="A files column. Send an empty object.")
    checkbox: Optional[EmptyConfig] = Field(
        None, description="A checkbox column. Send an empty object."
    )
    url: Optional[EmptyConfig] = Field(None, description="A URL column. Send an empty object.")
    email: Optional[EmptyConfig] = Field(None, description="An email column. Send an empty object.")
    phone_number: Optional[EmptyConfig] = Field(
        None, description="A phone number column. Send an empty object."
    )
    formula: Optional[FormulaConfig] = Field(
        None, description="A column computed from the page's other properties."
    )
    relation: Optional[RelationConfig] = Field(
        None, description="A column of links to pages in another data source."
    )
    rollup: Optional[RollupConfig] = Field(
        None, description="A column that gathers values through a relation."
    )
    created_time: Optional[EmptyConfig] = Field(
        None, description="When the page was created. Send an empty object."
    )
    created_by: Optional[EmptyConfig] = Field(
        None, description="Who created the page. Send an empty object."
    )
    last_edited_time: Optional[EmptyConfig] = Field(
        None, description="When the page was last edited. Send an empty object."
    )
    last_edited_by: Optional[EmptyConfig] = Field(
        None, description="Who last edited the page. Send an empty object."
    )
    last_visited_time: Optional[EmptyConfig] = Field(
        None, description="When the page was last visited. Send an empty object."
    )
    unique_id: Optional[UniqueIdConfig] = Field(
        None, description="An ID Notion increments for each new page."
    )
    verification: Optional[EmptyConfig] = Field(
        None, description="A wiki page's verification status. Send an empty object."
    )
    button: Optional[EmptyConfig] = Field(
        None, description="A button column. Send an empty object."
    )
    location: Optional[EmptyConfig] = Field(
        None, description="A location column. Send an empty object."
    )
    place: Optional[EmptyConfig] = Field(None, description="A place column. Send an empty object.")

    @model_validator(mode="after")
    def _one_type(self):
        return exactly_one_of(self, "type", _PROPERTY_TYPES)


class PropertyUpdate(PropertyConfiguration):
    """A change to one column of an existing data source.

    Adds ``name``, which renames the column. Every field is optional, including
    the type: sending only ``name`` renames without retyping. To *remove* a
    column, map its name to ``null`` rather than sending this object.

    API Reference: https://developers.notion.com/reference/update-a-data-source
    """

    name: Optional[str] = Field(None, description="The new name of the property.")

    @model_validator(mode="after")
    def _one_type(self):
        present = [n for n in _PROPERTY_TYPES if getattr(self, n, None) is not None]
        if len(present) > 1:
            raise ValueError(f"a property has one type, got {', '.join(present)}")
        if self.type is not None and present and self.type != present[0]:
            raise ValueError(f"type={self.type!r} does not name the `{present[0]}` given")
        return self


Filter.model_rebuild()
