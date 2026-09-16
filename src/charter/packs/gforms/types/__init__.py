"""Request and resource schemas for the Google Forms pack.

Six endpoints over two collections. ``forms`` carries the whole editing surface
in :mod:`~charter.packs.gforms.types.forms.requests`; ``forms.responses`` is two
reads whose shapes are modelled in
:mod:`~charter.packs.gforms.types.form_responses.models`.
:mod:`~charter.packs.gforms.types.feedback` is the v1 type both of them reach.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms
"""

from .feedback import ExtraMaterial, Feedback, TextLink, VideoLink
from .form_responses.actions import (
    FormsResponsesGetRequest,
    FormsResponsesListRequest,
)
from .forms.actions import (
    FormsBatchUpdateRequest,
    FormsCreateRequest,
    FormsGetRequest,
    FormsSetPublishSettingsRequest,
)

__all__ = [
    "FormsCreateRequest",
    "FormsGetRequest",
    "FormsBatchUpdateRequest",
    "FormsSetPublishSettingsRequest",
    "FormsResponsesGetRequest",
    "FormsResponsesListRequest",
    "Feedback",
    "ExtraMaterial",
    "TextLink",
    "VideoLink",
]
