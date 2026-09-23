# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Tavily research endpoints.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from charter.packs.tavily.types.common import (
    CitationFormat,
    OutputLength,
    ResearchModel,
)
from charter.types import Body, Path, Query, WireName

__all__ = [
    "ResearchCreateRequest",
    "ResearchGetRequest",
    "OutputSchemaProperty",
    "OutputSchema",
    "ResearchFile",
]

OutputSchemaPropertyType = Literal["object", "string", "integer", "number", "array"]


class OutputSchemaProperty(BaseModel):
    """One property in a research ``output_schema``.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research
    """

    type: OutputSchemaPropertyType = Field(..., description="Property type.")
    description: Optional[str] = Field(
        None,
        description="Property description. Required on top-level properties; optional on nested `items`.",
    )
    properties: Optional[Dict[str, OutputSchemaProperty]] = Field(
        None,
        description="Nested properties when `type` is `object`.",
    )
    items: Optional[OutputSchemaProperty] = Field(
        None,
        description="Item schema when `type` is `array`.",
    )

    @model_validator(mode="after")
    def _shape_matches_type(self) -> OutputSchemaProperty:
        if self.type == "object" and not self.properties:
            raise ValueError("output_schema properties with type `object` require `properties`.")
        if self.type == "array" and self.items is None:
            raise ValueError("output_schema properties with type `array` require `items`.")
        return self


class OutputSchema(BaseModel):
    """JSON Schema defining structured research output.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research
    """

    properties: Dict[str, OutputSchemaProperty] = Field(
        ...,
        description="Property definitions keyed by name.",
    )
    required: Optional[List[str]] = Field(
        None,
        description="Property names required in the output.",
    )


class ResearchFile(BaseModel):
    """A file attached as an additional research source.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Filename with a `.txt`, `.md`, or `.json` extension.")
    data: str = Field(..., description="Base64-encoded file contents.")
    type_: Annotated[
        Optional[Literal["base64"]],
        Field(
            None,
            alias="type",
            description="Encoding of the `data` field. The server applies `base64` when this is absent.",
        ),
        WireName("type"),
    ] = None

    @model_serializer(mode="wrap")
    def _type_on_the_wire(self, handler):
        data = handler(self)
        if "type_" in data:
            data["type"] = data.pop("type_")
        return data

    @model_validator(mode="after")
    def _allowed_extension(self) -> ResearchFile:
        lower = self.name.lower()
        if not lower.endswith((".txt", ".md", ".json")):
            raise ValueError("name must end with .txt, .md, or .json")
        return self


class ResearchCreateRequest(BaseModel):
    """Create an async research task that searches, analyzes sources, and generates a cited report.

    Poll results with ``research_get``. SSE streaming via ``stream=true`` is not
    exposed as a tool because the response is not JSON.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research
    """

    input: Annotated[
        str,
        Field(..., description="Research task or question."),
        Body(),
    ]
    model: Annotated[
        Optional[ResearchModel],
        Field(
            None,
            description="Research agent model tier. The server applies `auto` when this is absent.",
        ),
        Body(),
    ]
    output_schema: Annotated[
        Optional[OutputSchema],
        Field(
            None,
            description="JSON Schema defining structured output shape.",
        ),
        Body(),
    ]
    citation_format: Annotated[
        Optional[CitationFormat],
        Field(
            None,
            description="Citation format in the report. The server applies `numbered` when this is absent.",
        ),
        Body(),
    ]
    include_domains: Annotated[
        Optional[List[str]],
        Field(
            None,
            max_length=20,
            description="Soft source preference (max 20). Host-based subdomain matching.",
        ),
        Body(),
    ]
    exclude_domains: Annotated[
        Optional[List[str]],
        Field(
            None,
            max_length=20,
            description="Hard blocklist (max 20). Downward subdomain matching only.",
        ),
        Body(),
    ]
    output_length: Annotated[
        Optional[OutputLength],
        Field(
            None,
            description="Target response size. The server applies `standard` when this is absent.",
        ),
        Body(),
    ]
    files: Annotated[
        Optional[List[ResearchFile]],
        Field(
            None,
            max_length=5,
            description=(
                "Attach up to 5 files as additional sources. Each file may be at "
                "most 80,000 words; combined total at most 80,000 words."
            ),
        ),
        Body(),
    ]


class ResearchGetRequest(BaseModel):
    """Retrieve the status and results of a research task.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research-get
    """

    request_id: Annotated[
        str,
        Field(..., description="Research task UUID returned by `research_create`."),
        Path(),
    ]
    include_usage: Annotated[
        Optional[bool],
        Field(
            None,
            description="Include credit usage in the response.",
        ),
        Query(),
    ]


OutputSchemaProperty.model_rebuild()
