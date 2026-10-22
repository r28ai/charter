"""What can this agent touch? egress_map answers from the declarations themselves, so a
change that widens it shows up as a diff for a reviewer, not as a surprise in production.
"""

from charter import egress_map
from charter.packs import gdrive, gmail

DOCS_ONLY = "mimeType='application/vnd.google-apps.document'"


# What a reviewer approved: each tool, and the fields the model can set on it.
approved = egress_map(
    [gmail.messages_list, gdrive.files_list.derived(name="search_docs", pin={"q": DOCS_ONLY})]
)

# A later change: someone hands the agent Gmail's send tool, and drops the pin.
proposed = egress_map(
    [gmail.messages_list, gmail.messages_send, gdrive.files_list.derived(name="search_docs")]
)

for name, entry in sorted(proposed.items()):
    if name not in approved:
        print(f"{name:20}  new tool")
    elif widened := set(entry["visible"]) - set(approved[name]["visible"]):
        print(f"{name:20}  the model can now set {', '.join(sorted(widened))}")
# gdrive_search_docs    the model can now set q
# gmail_messages_send   new tool
#
# In CI: commit json.dumps(egress_map(tools), indent=2) and fail the build when it changes.
