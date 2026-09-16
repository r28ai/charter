"""Request schemas for notifications, favorites and saved views.

These are the three things that make Linear personal to whoever is holding the
API key: what they have been told about, what they have starred, and the filters
they have saved.

A **favorite** takes exactly one target out of twenty-odd possibilities, the
same shape as a comment's parent. A **custom view** is a saved filter, and its
``filter_data`` is an ``IssueFilter`` — the same type ``issues_list`` accepts,
so a view can be read here and its filter replayed there.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.linear.types.common import (
    InitiativeTab,
    PageVariables,
    PaginationOrderBy,
    PipelineTab,
    ProjectTab,
)
from charter.packs.linear.types.filters import (
    FeedItemFilter,
    InitiativeFilter,
    IssueFilter,
    ProjectFilter,
)
from charter.types import Body

__all__ = [
    "NotificationsListRequest",
    "NotificationGetRequest",
    "NotificationUpdateRequest",
    "NotificationArchiveRequest",
    "NotificationUnarchiveRequest",
    "NotificationMarkReadAllRequest",
    "FavoritesListRequest",
    "FavoriteCreateRequest",
    "FavoriteUpdateRequest",
    "FavoriteDeleteRequest",
    "CustomViewsListRequest",
    "CustomViewGetRequest",
    "CustomViewCreateRequest",
    "CustomViewDeleteRequest",
]

# What a favorite can point at. Enumerated once, so the validator and the
# message it raises cannot drift from the fields above them.
_NOTIFICATION_ENTITIES = (
    "id",
    "issue_id",
    "project_id",
    "project_update_id",
    "initiative_id",
    "initiative_update_id",
    "oauth_client_approval_id",
)

_FAVORITE_TARGETS = (
    "issue_id",
    "project_id",
    "document_id",
    "cycle_id",
    "initiative_id",
    "custom_view_id",
    "customer_id",
    "label_id",
    "project_label_id",
    "team_id",
    "user_id",
    "folder_name",
    "dashboard_id",
    "facet_id",
    "live_folder_preset",
    "predefined_view_type",
    "pull_request_id",
    "release_id",
    "release_note_id",
    "release_pipeline_id",
    "workflow_definition_id",
)


# -----------------------------------------------------
# notifications
# -----------------------------------------------------


class NotificationsListVariables(PageVariables):
    """Variables for the ``notifications`` connection."""

    include_archived: Optional[bool] = Field(
        default=None, description="Include archived notifications in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class NotificationsListRequest(BaseModel):
    """Read the authenticated user's notifications."""

    variables: Annotated[
        NotificationsListVariables,
        Field(default_factory=NotificationsListVariables, description="Paging."),
        Body(envelop=True),
    ]


class NotificationGetVariables(BaseModel):
    """Variables for the ``notification`` query."""

    id: str = Field(..., description="The notification's UUID.")


class NotificationGetRequest(BaseModel):
    """Get one notification."""

    variables: Annotated[
        NotificationGetVariables,
        Field(..., description="Which notification to fetch."),
        Body(envelop=True),
    ]


class NotificationUpdateInput(BaseModel):
    """The fields ``notificationUpdate`` changes. All optional.

    Marking one read is ``read_at`` set to a timestamp; marking it unread is the
    same field set to null, which this schema cannot express — use
    ``notification_mark_read_all`` or Linear's own UI for that.
    """

    read_at: Optional[str] = Field(
        None,
        description=(
            "The time at which the notification was marked as read, as an ISO 8601 "
            "timestamp."
        ),
    )
    snoozed_until_at: Optional[str] = Field(
        None,
        description=(
            "The time until which the notification is snoozed, as an ISO 8601 "
            "timestamp."
        ),
    )
    initiative_update_id: Optional[str] = Field(
        None, description="The id of the initiative update related to the notification."
    )
    project_update_id: Optional[str] = Field(
        None, description="The id of the project update related to the notification."
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> NotificationUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("notificationUpdate needs at least one field to change.")
        return self


class NotificationUpdateVariables(BaseModel):
    """Variables for the ``notificationUpdate`` mutation."""

    id: str = Field(..., description="The notification's UUID.")
    input: NotificationUpdateInput = Field(..., description="The fields to change.")


class NotificationUpdateRequest(BaseModel):
    """Mark a notification read, or snooze it."""

    variables: Annotated[
        NotificationUpdateVariables,
        Field(..., description="The notification to update."),
        Body(envelop=True),
    ]


class NotificationIdVariables(BaseModel):
    """Variables for the notification mutations that take only an id."""

    id: str = Field(..., description="The notification's UUID.")


class NotificationArchiveRequest(BaseModel):
    """Archive a notification."""

    variables: Annotated[
        NotificationIdVariables,
        Field(..., description="The notification to archive."),
        Body(envelop=True),
    ]


class NotificationUnarchiveRequest(BaseModel):
    """Restore an archived notification."""

    variables: Annotated[
        NotificationIdVariables,
        Field(..., description="The notification to restore."),
        Body(envelop=True),
    ]


class NotificationEntityInput(BaseModel):
    """Which thing's notifications to act on.

    Exactly one must be given.
    """

    id: Optional[str] = Field(None, description="The id of the notification.")
    issue_id: Optional[str] = Field(None, description="The id of the issue.")
    project_id: Optional[str] = Field(None, description="The id of the project.")
    project_update_id: Optional[str] = Field(
        None, description="The id of the project update."
    )
    initiative_id: Optional[str] = Field(None, description="The id of the initiative.")
    initiative_update_id: Optional[str] = Field(
        None, description="The id of the initiative update."
    )
    oauth_client_approval_id: Optional[str] = Field(
        None, description="The id of the OAuth client approval related to the notification."
    )

    @model_validator(mode="after")
    def _exactly_one_entity(self) -> NotificationEntityInput:
        named = [f for f in _NOTIFICATION_ENTITIES if getattr(self, f) is not None]
        if len(named) != 1:
            raise ValueError(
                "Name exactly one entity. Give one of "
                + ", ".join(_NOTIFICATION_ENTITIES)
                + (f"; got {', '.join(named)}." if named else "; none was given.")
            )
        return self


class NotificationMarkReadAllVariables(BaseModel):
    """Variables for the ``notificationMarkReadAll`` mutation.

    This is not "mark my whole inbox read". Linear scopes it to one entity —
    every notification raised by one issue, project or initiative — and both the
    entity and the timestamp are required.
    """

    input: NotificationEntityInput = Field(
        ..., description="Whose notifications to mark as read."
    )
    read_at: str = Field(
        ...,
        description=(
            "The time to record as the read time, as an ISO 8601 timestamp. "
            "Notifications created after it stay unread."
        ),
    )


class NotificationMarkReadAllRequest(BaseModel):
    """Mark every notification on one issue, project or initiative as read."""

    variables: Annotated[
        NotificationMarkReadAllVariables,
        Field(..., description="Whose notifications to mark read, and when."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# favorites
# -----------------------------------------------------


class FavoritesListRequest(BaseModel):
    """List what the authenticated user has starred."""

    variables: Annotated[
        PageVariables,
        Field(default_factory=PageVariables, description="Paging."),
        Body(envelop=True),
    ]


class FavoriteCreateInput(BaseModel):
    """The input to ``favoriteCreate``.

    Exactly one target must be given.
    """

    issue_id: Optional[str] = Field(None, description="The identifier of the issue to favorite.")
    project_id: Optional[str] = Field(
        None, description="The identifier of the project to favorite."
    )
    document_id: Optional[str] = Field(
        None, description="The identifier of the document to favorite."
    )
    cycle_id: Optional[str] = Field(None, description="The identifier of the cycle to favorite.")
    initiative_id: Optional[str] = Field(
        None, description="The identifier of the initiative to favorite."
    )
    custom_view_id: Optional[str] = Field(
        None, description="The identifier of the custom view to favorite."
    )
    customer_id: Optional[str] = Field(
        None, description="The identifier of the customer to favorite."
    )
    label_id: Optional[str] = Field(
        None, description="The identifier of the issue label to favorite."
    )
    project_label_id: Optional[str] = Field(
        None, description="The identifier of the project label to favorite."
    )
    team_id: Optional[str] = Field(None, description="The identifier of the team to favorite.")
    user_id: Optional[str] = Field(None, description="The identifier of the user to favorite.")
    folder_name: Optional[str] = Field(
        None, description="The name of a favorite folder to create."
    )
    parent_id: Optional[str] = Field(
        None, description="The identifier of the favorite folder to file this under."
    )
    sort_order: Optional[float] = Field(
        None, description="The position of the item in the favorites list."
    )
    dashboard_id: Optional[str] = Field(
        None, description="The identifier of the dashboard to favorite."
    )
    facet_id: Optional[str] = Field(
        None, description="The identifier of the facet to favorite."
    )
    live_folder_preset: Optional[str] = Field(
        None, description="The predefined live folder to create."
    )
    predefined_view_type: Optional[str] = Field(
        None, description="The type of the predefined view to favorite."
    )
    predefined_view_team_id: Optional[str] = Field(
        None, description="The identifier of team for the predefined view to favorite."
    )
    pull_request_id: Optional[str] = Field(
        None, description="The identifier of the pull request to favorite."
    )
    release_id: Optional[str] = Field(
        None, description="The identifier of the release to favorite."
    )
    release_note_id: Optional[str] = Field(
        None, description="The identifier of the release note to favorite."
    )
    release_pipeline_id: Optional[str] = Field(
        None, description="The identifier of the release pipeline to favorite."
    )
    workflow_definition_id: Optional[str] = Field(
        None, description="The identifier of the loop to favorite."
    )
    initiative_tab: Optional[InitiativeTab] = Field(
        None, description="The tab of the initiative to favorite."
    )
    project_tab: Optional[ProjectTab] = Field(
        None, description="The tab of the project to favorite."
    )
    pipeline_tab: Optional[PipelineTab] = Field(
        None, description="The tab of the release pipeline to favorite."
    )
    id: Optional[str] = Field(
        None,
        description="The identifier. If none is provided, the backend will generate one.",
    )

    @model_validator(mode="after")
    def _exactly_one_target(self) -> FavoriteCreateInput:
        named = [f for f in _FAVORITE_TARGETS if getattr(self, f) is not None]
        if len(named) != 1:
            raise ValueError(
                "A favorite needs exactly one target. Give one of "
                + ", ".join(_FAVORITE_TARGETS)
                + (f"; got {', '.join(named)}." if named else "; none was given.")
            )
        return self


class FavoriteCreateVariables(BaseModel):
    """Variables for the ``favoriteCreate`` mutation."""

    input: FavoriteCreateInput = Field(..., description="What to favorite.")


class FavoriteCreateRequest(BaseModel):
    """Star an issue, project, document, view or team."""

    variables: Annotated[
        FavoriteCreateVariables,
        Field(..., description="What to favorite."),
        Body(envelop=True),
    ]


class FavoriteUpdateInput(BaseModel):
    """The fields ``favoriteUpdate`` changes. All optional."""

    folder_name: Optional[str] = Field(
        None, description="The name of the favorite folder."
    )
    parent_id: Optional[str] = Field(
        None, description="The identifier of the favorite folder to file this under."
    )
    sort_order: Optional[float] = Field(
        None, description="The position of the item in the favorites list."
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> FavoriteUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("favoriteUpdate needs at least one field to change.")
        return self


class FavoriteUpdateVariables(BaseModel):
    """Variables for the ``favoriteUpdate`` mutation."""

    id: str = Field(..., description="The favorite's UUID.")
    input: FavoriteUpdateInput = Field(..., description="The fields to change.")


class FavoriteUpdateRequest(BaseModel):
    """Move a favorite, or rename its folder."""

    variables: Annotated[
        FavoriteUpdateVariables,
        Field(..., description="The favorite to update."),
        Body(envelop=True),
    ]


class FavoriteDeleteVariables(BaseModel):
    """Variables for the ``favoriteDelete`` mutation."""

    id: str = Field(..., description="The favorite's UUID.")


class FavoriteDeleteRequest(BaseModel):
    """Unstar something."""

    variables: Annotated[
        FavoriteDeleteVariables,
        Field(..., description="The favorite to remove."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# custom views
# -----------------------------------------------------


class CustomViewsListVariables(PageVariables):
    """Variables for the ``customViews`` connection."""

    include_archived: Optional[bool] = Field(
        default=None, description="Include archived views in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class CustomViewsListRequest(BaseModel):
    """List the workspace's saved views."""

    variables: Annotated[
        CustomViewsListVariables,
        Field(default_factory=CustomViewsListVariables, description="Paging."),
        Body(envelop=True),
    ]


class CustomViewGetVariables(BaseModel):
    """Variables for the ``customView`` query."""

    id: str = Field(..., description="The view's UUID.")


class CustomViewGetRequest(BaseModel):
    """Get one saved view, with the filter it holds."""

    variables: Annotated[
        CustomViewGetVariables,
        Field(..., description="Which view to fetch."),
        Body(envelop=True),
    ]


class CustomViewCreateInput(BaseModel):
    """The input to ``customViewCreate``.

    ``filter_data`` is an ``IssueFilter`` — the same type ``issues_list``
    accepts, so a filter that works there can be saved here unchanged.
    """

    name: str = Field(..., description="The name of the custom view.")
    description: Optional[str] = Field(
        None, description="The description of the custom view."
    )
    filter_data: Optional[IssueFilter] = Field(
        None, description="The filter applied to issues in the custom view."
    )
    project_filter_data: Optional[ProjectFilter] = Field(
        None, description="The filter applied to projects in the custom view."
    )
    team_id: Optional[str] = Field(
        None,
        description=(
            "The team associated with the custom view. Omit it for a view the "
            "whole workspace shares."
        ),
    )
    project_id: Optional[str] = Field(
        None, description="The project associated with the custom view."
    )
    owner_id: Optional[str] = Field(
        None, description="The owner of the custom view."
    )
    shared: Optional[bool] = Field(
        None, description="Whether the custom view is shared with everyone in the organization."
    )
    icon: Optional[str] = Field(None, description="The icon of the custom view.")
    color: Optional[str] = Field(
        None, description="The color of the icon, as a hex string."
    )
    initiative_id: Optional[str] = Field(
        None, description="The id of the initiative associated with the custom view."
    )
    initiative_filter_data: Optional[InitiativeFilter] = Field(
        None,
        description="[ALPHA] The initiative filter applied to issues in the custom view.",
    )
    feed_item_filter_data: Optional[FeedItemFilter] = Field(
        None, description="The feed item filter applied to issues in the custom view."
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class CustomViewCreateVariables(BaseModel):
    """Variables for the ``customViewCreate`` mutation."""

    input: CustomViewCreateInput = Field(..., description="The view to create.")


class CustomViewCreateRequest(BaseModel):
    """Save a filter as a view."""

    variables: Annotated[
        CustomViewCreateVariables,
        Field(..., description="The view to create."),
        Body(envelop=True),
    ]


class CustomViewDeleteVariables(BaseModel):
    """Variables for the ``customViewDelete`` mutation."""

    id: str = Field(..., description="The view's UUID.")


class CustomViewDeleteRequest(BaseModel):
    """Delete a saved view."""

    variables: Annotated[
        CustomViewDeleteVariables,
        Field(..., description="The view to delete."),
        Body(envelop=True),
    ]
