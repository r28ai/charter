"""Cut a tool to the job: 33 kinds of Docs edit behind one URL, down to the 3 that edit text."""

from charter.packs import gdocs

full = gdocs.documents_batch_update
edit = full.derived(
    name="edit_text", keep={"insert_text", "delete_content_range", "replace_all_text"}
)

print(f"both tools call  {full.method} {full.url_template}")
print(f"full            {len(full.paths(under='body.requests'))} kinds of edit")
print(f"edit_text       {', '.join(edit.paths(under='body.requests'))}")
# both tools call  POST v1/documents/{document_id}:batchUpdate
# full            33 kinds of edit
# edit_text       replace_all_text, insert_text, delete_content_range
