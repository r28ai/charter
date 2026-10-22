"""Pin a value the model can neither see nor set: a Drive search locked to Google Docs."""

from charter import egress_map
from charter.packs import gdrive

search_documents = gdrive.files_list.derived(
    name="search_documents",
    pin={"q": "mimeType='application/vnd.google-apps.document'"},
)

boundary = egress_map([search_documents])["gdrive_search_documents"]
print(
    f"the model sets  {', '.join(boundary['visible'][:4])} and {len(boundary['visible']) - 4} more"
)
print(f"it never sees   q, which every call sends as {boundary['pinned']['q']}")
# the model sets  page_size, page_token, corpora, drive_id and 6 more
# it never sees   q, which every call sends as "mimeType='application/vnd.google-apps.document'"
