"""
Google Forms — six tools over two collections.

    from charter import StaticTokenProvider
    from charter.packs import gforms

    gforms.configure(StaticTokenProvider(access_token))
    form = await gforms.forms_create.ainvoke(body={"info": {"title": "Q3 survey"}})
    await gforms.forms_batch_update.ainvoke(
        form_id=form["formId"],
        body={"requests": [{"create_item": {
            "item": {"title": "How did it go?",
                     "question_item": {"question": {"text_question": {}}}},
            "location": {"index": 0}}}]},
    )

``configure()`` is optional if ``$GOOGLE_ACCESS_TOKEN`` is set.

**Creating a form takes two calls, and the API says so.** ``forms.create``
copies only ``info.title`` and ``info.documentTitle``; a description, items and
settings are refused there and set afterwards through ``forms_batch_update``.
The create body models the two fields that are honoured rather than the whole
``Form``, so the schema cannot offer a field the endpoint rejects.

**One ``Info``, two contracts.** ``documentTitle`` "can be set on create, but
cannot be modified by a batchUpdate request", and the description is disallowed
on create and accepted on batchUpdate. Rather than two near-identical models
that drift apart, ``Info`` carries ``Mode("create")`` and ``Mode("update")`` and
the tools declare which they are — so each endpoint is offered exactly the
fields Google accepts there.

**batchUpdate is a union of six edits**, which makes this the cheap end of
Google's batch APIs: ``forms_batch_update``'s JSON schema is roughly a third of
the Docs one. The breadth is in the ``Item`` a ``create_item`` carries — every
question type, its options, its media and its quiz grading — not in the number
of edits.

Known limits, named rather than hidden:

* **The form response is not trimmed, on purpose.** Google's documented way to
  change an item is to read the form, edit your copy of the item and write it
  back with the same IDs, so a reshaped item is one that cannot be written back.
  ``forms_get`` returns Google's payload as it arrived. The responses collection
  *is* trimmed — see :mod:`~charter.packs.gforms.response_handlers`.
* **File upload questions cannot be created.** Google does not support it
  through the API; ``FileUploadQuestion`` is modelled because an existing one
  comes back on ``forms_get`` and can be moved or deleted.
* **Deleting a form is a Drive operation**, not a Forms one. Use the
  :mod:`~charter.packs.gdrive` pack.
* **Two scopes, not one.** Reading responses is ``forms.responses.readonly``,
  which the body scope does not cover, so the two response tools carry it.
"""

from __future__ import annotations

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.gforms.response_handlers import extract_response, extract_responses
from charter.packs.gforms.types.form_responses.actions import (
    FormsResponsesGetRequest,
    FormsResponsesListRequest,
)
from charter.packs.gforms.types.forms.actions import (
    FormsBatchUpdateRequest,
    FormsCreateRequest,
    FormsGetRequest,
    FormsSetPublishSettingsRequest,
)
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://forms.googleapis.com/"
QUOTA_DOC_URL = "https://developers.google.com/workspace/forms/api/limits"

# Google list endpoints page with an opaque nextPageToken, and omit it on the
# last page — so the cursor's own absence is the stop signal and no more_field
# is needed.
GOOGLE_PAGINATION = Pagination(cursor_field="nextPageToken", cursor_param="pageToken")

# `forms.body` covers reading and editing the form itself. It does not reach the
# responses: Google scopes those separately, and `drive` is the only scope that
# would cover both.
SCOPES = ["https://www.googleapis.com/auth/forms.body"]
RESPONSE_SCOPES = ["https://www.googleapis.com/auth/forms.responses.readonly"]

_credentials = DeferredCredentialProvider("gforms", env_var="GOOGLE_ACCESS_TOKEN")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


_forms = oauth_tool_factory(
    pack="gforms",
    base_url=BASE_URL,
    provider="google",
    credential_provider=_credentials,
    scopes=SCOPES,
    # Google is camelCase in both directions: `pageToken` and `pageSize`, not
    # `page_token` and `page_size`, which it would accept and ignore — every
    # call would return the unfiltered first page and none of them would fail.
    query_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
    # Pagination is a property of the one endpoint that lists, not of the API.
)

forms_create = _forms(
    name="forms_create",
    # `create`, so Info.document_title is offered here and Info.description —
    # which forms.create refuses — is not.
    mode="create",
    args_schema=FormsCreateRequest,
    method="POST",
    url_template="v1/forms",
    description=(
        "Create a new form from a title. Only the title and the document title "
        "are honoured: the form is created with no description, no items and "
        "default settings. To add questions, call this and then "
        "forms_batch_update with the returned formId. Pass unpublished=true to "
        "create a form that does not yet accept responses."
    ),
    action_label="Creates an empty titled form.",
    quota_cost=1,
)

forms_get = _forms(
    name="forms_get",
    args_schema=FormsGetRequest,
    method="GET",
    url_template="v1/forms/{form_id}",
    description=(
        "Read a form: its title and description, its settings, and every item in "
        "order with the item and question IDs. This is the first half of "
        "changing a question: read the item, edit it, and write it back with "
        "forms_batch_update's update_item, keeping the IDs."
    ),
    action_label="Reads a form.",
    quota_cost=1,
)

forms_batch_update = _forms(
    name="forms_batch_update",
    # `update`, so Info.description is offered here and Info.document_title —
    # which a batchUpdate cannot modify — is not.
    mode="update",
    args_schema=FormsBatchUpdateRequest,
    method="POST",
    url_template="v1/forms/{form_id}:batchUpdate",
    description=(
        "Change a form with a batch of updates. Each request sets exactly one "
        "kind of edit, one of update_form_info, update_settings, create_item, "
        "move_item, delete_item or update_item, and they apply in order, "
        "atomically. Items are addressed by index, and indices shift as the "
        "batch applies: inserting at index 2 moves every later item down, so "
        "order several insertions back-to-front or state each location against "
        "the form as it will be by then."
    ),
    action_label="Edits a form.",
    quota_cost=1,
)

forms_set_publish_settings = _forms(
    name="forms_set_publish_settings",
    args_schema=FormsSetPublishSettingsRequest,
    method="POST",
    url_template="v1/forms/{form_id}:setPublishSettings",
    description=(
        "Publish or unpublish a form, and turn response collection on or off. "
        "Both is_published and is_accepting_responses must be set when updating "
        "the publish state; accepting responses while unpublished is not "
        "supported. Legacy forms have no publish settings and are not supported."
    ),
    action_label="Changes a form's publish settings.",
    quota_cost=1,
)

forms_responses_get = _forms(
    name="forms_responses_get",
    args_schema=FormsResponsesGetRequest,
    method="GET",
    url_template="v1/forms/{form_id}/responses/{response_id}",
    description=(
        "Read one submitted response by ID. Answers come back keyed by "
        "questionId, which forms_get is where you look up."
    ),
    action_label="Reads one form response.",
    quota_cost=1,
    scopes_override=RESPONSE_SCOPES,
    response_handler=extract_response,
)

forms_responses_list = _forms(
    name="forms_responses_list",
    args_schema=FormsResponsesListRequest,
    method="GET",
    url_template="v1/forms/{form_id}/responses",
    description=(
        "List a form's submitted responses, newest page first, up to 5000 per "
        "page. The only supported filter is on submission time: pass filter="
        "'timestamp >= 2026-01-01T00:00:00Z' to read what has arrived since a "
        "point in time. Answers come back keyed by questionId."
    ),
    action_label="Reads a form's responses.",
    quota_cost=1,
    scopes_override=RESPONSE_SCOPES,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_responses,
)

TOOLS: list[Tool] = [
    forms_create,
    forms_get,
    forms_batch_update,
    forms_set_publish_settings,
    forms_responses_get,
    forms_responses_list,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "SCOPES",
    "RESPONSE_SCOPES",
    "QUOTA_DOC_URL",
    "GOOGLE_PAGINATION",
    "forms_create",
    "forms_get",
    "forms_batch_update",
    "forms_set_publish_settings",
    "forms_responses_get",
    "forms_responses_list",
]
