# /// script
# requires-python = ">=3.10"
# dependencies = ["charter-ai>=0.2.7"]
# ///
"""Save a message's attachments to disk, and show what a model would read.

Charter does the parts that usually break: it decodes Gmail's unpadded base64url
into the file's bytes, and gives a model a text file as text and a binary one as
a plain "this is binary" rather than base64. You choose where the files go. No
Google client library.

    GOOGLE_TOKEN_FILE=google.json uv run save_attachments.py MESSAGE_ID  # any authorized-user JSON
"""

import argparse
import asyncio
import hashlib
from pathlib import Path

from charter.packs import gmail
from charter.packs.gmail.response_handlers import attachment_bytes

# The same call, with the file's bytes as the result instead of what a model reads.
download = gmail.messages_attachments_get.derived(
    name="messages_attachments_download", response_handler=attachment_bytes
)


async def save(message_id: str, into: Path) -> None:
    message = await gmail.messages_get.ainvoke({"id": message_id})
    for meta in message.get("attachments", []):
        ids = {"messageId": message_id, "id": meta["attachmentId"]}
        data = await download.ainvoke(ids)
        path = into / Path(meta["filename"]).name  # never a path the sender chose
        path.write_bytes(data)
        model = await gmail.messages_attachments_get.ainvoke(ids)
        digest = hashlib.sha256(data).hexdigest()[:12]
        print(f"{path}  {len(data)} bytes  sha256 {digest}")
        print(f"  a model reads: {model['text'][:70]!r}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("message_id")
    cli.add_argument("--into", type=Path, default=Path("."))
    args = cli.parse_args()
    asyncio.run(save(args.message_id, args.into))
