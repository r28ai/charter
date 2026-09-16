"""
Request schema for Notion's search endpoint.

API Reference: https://developers.notion.com/reference/post-search
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Body

__all__ = ["SearchRequest"]


class SearchSort(BaseModel):
    """How to order search results.

    Either by when a result was last edited, or by relevance to the query.

    API Reference: https://developers.notion.com/reference/post-search
    """

    timestamp: Optional[Literal["last_edited_time"]] = Field(
        None, description="Sort by when the result was last edited."
    )
    direction: Optional[Literal["ascending", "descending"]] = Field(
        None, description="The sort order. Required alongside `timestamp`."
    )
    property: Optional[Literal["relevance"]] = Field(
        None, description="Sort by how well the result matches the query."
    )

    @model_validator(mode="after")
    def _one_key(self):
        if (self.timestamp is None) == (self.property is None):
            raise ValueError("a search sort takes exactly one of `timestamp` or `property`")
        if self.timestamp is not None and self.direction is None:
            raise ValueError("sorting by `timestamp` needs a `direction`")
        if self.property is not None and self.direction is not None:
            raise ValueError("`direction` is not read when sorting by relevance")
        return self


class SearchFilter(BaseModel):
    """Which kinds of object a search returns.

    API Reference: https://developers.notion.com/reference/post-search
    """

    property: Optional[Literal["object"]] = Field(
        None, description="Always `object`. Required alongside `value`."
    )
    value: Optional[Literal["page", "data_source"]] = Field(
        None, description="Whether to return only pages or only data sources."
    )
    in_trash: Optional[bool] = Field(
        None, description="Whether to search the trash instead of live content."
    )

    @model_validator(mode="after")
    def _paired(self):
        if (self.property is None) != (self.value is None):
            raise ValueError("`property` and `value` are set together or not at all")
        if self.property is None and self.in_trash is None:
            raise ValueError(
                "a search filter needs `property` with `value`, or `in_trash`"
            )
        return self


class SearchBody(BaseModel):
    """The body of a search request.

    API Reference: https://developers.notion.com/reference/post-search
    """

    query: Optional[str] = Field(
        default=None,
        description=(
            "The text to match against page and data source titles. Omit it to list "
            "everything the integration can see."
        ),
    )
    filter: Optional[SearchFilter] = Field(
        default=None, description="Restrict the results to pages or to data sources."
    )
    sort: Optional[SearchSort] = Field(default=None, description="How to order the results.")
    start_cursor: Optional[str] = Field(
        default=None, description="A `next_cursor` from a previous response."
    )
    page_size: Optional[int] = Field(
        default=None, ge=1, le=100, description="How many results to return. Maximum 100."
    )


class SearchRequest(BaseModel):
    """Search the pages and data sources the integration can see.

    Titles only: this does not search page content, and it returns nothing that
    has not been shared with the integration.

    API Reference: https://developers.notion.com/reference/post-search
    """

    body: Annotated[
        SearchBody,
        Field(
            default_factory=SearchBody,
            description="The query and its options. All optional.",
        ),
        Body(),
    ]
