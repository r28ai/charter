# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
``Feedback`` — a v1 type of its own, shared by both collections.

Google documents this outside ``forms`` and outside ``forms.responses`` because
both reach it: a quiz question declares the feedback a respondent will see
(:class:`~charter.packs.gforms.types.forms.models.Grading`), and a graded answer
carries the feedback they were given
(:class:`~charter.packs.gforms.types.form_responses.models.Grade`). It lives in
its own module here for the same reason.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/Feedback
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "TextLink",
    "VideoLink",
    "ExtraMaterial",
    "Feedback",
]


class TextLink(BaseModel):
    """Link for text.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/Feedback#TextLink
    """

    uri: str = Field(
        ...,
        description="Required. The URI.",
    )
    display_text: str = Field(
        ...,
        description="Required. Display text for the URI.",
    )


class VideoLink(BaseModel):
    """Link to a video.

    ``youtubeUri`` is the sole member of the required ``video`` union, so it is
    declared optional and required by the validator rather than by the
    annotation: the day Google adds a second source, the member becomes one of
    two and nothing about this model's shape has to change.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/Feedback#VideoLink
    """

    display_text: str = Field(
        ...,
        description="Required. The display text for the link.",
    )
    youtube_uri: Optional[str] = Field(
        default=None,
        description="The URI of a YouTube video.",
    )

    @model_validator(mode="after")
    def _exactly_one_video(self) -> VideoLink:
        if self.youtube_uri is None:
            raise ValueError("VideoLink requires its `video` union: set `youtube_uri`.")
        return self


class ExtraMaterial(BaseModel):
    """Supplementary material to the feedback.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/Feedback#ExtraMaterial
    """

    link: Optional[TextLink] = Field(
        default=None,
        description="Text feedback.",
    )
    video: Optional[VideoLink] = Field(
        default=None,
        description="Video feedback.",
    )

    @model_validator(mode="after")
    def _exactly_one_content(self) -> ExtraMaterial:
        provided = [name for name in ("link", "video") if getattr(self, name) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of `link` or `video` must be set on ExtraMaterial, found: {provided}"
            )
        return self


class Feedback(BaseModel):
    """Feedback for a respondent about their response to a question.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/Feedback
    """

    text: str = Field(
        ...,
        description="Required. The main text of the feedback.",
    )
    material: Optional[List[ExtraMaterial]] = Field(
        default=None,
        description=(
            "Additional information provided as part of the feedback, often used "
            "to point the respondent to more reading and resources."
        ),
    )
