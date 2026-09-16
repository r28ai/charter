"""
The flagship path: an email as a schema, not as MIME glue.

The LLM fills in an `EmailContent`. `Format("rfc822_base64")` turns it into the
base64url RFC822 blob Gmail's `raw` field wants — multipart assembly, header
encoding and URL-safe base64 are the runtime's problem, not yours.

`Mode("response_only")` keeps `id` and `thread_id` out of the model's view:
Gmail returns them, it never accepts them.

Run with a token obtained per docs/oauth-flow.md (or examples/connect_google.py):
    GOOGLE_ACCESS_TOKEN=... python examples/gmail_send.py
"""

import asyncio
from typing import Annotated, Optional

from pydantic import BaseModel

from charter import Body, EmailContent, Format, Mode, Path, oauth_tool_factory
from charter.auth import EnvTokenProvider


class MessagesSend(BaseModel):
    user_id: Annotated[str, Path()] = "me"
    raw: Annotated[EmailContent, Body(), Format("rfc822_base64")]
    id: Annotated[Optional[str], Body(), Mode("response_only")] = None
    thread_id: Annotated[Optional[str], Body(), Mode("response_only")] = None


def build_tool():
    gmail = oauth_tool_factory(
        base_url="https://gmail.googleapis.com/",
        provider="google",
        credential_provider=EnvTokenProvider("GOOGLE_ACCESS_TOKEN"),
        scopes=["https://www.googleapis.com/auth/gmail.modify"],
    )
    return gmail(
        name="messages_send",
        description="Send an email via Gmail.",
        method="POST",
        url_template="gmail/v1/users/{user_id}/messages/send",
        args_schema=MessagesSend,
        action_label="Send an email",
    )


async def main() -> None:
    tool = build_tool()
    # The response-only fields are absent from what the model sees.
    print(sorted(tool.llm_schema().model_fields))
    print(await tool.ainvoke(raw={
        "to": "ada@example.com",
        "subject": "Sent from Charter",
        "body": "The schema is the contract.",
    }))


if __name__ == "__main__":
    asyncio.run(main())
