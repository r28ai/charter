# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for the user's master list of Outlook categories.

A category's name is set when it is created and never again, so the create
body takes a name and a colour and the update body takes a colour.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import Field

from charter.types import Body, Path
from charter.types.model import PackModel

from .._odata import Select
from ..common import CategoryColor

__all__ = [
    "CategoriesCreateRequest",
    "CategoriesListRequest",
    "CategoriesUpdateRequest",
    "CategoryCreate",
    "CategoryIdRequest",
    "CategoryUpdate",
]

_COLOR = (
    "A pre-set color constant that characterizes a category, and that is mapped to one of "
    "25 predefined colors: preset0 Red, preset1 Orange, preset2 Brown, preset3 Yellow, "
    "preset4 Green, preset5 Teal, preset6 Olive, preset7 Blue, preset8 Purple, preset9 "
    "Cranberry, preset10 Steel, preset11 DarkSteel, preset12 Gray, preset13 DarkGray, "
    "preset14 Black, preset15 DarkRed, preset16 DarkOrange, preset17 DarkBrown, preset18 "
    "DarkYellow, preset19 DarkGreen, preset20 DarkTeal, preset21 DarkOlive, preset22 "
    "DarkBlue, preset23 DarkPurple, preset24 DarkCranberry; none for no color mapped."
)

CategoryId = Annotated[str, Field(..., description="The ID of the category."), Path()]


class CategoriesListRequest(PackModel):
    """Get all the categories that have been defined for a user.

    No ``$filter``: Graph accepts one here and returns every category anyway,
    which a model reads as "this is the one I asked for". ``$select`` is honoured.

    API Reference: https://learn.microsoft.com/en-us/graph/api/outlookuser-list-mastercategories?view=graph-rest-1.0
    """

    select: Select


class CategoryIdRequest(PackModel):
    """A request that names one category and sends nothing else.

    API Reference: https://learn.microsoft.com/en-us/graph/api/outlookcategory-get?view=graph-rest-1.0
    """

    category_id: CategoryId


class CategoryCreate(PackModel):
    """An outlookCategory, as it is created.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory
    """

    display_name: str = Field(
        ...,
        description=(
            "A unique name that identifies a category in the user's mailbox. After a "
            "category is created, the name cannot be changed."
        ),
    )
    color: Optional[CategoryColor] = Field(None, description=_COLOR)


class CategoriesCreateRequest(PackModel):
    """Create an outlookCategory object in the user's master list of categories.

    API Reference: https://learn.microsoft.com/en-us/graph/api/outlookuser-post-mastercategories?view=graph-rest-1.0
    """

    category: Annotated[
        CategoryCreate,
        Field(..., description="A JSON representation of an outlookCategory object."),
        Body(),
    ]


class CategoryUpdate(PackModel):
    """The writable property, color, of an outlookCategory.

    API Reference: https://learn.microsoft.com/en-us/graph/api/outlookcategory-update?view=graph-rest-1.0
    """

    color: Optional[CategoryColor] = Field(None, description=_COLOR)


class CategoriesUpdateRequest(PackModel):
    """Update the writable property, color, of the specified outlookCategory object.

    You can't modify the displayName property once you have created the category.

    API Reference: https://learn.microsoft.com/en-us/graph/api/outlookcategory-update?view=graph-rest-1.0
    """

    category_id: CategoryId
    category: Annotated[
        CategoryUpdate,
        Field(..., description="The values for relevant fields that should be updated."),
        Body(),
    ]
