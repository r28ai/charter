---
title: "Transform system"
description: "Turn semantic types the model understands into the wire formats an API requires."
---

## Overview

The transform system bridges **rigid API specifications** and **LLM-friendly
interfaces**. You define schemas that match the API documentation exactly, and
the LLM gets semantic, human-readable types.

> **Core principle:** LLMs should interact with data like humans, not like
> computers dealing with wire formats.

Transforms compose with the [mode system](/boundary/mode-system), which controls *which*
fields the LLM sees; transforms control *what type* those fields have.

## The pipeline

1. APIs speak in rigid formats — base64, RFC822, protobuf JSON.
2. You annotate schema fields with `Format` markers matching the API docs.
3. Charter generates the LLM-facing view, where those fields carry semantic types.
4. The LLM provides natural input (`to`/`subject`/`body`, not raw MIME).
5. The transform engine converts semantic input to the exact wire format.
6. The API receives the payload it expects. No glue code.

## Components

### 1. Transform registry

One place where every transformation is declared, via
[`TransformRegistry`](/reference/transforms#transformregistry):

```python rfc822_transform.py
from charter import EmailContent, TransformRegistry

@TransformRegistry.register("rfc822_base64", EmailContent, "Email message content")
def transform_email_to_rfc822_base64(email: EmailContent) -> str:
    """Convert EmailContent -> RFC822 -> base64url."""
```

- Declarative registration
- Semantic type recorded alongside the function, so schema generation knows what
  to show the LLM
- LLM-friendly description attached to the field

### 2. Format markers

Annotate the fields that need conversion with
[`Format`](/reference/markers#format):

```python format_marker.py
from typing import Annotated
from pydantic import BaseModel, Field
from charter import Format

class SendEmailRequest(BaseModel):
    raw: Annotated[
        str,
        Field(description="RFC-822, base64url encoded"),
        Format("rfc822_base64"),
    ]
```

The schema still says exactly what the API says. The marker records where the
bridge goes.

### 3. LLM schema generation

```python send_email_request.py
# You write:
class SendEmailRequest(BaseModel):
    raw: Annotated[str, Format("rfc822_base64")]

# The LLM sees:
class SendEmailRequest_LLM(BaseModel):
    raw: EmailContent  # semantic type
```

The generator:

1. detects `Format` markers,
2. replaces the wire type with the registered semantic type,
3. swaps in the transform's LLM-facing description,
4. preserves the [`Path`](/reference/markers#path)/[`Query`](/reference/markers#query)/[`Body`](/reference/markers#body)/[`Case`](/reference/markers#case)/[`Mode`](/reference/markers#mode)
   markers.

## Built-in transforms

| Name             | Semantic type     | Wire format                                    |
|------------------|-------------------|------------------------------------------------|
| `rfc822_base64`  | [`EmailContent`](/reference/semantic-types#emailcontent) | base64url RFC822 message, unpadded |
| `email_json`     | [`EmailContent`](/reference/semantic-types#emailcontent) | JSON object with wire aliases |
| `base64`         | `str`             | standard base64, padded                        |
| `base64url`      | `str`             | URL-safe base64, unpadded                      |
| `bytes`          | `str`             | URL-safe base64 (Google "bytes" fields)        |
| `json_base64`    | `dict`            | compact JSON, base64                           |
| `file_base64`    | [`FileContent`](/reference/semantic-types#filecontent) | standard base64 of the file body |
| `document_json`  | [`DocumentContent`](/reference/semantic-types#documentcontent) | JSON object |
| `field_mask`     | [`FieldMask`](/reference/protobuf-types#fieldmask) | comma-joined path string      |
| `proto_json`     | [protobuf models](/reference/protobuf-types) | plain JSON primitives               |

`bytes` and `base64url` encode identically. The separate name exists for
fidelity with Google API specs that annotate a field as `bytes`.

## Nesting

Transforms apply at any depth. The runtime walks nested models and lists,
applying every `Format` marker it finds, then routes the transformed value to the
HTTP location its `Path`/`Query`/`Body` marker names.

## Registering your own

Call [`register_transform`](/reference/transforms#register_transform) with the
semantic type, the conversion, and the description the LLM will see:

```python custom_transform.py
from pydantic import BaseModel
from charter import register_transform

class Coordinates(BaseModel):
    lat: float
    lon: float

register_transform(
    "latlon_string",
    Coordinates,
    lambda c: f"{c.lat},{c.lon}",
    "Geographic coordinates",
)
```

Then `Annotated[str, Query(), Format("latlon_string")]` shows the LLM a
`Coordinates` object and sends `"48.8584,2.2945"`.

## Failure

An unknown transform name, a payload that will not validate as the semantic
type, or a transform function that raises all produce a
[`TransformError`](/reference/errors#transformerror) naming the transform and the
field. Transform failures are never swallowed — a silently untransformed value
reaches the API as a confusing 400.

## Related

- [`TransformSpec`, `TransformRegistry`, `register_transform`](/reference/transforms) — the registry API in full
- [`Format`](/reference/markers#format) — the marker that names a transform
- [Semantic types](/reference/semantic-types) — `EmailContent`, `CalendarEvent`, `DocumentContent`, `FileContent`
- [`TransformError`](/reference/errors#transformerror) — what a failed conversion raises
