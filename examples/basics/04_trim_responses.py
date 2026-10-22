"""Decide what comes back to the model: a response handler on a tool you declare.

Do nothing and the model gets the whole response. JSONPlaceholder, a free fake API,
plays your API: its users come with street addresses, map coordinates and slogans.
"""

from pydantic import BaseModel

from charter import api_key_tool_factory


class ListUsers(BaseModel):
    pass


myapi = api_key_tool_factory(
    pack="myapi",
    base_url="https://jsonplaceholder.typicode.com/",
    api_key_headers={"Authorization": "Bearer sk_live_123"},
)
list_users = myapi(
    name="list_users",
    description="List the users.",
    method="GET",
    url_template="users",
    args_schema=ListUsers,
)

everything = list_users.invoke({})
print(f"do nothing:     {len(str(everything)):>5,} characters, fields {', '.join(everything[0])}")
# do nothing:     4,423 characters, fields id, name, username, email, address, phone, website, company


# Keep what the model needs, and reshape it on the way.
async def who_and_where(users: list) -> list:
    return [
        {"name": u["name"], "email": u["email"], "company": u["company"]["name"]} for u in users
    ]


kept = list_users.derived(name="list_users", response_handler=who_and_where).invoke({})
print(f"with a handler: {len(str(kept)):>5,} characters, fields {', '.join(kept[0])}")
# with a handler:   931 characters, fields name, email, company
