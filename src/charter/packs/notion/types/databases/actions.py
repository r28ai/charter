"""
Request schemas for Notion's database endpoints.

Since the 2025-09-03 API version a database is a *container*: it holds one or
more data sources, and the columns and rows belong to those. What is left here
is the container's own metadata — title, description, icon, cover, where it
sits, and whether it renders inline.

API Reference: https://developers.notion.com/reference/database
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.notion.types.common import Cover, Icon, RichText
from charter.packs.notion.types.data_sources.models import PropertyConfiguration
from charter.types import Body, ConflictsWith, Path

__all__ = [
    "DatabasesCreateRequest",
    "DatabasesRetrieveRequest",
    "DatabasesUpdateRequest",
]

DATABASE_ID = "The ID of the database."


class DatabaseParent(BaseModel):
    """Where a database lives.

    A database sits on a page or at the top level of the workspace.

    API Reference: https://developers.notion.com/reference/create-a-database
    """

    type: Optional[Literal["page_id", "workspace"]] = Field(
        None, description="The type of parent."
    )
    page_id: Optional[str] = Field(None, description="The ID of the parent page.")
    workspace: Optional[Literal[True]] = Field(
        None,
        description="Always true, to create the database at the top level of the workspace.",
    )

    @model_validator(mode="after")
    def _one_parent(self):
        if (self.page_id is None) == (self.workspace is None):
            raise ValueError("a database parent is exactly one of `page_id` or `workspace`")
        return self


class InitialDataSource(BaseModel):
    """The first data source created alongside a new database.

    A database needs at least one table, and this is it.

    API Reference: https://developers.notion.com/reference/create-a-database
    """

    properties: Dict[str, PropertyConfiguration] = Field(
        ...,
        description=(
            "The columns of the first data source, keyed by name. Exactly one must "
            "be the `title` column."
        ),
    )


class DatabaseCreateBody(BaseModel):
    """The body of a create-database request.

    API Reference: https://developers.notion.com/reference/create-a-database
    """

    parent: DatabaseParent = Field(..., description="Where the database is created.")
    title: Optional[List[RichText]] = Field(
        None, max_length=100, description="The title of the database."
    )
    description: Optional[List[RichText]] = Field(
        None, max_length=100, description="The description of the database."
    )
    is_inline: Optional[bool] = Field(
        None,
        description=(
            "Whether the database renders inside its parent page rather than as a "
            "page of its own. Not inline when absent."
        ),
    )
    initial_data_source: Annotated[
        Optional[InitialDataSource],
        Field(
            None,
            description="The first data source, and the columns it starts with.",
        ),
        ConflictsWith(
            "database_type",
            reason="A typed database brings Notion's own schema with it.",
        ),
    ]
    database_type: Optional[Literal["tasks", "projects", "skills"]] = Field(
        None,
        description=(
            "Create a database with Notion's canonical schema for tasks, projects "
            "or skills. When `title` is absent the database is named after the type."
        ),
    )
    icon: Optional[Icon] = Field(None, description="The database's icon.")
    cover: Optional[Cover] = Field(None, description="The database's cover image.")


class DatabasesCreateRequest(BaseModel):
    """Create a database.

    API Reference: https://developers.notion.com/reference/create-a-database
    """

    body: Annotated[
        DatabaseCreateBody, Field(..., description="The database to create."), Body()
    ]


class DatabasesRetrieveRequest(BaseModel):
    """Retrieve a database and the data sources it contains.

    The columns are on the data sources, not here — follow the returned
    `data_sources` to `data_sources_retrieve` for a schema.

    API Reference: https://developers.notion.com/reference/retrieve-a-database
    """

    database_id: Annotated[str, Field(..., description=DATABASE_ID), Path()]


class DatabaseUpdateBody(BaseModel):
    """The body of an update-database request.

    API Reference: https://developers.notion.com/reference/update-a-database
    """

    parent: Optional[DatabaseParent] = Field(
        None, description="A new parent, to move the database."
    )
    title: Optional[List[RichText]] = Field(
        None, max_length=100, description="The title of the database."
    )
    description: Optional[List[RichText]] = Field(
        None, max_length=100, description="The description of the database."
    )
    is_inline: Optional[bool] = Field(
        None, description="Whether the database renders inside its parent page."
    )
    icon: Optional[Icon] = Field(None, description="The database's icon.")
    cover: Optional[Cover] = Field(None, description="The database's cover image.")
    in_trash: Optional[bool] = Field(
        None, description="Whether the database is in the trash. False restores it."
    )
    is_locked: Optional[bool] = Field(
        None,
        description=(
            "Whether the database is locked against editing in the Notion app. It "
            "does not block writes through the API."
        ),
    )


class DatabasesUpdateRequest(BaseModel):
    """Update a database's metadata, or move it.

    API Reference: https://developers.notion.com/reference/update-a-database
    """

    database_id: Annotated[str, Field(..., description=DATABASE_ID), Path()]
    body: Annotated[
        DatabaseUpdateBody, Field(..., description="The fields to change."), Body()
    ]
