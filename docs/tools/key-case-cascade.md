---
title: "Key case cascade"
description: "Four levels of granularity for the casing an API expects on the wire."
---

All schema fields are written **snake_case**. Charter converts keys to the API's
expected casing at serialization time — request only. Responses are never
case-converted, and values are never touched, only keys.

## Four levels of granularity

Each level overrides the one before it. First non-`None` wins.

| # | Level    | Where                                                                          | Scope                |
|---|----------|--------------------------------------------------------------------------------|----------------------|
| 1 | Factory  | [`api_key_tool_factory(body_case=, query_case=, path_case=)`](/reference/factories#api_key_tool_factory) | All tools in factory |
| 2 | Endpoint | [`factory(..., body_case_override=, …)`](/reference/factories#the-builder)      | Single tool          |
| 3 | Schema   | `__case__ = "pascal"` class attribute on a model                                | All keys in that model |
| 4 | Field    | [`Annotated[str, Case("kebab"), Body()]`](/reference/markers#case)               | Single field key     |

### Per-location parameters

Cases are specified **per HTTP location**, not one-for-all:

- `body_case` — JSON request body keys (default `"camel"`)
- `query_case` — URL query string keys (default `"snake"`)
- `path_case` — URL path parameter keys (default `"snake"`)

This matters more often than it sounds: Google APIs typically want camelCase
bodies but snake_case query parameters.

### Supported cases

| Case       | Example       |
|------------|---------------|
| `"snake"`  | `date_time`   |
| `"camel"`  | `dateTime`    |
| `"pascal"` | `DateTime`    |
| `"kebab"`  | `date-time`   |

## Examples

### Clean API (most common) — factory level only

```python camel_api_factory.py
from charter import oauth_tool_factory

gmail = oauth_tool_factory(
    base_url="https://gmail.googleapis.com/",
    provider="google",
    credential_provider=provider,
    body_case="camel",  # default — all body keys become camelCase
)
```

### API with snake_case everywhere

```python snake_api_factory.py
from charter import api_key_tool_factory

api = api_key_tool_factory(
    base_url="https://api.example.com/v1/",
    api_key_headers={"Authorization": f"Bearer {key}"},
    body_case="snake",
    query_case="snake",
)
```

### Mixed API — one endpoint differs

```python per_endpoint_case.py
special = factory(
    name="special_endpoint",
    args_schema=SpecialInput,
    method="POST",
    url_template="v1/special",
    body_case_override="pascal",  # this endpoint wants a PascalCase body
)
```

### Schema-level override (nested model)

```python schema_case.py
class EventDateTime(BaseModel):
    __case__ = "camel"
    date_time: str
    time_zone: str

# Serialized body keys: {"dateTime": ..., "timeZone": ...}
```

### Field-level override (single field)

```python field_case.py
from typing import Annotated
from charter import Body, Case

class MixedInput(BaseModel):
    display_name: Annotated[str, Case("pascal"), Body()]  # -> DisplayName
    user_id: Annotated[str, Body()]                       # -> follows the default
```

## Resolution at serialization time

```
for each key:
    1. Field-level Case("kebab") marker      -> use it
    2. Schema-level __case__ on the model    -> use it
    3. Endpoint / factory *_case setting     -> use it
    4. Fallback                              -> snake_case (no conversion)
```

Field-level and schema-level overrides apply at the top level of the body. Nested
objects recurse with the endpoint/factory default, because a field marker names a
field on *that* schema — it would be meaningless keyed against a nested object's
field names.

## When no convention is right

The cascade converts a whole word at a time, and an acronym inside a field name
is where that goes wrong. `snake_to_camel` capitalises each component, so
`i_cal_uid` becomes `iCalUid` — and Google Calendar documents `iCalUID`. The same
shape gives `htmlUrl` for `htmlURL` and `ipAddress` for `IPAddress`. No entry in
the cascade produces those, because they are not a convention.

[`WireName`](/reference/markers#wirename) names the key outright, and wins over
every level above:

```python
i_cal_uid: Annotated[Optional[str], Field(None), Query(), WireName("iCalUID")]
```

Reach for it only where the API's reference actually spells an acronym in full.
Most do not — `eventId` and `fileUrl` are camelCase in Google's own docs — so
check rather than guess.

This failure is silent, which is why it is worth a marker. Many APIs ignore a
query parameter they do not recognise, so the misspelled filter is dropped, the
unfiltered result comes back, and the call answers `200`. Charter's own Calendar
pack sent `iCalUid` for as long as it existed. Assert the parameter names on the
wire against a `respx` route; reading the schema is what misses it.

## Related

- [`WireName`](/reference/markers#wirename) — the key the API documents, verbatim
- [`Case`](/reference/markers#case) — the field-level marker
- [`KeyCase`](/reference/markers#keycase) — the type the `*_case` settings accept
- [Casing and encoding](/reference/tool#casing-and-encoding) — the resolved settings on a built `Tool`
- [The builder](/reference/factories#the-builder) — the `*_case_override` parameters
