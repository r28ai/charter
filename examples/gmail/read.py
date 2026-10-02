# /// script
# requires-python = ">=3.10"
# dependencies = ["charter-ai>=0.2.7"]
# ///
"""Read a message in one call, as its reader sees it.

Charter does the parts that usually break: it walks the MIME tree, decodes the
base64url and the charsets, turns HTML into text, and keeps the part that holds
the message, not the "View this email in your browser" placeholder many senders
put in text/plain. You get the text. No Google client library. This prints what
the plain part held, what Charter returned, and both sizes.

    GOOGLE_TOKEN_FILE=google.json uv run read.py MESSAGE_ID  # any authorized-user JSON
"""

import argparse
import asyncio
import json

from charter import pass_through
from charter.packs import gmail
from charter.text import decode_base64url

# The same tool with the response left as Gmail sent it, to show what was there.
as_sent = gmail.messages_get.derived(name="messages_get_as_sent", response_handler=pass_through)


def parts(node: dict):
    yield node
    for child in node.get("parts") or []:
        yield from parts(child)


async def read(message_id: str) -> None:
    api = await as_sent.ainvoke({"id": message_id})
    message = await gmail.messages_get.ainvoke({"id": message_id})
    plain = next((p for p in parts(api["payload"]) if p["mimeType"] == "text/plain"), None)
    if plain:
        text = decode_base64url(plain["body"].get("data", "")).strip()
        print(f"text/plain part: {len(text.split())} words: {text[:70]!r}")
    body = message["bodyText"]
    print(f"Charter's bodyText: {len(body.split())} words\n\n{body[:600]}\n")
    kb = [len(json.dumps(r)) / 1000 for r in (api, message)]
    print(f"Gmail's response {kb[0]:.1f} KB, Charter's {kb[1]:.1f} KB")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("message_id")
    asyncio.run(read(cli.parse_args().message_id))
