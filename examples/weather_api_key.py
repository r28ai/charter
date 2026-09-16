"""
An API-key tool, end to end.

The schema is the whole contract: `Path()` puts `city` in the URL, `Query()`
puts `units` in the query string. Nothing else to write.

Run with:
    OPENWEATHER_API_KEY=... python examples/weather_api_key.py
"""

import asyncio
import os
from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter import Path, Query, api_key_tool_factory


class GetWeather(BaseModel):
    city: Annotated[str, Path()] = Field(description="City name, e.g. 'Tokyo'")
    units: Annotated[Optional[str], Query()] = Field(
        default="metric", description="'metric' or 'imperial'"
    )


def build_tool():
    weather = api_key_tool_factory(
        base_url="https://api.openweathermap.org/",
        api_key_headers={"x-api-key": os.environ.get("OPENWEATHER_API_KEY", "")},
    )
    return weather(
        name="get_current_weather",
        description="Get the current weather for a city.",
        method="GET",
        url_template="data/2.5/weather/{city}",
        args_schema=GetWeather,
        action_label="Check the weather",
    )


async def main() -> None:
    tool = build_tool()

    # What an LLM would be shown — an OpenAI-style function definition.
    print(tool.to_json_schema()["parameters"]["properties"])

    print(await tool.ainvoke(city="Tokyo"))


if __name__ == "__main__":
    asyncio.run(main())
