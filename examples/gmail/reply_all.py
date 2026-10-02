# /// script
# requires-python = ">=3.10"
# dependencies = ["charter-ai>=0.2.7"]
# ///
"""Reply-all in two calls: read the original, send the reply.

Charter does the parts that usually break: it reads headers whatever their
spelling (Outlook writes `CC`), and builds the In-Reply-To and References
headers, the MIME document, its base64url encoding and Gmail's `raw` envelope.
You write the recipient list, the part that's yours. No Google client library.

    GOOGLE_TOKEN_FILE=google.json uv run reply_all.py MESSAGE_ID  # any authorized-user JSON
    # prints the headers it would send; add --send to send it
"""

import argparse
import asyncio
import base64
import re
from email.utils import formataddr, getaddresses

from charter.packs import gmail
from charter.transforms import apply_transform


async def reply_all(message_id: str, body: str, send: bool) -> None:
    got = await gmail.messages_get.ainvoke({"id": message_id, "format": "metadata"})
    h = got["headers"]
    sender = h.get("Reply-To") or h["From"]
    skip = {a.lower() for _, a in getaddresses([h.get("Delivered-To", ""), sender])}
    everyone = getaddresses([h.get("To", ""), h.get("Cc", "")])
    subject = h.get("Subject", "")
    reply = {
        "to": sender,
        "cc": [formataddr(p) for p in everyone if p[1].lower() not in skip] or None,
        "subject": subject if subject.lower().startswith("re:") else f"Re: {subject}",
        "body": body,
        "in_reply_to": h["Message-ID"],
        "references": f"{h.get('References', '')} {h['Message-ID']}".strip(),
    }
    if not send:
        raw = apply_transform("rfc822_base64", reply)
        wire = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        print(re.split(r"\r?\n\r?\n", wire, maxsplit=1)[0])
        return
    sent = await gmail.messages_send.ainvoke({"body": {"raw": reply, "threadId": got["threadId"]}})
    check = await gmail.messages_get.ainvoke({"id": sent["id"], "format": "metadata"})
    print({k: check["headers"].get(k) for k in ("To", "Cc", "Subject")}, sent["threadId"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("message_id")
    cli.add_argument("--body", default="Thanks, everyone.")
    cli.add_argument("--send", action="store_true")
    args = cli.parse_args()
    asyncio.run(reply_all(args.message_id, args.body, args.send))
