"""The model fills in an email. Charter writes the MIME and the base64 the API wants.

Gmail's send endpoint takes one field, `raw`: the whole message as base64url MIME. The
model never builds that. httpbin.org stands in for Gmail and echoes back what it got.
"""

import base64
from typing import Annotated

from pydantic import BaseModel

from charter import Body, EmailContent, Format, api_key_tool_factory


class SendEmail(BaseModel):
    raw: Annotated[
        EmailContent,
        Body(envelop=True),
        Format("rfc822_base64"),
    ]


mail_api = api_key_tool_factory(
    pack="mail",
    base_url="https://httpbin.org/anything/",
    api_key_headers={"Authorization": "Bearer sk_live_123"},
)
send_email = mail_api(
    name="send_email",
    description="Send an email.",
    method="POST",
    url_template="gmail/v1/users/me/messages/send",
    args_schema=SendEmail,
)

email_fields = send_email.to_json_schema()["parameters"]["$defs"]["EmailContent"]["properties"]
print("the model fills in ", ", ".join(email_fields))
# the model fills in  to, subject, body, mimeType, bodyHtml, cc, bcc, from, reply_to, ...

email = {"to": "ada@example.com", "subject": "Lunch?", "body": "Thursday at noon?"}
raw = send_email.invoke({"raw": email})["json"]["raw"]
print(f"Charter sent       {{'raw': '{raw[:40]}...'}}")
# Charter sent       {'raw': 'Q29udGVudC1UeXBlOiB0ZXh0L3BsYWluOyBjaGFy...'}

print("\nwhich decodes to:")
print(base64.urlsafe_b64decode(raw + "==").decode())
# which decodes to:
# Content-Type: text/plain; charset="utf-8"
# Content-Transfer-Encoding: 7bit
# MIME-Version: 1.0
# To: ada@example.com
# Subject: Lunch?
#
# Thursday at noon?
