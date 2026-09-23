# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Resource types for the ``forms.responses`` collection.

Every field of a ``FormResponse`` is Output only — this collection has no write
endpoint — so the whole graph carries ``Mode("response_only")``. Charter models
requests, and these are here because the shape of an answer is what a caller
has to read: a ``CHECKBOX`` answer is several ``TextAnswer`` values, a date
answer is a string whose format depends on how the question was configured, and
neither is guessable from the endpoint alone.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, Field

from charter.packs.gforms.types.feedback import Feedback
from charter.types import Mode

__all__ = [
    "TextAnswer",
    "TextAnswers",
    "FileUploadAnswer",
    "FileUploadAnswers",
    "Grade",
    "Answer",
    "FormResponse",
    "ListFormResponsesResponse",
]


class TextAnswer(BaseModel):
    """An answer to a question represented as text.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses#TextAnswer
    """

    value: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. The answer value. Formatting used for different kinds of "
                "question: `ChoiceQuestion` - `RADIO` or `DROP_DOWN`: A single string "
                "corresponding to the option that was selected. `CHECKBOX`: Multiple "
                "strings corresponding to each option that was selected. `TextQuestion`: "
                "The text that the user entered. `ScaleQuestion`: A string containing "
                "the number that was selected. `DateQuestion` - Without time or year: "
                'MM-DD e.g. "05-19" - With year: YYYY-MM-DD e.g. "1986-05-19" - With '
                'time: MM-DD HH:MM e.g. "05-19 14:51" - With year and time: '
                'YYYY-MM-DD HH:MM e.g. "1986-05-19 14:51". `TimeQuestion`: String with '
                'time or duration in HH:MM format e.g. "14:51". `RowQuestion` within '
                "`QuestionGroupItem`: The answer for each row of a `QuestionGroupItem` is "
                "represented as a separate `Answer`. Each will contain one string for "
                "`RADIO`-type choices or multiple strings for `CHECKBOX` choices."
            ),
        ),
    ] = None


class TextAnswers(BaseModel):
    """A question's answers as text.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses#TextAnswers
    """

    answers: Annotated[
        Optional[List[TextAnswer]],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. Answers to a question. For multiple-value "
                "`ChoiceQuestion`s, each answer is a separate value."
            ),
        ),
    ] = None


class FileUploadAnswer(BaseModel):
    """Info for a single file submitted to a file upload question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses#FileUploadAnswer
    """

    file_id: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="Output only. The ID of the Google Drive file."),
    ] = None
    file_name: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=("Output only. The file name, as stored in Google Drive on upload."),
        ),
    ] = None
    mime_type: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. The MIME type of the file, as stored in Google Drive on upload."
            ),
        ),
    ] = None


class FileUploadAnswers(BaseModel):
    """All submitted files for a FileUpload question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses#FileUploadAnswers
    """

    answers: Annotated[
        Optional[List[FileUploadAnswer]],
        Mode("response_only"),
        Field(
            default=None,
            description=("Output only. All submitted files for a FileUpload question."),
        ),
    ] = None


class Grade(BaseModel):
    """Grade information associated with a respondent's answer to a question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses#Grade
    """

    score: Annotated[
        Optional[float],
        Mode("response_only"),
        Field(
            default=None,
            description="Output only. The numeric score awarded for the answer.",
        ),
    ] = None
    correct: Annotated[
        Optional[bool],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. Whether the question was answered correctly or not. A "
                "zero-point score is not enough to infer incorrectness, since a "
                "correctly answered question could be worth zero points."
            ),
        ),
    ] = None
    feedback: Annotated[
        Optional[Feedback],
        Mode("response_only"),
        Field(
            default=None,
            description="Output only. Additional feedback given for an answer.",
        ),
    ] = None


class Answer(BaseModel):
    """The submitted answer for a question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses#Answer
    """

    question_id: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="Output only. The question's ID."),
    ] = None
    grade: Annotated[
        Optional[Grade],
        Mode("response_only"),
        Field(
            default=None,
            description="Output only. The grade for the answer if the form was a quiz.",
        ),
    ] = None
    text_answers: Annotated[
        Optional[TextAnswers],
        Mode("response_only"),
        Field(
            default=None,
            description="Output only. The specific answers as text.",
        ),
    ] = None
    file_upload_answers: Annotated[
        Optional[FileUploadAnswers],
        Mode("response_only"),
        Field(
            default=None,
            description=("Output only. The answers to a file upload question."),
        ),
    ] = None


class FormResponse(BaseModel):
    """A form response.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses#FormResponse
    """

    form_id: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="Output only. The form ID."),
    ] = None
    response_id: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(default=None, description="Output only. The response ID."),
    ] = None
    create_time: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. Timestamp for the first time the response was submitted. "
                "Uses RFC 3339, where generated output will always be Z-normalized and "
                'uses 0, 3, 6 or 9 fractional digits. Offsets other than "Z" are also '
                "accepted."
            ),
        ),
    ] = None
    last_submitted_time: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. Timestamp for the most recent time the response was "
                "submitted. Does not track changes to grades. Uses RFC 3339, where "
                "generated output will always be Z-normalized and uses 0, 3, 6 or 9 "
                'fractional digits. Offsets other than "Z" are also accepted.'
            ),
        ),
    ] = None
    respondent_email: Annotated[
        Optional[str],
        Mode("response_only"),
        Field(
            default=None,
            description=("Output only. The email address (if collected) for the respondent."),
        ),
    ] = None
    answers: Annotated[
        Optional[Dict[str, Answer]],
        Mode("response_only"),
        Field(
            default=None,
            description=("Output only. The actual answers to the questions, keyed by questionId."),
        ),
    ] = None
    total_score: Annotated[
        Optional[float],
        Mode("response_only"),
        Field(
            default=None,
            description=(
                "Output only. The total number of points the respondent received for "
                "their submission. Only set if the form was a quiz and the response was "
                "graded. This includes points automatically awarded via autograding "
                "adjusted by any manual corrections entered by the form owner."
            ),
        ),
    ] = None


class ListFormResponsesResponse(BaseModel):
    """Response to a ListFormResponsesRequest.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses/list#body.ListFormResponsesResponse
    """

    responses: Optional[List[FormResponse]] = Field(
        default=None,
        description=(
            "The returned form responses. Note: The `formId` field is not returned in "
            "the `FormResponse` object for list requests."
        ),
    )
    next_page_token: Optional[str] = Field(
        default=None,
        description=(
            "If set, there are more responses. To get the next page of responses, "
            "provide this as `pageToken` in a future request."
        ),
    )
