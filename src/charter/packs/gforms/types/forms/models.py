# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Resource types for the ``forms`` collection.

Field names, types, enums and descriptions follow the Forms API v1 reference.
Server-set fields carry ``Mode("response_only")``.

Two fields are accepted by one operation and refused by another, and the
resource is not the place to settle that: ``documentTitle`` "can be set on
create, but cannot be modified by a batchUpdate request", and the form
description is one of the fields ``forms.create`` calls disallowed. They carry
``Mode("create")`` and ``Mode("update")``, which the tool's own mode resolves —
so one ``Info`` serves both operations and neither is offered a field the API
would refuse.

Classes are defined leaf-first, so every reference resolves at import.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.gforms.types.feedback import Feedback
from charter.types import ConflictsWith, Mode

__all__ = [
    "Alignment",
    "ChoiceType",
    "EmailCollectionType",
    "FileType",
    "GoToAction",
    "RatingIconType",
    "MediaProperties",
    "Image",
    "Option",
    "ChoiceQuestion",
    "CorrectAnswer",
    "CorrectAnswers",
    "Grading",
    "TextQuestion",
    "ScaleQuestion",
    "DateQuestion",
    "TimeQuestion",
    "FileUploadQuestion",
    "RowQuestion",
    "RatingQuestion",
    "Question",
    "QuestionItem",
    "Grid",
    "QuestionGroupItem",
    "PageBreakItem",
    "TextItem",
    "ImageItem",
    "Video",
    "VideoItem",
    "Item",
    "QuizSettings",
    "FormSettings",
    "Info",
    "PublishState",
    "PublishSettings",
    "Form",
]


# -----------------------------------------------------
# Enums
# -----------------------------------------------------

Alignment = Literal[
    "ALIGNMENT_UNSPECIFIED",
    "LEFT",
    "RIGHT",
    "CENTER",
]
"""Alignment on the page.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Alignment
"""

ChoiceType = Literal[
    "CHOICE_TYPE_UNSPECIFIED",
    "RADIO",
    "CHECKBOX",
    "DROP_DOWN",
]
"""The type of choice.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#ChoiceType
"""

EmailCollectionType = Literal[
    "EMAIL_COLLECTION_TYPE_UNSPECIFIED",
    "DO_NOT_COLLECT",
    "VERIFIED",
    "RESPONDER_INPUT",
]
"""Whether the form collects email addresses from respondents, and how.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#EmailCollectionType
"""

FileType = Literal[
    "FILE_TYPE_UNSPECIFIED",
    "ANY",
    "DOCUMENT",
    "PRESENTATION",
    "SPREADSHEET",
    "DRAWING",
    "PDF",
    "IMAGE",
    "VIDEO",
    "AUDIO",
]
"""File types that can be uploaded to a file upload question.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#FileType
"""

GoToAction = Literal[
    "GO_TO_ACTION_UNSPECIFIED",
    "NEXT_SECTION",
    "RESTART_FORM",
    "SUBMIT_FORM",
]
"""Constants for section navigation.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#GoToAction
"""

RatingIconType = Literal[
    "RATING_ICON_TYPE_UNSPECIFIED",
    "STAR",
    "HEART",
    "THUMB_UP",
]
"""The type of icon to use for the rating.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#RatingIconType
"""


# -----------------------------------------------------
# Media
# -----------------------------------------------------


class MediaProperties(BaseModel):
    """Properties of the media.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#MediaProperties
    """

    alignment: Optional[Alignment] = Field(
        default=None,
        description="Position of the media.",
    )
    width: Optional[int] = Field(
        default=None,
        ge=0,
        le=740,
        description=(
            "The width of the media in pixels. When the media is displayed, it is "
            "scaled to the smaller of this value or the width of the displayed "
            "form. The original aspect ratio of the media is preserved. If a width "
            "is not specified when the media is added to the form, it is set to the "
            "width of the media source. Width must be between 0 and 740, inclusive. "
            "Setting width to 0 or unspecified is only permitted when updating the "
            "media source."
        ),
    )


class Image(BaseModel):
    """Data representing an image.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Image
    """

    content_uri: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. A URI from which you can download the image; this is "
                "valid only for a limited time."
            ),
        ),
    ] = None
    alt_text: Optional[str] = Field(
        default=None,
        description=(
            "A description of the image that is shown on hover and read by screenreaders."
        ),
    )
    properties: Optional[MediaProperties] = Field(
        default=None,
        description="Properties of an image.",
    )
    source_uri: Annotated[
        Optional[str],
        Mode("request_only"),
        Field(
            default=None,
            description=(
                "Input only. The source URI is the URI used to insert the image. The "
                "source URI can be empty when fetched. Exactly one image source field "
                "must be set when creating new images."
            ),
        ),
    ] = None


class Video(BaseModel):
    """Data representing a video.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Video
    """

    youtube_uri: str = Field(
        ...,
        description="Required. A YouTube URI.",
    )
    properties: Optional[MediaProperties] = Field(
        default=None,
        description="Properties of a video.",
    )


# -----------------------------------------------------
# Questions
# -----------------------------------------------------


class Option(BaseModel):
    """An option for a Choice question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Option
    """

    value: str = Field(
        ...,
        description="Required. The choice as presented to the user.",
    )
    image: Optional[Image] = Field(
        default=None,
        description="Display image as an option.",
    )
    is_other: Optional[bool] = Field(
        default=None,
        description=(
            'Whether the option is "other". Currently only applies to `RADIO` and '
            "`CHECKBOX` choice types, but is not allowed in a `QuestionGroupItem`."
        ),
    )
    go_to_action: Annotated[
        Optional[GoToAction],
        Field(
            default=None,
            description=(
                "Section navigation type. Which section to go to if this option is "
                "selected. Currently only applies to `RADIO` and `SELECT` choice type, "
                "but is not allowed in a `QuestionGroupItem`."
            ),
        ),
        ConflictsWith(
            "go_to_section_id",
            reason=("An option navigates by action or by section id, never both. Drop one."),
        ),
    ] = None
    go_to_section_id: Optional[str] = Field(
        default=None,
        description="Item ID of section header to go to.",
    )


class ChoiceQuestion(BaseModel):
    """A radio/checkbox/dropdown question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#ChoiceQuestion
    """

    type: ChoiceType = Field(
        ...,
        description="Required. The type of choice question.",
    )
    options: List[Option] = Field(
        ...,
        description="Required. List of options that a respondent must choose from.",
    )
    shuffle: Optional[bool] = Field(
        default=None,
        description=(
            "Whether the options should be displayed in random order for different "
            "instances of the quiz. This is often used to prevent cheating by "
            "respondents who might be looking at another respondent's screen, or to "
            "address bias in a survey that might be introduced by always putting the "
            "same options first or last."
        ),
    )


class TextQuestion(BaseModel):
    """A text-based question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#TextQuestion
    """

    paragraph: Optional[bool] = Field(
        default=None,
        description=(
            "Whether the question is a paragraph question or not. If not, the "
            "question is a short text question."
        ),
    )


class ScaleQuestion(BaseModel):
    """A scale question. The user has a range of numeric values to choose from.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#ScaleQuestion
    """

    low: int = Field(
        ...,
        description="Required. The lowest possible value for the scale.",
    )
    high: int = Field(
        ...,
        description="Required. The highest possible value for the scale.",
    )
    low_label: Optional[str] = Field(
        default=None,
        description="The label to display describing the lowest point on the scale.",
    )
    high_label: Optional[str] = Field(
        default=None,
        description="The label to display describing the highest point on the scale.",
    )


class DateQuestion(BaseModel):
    """A date question. Date questions default to just month + day.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#DateQuestion
    """

    include_time: Optional[bool] = Field(
        default=None,
        description="Whether to include the time as part of the question.",
    )
    include_year: Optional[bool] = Field(
        default=None,
        description="Whether to include the year as part of the question.",
    )


class TimeQuestion(BaseModel):
    """A time question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#TimeQuestion
    """

    duration: Optional[bool] = Field(
        default=None,
        description=(
            "`true` if the question is about an elapsed time. Otherwise it is about a time of day."
        ),
    )


class FileUploadQuestion(BaseModel):
    """A file upload question.

    The API currently does not support creating file upload questions; one that
    already exists comes back on ``forms.get`` and can be moved or deleted.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#FileUploadQuestion
    """

    folder_id: str = Field(
        ...,
        description=("Required. The ID of the Drive folder where uploaded files are stored."),
    )
    types: Optional[List[FileType]] = Field(
        default=None,
        description="File types accepted by this question.",
    )
    max_files: Optional[int] = Field(
        default=None,
        description=(
            "Maximum number of files that can be uploaded for this question in a single response."
        ),
    )
    max_file_size: Optional[str] = Field(
        default=None,
        description=(
            "Maximum number of bytes allowed for any single file uploaded to this "
            "question. An int64, which this API carries as a string."
        ),
    )


class RowQuestion(BaseModel):
    """Configuration for a question that is part of a question group.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#RowQuestion
    """

    title: str = Field(
        ...,
        description="Required. The title for the single row in the `QuestionGroupItem`.",
    )


class RatingQuestion(BaseModel):
    """A rating question. The user has a range of icons to choose from.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#RatingQuestion
    """

    rating_scale_level: int = Field(
        ...,
        description="Required. The rating scale level of the rating question.",
    )
    icon_type: RatingIconType = Field(
        ...,
        description="Required. The icon type to use for the rating.",
    )


# -----------------------------------------------------
# Grading
# -----------------------------------------------------


class CorrectAnswer(BaseModel):
    """A single correct answer for a question.

    For multiple-valued (``CHECKBOX``) questions, several ``CorrectAnswer``s may
    be needed to represent a single correct response option.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#CorrectAnswer
    """

    value: str = Field(
        ...,
        description=(
            "Required. The correct answer value. See the documentation for "
            "`TextAnswer.value` for details on how various value types are formatted."
        ),
    )


class CorrectAnswers(BaseModel):
    """The answer key for a question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#CorrectAnswers
    """

    answers: Optional[List[CorrectAnswer]] = Field(
        default=None,
        description=(
            "A list of correct answers. A quiz response can be automatically graded "
            "based on these answers. For single-valued questions, a response is "
            "marked correct if it matches any value in this list (in other words, "
            "multiple correct answers are possible). For multiple-valued (`CHECKBOX`) "
            "questions, a response is marked correct if it contains exactly the "
            "values in this list."
        ),
    )


class Grading(BaseModel):
    """Grading for a single question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Grading
    """

    point_value: int = Field(
        ...,
        ge=0,
        description=(
            "Required. The maximum number of points a respondent can automatically "
            "get for a correct answer. This must not be negative."
        ),
    )
    correct_answers: CorrectAnswers = Field(
        ...,
        description=(
            "Required. The answer key for the question. Responses are automatically "
            "graded based on this field."
        ),
    )
    when_right: Optional[Feedback] = Field(
        default=None,
        description=(
            "The feedback displayed for correct responses. This feedback can only be "
            "set for multiple choice questions that have correct answers provided."
        ),
    )
    when_wrong: Optional[Feedback] = Field(
        default=None,
        description=(
            "The feedback displayed for incorrect responses. This feedback can only "
            "be set for multiple choice questions that have correct answers provided."
        ),
    )
    general_feedback: Optional[Feedback] = Field(
        default=None,
        description=(
            "The feedback displayed for all answers. This is commonly used for short "
            "answer questions when a quiz owner wants to quickly give respondents "
            "some sense of whether they answered the question correctly before "
            "they've had a chance to officially grade the response. General feedback "
            "cannot be set for automatically graded multiple choice questions."
        ),
    )


# -----------------------------------------------------
# Items
# -----------------------------------------------------

# The members of each `kind` oneof, kept as module constants rather than class
# attributes: pydantic claims a leading-underscore name in a model body as a
# private attribute, so `Question._KINDS` would read back a descriptor. The
# validators close over these, which is also what carries them into the derived
# LLM view.
_QUESTION_KINDS = (
    "choice_question",
    "text_question",
    "scale_question",
    "date_question",
    "time_question",
    "file_upload_question",
    "row_question",
    "rating_question",
)

_ITEM_KINDS = (
    "question_item",
    "question_group_item",
    "page_break_item",
    "text_item",
    "image_item",
    "video_item",
)


class Question(BaseModel):
    """Any question. The specific type of question is known by its ``kind``.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Question
    """

    question_id: Optional[str] = Field(
        default=None,
        description=(
            "Read only. The question ID. On creation, it can be provided but the ID "
            "must not be already used in the form. If not provided, a new ID is "
            "assigned."
        ),
    )
    required: Optional[bool] = Field(
        default=None,
        description=(
            "Whether the question must be answered in order for a respondent to "
            "submit their response."
        ),
    )
    grading: Optional[Grading] = Field(
        default=None,
        description="Grading setup for the question.",
    )
    choice_question: Optional[ChoiceQuestion] = Field(
        default=None,
        description="A respondent can choose from a pre-defined set of options.",
    )
    text_question: Optional[TextQuestion] = Field(
        default=None,
        description="A respondent can enter a free text response.",
    )
    scale_question: Optional[ScaleQuestion] = Field(
        default=None,
        description="A respondent can choose a number from a range.",
    )
    date_question: Optional[DateQuestion] = Field(
        default=None,
        description="A respondent can enter a date.",
    )
    time_question: Optional[TimeQuestion] = Field(
        default=None,
        description="A respondent can enter a time.",
    )
    file_upload_question: Optional[FileUploadQuestion] = Field(
        default=None,
        description="A respondent can upload one or more files.",
    )
    row_question: Optional[RowQuestion] = Field(
        default=None,
        description="A row of a `QuestionGroupItem`.",
    )
    rating_question: Optional[RatingQuestion] = Field(
        default=None,
        description="A respondent can choose a rating from a pre-defined set of icons.",
    )

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> Question:
        provided = [name for name in _QUESTION_KINDS if getattr(self, name) is not None]
        if len(provided) != 1:
            raise ValueError(
                "Exactly one question kind must be set on Question "
                f"({', '.join(_QUESTION_KINDS)}), found: {provided}"
            )
        return self


class QuestionItem(BaseModel):
    """A form item containing a single question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#QuestionItem
    """

    question: Question = Field(
        ...,
        description="Required. The displayed question.",
    )
    image: Optional[Image] = Field(
        default=None,
        description="The image displayed within the question.",
    )


class Grid(BaseModel):
    """A grid of choices (radio or check boxes) with each row constituting a
    separate question. Each row has the same choices, which are shown as the
    columns.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Grid
    """

    columns: ChoiceQuestion = Field(
        ...,
        description=(
            "Required. The choices shared by each question in the grid. In other "
            "words, the values of the columns. Only `CHECK_BOX` and `RADIO` choices "
            "are allowed."
        ),
    )
    shuffle_questions: Optional[bool] = Field(
        default=None,
        description=(
            "If `true`, the questions are randomly ordered. In other words, the rows "
            "appear in a different order for every respondent."
        ),
    )


class QuestionGroupItem(BaseModel):
    """Defines a question that comprises multiple questions grouped together.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#QuestionGroupItem
    """

    questions: List[Question] = Field(
        ...,
        description=(
            "Required. A list of questions that belong in this question group. A "
            "question must only belong to one group. The `kind` of the group may "
            "affect what types of questions are allowed."
        ),
    )
    image: Optional[Image] = Field(
        default=None,
        description=("The image displayed within the question group above the specific questions."),
    )
    grid: Optional[Grid] = Field(
        default=None,
        description=(
            "The question group is a grid with rows of multiple choice questions that "
            "share the same options. When `grid` is set, all questions in the group "
            "must be of kind `row`."
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> QuestionGroupItem:
        if self.grid is None:
            raise ValueError("QuestionGroupItem requires its `kind` union: set `grid`.")
        return self


class PageBreakItem(BaseModel):
    """A page break. The title and description of this item are shown at the top
    of the new page.

    This type has no fields.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#PageBreakItem
    """


class TextItem(BaseModel):
    """A text item.

    This type has no fields.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#TextItem
    """


class ImageItem(BaseModel):
    """An item containing an image.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#ImageItem
    """

    image: Image = Field(
        ...,
        description="Required. The image displayed in the item.",
    )


class VideoItem(BaseModel):
    """An item containing a video.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#VideoItem
    """

    video: Video = Field(
        ...,
        description="Required. The video displayed in the item.",
    )
    caption: Optional[str] = Field(
        default=None,
        description="The text displayed below the video.",
    )


class Item(BaseModel):
    """A single item of the form. ``kind`` defines which kind of item it is.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Item
    """

    item_id: Optional[str] = Field(
        default=None,
        description=(
            "The item ID. On creation, it can be provided but the ID must not be "
            "already used in the form. If not provided, a new ID is assigned."
        ),
    )
    title: Optional[str] = Field(
        default=None,
        description="The title of the item.",
    )
    description: Optional[str] = Field(
        default=None,
        description="The description of the item.",
    )
    question_item: Optional[QuestionItem] = Field(
        default=None,
        description="Poses a question to the user.",
    )
    question_group_item: Optional[QuestionGroupItem] = Field(
        default=None,
        description="Poses one or more questions to the user with a single major prompt.",
    )
    page_break_item: Optional[PageBreakItem] = Field(
        default=None,
        description="Starts a new page with a title.",
    )
    text_item: Optional[TextItem] = Field(
        default=None,
        description="Displays a title and description on the page.",
    )
    image_item: Optional[ImageItem] = Field(
        default=None,
        description="Displays an image on the page.",
    )
    video_item: Optional[VideoItem] = Field(
        default=None,
        description="Displays a video on the page.",
    )

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> Item:
        provided = [name for name in _ITEM_KINDS if getattr(self, name) is not None]
        if len(provided) != 1:
            raise ValueError(
                "Exactly one item kind must be set on Item "
                f"({', '.join(_ITEM_KINDS)}), found: {provided}"
            )
        return self


# -----------------------------------------------------
# Settings, info, publishing
# -----------------------------------------------------


class QuizSettings(BaseModel):
    """Settings related to quiz forms and grading.

    These must be updated with the ``UpdateSettingsRequest``.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#QuizSettings
    """

    is_quiz: Optional[bool] = Field(
        default=None,
        description=(
            "Whether this form is a quiz or not. When true, responses are graded "
            "based on question `Grading`. Upon setting to false, all question "
            "`Grading` is deleted."
        ),
    )


class FormSettings(BaseModel):
    """A form's settings.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#FormSettings
    """

    quiz_settings: Optional[QuizSettings] = Field(
        default=None,
        description="Settings related to quiz forms and grading.",
    )
    email_collection_type: Optional[EmailCollectionType] = Field(
        default=None,
        description=(
            "Optional. The setting that determines whether the form collects email "
            "addresses from respondents. If the form collects email addresses, the "
            "values are populated in the `formResponse.respondentEmail` field."
        ),
    )


class Info(BaseModel):
    """The general information for a form.

    One resource, two operations that disagree about it. ``forms.create``
    honours ``title`` and ``documentTitle`` and calls the description
    disallowed; ``batchUpdate``'s ``UpdateFormInfoRequest`` accepts the
    description and cannot modify ``documentTitle``. The modes below are what
    keeps a single ``Info`` honest on both.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Info
    """

    title: str = Field(
        ...,
        description="Required. The title of the form which is visible to responders.",
    )
    document_title: Annotated[
        Optional[str],
        Mode("create"),
        Field(
            default=None,
            description=(
                "Output only. The title of the document which is visible in Drive. If "
                "`Info.title` is empty, `documentTitle` may appear in its place in the "
                "Google Forms UI and be visible to responders. `documentTitle` can be "
                "set on create, but cannot be modified by a batchUpdate request. "
                "Please use the Google Drive API if you need to programmatically "
                "update `documentTitle`."
            ),
        ),
    ] = None
    description: Annotated[
        Optional[str],
        Mode("update"),
        Field(
            default=None,
            description="The description of the form.",
        ),
    ] = None


class PublishState(BaseModel):
    """The publishing state of a form.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#PublishState
    """

    is_published: bool = Field(
        ...,
        description="Required. Whether the form is published and visible to others.",
    )
    is_accepting_responses: bool = Field(
        ...,
        description=(
            "Required. Whether the form accepts responses. If `isPublished` is set to "
            "`false`, this field is forced to `false`."
        ),
    )

    @model_validator(mode="after")
    def _accepting_responses_needs_publishing(self) -> PublishState:
        if self.is_accepting_responses and not self.is_published:
            raise ValueError(
                "Setting `is_accepting_responses` to true while `is_published` is "
                "false is not supported and returns an error. Publish the form, or "
                "stop accepting responses."
            )
        return self


class PublishSettings(BaseModel):
    """The publishing settings of a form.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#PublishSettings
    """

    publish_state: Optional[PublishState] = Field(
        default=None,
        description=(
            "Optional. The publishing state of a form. When updating `publishState`, "
            "both `isPublished` and `isAcceptingResponses` must be set. However, "
            "setting `isAcceptingResponses` to `true` and `isPublished` to `false` "
            "isn't supported and returns an error."
        ),
    )


class Form(BaseModel):
    """A Google Forms document.

    A form is created in Drive, and deleting a form or changing its access
    protections is done via the Drive API.

    This is what ``forms.get`` returns and what ``batchUpdate`` echoes back. It
    is not the body of ``forms.create``: Google's reference says the create body
    is a ``Form`` and then says every field but the title and document title is
    disallowed, so the create schema models the two that are honoured. See
    :class:`~charter.packs.gforms.types.forms.actions.FormsCreateBody`.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms#Form
    """

    form_id: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="Output only. The form ID."),
    ] = None
    info: Info = Field(
        ...,
        description="Required. The title and description of the form.",
    )
    settings: Optional[FormSettings] = Field(
        default=None,
        description=(
            "The form's settings. This must be updated with `UpdateSettingsRequest`; "
            "it is ignored during `CreateForm` and `UpdateFormInfoRequest`."
        ),
    )
    items: List[Item] = Field(
        ...,
        description=(
            "Required. A list of the form's items, which can include section headers, "
            "questions, embedded media, etc."
        ),
    )
    revision_id: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. The revision ID of the form. Used in the `WriteControl` "
                "in update requests to identify the revision on which the changes are "
                "based. The format of the revision ID may change over time, so it "
                "should be treated opaquely. A returned revision ID is only guaranteed "
                "to be valid for 24 hours after it has been returned and cannot be "
                "shared across users. If the revision ID is unchanged between calls, "
                "then the form content has not changed. Conversely, a changed ID (for "
                "the same form and user) usually means the form content has been "
                "updated; however, a changed ID can also be due to internal factors "
                "such as ID format changes."
            ),
        ),
    ] = None
    responder_uri: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. The form URI to share with responders. This opens a page "
                "that allows the user to submit responses but not edit the questions. "
                "For forms that have `publishSettings` value set, this is the published "
                "form URI."
            ),
        ),
    ] = None
    linked_sheet_id: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. The ID of the linked Google Sheet which is accumulating "
                "responses from this Form (if such a Sheet exists)."
            ),
        ),
    ] = None
    publish_settings: Annotated[
        Optional[PublishSettings],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. The publishing settings for a form. This field isn't set "
                "for legacy forms because they don't have the `publishSettings` field. "
                "All newly created forms support publish settings. Forms with "
                "`publishSettings` value set can call the `SetPublishSettings` API to "
                "publish or unpublish the form."
            ),
        ),
    ] = None
