# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Mode

# Enums
MessageListVisibility = Literal["show", "hide"]
LabelListVisibility = Literal["labelShow", "labelShowIfUnread", "labelHide"]
LabelType = Literal["system", "user"]


class Color(BaseModel):
    """
    Color settings for a label.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels#Color
    """

    textColor: Optional[str] = Field(
        None,
        description=(
            "The text color of the label, represented as hex string. This field is required in order to set the color of a label. "
            "Only the following predefined set of color values are allowed: "
            "#000000, #434343, #666666, #999999, #cccccc, #efefef, #f3f3f3, #ffffff, #fb4c2f, #ffad47, #fad165, #16a766, #43d692, "
            "#4a86e8, #a479e2, #f691b3, #f6c5be, #ffe6c7, #fef1d1, #b9e4d0, #c6f3de, #c9daf8, #e4d7f5, #fcdee8, #efa093, #ffd6a2, "
            "#fce8b3, #89d3b2, #a0eac9, #a4c2f4, #d0bcf1, #fbc8d9, #e66550, #ffbc6b, #fcda83, #44b984, #68dfa9, #6d9eeb, #b694e8, "
            "#f7a7c0, #cc3a21, #eaa041, #f2c960, #149e60, #3dc789, #3c78d8, #8e63ce, #e07798, #ac2b16, #cf8933, #d5ae49, #0b804b, "
            "#2a9c68, #285bac, #653e9b, #b65775, #822111, #a46a21, #aa8831, #076239, #1a764d, #1c4587, #41236d, #83334c, #464646, "
            "#e7e7e7, #0d3472, #b6cff5, #0d3b44, #98d7e4, #3d188e, #e3d7ff, #711a36, #fbd3e0, #8a1c0a, #f2b2a8, #7a2e0b, #ffc8af, "
            "#7a4706, #ffdeb5, #594c05, #fbe983, #684e07, #fdedc1, #0b4f30, #b3efd3, #04502e, #a2dcc1, #c2c2c2, #4986e7, #2da2bb, "
            "#b99aff, #994a64, #f691b2, #ff7537, #ffad46, #662e37, #ebdbde, #cca6ac, #094228, #42d692, #16a765"
        ),
    )
    backgroundColor: Optional[str] = Field(
        None,
        description=(
            "The background color represented as hex string #RRGGBB (ex #000000). This field is required in order to set the color of a label. "
            "Only the following predefined set of color values are allowed: "
            "#000000, #434343, #666666, #999999, #cccccc, #efefef, #f3f3f3, #ffffff, #fb4c2f, #ffad47, #fad165, #16a766, #43d692, "
            "#4a86e8, #a479e2, #f691b3, #f6c5be, #ffe6c7, #fef1d1, #b9e4d0, #c6f3de, #c9daf8, #e4d7f5, #fcdee8, #efa093, #ffd6a2, "
            "#fce8b3, #89d3b2, #a0eac9, #a4c2f4, #d0bcf1, #fbc8d9, #e66550, #ffbc6b, #fcda83, #44b984, #68dfa9, #6d9eeb, #b694e8, "
            "#f7a7c0, #cc3a21, #eaa041, #f2c960, #149e60, #3dc789, #3c78d8, #8e63ce, #e07798, #ac2b16, #cf8933, #d5ae49, #0b804b, "
            "#2a9c68, #285bac, #653e9b, #b65775, #822111, #a46a21, #aa8831, #076239, #1a764d, #1c4587, #41236d, #83334c, #464646, "
            "#e7e7e7, #0d3472, #b6cff5, #0d3b44, #98d7e4, #3d188e, #e3d7ff, #711a36, #fbd3e0, #8a1c0a, #f2b2a8, #7a2e0b, #ffc8af, "
            "#7a4706, #ffdeb5, #594c05, #fbe983, #684e07, #fdedc1, #0b4f30, #b3efd3, #04502e, #a2dcc1, #c2c2c2, #4986e7, #2da2bb, "
            "#b99aff, #994a64, #f691b2, #ff7537, #ffad46, #662e37, #ebdbde, #cca6ac, #094228, #42d692, #16a765"
        ),
    )

    @model_validator(mode="after")
    def _colors_come_as_a_pair(self) -> Color:
        """Both fields are documented as required to set a label's color.

        Gmail answers a half-set color with a 400, and the model cannot tell
        that from the label id being wrong. Named locally, it can.
        """
        if (self.textColor is None) != (self.backgroundColor is None):
            raise ValueError(
                "textColor and backgroundColor are both required to set a label's color."
            )
        return self


class ListLabelsResponse(BaseModel):
    """
    Response model for users.labels.list.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/list
    """

    labels: Annotated[
        Optional[List[Label]],
        Field(
            None,
            description="List of labels. Note that each label resource only contains an id, name, messageListVisibility, labelListVisibility, and type.",
        ),
        Mode("response_only"),
    ]


class Label(BaseModel):
    """
    Labels are used to categorize messages and threads within the user's mailbox.
    The maximum number of labels supported for a user's mailbox is 10,000.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels#Label
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The immutable ID of the label."),
        Mode("response_only"),
    ]
    name: str = Field(..., description="The display name of the label.")
    messageListVisibility: Optional[MessageListVisibility] = Field(
        None,
        description="The visibility of messages with this label in the message list in the Gmail web interface.",
    )
    labelListVisibility: Optional[LabelListVisibility] = Field(
        None,
        description="The visibility of the label in the label list in the Gmail web interface.",
    )
    type: Annotated[
        Optional[LabelType],
        Field(
            None,
            description=(
                "The owner type for the label. User labels are created by the user and can be modified and deleted by the user "
                "and can be applied to any message or thread. System labels are internally created and cannot be added, modified, "
                "or deleted. System labels may be able to be applied to or removed from messages and threads under some circumstances "
                "but this is not guaranteed. For example, users can apply and remove the INBOX and UNREAD labels from messages and threads, "
                "but cannot apply or remove the DRAFTS or SENT labels from messages or threads."
            ),
        ),
        Mode("response_only"),
    ]
    messagesTotal: Annotated[
        Optional[int],
        Field(None, description="The total number of messages with the label."),
        Mode("response_only"),
    ]
    messagesUnread: Annotated[
        Optional[int],
        Field(None, description="The number of unread messages with the label."),
        Mode("response_only"),
    ]
    threadsTotal: Annotated[
        Optional[int],
        Field(None, description="The total number of threads with the label."),
        Mode("response_only"),
    ]
    threadsUnread: Annotated[
        Optional[int],
        Field(None, description="The number of unread threads with the label."),
        Mode("response_only"),
    ]
    color: Optional[Color] = Field(
        None,
        description="The color to assign to the label. Color is only available for labels that have their type set to user.",
    )


ListLabelsResponse.model_rebuild()
