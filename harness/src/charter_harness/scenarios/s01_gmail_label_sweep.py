"""gmail — move every message from one label to a new one."""

from __future__ import annotations

from charter_harness.scenarios._fixtures import email, person
from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check
from charter_harness.scenarios.registry import register
from charter_harness.world import World


class GmailLabelSweep(Scenario):
    id = "gmail_label_sweep"
    packs = ("gmail",)
    summary = "Create a label and move every message carrying label A onto it."
    # count: messages under label A. distractors: messages under a third label
    # in the same inbox, which must not be touched.
    defaults = {"count": 4, "distractors": 0}
    variants = {
        "two": {"count": 2},
        "six": {"count": 6},
        "eight": {"count": 8},
        "with_distractors": {"count": 4, "distractors": 2},
        "six_with_distractors": {"count": 6, "distractors": 3},
    }

    async def seed(self, world: World, ns: str) -> Expected:
        label_a = await world.gmail.label_create(f"{ns}-review")
        ids: list[str] = []
        for i in range(self.params["count"]):
            name, _ = person(i)
            msg = await world.gmail.message_insert(
                sender=f"{name} <{email(ns, i)}>",
                to="me@harness.invalid",
                subject=f"[{ns}] Review request {i + 1}",
                body=f"Please review item {i + 1}.",
                label_ids=["INBOX", label_a["id"]],
            )
            ids.append(msg["id"])
        await world.gmail.await_labelled(label_a["id"], ids)
        expected: Expected = {
            "label_a": {"id": label_a["id"], "name": label_a["name"]},
            "label_b_name": f"{ns}-reviewed",
            "message_ids": ids,
            "distractor_ids": [],
        }
        if self.params["distractors"]:
            label_other = await world.gmail.label_create(f"{ns}-archive")
            for i in range(self.params["distractors"]):
                name, _ = person(i + 3)
                msg = await world.gmail.message_insert(
                    sender=f"{name} <{email(ns, i + 3)}>",
                    to="me@harness.invalid",
                    subject=f"[{ns}] Archived note {i + 1}",
                    body="Nothing to review here.",
                    label_ids=["INBOX", label_other["id"]],
                )
                expected["distractor_ids"].append(msg["id"])
            expected["label_other"] = {"id": label_other["id"], "name": label_other["name"]}
            await world.gmail.await_labelled(label_other["id"], expected["distractor_ids"])
        return expected

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"In Gmail, create a label named \"{expected['label_b_name']}\". Then move every message "
            f"that currently has the label \"{expected['label_a']['name']}\" onto the new label: each of "
            f"those messages must end up with \"{expected['label_b_name']}\" and without "
            f"\"{expected['label_a']['name']}\". Leave every other label on the messages as it is, and "
            f"do not touch messages that do not carry \"{expected['label_a']['name']}\"."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        label_b = await world.gmail.label_by_name(expected["label_b_name"])
        with_a = [m["id"] for m in await world.gmail.messages_list(label_ids=[expected["label_a"]["id"]])]
        with_b: list[str] = []
        if label_b:
            with_b = [m["id"] for m in await world.gmail.messages_list(label_ids=[label_b["id"]])]
        observed: Observed = {"label_b_exists": label_b is not None, "with_a": sorted(with_a), "with_b": sorted(with_b)}
        if expected.get("label_other"):
            observed["with_other"] = sorted(m["id"] for m in await world.gmail.messages_list(label_ids=[expected["label_other"]["id"]]))
        return observed

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        wanted = set(expected["message_ids"])
        distractors = set(expected.get("distractor_ids") or [])
        conditions = [
            (observed["label_b_exists"], "the new label was not created"),
            (not (wanted & set(observed["with_a"])), "some messages still carry the old label"),
            (wanted <= set(observed["with_b"]), "some messages did not receive the new label"),
            (not (distractors & set(observed["with_b"])), "a message that never had the old label received the new one"),
        ]
        if distractors:
            conditions.append((distractors <= set(observed.get("with_other") or []), "a message outside the old label lost its own label"))
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected: Expected = {
            "label_a": {"id": "Label_1", "name": "hx-review"},
            "label_b_name": "hx-reviewed",
            "message_ids": ["m1", "m2", "m3", "m4"],
            "distractor_ids": [],
        }
        observed: Observed = {"label_b_exists": True, "with_a": [], "with_b": ["m1", "m2", "m3", "m4"]}
        if self.params["distractors"]:
            expected["distractor_ids"] = ["d1", "d2"]
            expected["label_other"] = {"id": "Label_9", "name": "hx-archive"}
            observed["with_other"] = ["d1", "d2"]
        return expected, observed

    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]:
        ids = expected["message_ids"]
        wrongs = [
            ("one message still carries the old label", {**observed, "with_a": [ids[0]]}),
            ("one message never received the new label", {**observed, "with_b": ids[1:]}),
            ("the new label does not exist", {**observed, "label_b_exists": False, "with_b": []}),
        ]
        if expected.get("distractor_ids"):
            d = expected["distractor_ids"]
            wrongs.append(("a distractor received the new label", {**observed, "with_b": observed["with_b"] + [d[0]]}))
            wrongs.append(("a distractor lost its own label", {**observed, "with_other": d[1:]}))
        return wrongs

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for mid in expected.get("message_ids", []) + expected.get("distractor_ids", []):
            await world.gmail.message_trash(mid)
        await world.gmail.label_delete(expected["label_a"]["id"])
        if expected.get("label_other"):
            await world.gmail.label_delete(expected["label_other"]["id"])
        label_b = await world.gmail.label_by_name(expected["label_b_name"])
        if label_b:
            await world.gmail.label_delete(label_b["id"])


register(GmailLabelSweep())
