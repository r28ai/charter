"""Let each of your users paste their own API key, and act as each of them.

httpbin.org plays your users' API: it echoes back the key each call carried.
"""

from pydantic import BaseModel

from charter import CredentialError, oauth_tool_factory
from charter.auth import StaticTokenProvider, SubjectProvider, use_subject

# Your table of what each user pasted. Ada has connected; Bo hasn't.
pasted = {"ada": "sk_live_ada_123"}


def key_of(user: str) -> StaticTokenProvider:
    if user not in pasted:
        raise CredentialError(f"{user} hasn't connected yet")
    return StaticTokenProvider(pasted[user])


class Ping(BaseModel):
    pass


# Once, at startup. Any credential provider fits here, a pasted key included.
api = oauth_tool_factory(
    pack="theirapi",
    base_url="https://httpbin.org/anything/",
    provider="theirapi",
    credential_provider=SubjectProvider(key_of),
)
ping = api(name="ping", description="Check the connection.", method="GET",
           url_template="ping", args_schema=Ping)  # fmt: skip


def sent_as() -> str:
    try:
        return "sent     " + ping.invoke({})["headers"]["Authorization"]
    except CredentialError as error:
        return "refused  " + str(error).split(". ")[0]


with use_subject("ada"):
    print("ada     ", sent_as())  # ada      sent     Bearer sk_live_ada_123
with use_subject("bo"):
    print("bo      ", sent_as())  # bo       refused  bo hasn't connected yet
print("nobody  ", sent_as())  # nobody   refused  No subject is set for this call, so Charter ...
