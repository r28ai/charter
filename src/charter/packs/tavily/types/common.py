# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Shared literals and response fragments for the Tavily API.

API Reference: https://docs.tavily.com/documentation/api-reference/introduction
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

from charter.types import Mode

SearchDepth = Literal["advanced", "basic", "fast", "ultra-fast"]
Topic = Literal["general", "news", "finance"]
TimeRange = Literal["day", "week", "month", "year", "d", "w", "m", "y"]
IncludeDomainsMode = Literal["filter", "boost"]
IncludeAnswer = Union[bool, Literal["basic", "advanced"]]
IncludeRawContent = Union[bool, Literal["markdown", "text"]]
ExtractDepth = Literal["basic", "advanced"]
ContentFormat = Literal["markdown", "text"]
ResearchModel = Literal["mini", "pro", "auto"]
CitationFormat = Literal["numbered", "mla", "apa", "chicago"]
OutputLength = Literal["short", "standard", "long"]
LogEndpoint = Literal["search", "extract", "map", "crawl", "research"]
OrgUsageDepth = Literal["basic", "advanced", "fast", "pro", "mini", "auto", "ultra-fast"]
ResearchStatus = Literal["pending", "in_progress", "completed", "failed"]
Country = Literal[
    "afghanistan",
    "albania",
    "algeria",
    "andorra",
    "angola",
    "argentina",
    "armenia",
    "australia",
    "austria",
    "azerbaijan",
    "bahamas",
    "bahrain",
    "bangladesh",
    "barbados",
    "belarus",
    "belgium",
    "belize",
    "benin",
    "bhutan",
    "bolivia",
    "bosnia and herzegovina",
    "botswana",
    "brazil",
    "brunei",
    "bulgaria",
    "burkina faso",
    "burundi",
    "cambodia",
    "cameroon",
    "canada",
    "cape verde",
    "central african republic",
    "chad",
    "chile",
    "china",
    "colombia",
    "comoros",
    "congo",
    "costa rica",
    "croatia",
    "cuba",
    "cyprus",
    "czech republic",
    "denmark",
    "djibouti",
    "dominican republic",
    "ecuador",
    "egypt",
    "el salvador",
    "equatorial guinea",
    "eritrea",
    "estonia",
    "ethiopia",
    "fiji",
    "finland",
    "france",
    "gabon",
    "gambia",
    "georgia",
    "germany",
    "ghana",
    "greece",
    "guatemala",
    "guinea",
    "haiti",
    "honduras",
    "hungary",
    "iceland",
    "india",
    "indonesia",
    "iran",
    "iraq",
    "ireland",
    "israel",
    "italy",
    "jamaica",
    "japan",
    "jordan",
    "kazakhstan",
    "kenya",
    "kuwait",
    "kyrgyzstan",
    "latvia",
    "lebanon",
    "lesotho",
    "liberia",
    "libya",
    "liechtenstein",
    "lithuania",
    "luxembourg",
    "madagascar",
    "malawi",
    "malaysia",
    "maldives",
    "mali",
    "malta",
    "mauritania",
    "mauritius",
    "mexico",
    "moldova",
    "monaco",
    "mongolia",
    "montenegro",
    "morocco",
    "mozambique",
    "myanmar",
    "namibia",
    "nepal",
    "netherlands",
    "new zealand",
    "nicaragua",
    "niger",
    "nigeria",
    "north korea",
    "north macedonia",
    "norway",
    "oman",
    "pakistan",
    "panama",
    "papua new guinea",
    "paraguay",
    "peru",
    "philippines",
    "poland",
    "portugal",
    "qatar",
    "romania",
    "russia",
    "rwanda",
    "saudi arabia",
    "senegal",
    "serbia",
    "singapore",
    "slovakia",
    "slovenia",
    "somalia",
    "south africa",
    "south korea",
    "south sudan",
    "spain",
    "sri lanka",
    "sudan",
    "sweden",
    "switzerland",
    "syria",
    "taiwan",
    "tajikistan",
    "tanzania",
    "thailand",
    "togo",
    "trinidad and tobago",
    "tunisia",
    "turkey",
    "turkmenistan",
    "uganda",
    "ukraine",
    "united arab emirates",
    "united kingdom",
    "united states",
    "uruguay",
    "uzbekistan",
    "venezuela",
    "vietnam",
    "yemen",
    "zambia",
    "zimbabwe",
]


class Usage(BaseModel):
    """Credit usage returned when ``include_usage`` is requested.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/search
    """

    credits: Annotated[
        Optional[int],
        Field(None, description="Credits consumed by this request."),
        Mode("response_only"),
    ]


class SearchImage(BaseModel):
    """An image attached to a search result or the top-level query.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/search
    """

    url: Annotated[Optional[str], Field(None, description="Image URL."), Mode("response_only")]
    description: Annotated[
        Optional[str],
        Field(None, description="Descriptive text for the image when requested."),
        Mode("response_only"),
    ]
