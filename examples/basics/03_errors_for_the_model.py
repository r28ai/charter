"""When the model gets an argument wrong, the call is refused before anything is sent,
with a message written for the model to fix it on its next try.
"""

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter import ConflictsWith, Query, ToolValidationError, api_key_tool_factory

FRESH_OR_CONTINUE = (
    "A sync continues the query its token came from. Drop syncToken to run a fresh "
    "search, or drop the filters to continue the sync."
)


class ListEvents(BaseModel):
    max_results: Annotated[int, Query()] = Field(10, ge=1, le=250)
    q: Annotated[Optional[str], Query(), ConflictsWith("sync_token", reason=FRESH_OR_CONTINUE)] = (
        None
    )
    sync_token: Annotated[Optional[str], Query()] = None


calendar_api = api_key_tool_factory(
    pack="calendar",
    base_url="https://httpbin.org/anything/",
    api_key_headers={"Authorization": "Bearer sk_live_123"},
)
list_events = calendar_api(
    name="list_events",
    description="List the events on a calendar.",
    method="GET",
    url_template="calendars/primary/events",
    args_schema=ListEvents,
)

for call in ({"max_results": "ten"}, {"q": "standup", "sync_token": "CPDAlvWDx70CEPDAlvWDx70C"}):
    try:
        list_events.invoke(call)
    except ToolValidationError as refused:
        print(f"the model sent  {call}\nand reads back  {refused}\n")
# the model sent  {'max_results': 'ten'}
# and reads back  Validation error:
# - **max_results**: Input should be a valid integer, unable to parse string as an integer (got 'ten')
#
# the model sent  {'q': 'standup', 'sync_token': 'CPDAlvWDx70CEPDAlvWDx70C'}
# and reads back  Validation error:
# - **(input)**: Value error, q cannot be combined with syncToken. A sync continues the
#   query its token came from. Drop syncToken to run a fresh search, or drop the filters ...
