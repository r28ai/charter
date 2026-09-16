"""
Page property values — what sits in a page's ``properties`` map.

A page that is a row of a database has one entry here per column of that
database's schema, keyed by the column's name or ID. The *shape* of each entry
is decided by the column's type, and Notion has twenty-odd of them.

Six of those types Notion computes and will not accept on write — a formula
result, a rollup, the created/edited stamps, the auto-incrementing ID. They are
marked ``Mode("response_only")`` so they are returned by a read and never
offered to a model composing a write, which is the difference between a failed
call and a call that was never made.

API Reference: https://developers.notion.com/reference/page-property-values
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.notion.types.common import (
    DateValue,
    FileObject,
    PartialUser,
    RichText,
    SelectColor,
)
from charter.types import Mode

__all__ = [
    "SelectValue",
    "StatusValue",
    "RelationRef",
    "VerificationValue",
    "UniqueIdValue",
    "FormulaValue",
    "RollupValue",
    "RollupFunction",
    "PagePropertyValue",
]


class SelectValue(BaseModel):
    """One chosen option of a select or multi-select property.

    Name it or reference it by ID; naming an option that does not exist yet
    creates it. ``color`` and ``description`` come back on a read and are set on
    the *database's* schema, not here.

    API Reference: https://developers.notion.com/reference/page-property-values#select
    """

    id: Optional[str] = Field(
        None, description="The ID of the option. Use this or `name`, not both."
    )
    name: Optional[str] = Field(
        None,
        description=(
            "The name of the option as it appears in Notion. Commas are not valid "
            "in a select value. An option that does not exist yet is created."
        ),
    )
    color: Annotated[
        Optional[SelectColor],
        Field(None, description="The color of the option, as set on the database schema."),
        Mode("response_only"),
    ]
    description: Annotated[
        Optional[str],
        Field(None, description="The description of the option."),
        Mode("response_only"),
    ]

    @model_validator(mode="after")
    def _identified(self):
        if self.id is None and self.name is None:
            raise ValueError("a select option needs either `name` or `id`")
        return self


class StatusValue(BaseModel):
    """The current status of a page in a status property.

    Unlike a select, a status option cannot be created by naming it: the set of
    statuses and their groups is fixed by the database schema.

    API Reference: https://developers.notion.com/reference/page-property-values#status
    """

    id: Optional[str] = Field(
        None, description="The ID of the status option. Use this or `name`, not both."
    )
    name: Optional[str] = Field(
        None,
        description=(
            "The name of the status option. It must already exist on the database's "
            "status property."
        ),
    )
    color: Annotated[
        Optional[SelectColor],
        Field(None, description="The color of the status option."),
        Mode("response_only"),
    ]
    description: Annotated[
        Optional[str],
        Field(None, description="The description of the status option."),
        Mode("response_only"),
    ]

    @model_validator(mode="after")
    def _identified(self):
        if self.id is None and self.name is None:
            raise ValueError("a status needs either `name` or `id`")
        return self


class RelationRef(BaseModel):
    """One related page, referenced by ID.

    API Reference: https://developers.notion.com/reference/page-property-values#relation
    """

    id: str = Field(..., description="The ID of the related page.")


class VerificationValue(BaseModel):
    """The verification state of a page in a wiki database.

    Only available on pages in a wiki database.

    API Reference: https://developers.notion.com/reference/page-property-values#verification
    """

    state: Literal["verified", "unverified", "expired"] = Field(
        ...,
        description=(
            "The verification state of the page. `expired` is a state Notion moves a "
            "page into when its verification lapses; set `verified` or `unverified`."
        ),
    )
    date: Optional[DateValue] = Field(
        None,
        description=(
            "The date the page was verified and the date the verification expires. "
            "Only meaningful when `state` is `verified`."
        ),
    )
    verified_by: Annotated[
        Optional[PartialUser],
        Field(None, description="The user who verified the page."),
        Mode("response_only"),
    ]


class UniqueIdValue(BaseModel):
    """The auto-incrementing ID Notion assigns a page in a database.

    Computed by Notion and never accepted on write.

    API Reference: https://developers.notion.com/reference/page-property-values#unique-id
    """

    number: Optional[int] = Field(None, description="The ID's number part.")
    prefix: Optional[str] = Field(
        None, description="The optional prefix shown before the number, for example `RC`."
    )


class FormulaValue(BaseModel):
    """The result of a formula property.

    Computed by Notion from the formula on the database schema, and never
    accepted on write. A formula Notion could not evaluate comes back with
    ``type`` of ``unsupported``.

    API Reference: https://developers.notion.com/reference/page-property-values#formula
    """

    type: Optional[Literal["boolean", "date", "number", "string", "unsupported"]] = Field(
        None, description="The type of the formula's result."
    )
    boolean: Optional[bool] = Field(None, description="A boolean result.")
    date: Optional[DateValue] = Field(None, description="A date result.")
    number: Optional[float] = Field(None, description="A number result.")
    string: Optional[str] = Field(None, description="A string result.")


RollupFunction = Literal[
    "average",
    "checked",
    "count",
    "count_per_group",
    "count_values",
    "date_range",
    "earliest_date",
    "empty",
    "latest_date",
    "max",
    "median",
    "min",
    "not_empty",
    "percent_checked",
    "percent_empty",
    "percent_not_empty",
    "percent_per_group",
    "percent_unchecked",
    "range",
    "show_original",
    "show_unique",
    "sum",
    "unchecked",
    "unique",
]
"""How a rollup aggregates the related pages' values.

API Reference: https://developers.notion.com/reference/page-property-values#rollup
"""


class RollupValue(BaseModel):
    """The result of a rollup property.

    Computed by Notion from a relation and never accepted on write — the
    documentation says so twice, once on the page object and once on the update
    endpoint.

    API Reference: https://developers.notion.com/reference/page-property-values#rollup
    """

    type: Optional[Literal["array", "date", "incomplete", "number", "unsupported"]] = Field(
        None, description="The type of the rollup's result."
    )
    array: Optional[List[dict]] = Field(
        None,
        description=(
            "The rolled-up property values, for a rollup that shows rather than "
            "aggregates. Each entry is itself a property value."
        ),
    )
    date: Optional[DateValue] = Field(None, description="A date result.")
    number: Optional[float] = Field(None, description="A number result.")
    function: Optional[RollupFunction] = Field(
        None, description="The aggregation applied to the related pages' values."
    )


class PagePropertyValue(BaseModel):
    """One entry in a page's ``properties`` map.

    Exactly one field is set, and which one is decided by the type of the
    database column this entry belongs to — a page under a plain page rather
    than a database has only ``title``.

    Setting a value to ``null`` clears it. The computed types below are marked
    response-only: Notion returns them and rejects them on a write, and the
    update endpoint's documentation says to leave them out of the map rather
    than send them as null.

    API Reference: https://developers.notion.com/reference/page-property-values
    """

    type: Optional[str] = Field(
        None,
        description=(
            "The type of this property value. Returned on a read; on a write Notion "
            "infers it from whichever field below is set."
        ),
    )
    id: Annotated[
        Optional[str],
        Field(None, description="The ID of the property, as defined by the database schema."),
        Mode("response_only"),
    ]

    # ---------- writable ----------
    title: Optional[List[RichText]] = Field(
        None,
        max_length=100,
        description=(
            "The page's title, as rich text. Every page has exactly one title "
            "property, and it is the only property a page outside a database has."
        ),
    )
    rich_text: Optional[List[RichText]] = Field(
        None, max_length=100, description="A text property, as rich text."
    )
    number: Optional[float] = Field(
        None, description="A number. Send null to clear it."
    )
    select: Optional[SelectValue] = Field(
        None, description="The chosen option of a select property. Send null to clear it."
    )
    multi_select: Optional[List[SelectValue]] = Field(
        None, max_length=100, description="The chosen options of a multi-select property."
    )
    status: Optional[StatusValue] = Field(
        None, description="The current status of the page."
    )
    date: Optional[DateValue] = Field(
        None, description="A date or date range. Send null to clear it."
    )
    people: Optional[List[PartialUser]] = Field(
        None, max_length=100, description="The users assigned to a people property."
    )
    files: Optional[List[FileObject]] = Field(
        None,
        max_length=100,
        description=(
            "The files attached to a files property. An `external` entry must carry "
            "a `name`. Sending this replaces the whole list rather than adding to it."
        ),
    )
    checkbox: Optional[bool] = Field(None, description="Whether a checkbox is checked.")
    url: Optional[str] = Field(
        None, max_length=2000, description="A URL. Maximum 2000 characters."
    )
    email: Optional[str] = Field(
        None, max_length=200, description="An email address. Maximum 200 characters."
    )
    phone_number: Optional[str] = Field(
        None,
        max_length=200,
        description=(
            "A phone number. No structure is enforced, so any string up to 200 "
            "characters is accepted."
        ),
    )
    relation: Optional[List[RelationRef]] = Field(
        None,
        max_length=100,
        description=(
            "The related pages. At most 100 may be sent or read in one request; a "
            "relation holding more reports `has_more` and is read in full through "
            "the page property item endpoint."
        ),
    )
    verification: Optional[VerificationValue] = Field(
        None, description="The verification state of a page in a wiki database."
    )

    # ---------- computed by Notion ----------
    formula: Annotated[
        Optional[FormulaValue],
        Field(None, description="The result of a formula property."),
        Mode("response_only"),
    ]
    rollup: Annotated[
        Optional[RollupValue],
        Field(None, description="The result of a rollup property."),
        Mode("response_only"),
    ]
    unique_id: Annotated[
        Optional[UniqueIdValue],
        Field(None, description="The page's auto-incrementing ID within its database."),
        Mode("response_only"),
    ]
    created_time: Annotated[
        Optional[str],
        Field(None, description="When the page was created, in ISO 8601 format."),
        Mode("response_only"),
    ]
    created_by: Annotated[
        Optional[PartialUser],
        Field(None, description="The user who created the page."),
        Mode("response_only"),
    ]
    last_edited_time: Annotated[
        Optional[str],
        Field(None, description="When the page was last edited, in ISO 8601 format."),
        Mode("response_only"),
    ]
    last_edited_by: Annotated[
        Optional[PartialUser],
        Field(None, description="The user who last edited the page."),
        Mode("response_only"),
    ]
    has_more: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether a relation, people or rich text property holds more entries "
                "than the 25 this page object carries. Read them in full through the "
                "page property item endpoint."
            ),
        ),
        Mode("response_only"),
    ]
