"""Declare one API call, see what the model gets, then make the call.

httpbin.org stands in for a calendar API: it echoes back the request it received.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from charter import Body, Path, Query, api_key_tool_factory


class CreateEvent(BaseModel):
    calendar: Annotated[str, Path()] = Field(description="Which calendar, e.g. 'primary'.")
    notify: Annotated[bool, Query()] = Field(False, description="Email the attendees.")
    title: Annotated[str, Body()] = Field(description="What the meeting is about.")
    start: Annotated[datetime, Body()] = Field(description="When it starts.")
    attendees: Annotated[list[str], Body()] = Field([], description="Who to invite, by email.")


calendar_api = api_key_tool_factory(
    pack="calendar",
    base_url="https://httpbin.org/anything/",
    api_key_headers={"Authorization": "Bearer sk_live_123"},
)
create_event = calendar_api(
    name="create_event",
    description="Put a meeting on a calendar.",
    method="POST",
    url_template="calendars/{calendar}/events",
    args_schema=CreateEvent,
)

# What the model gets: to_json_schema() is the full JSON, printed here a field a line.
schema = create_event.to_json_schema()
fields = schema["parameters"]["properties"]
print(f"the model gets  {schema['name']}: {schema['description']}")
for name, field in fields.items():
    required = "required" if name in schema["parameters"]["required"] else ""
    print(f"  {name:9} {field['type']:7} {required:8}  {field['description']}")
# the model gets  create_event: Put a meeting on a calendar.
#   calendar  string  required  Which calendar, e.g. 'primary'.
#   notify    boolean           Email the attendees.
#   title     string  required  What the meeting is about.
#   start     string  required  When it starts.
#   attendees array             Who to invite, by email.

meeting = {
    "calendar": "primary",
    "notify": True,
    "title": "Coffee with Ada",
    "start": "2026-10-20T10:00:00",
    "attendees": ["ada@example.com"],
}
sent = create_event.invoke(meeting)
print(f"\nCharter sent    {sent['method']} {sent['url']}")
print(f"  body          {sent['json']}")
print(f"  auth header   {sent['headers']['Authorization']}  (the model never saw it)")
#
# Charter sent    POST https://httpbin.org/anything/calendars/primary/events?notify=true
#   body          {'attendees': ['ada@example.com'], 'start': '2026-10-20T10:00:00', 'title': ...}
#   auth header   Bearer sk_live_123  (the model never saw it)
