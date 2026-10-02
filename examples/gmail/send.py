# /// script
# requires-python = ">=3.10"
# dependencies = ["charter-ai>=0.2.6"]
# ///
"""Send an email in one call, to a name like `"Müller, José"`.

Charter does the parts that usually break: it encodes the accents (RFC 2047)
and quotes the comma, so Gmail neither rejects the header nor splits one
recipient into two, and it builds the MIME document, its base64url encoding and
Gmail's `raw` envelope. You write the address, subject and body. No Google
client library.

    GOOGLE_TOKEN_FILE=google.json uv run send.py you@gmail.com  # any authorized-user JSON
    # prints the headers it would send; add --send to send it, to yourself
"""

import argparse
import asyncio
import base64
import re

from charter.packs import gmail
from charter.transforms import apply_transform


async def send(address: str, really: bool) -> None:
    email = {
        "to": f'"Müller, José" <{address}>',
        "subject": "Café ☕ — réunion à 10h",
        "body": "Grüße aus Zürich.",
    }
    if not really:
        raw = apply_transform("rfc822_base64", email)
        wire = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        print(re.split(r"\r?\n\r?\n", wire, maxsplit=1)[0])
        return
    sent = await gmail.messages_send.ainvoke({"body": {"raw": email}})
    check = await gmail.messages_get.ainvoke({"id": sent["id"], "format": "metadata"})
    print({k: check["headers"].get(k) for k in ("To", "Subject")})


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("address", help="where to send it: your own address")
    cli.add_argument("--send", action="store_true")
    args = cli.parse_args()
    asyncio.run(send(args.address, args.send))
