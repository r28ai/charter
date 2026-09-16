"""
Request schemas for Notion's data source endpoints.

API Reference: https://developers.notion.com/reference/data-source
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.notion.types.common import Icon, PaginatedQuery, Parent, RichText
from charter.packs.notion.types.data_sources.models import (
    Filter,
    PropertyConfiguration,
    PropertyUpdate,
    Sort,
)
from charter.types import Body, Path, Query

__all__ = [
    "DataSourcesCreateRequest",
    "DataSourcesRetrieveRequest",
    "DataSourcesUpdateRequest",
    "DataSourcesQueryRequest",
    "DataSourcesTemplatesListRequest",
]

DATA_SOURCE_ID = "The ID of the data source."
TITLE = "The title of the data source, as it appears in Notion."


class DataSourceCreateBody(BaseModel):
    """The body of a create-data-source request.

    API Reference: https://developers.notion.com/reference/create-a-data-source
    """

    parent: Parent = Field(
        ...,
        description=(
            "The database this data source becomes a table of, as "
            "`{\"type\": \"database_id\", \"database_id\": ...}`."
        ),
    )
    properties: Dict[str, PropertyConfiguration] = Field(
        ...,
        description=(
            "The columns, keyed by name. Exactly one must be the `title` column — "
            "every data source has one and it cannot be removed."
        ),
    )
    title: Optional[List[RichText]] = Field(None, max_length=100, description=TITLE)
    icon: Optional[Icon] = Field(None, description="The data source's icon.")


class DataSourcesCreateRequest(BaseModel):
    """Add a data source to an existing database.

    API Reference: https://developers.notion.com/reference/create-a-data-source
    """

    body: Annotated[
        DataSourceCreateBody, Field(..., description="The data source to create."), Body()
    ]


class DataSourcesRetrieveRequest(BaseModel):
    """Retrieve a data source, including its property schema.

    This returns the *schema*, not the rows. Use `data_sources_query` for those.

    API Reference: https://developers.notion.com/reference/retrieve-a-data-source
    """

    data_source_id: Annotated[str, Field(..., description=DATA_SOURCE_ID), Path()]


class DataSourceParent(BaseModel):
    """The database a data source belongs to.

    API Reference: https://developers.notion.com/reference/update-a-data-source
    """

    type: Optional[Literal["database_id"]] = Field(
        None, description="Always `database_id`."
    )
    database_id: str = Field(
        ..., description="The ID of the parent database, with or without dashes."
    )


class DataSourceUpdateBody(BaseModel):
    """The body of an update-data-source request.

    API Reference: https://developers.notion.com/reference/update-a-data-source
    """

    parent: Optional[DataSourceParent] = Field(
        None,
        description=(
            "A different database to move this data source into. Left where it is "
            "when absent."
        ),
    )
    title: Optional[List[RichText]] = Field(None, max_length=100, description=TITLE)
    icon: Optional[Icon] = Field(
        None, description="The data source's icon. Null removes it."
    )
    properties: Optional[Dict[str, Optional[PropertyUpdate]]] = Field(
        None,
        description=(
            "The columns to change, keyed by current name or ID. A name not already "
            "on the data source adds a column; `{\"name\": \"...\"}` renames one; "
            "mapping a key to null removes it."
        ),
    )
    in_trash: Optional[bool] = Field(
        None, description="Whether the data source is in the trash."
    )


class DataSourcesUpdateRequest(BaseModel):
    """Update a data source's title, icon or column schema.

    API Reference: https://developers.notion.com/reference/update-a-data-source
    """

    data_source_id: Annotated[str, Field(..., description=DATA_SOURCE_ID), Path()]
    body: Annotated[
        DataSourceUpdateBody, Field(..., description="The fields to change."), Body()
    ]


class DataSourceQueryBody(BaseModel):
    """The body of a query request.

    API Reference: https://developers.notion.com/reference/query-a-data-source
    """

    filter: Optional[Filter] = Field(
        default=None,
        description=(
            "Which rows to return. Omit to return all of them."
        ),
    )
    sorts: Optional[List[Sort]] = Field(
        default=None,
        description=(
            "How to order the rows. Earlier entries in the list take precedence."
        ),
    )
    start_cursor: Optional[str] = Field(
        default=None, description="A `next_cursor` from a previous response."
    )
    page_size: Optional[int] = Field(
        default=None, ge=1, le=100, description="How many rows to return. Maximum 100."
    )
    is_archived: Optional[bool] = Field(
        default=None,
        description=(
            "Whether to return archived pages instead of live ones. Live pages when "
            "absent."
        ),
    )
    result_type: Optional[Literal["page", "data_source"]] = Field(
        default=None,
        description=(
            "Restrict the results to pages or to nested data sources. Only a wiki "
            "database has data source children; absent, both come back."
        ),
    )


class DataSourcesQueryRequest(BaseModel):
    """Query a data source for its rows.

    API Reference: https://developers.notion.com/reference/query-a-data-source
    """

    data_source_id: Annotated[str, Field(..., description=DATA_SOURCE_ID), Path()]
    filter_properties: Annotated[
        Optional[List[str]],
        Field(
            None,
            max_length=100,
            description=(
                "Property IDs to return on each row, instead of all of them. The "
                "cheapest way to keep a wide table's query readable."
            ),
        ),
        Query(),
    ]
    body: Annotated[
        DataSourceQueryBody,
        Field(
            default_factory=DataSourceQueryBody,
            description="The filter, sort and paging options. All optional.",
        ),
        Body(),
    ]


class DataSourcesTemplatesListRequest(PaginatedQuery):
    """List a data source's page templates.

    API Reference: https://developers.notion.com/reference/list-data-source-templates
    """

    data_source_id: Annotated[str, Field(..., description=DATA_SOURCE_ID), Path()]
    name: Annotated[
        Optional[str],
        Field(None, description="Return only templates whose name matches this."),
        Query(),
    ]

