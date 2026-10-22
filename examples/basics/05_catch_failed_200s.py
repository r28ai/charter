"""A GraphQL API answers a bad query with HTTP 200 and an `errors` list, so anything that
trusts the status code reads it as a success. One line on the factory makes it raise.
"""

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter import GRAPHQL_ENVELOPE, APIError, Body, api_key_tool_factory


class GraphQLRequest(BaseModel):
    query: Annotated[str, Body()] = Field(description="A GraphQL query.")
    variables: Annotated[Optional[dict], Body()] = None


def countries_api(**options):
    factory = api_key_tool_factory(
        pack="countries",
        base_url="https://countries.trevorblades.com/",
        api_key_headers={"Authorization": "Bearer sk_live_123"},
        **options,
    )
    return factory(
        name="query",
        description="Query countries, their capitals and currencies.",
        method="POST",
        url_template="graphql",
        args_schema=GraphQLRequest,
    )


bad = {"query": '{ country(code: "FR") { name population } }'}  # there is no population

answer = countries_api().invoke(bad)
print(f"without the envelope: no error, the call returned {list(answer)}")
# without the envelope: no error, the call returned ['errors']

try:
    countries_api(envelope=GRAPHQL_ENVELOPE).invoke(bad)
except APIError as error:
    print(f"\nwith the envelope:    APIError on HTTP {error.status_code}, {error.message}")
    #
    # with the envelope:    APIError on HTTP 200, the API rejected the call: Cannot query
    #                       field "population" on type "Country".
