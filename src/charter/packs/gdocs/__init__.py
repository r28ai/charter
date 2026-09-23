# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Google Docs — three tools over the Docs API.

    from charter import StaticTokenProvider
    from charter.packs import gdocs

    gdocs.configure(StaticTokenProvider(access_token))
    doc = await gdocs.documents_create.ainvoke(body={"title": "Q3 review"})
    await gdocs.documents_batch_update.ainvoke(
        document_id=doc["documentId"],
        body={"requests": [{"insert_text": {"text": "Hello", "location": {"index": 1}}}]},
    )

``configure()`` is optional if ``$GOOGLE_ACCESS_TOKEN`` is set.

Three endpoints is the whole API, and yet this is the hardest pack here,
because one of them carries everything.

**batchUpdate is a union of thirty-three edits.** Every change you can make to a
document — insert text, style a range, merge table cells, pin header rows — is
one member of a ``Request`` oneof, and a batch is a list of them.
:mod:`~charter.packs.gdocs.types.requests` models all thirty-three, with the oneof
declared as a ``model_validator`` on ``Request`` and on the eleven edits that
have a oneof of their own.

Those validators are the reason this pack matters. Until recently they were
written, enforced against the wire schema, and *silently dropped* from the view
the model fills in — so the one input that needed checking was the one input
never checked. Deriving the LLM view now carries a schema's validators and its
``extra="forbid"`` across. See ``tests/test_schema.py``.

**Indices shift as edits apply.** ``batchUpdate`` applies its requests in order,
against a document that is changing under them: insert text at index 1 and every
later index moves. The API will not warn you. When inserting at several
positions, order the requests back-to-front. This is documented on the
``requests`` field, because it is the single most common way a correct-looking
batch produces a scrambled document.

Known limits, named rather than hidden:

* **This tool is expensive in context, and narrowing it is the answer.**
  ``documents_batch_update``'s JSON schema is 8,874 tokens before the model has
  read a word of the actual task. That is what complete coverage of a union this
  wide costs, and it is why :meth:`~charter.tool.Tool.derived` exists::

      edit_text = gdocs.documents_batch_update.derived(
          name="documents_edit_text",
          keep={"insert_text", "delete_content_range", "replace_all_text"},
      )

  That view is 1,942 tokens, 78% smaller, and the batch survives: several edits
  still apply in one atomic call, which is the guarantee a tool-per-edit surface
  gives up. The permission is the better reason. Google's ``documents`` scope
  grants all 33 edits as one indivisible grant, so pruning the union member is
  the only place "may edit text, may not delete content" can be said.
* **Responses are not modelled.** A ``Document`` is a deeply nested structural
  document, and Charter models requests. ``documents_get`` returns Google's payload
  as-is; for long documents, write a response handler that extracts the text.
* **Tabs are the newer model.** A document may have several tabs, and the
  top-level ``body`` reflects only the first. Pass ``include_tabs_content=true``
  to ``documents_get`` for the whole thing.
"""

from __future__ import annotations

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.gdocs.response_handlers import extract_document
from charter.packs.gdocs.types import (
    DocumentsBatchUpdateRequest,
    DocumentsCreateRequest,
    DocumentsGetRequest,
)
from charter.tool import Tool

BASE_URL = "https://docs.googleapis.com/"
QUOTA_DOC_URL = "https://developers.google.com/workspace/docs/api/limits"

# Docs needs write access to the document itself. `documents.readonly` is
# enough for documents_get alone.
SCOPES = ["https://www.googleapis.com/auth/documents"]

_credentials = DeferredCredentialProvider("gdocs", env_var="GOOGLE_ACCESS_TOKEN")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


_docs = oauth_tool_factory(
    pack="gdocs",
    base_url=BASE_URL,
    provider="google",
    credential_provider=_credentials,
    scopes=SCOPES,
    # Google is camelCase in both directions: `includeTabsContent`, not
    # `include_tabs_content`, which it would silently ignore.
    query_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
)

documents_get = _docs(
    name="documents_get",
    args_schema=DocumentsGetRequest,
    method="GET",
    url_template="v1/documents/{document_id}",
    description=(
        "Read a document's full structural content. The document ID is the long "
        "string in its URL, between '/d/' and '/edit'. Pass "
        "include_tabs_content=true for a document with several tabs, since the "
        "default response covers only the first."
    ),
    action_label="Reads a document.",
    quota_cost=1,
    response_handler=extract_document,
)

documents_create = _docs(
    name="documents_create",
    args_schema=DocumentsCreateRequest,
    method="POST",
    url_template="v1/documents",
    description=(
        "Create a blank document with a title. Only the title is honoured — the "
        "document is created empty. To add content, call this and then "
        "documents_batch_update with the returned documentId."
    ),
    action_label="Creates a blank titled document.",
    quota_cost=1,
    response_handler=extract_document,
)

documents_batch_update = _docs(
    name="documents_batch_update",
    args_schema=DocumentsBatchUpdateRequest,
    method="POST",
    url_template="v1/documents/{document_id}:batchUpdate",
    description=(
        "Apply a list of edits to a document. Each request sets exactly one kind "
        "of edit — insert_text, replace_all_text, update_text_style, insert_table "
        "and so on. Edits apply in order against a document that shifts as they "
        "do: when inserting at several indices, order the requests back-to-front "
        "so earlier insertions do not move the positions later ones refer to."
    ),
    action_label="Edits a document.",
    quota_cost=1,
)

TOOLS: list[Tool] = [documents_get, documents_create, documents_batch_update]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "SCOPES",
    "QUOTA_DOC_URL",
    "documents_get",
    "documents_create",
    "documents_batch_update",
]
