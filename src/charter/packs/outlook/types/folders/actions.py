# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for mail folders and mail search folders.

Listing and creating folders are served at the mailbox root
(``/me/mailFolders``) and under a parent (``/me/mailFolders/{id}/childFolders``)
with the same parameters, so each is one tool with an optional
``parent_folder_id``. A search folder is a folder too: it is created and
updated through the same operations, told apart by its ``@odata.type``, so the
bodies here are a folder or a search folder.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field, model_validator

from charter.types import Body, Path, Query, WireName
from charter.types.model import PackModel

from .._common import FOLDER_ID_DESCRIPTION
from .._odata import Count, DeltaLink, Expand, Filter, NextLink, Select
from ..common import MultiValueLegacyExtendedProperty, SingleValueLegacyExtendedProperty

__all__ = [
    "MailFolderCreate",
    "MailFolderIdRequest",
    "MailFolderUpdate",
    "MailFoldersCreateRequest",
    "MailFoldersDeltaRequest",
    "MailFoldersGetRequest",
    "MailFoldersListRequest",
    "MailFoldersMoveRequest",
    "MailFoldersUpdateRequest",
    "MailSearchFolder",
    "MailSearchFolderUpdate",
]

FolderId = Annotated[str, Field(..., description=FOLDER_ID_DESCRIPTION), Path()]

_PARENT = (
    "The parent folder, as a folder ID or a well-known folder name. Well-known names work "
    "regardless of the locale of the user's mailbox."
)

_SEARCH_FOLDER = "microsoft.graph.mailSearchFolder"

_INCLUDE_NESTED = (
    "Indicates how the mailbox folder hierarchy should be traversed in the search. "
    "`true` means that a deep search should be done to include child folders in the "
    "hierarchy of each folder explicitly specified in sourceFolderIds. `false` means "
    "a shallow search of only each of the folders explicitly specified in "
    "sourceFolderIds."
)
_SOURCE_FOLDERS = "The mailbox folders that should be mined."
_FILTER_QUERY = "The OData query to filter the messages."


class MailFoldersListRequest(PackModel):
    """Get the mail folders directly under the root folder, or under another folder.

    By default, this operation doesn't return hidden folders. It doesn't return
    every folder in a mailbox, only the children of one: each child folder must
    be traversed separately.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-list-mailfolders?view=graph-rest-1.0
    """

    parent_folder_id: Annotated[
        Optional[str],
        Field(None, description=_PARENT + " Omit it for the folders under the root."),
        Path(),
    ]
    include_hidden_folders: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "To return a list of all mailFolders including those that are hidden (their "
                "isHidden property is true), specify the `includeHiddenFolders` query "
                "parameter as `true`."
            ),
        ),
        Query(),
    ]
    top: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            description=(
                "Use the $top query parameter to specify the number of items to be included "
                "in the result. If a collection exceeds the default page size (10 items), the "
                "next page is returned as next_link."
            ),
        ),
        Query(),
        WireName("$top"),
    ]
    filter: Filter
    select: Select
    count: Count
    next_link: NextLink


class MailFoldersGetRequest(PackModel):
    """Retrieve the properties and relationships of a message folder object.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailfolder-get?view=graph-rest-1.0
    """

    folder_id: FolderId
    select: Select
    expand: Expand


class MailFolderIdRequest(PackModel):
    """A request that names one folder and sends nothing else.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/mailfolder
    """

    folder_id: FolderId


class MailFolderCreate(PackModel):
    """``displayName`` and ``isHidden`` are the only writable properties for a mailFolder object.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-post-mailfolders?view=graph-rest-1.0
    """

    display_name: str = Field(..., description="The display name of the new folder.")
    is_hidden: Optional[bool] = Field(
        None,
        description=(
            "Indicates whether the new folder is hidden. The default value is `false`. "
            "Setting the property is optional. Once set, you cannot update this property."
        ),
    )


class MailSearchFolder(PackModel):
    """A virtual folder in the user's mailbox that contains all the email items matching specified search criteria.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailsearchfolder-post?view=graph-rest-1.0
    """

    odata_type: Annotated[
        Literal["microsoft.graph.mailSearchFolder"],
        Field(_SEARCH_FOLDER, description="The type of folder to be created."),
        WireName("@odata.type"),
    ]
    display_name: str = Field(..., description="The display name of the new folder.")
    include_nested_folders: Optional[bool] = Field(None, description=_INCLUDE_NESTED)
    source_folder_ids: List[str] = Field(..., description=_SOURCE_FOLDERS)
    filter_query: str = Field(..., description=_FILTER_QUERY)


class MailFoldersCreateRequest(PackModel):
    """Create a mail folder or a mail search folder, at the root or under a parent folder.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailfolder-post-childfolders?view=graph-rest-1.0
    """

    parent_folder_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                _PARENT + " Omit it to create the folder under the root. A search folder "
                "goes under a parent, usually `searchfolders`."
            ),
        ),
        Path(),
    ]
    # MailFolderCreate first: it is the narrower of the two, so a plain folder
    # never reads as a search folder that forgot its query.
    folder: Annotated[
        Union[MailFolderCreate, MailSearchFolder],
        Field(..., description="The new folder, or the new search folder."),
        Body(),
    ]

    @model_validator(mode="after")
    def _a_search_folder_has_a_parent(self) -> MailFoldersCreateRequest:
        # Read off the type it declares, not its class: the view a model fills
        # in validates against its own copy of each model.
        searching = getattr(self.folder, "odata_type", None) == _SEARCH_FOLDER
        if searching and self.parent_folder_id is None:
            raise ValueError(
                "a search folder is created under a parent folder: set parent_folder_id, "
                "usually to searchfolders"
            )
        return self


class MailFolderUpdate(PackModel):
    """The properties of a mailFolder an update can change.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailfolder-update?view=graph-rest-1.0
    """

    display_name: Optional[str] = Field(None, description="The mailFolder's display name.")
    single_value_extended_properties: Optional[List[SingleValueLegacyExtendedProperty]] = Field(
        None, description="An array of one or more single-valued extended properties."
    )
    multi_value_extended_properties: Optional[List[MultiValueLegacyExtendedProperty]] = Field(
        None, description="An array of one or more multi-valued extended properties."
    )


class MailSearchFolderUpdate(PackModel):
    """The writable properties of a mailSearchFolder, all optional.

    Written out rather than derived with ``partial_of``, which relaxes every
    field to ``None`` — and ``@odata.type`` is the one field an update must still
    send, since it is what tells Graph the patch is for a search folder. The
    descriptions are the create body's, through the same constants.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailsearchfolder-update?view=graph-rest-1.0
    """

    odata_type: Annotated[
        Literal["microsoft.graph.mailSearchFolder"],
        Field(_SEARCH_FOLDER, description="The type of folder being updated."),
        WireName("@odata.type"),
    ]
    display_name: Optional[str] = Field(None, description="The display name of the mailFolder.")
    include_nested_folders: Optional[bool] = Field(None, description=_INCLUDE_NESTED)
    source_folder_ids: Optional[List[str]] = Field(None, description=_SOURCE_FOLDERS)
    filter_query: Optional[str] = Field(None, description=_FILTER_QUERY)


class MailFoldersUpdateRequest(PackModel):
    """Update the properties of a mail folder or a mail search folder.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailfolder-update?view=graph-rest-1.0
    """

    folder_id: FolderId
    folder: Annotated[
        Union[MailFolderUpdate, MailSearchFolderUpdate],
        Field(
            ...,
            description=(
                "The values for relevant fields that should be updated: a folder's name or "
                "extended properties, or a search folder's name, source folders or query."
            ),
        ),
        Body(),
    ]


class MailFoldersMoveRequest(PackModel):
    """Move or copy a mailfolder and its contents to another mailfolder.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailfolder-move?view=graph-rest-1.0
    """

    folder_id: FolderId
    destination_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "The folder ID, or a well-known folder name. For a list of supported "
                "well-known folder names, see mailFolder resource type."
            ),
        ),
        Body(),
    ]


class MailFoldersDeltaRequest(PackModel):
    """Get a set of mail folders that have been added, deleted, or removed from the user's mailbox.

    The last page carries a ``delta_link`` instead of a ``next_link``. Pass it
    back as ``next_link`` on a later call to get only what changed since.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailfolder-delta?view=graph-rest-1.0
    """

    select: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "You can use a `$select` query parameter as in any GET request to specify "
                "only the properties your need for best performance. The id property is "
                "always returned."
            ),
        ),
        Query(),
        WireName("$select"),
    ]
    next_link: DeltaLink
