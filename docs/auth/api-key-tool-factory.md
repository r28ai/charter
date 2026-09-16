---
title: "api_key_tool_factory"
description: "Build tools against an API that authenticates with a static key or header."
sidebarTitle: "API keys"
---

## Overview

[`api_key_tool_factory`](/reference/factories#api_key_tool_factory) builds tools
for any API that authenticates with static headers. No credential provider, no
refresh flow — just header injection.

Use [`oauth_tool_factory`](/reference/factories#oauth_tool_factory) instead when
the token is fetched or refreshed per call.

## Design

- **Simple** — one dictionary of headers
- **Flexible** — single or multiple auth headers
- **Overridable** — set defaults on the factory, override per tool
- **Checked** — an empty header value is rejected at build time, not at the first
  401

## Basic usage

### Single header (most common)

```python scraper_client.py
from charter import api_key_tool_factory

scraper = api_key_tool_factory(
    base_url="https://api.example.com/",
    api_key_headers={"x-api-key": API_KEY},
)

transcript_tool = scraper(
    name="fetch_transcript",
    args_schema=TranscriptRequest,
    method="GET",
    url_template="transcript/{video_id}",
    description="Fetch the transcript of a video.",
)
```

### Multiple headers

```python multi_header_client.py
multi_auth = api_key_tool_factory(
    base_url="https://api.example.com/",
    api_key_headers={
        "x-api-key": "key123",
        "x-client-id": "client456",
        "x-custom-token": "token789",
    },
)
```

### Bearer token

```python bearer_client.py
bearer = api_key_tool_factory(
    base_url="https://api.example.com/v1/",
    api_key_headers={"Authorization": f"Bearer {API_TOKEN}"},
)
```

## Per-tool overrides

Different endpoints can use different keys:

```python per_tool_keys.py
api = api_key_tool_factory(
    base_url="https://api.example.com/",
    api_key_headers={"x-api-key": "default-key"},
)

# Most tools use the default key
public_tool = api(
    name="get_public_data",
    args_schema=PublicRequest,
    method="GET",
    url_template="public/data",
    description="Public endpoint.",
)

# One endpoint needs a privileged key
admin_tool = api(
    name="get_admin_data",
    args_schema=AdminRequest,
    method="GET",
    url_template="admin/data",
    description="Admin endpoint.",
    api_key_headers_override={"x-api-key": "admin-key"},
)
```

## Signature

```python
api_key_tool_factory(
    base_url: str,
    api_key_headers: dict[str, str] | None = None,
    *,
    body_case: KeyCase = "camel",
    query_case: KeyCase = "snake",
    path_case: KeyCase = "snake",
    timeout: int = 20,
) -> ToolBuilder
```

The returned builder takes:

| Parameter                | Purpose                                            |
|--------------------------|----------------------------------------------------|
| `name`                   | Tool name                                          |
| `args_schema`            | The schema — the contract                          |
| `method`                 | `GET` / `POST` / `PATCH` / `PUT` / `DELETE`        |
| `url_template`           | Path with `{placeholders}` for [`Path()`](/reference/markers#path) fields     |
| `description`            | What the tool does, for the model                  |
| `action_label`           | Short user-facing phrase, for approval UIs         |
| `mode`                   | Mode filter for the LLM schema                     |
| `response_handler`       | Async callable to trim the response                |
| `build_request`          | Escape hatch returning a [`TransportOverride`](/reference/markers#transportoverride)       |
| `*_case_override`        | Per-endpoint casing                                |
| `timeout_override`       | Per-endpoint timeout                               |
| `api_key_headers_override` | Per-endpoint auth headers                        |

## Errors

- Empty header value, on the factory or a tool -> [`DeclarationError`](/reference/errors#declarationerror) at build time
- No headers on either the factory or the tool -> [`DeclarationError`](/reference/errors#declarationerror) naming the tool
- `401` from the API -> [`CredentialError`](/reference/errors#credentialerror) (declare `credential_statuses={401, 403}`
  if the API means "your token" by 403 too — most mean "not allowed", which is an
  [`APIError`](/reference/errors#apierror))
- Any other `>= 400` -> `APIError` carrying the status and a body excerpt
