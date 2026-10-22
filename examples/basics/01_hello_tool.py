"""Declare one API call, see what the model gets, then make the call.

httpbin.org stands in for Google Calendar: it echoes back the request it received.
"""

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter import Path, Query, api_key_tool_factory


class ListEvents(BaseModel):
    calendar_id: Annotated[str, Path()] = Field(description="Which calendar, e.g. 'primary'.")
    max_results: Annotated[int, Query()] = Field(
        10, ge=1, le=250, description="How many events to return."
    )
    time_min: Annotated[Optional[datetime], Query()] = Field(
        None, description="Only events that end after this."
    )


calendar_api = api_key_tool_factory(
    pack="calendar",
    base_url="https://httpbin.org/anything/",
    api_key_headers={"Authorization": "Bearer sk_live_123"},
    query_case="camel",  # Google's convention, declared once for every tool of this API
)
list_events = calendar_api(
    name="list_events",
    description="List the events on a calendar.",
    method="GET",
    url_template="calendars/{calendar_id}/events",
    args_schema=ListEvents,
)

print("the model fills in", list(list_events.to_json_schema()["parameters"]["properties"]))
# the model fills in ['calendarId', 'maxResults', 'timeMin']: no key, no URL

call = {"calendar_id": "primary", "max_results": 5, "time_min": "2026-10-20T10:00:00"}
sent = list_events.invoke(call)
print(f"Charter sent       {sent['method']} {sent['url']}")
print(f"  auth header      {sent['headers']['Authorization']}  (the model never saw it)")
# Charter sent       GET https://httpbin.org/anything/calendars/primary/events?maxResults=5&timeMin=...
#   auth header      Bearer sk_live_123  (the model never saw it)
#
# Google wants maxResults. Send max_results instead and it ignores it, answers 200, and
# returns its default page. The casing is declared once, on the factory, so every tool
# of this API gets it right.
