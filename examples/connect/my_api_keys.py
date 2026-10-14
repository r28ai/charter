"""Where your own key comes from: fixed at startup, or fetched on every call.

httpbin.org plays your API: it echoes back the key each call carried. A shipped pack
reads its own variable instead, GITHUB_TOKEN for GitHub, and needs neither.
"""

import itertools

from pydantic import BaseModel

from charter import api_key_tool_factory


class Ping(BaseModel):
    pass


def ping_with(api_key_headers):
    api = api_key_tool_factory(
        pack="myapi", base_url="https://httpbin.org/anything/", api_key_headers=api_key_headers
    )
    return api(name="ping", description="Check the connection.", method="GET",
               url_template="ping", args_schema=Ping)  # fmt: skip


# 1. Fixed at startup, read from the environment or a config file.
fixed = ping_with({"Authorization": "Bearer sk_live_123"})
print("fixed    ", fixed.invoke({})["headers"]["Authorization"])  # fixed     Bearer sk_live_123

# 2. A function, called on every request: a key rotated in your secret store is picked
#    up without a restart. Here the store rotates it between two calls.
secret_store = itertools.cycle(["sk_live_v1", "sk_live_v2"])
fetched = ping_with(lambda: {"Authorization": f"Bearer {next(secret_store)}"})
print("fetched  ", fetched.invoke({})["headers"]["Authorization"])  # fetched   Bearer sk_live_v1
print("fetched  ", fetched.invoke({})["headers"]["Authorization"])  # fetched   Bearer sk_live_v2
