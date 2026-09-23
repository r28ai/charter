"""gdocs + gmail — draft a reply on a thread from a document template; never send."""

from __future__ import annotations

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check
from charter_harness.scenarios.registry import register
from charter_harness.world import World
from charter_harness.world.google import body_text, header

TEMPLATE = (
    "Hello,\n\nThank you for reaching out about your invoice. We have reviewed the account and the "
    "balance shown was carried over from the previous billing cycle in error. A corrected invoice will "
    "follow within two business days; no payment is due until then.\n\nKind regards,\nBilling team\n"
)
KEY_PHRASE = "corrected invoice will follow within two business days"

SHIPPING_TEMPLATE = (
    "Hello,\n\nThanks for your patience. Your order left our warehouse this morning and the carrier's "
    "tracking page will update within 24 hours. If it has not arrived in five business days, reply to this "
    "message and we will reship at no cost.\n\nBest,\nSupport\n"
)
SHIPPING_PHRASE = "we will reship at no cost"
SHORT_TEMPLATE = "Hi,\n\nConfirmed — the duplicate charge has been reversed and will show on your statement within three days.\n\nThanks,\nBilling\n"
SHORT_PHRASE = "duplicate charge has been reversed"
LONG_TEMPLATE = (
    "Hello,\n\nThank you for writing in about the discrepancy on your account.\n\n"
    "What happened: a pricing change scheduled for next quarter was applied to a subset of accounts a cycle early. "
    "Yours was one of them.\n\n"
    "What we are doing: the affected invoices are being voided and reissued at the correct rate, and a credit "
    "for the difference will be applied automatically.\n\n"
    "What you need to do: nothing. If you have already paid the higher amount, the credit will offset your next invoice.\n\n"
    "Kind regards,\nBilling team\n"
)
LONG_PHRASE = "voided and reissued at the correct rate"
DISTRACTOR_SUBJECTS = [
    "Quick question about the dashboard",
    "Re: our call last week",
    "Feature idea",
]


class DocToGmailDraft(Scenario):
    id = "doc_to_gmail_draft"
    packs = ("gdocs", "gmail")
    summary = (
        "Create a Gmail draft reply on a labelled thread using the text of a template document."
    )
    # template/key_phrase: the document text and the sentence the judge requires.
    # distractors: other threads from the same sender, without the label.
    defaults = {"template": TEMPLATE, "key_phrase": KEY_PHRASE, "distractors": 0}
    variants = {
        "shipping": {"template": SHIPPING_TEMPLATE, "key_phrase": SHIPPING_PHRASE},
        "short": {"template": SHORT_TEMPLATE, "key_phrase": SHORT_PHRASE},
        "long": {"template": LONG_TEMPLATE, "key_phrase": LONG_PHRASE},
        "with_distractor_thread": {"distractors": 1},
        "two_distractor_threads": {"distractors": 2},
        "shipping_with_distractors": {
            "template": SHIPPING_TEMPLATE,
            "key_phrase": SHIPPING_PHRASE,
            "distractors": 2,
        },
    }

    async def seed(self, world: World, ns: str) -> Expected:
        label = await world.gmail.label_create(f"{ns}-billing")
        sender = f"ada.{ns}@harness.invalid"
        msg = await world.gmail.message_insert(
            sender=f"Ada Lovelace <{sender}>",
            to="me@harness.invalid",
            subject=f"[{ns}] Invoice balance looks wrong",
            body="Hi, my latest invoice shows a balance I do not recognise. Can you check?",
            label_ids=["INBOX", label["id"]],
        )
        distractor_ids = []
        for i in range(self.params["distractors"]):
            other = await world.gmail.message_insert(
                sender=f"Ada Lovelace <{sender}>",
                to="me@harness.invalid",
                subject=f"[{ns}] {DISTRACTOR_SUBJECTS[i % len(DISTRACTOR_SUBJECTS)]}",
                body="Unrelated to billing.",
                label_ids=["INBOX"],
            )
            distractor_ids.append(other["id"])
        await world.gmail.await_labelled(label["id"], [msg["id"]])
        doc = await world.docs.document_create(
            f"{ns} billing reply template", text=self.params["template"]
        )
        return {
            "label": {"id": label["id"], "name": label["name"]},
            "message_id": msg["id"],
            "distractor_ids": distractor_ids,
            "thread_id": msg["threadId"],
            "sender": sender,
            "doc_id": doc["documentId"],
            "doc_title": f"{ns} billing reply template",
            "key_phrase": self.params["key_phrase"],
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f'There is one Gmail thread labelled "{expected["label"]["name"]}". Its thread id is '
            f"{expected['thread_id']}. Draft a reply *on that thread* (Gmail will open a new thread "
            f"unless the draft's message.threadId is {expected['thread_id']} and the subject stays a "
            f"Re: of the original) to the person who wrote it, using the text of the Google Doc with "
            f'id {expected["doc_id"]} ("{expected["doc_title"]}") as the body of the reply. Save it '
            f"as a draft only — do not send anything."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        drafts = []
        for d in await world.gmail.drafts_list():
            full = await world.gmail.draft_get(d["id"])
            if full is None:
                continue
            message = full.get("message") or {}
            subject = header(message, "Subject")
            # Drafts on our thread are ours. A draft elsewhere whose subject or
            # recipient carries the namespace is a misthreaded attempt — keep it
            # so the judge can say so; anything else in the mailbox is not ours.
            if not self._ours(message, ns, expected):
                continue
            drafts.append(
                {
                    "id": d["id"],
                    "thread_id": message.get("threadId"),
                    "to": header(message, "To"),
                    "subject": subject,
                    "body": body_text(message),
                }
            )
        thread = await world.gmail.thread_get(expected["thread_id"])
        sent = [m for m in thread.get("messages", []) if "SENT" in (m.get("labelIds") or [])]
        return {"drafts": drafts, "sent_in_thread": len(sent)}

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        on_thread = [d for d in observed["drafts"] if d["thread_id"] == expected["thread_id"]]
        conditions = [
            (observed["sent_in_thread"] == 0, "a message was sent"),
            (
                len(on_thread) == 1,
                f"expected exactly one draft on the thread, found {len(on_thread)} (of {len(observed['drafts'])} drafts)",
            ),
        ]
        if len(on_thread) == 1:
            d = on_thread[0]
            conditions.append(
                (
                    expected["sender"].casefold() in d["to"].casefold(),
                    f"draft is addressed to {d['to']!r}, not the sender",
                )
            )
            conditions.append(
                (
                    expected["key_phrase"].casefold() in " ".join(d["body"].split()).casefold(),
                    "draft body does not carry the template text",
                )
            )
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "label": {"id": "L", "name": "hx-billing"},
            "message_id": "m1",
            "thread_id": "t1",
            "sender": "ada.hx@harness.invalid",
            "doc_id": "d1",
            "doc_title": "hx billing reply template",
            "key_phrase": self.params["key_phrase"],
        }
        observed = {
            "drafts": [
                {
                    "id": "r1",
                    "thread_id": "t1",
                    "to": "Ada Lovelace <ada.hx@harness.invalid>",
                    "subject": "Re: [hx] Invoice balance looks wrong",
                    "body": self.params["template"],
                }
            ],
            "sent_in_thread": 0,
        }
        return expected, observed

    def wrong_observations(
        self, expected: Expected, observed: Observed
    ) -> list[tuple[str, Observed]]:
        d = observed["drafts"][0]
        return [
            (
                "the draft is not on the thread",
                {**observed, "drafts": [dict(d, thread_id="other")]},
            ),
            (
                "the draft is addressed to someone else",
                {**observed, "drafts": [dict(d, to="me@harness.invalid")]},
            ),
            (
                "the draft body is not the template",
                {**observed, "drafts": [dict(d, body="Hi, looking into it.")]},
            ),
            ("the reply was sent instead of drafted", {**observed, "sent_in_thread": 1}),
        ]

    @staticmethod
    def _ours(message: dict, ns: str, expected: Expected) -> bool:
        # The recipient check catches a draft whose subject mistyped the namespace
        # (seen once: "hhac680" for "hdac680") — it is still addressed to our
        # seeded sender, so it is still ours to grade and to delete.
        return (
            message.get("threadId") == expected["thread_id"]
            or ns in header(message, "Subject")
            or expected["sender"].casefold() in header(message, "To").casefold()
        )

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for d in await world.gmail.drafts_list():
            full = await world.gmail.draft_get(d["id"])
            if full is None:
                continue
            message = full.get("message") or {}
            if self._ours(message, ns, expected):
                await world.gmail.draft_delete(d["id"])
        for mid in [expected["message_id"]] + expected.get("distractor_ids", []):
            await world.gmail.message_trash(mid)
        await world.gmail.label_delete(expected["label"]["id"])
        await world.drive.file_delete(expected["doc_id"])


register(DocToGmailDraft())
