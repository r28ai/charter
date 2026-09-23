"""linear + slack — one digest message listing a set of issues."""

from __future__ import annotations

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check
from charter_harness.scenarios.registry import register
from charter_harness.world import World

ISSUES = [
    "Rotate the staging TLS certificate",
    "Backfill missing invoice PDFs",
    "Upgrade Postgres to 17",
]
MORE_ISSUES = [
    "Remove the legacy webhook signer",
    "Add rate limits to the export API",
    "Fix flaky checkout e2e test",
]
DISTRACTORS = [
    "Plan the Q4 offsite",
    "Renew the design tool licences",
    "Archive stale feature flags",
]


class LinearToSlackDigest(Scenario):
    id = "linear_to_slack_digest"
    packs = ("linear", "slack")
    summary = "Post a single Slack message listing each tagged Linear issue's identifier and title."
    # issues: tagged issue titles. distractors: issues in the same team that
    # mention the run but do not carry the tag prefix; they must not be listed.
    defaults = {"issues": ISSUES, "distractors": 0}
    variants = {
        "two": {"issues": ISSUES[:2]},
        "five": {"issues": ISSUES + MORE_ISSUES[:2]},
        "six": {"issues": ISSUES + MORE_ISSUES},
        "with_distractors": {"issues": ISSUES, "distractors": 2},
        "five_with_distractors": {"issues": ISSUES + MORE_ISSUES[:2], "distractors": 3},
        "long_titles": {
            "issues": [
                "Investigate intermittent 502s from the EU load balancer during the 03:00 UTC backup window",
                "Migrate the notification service from the deprecated push gateway to the new provider before the sunset date",
                "Audit every third-party script on the checkout page for PCI scope",
            ]
        },
    }

    async def seed(self, world: World, ns: str) -> Expected:
        created = []
        for title in self.params["issues"]:
            issue = await world.linear.issue_create(
                title=f"[{ns}] {title}", description="Seeded by the harness."
            )
            created.append(
                {"id": issue["id"], "identifier": issue["identifier"], "title": f"[{ns}] {title}"}
            )
        distractors = []
        for i in range(self.params["distractors"]):
            title = DISTRACTORS[i % len(DISTRACTORS)]
            issue = await world.linear.issue_create(
                title=f"{title} ({ns})", description="Seeded by the harness; not tagged."
            )
            distractors.append(
                {"id": issue["id"], "identifier": issue["identifier"], "title": f"{title} ({ns})"}
            )
        await world.linear.await_tagged(f"[{ns}]", [c["id"] for c in created])
        if distractors:
            await world.linear.await_tagged(f"({ns})", [d["id"] for d in distractors])
        channel_id = await world.slack.channel_id()
        marker = await world.slack.post(
            f"[{ns}] digest requested"
        )  # a timestamp to read history from
        return {
            "tag": f"[{ns}]",
            "team_key": world.linear.team_key,
            "issues": created,
            "distractors": distractors,
            "channel": world.slack.channel_name,
            "channel_id": channel_id,
            "since_ts": marker["ts"],
            "owned": {"slack.channel": [channel_id, world.slack.channel_name]},
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"Post a digest to the Slack channel #{expected['channel']}: a single message that starts with "
            f'"{expected["tag"]}" and then lists every issue in the Linear team {expected["team_key"]} whose '
            f'title starts with "{expected["tag"]}" — one line per issue with its identifier (for example '
            f"{expected['team_key']}-42) and its title. Post exactly one message, and list nothing else."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        history = await world.slack.history(oldest=expected["since_ts"])
        messages = [
            {"ts": m.get("ts"), "text": m.get("text", "")}
            for m in history
            if m.get("ts") != expected["since_ts"] and expected["tag"] in m.get("text", "")
        ]
        return {"messages": messages}

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        msgs = observed["messages"]
        if len(msgs) != 1:
            return Verdict.fail(f"expected exactly one digest message, found {len(msgs)}")
        text = msgs[0]["text"].upper()
        conditions = [
            (i["identifier"].upper() in text, f"{i['identifier']} is missing from the digest")
            for i in expected["issues"]
        ]
        conditions += [
            (d["identifier"].upper() not in text, f"untagged issue {d['identifier']} was listed")
            for d in expected.get("distractors", [])
        ]
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected: Expected = {
            "tag": "[hx]",
            "team_key": "ENG",
            "issues": [
                {
                    "id": "a",
                    "identifier": "ENG-40",
                    "title": "[hx] Rotate the staging TLS certificate",
                },
                {"id": "b", "identifier": "ENG-41", "title": "[hx] Backfill missing invoice PDFs"},
            ],
            "distractors": [],
            "channel": "harness",
            "channel_id": "C1",
            "since_ts": "1.0",
        }
        if self.params["distractors"]:
            expected["distractors"] = [
                {"id": "z", "identifier": "ENG-99", "title": "Plan the Q4 offsite (hx)"}
            ]
        observed = {
            "messages": [
                {
                    "ts": "2.0",
                    "text": "[hx] Open issues\n• ENG-40 — [hx] Rotate the staging TLS certificate\n• eng-41 — [hx] Backfill missing invoice PDFs",
                }
            ]
        }
        return expected, observed

    def wrong_observations(
        self, expected: Expected, observed: Observed
    ) -> list[tuple[str, Observed]]:
        m = observed["messages"][0]
        wrongs = [
            (
                "an identifier is missing",
                {
                    "messages": [
                        dict(
                            m,
                            text="[hx] Open issues\n• ENG-40 — Rotate the staging TLS certificate",
                        )
                    ]
                },
            ),
            ("two messages were posted", {"messages": [m, dict(m, ts="3.0")]}),
            ("nothing was posted", {"messages": []}),
        ]
        if expected.get("distractors"):
            wrongs.append(
                (
                    "an untagged issue was listed",
                    {
                        "messages": [
                            dict(m, text=m["text"] + "\n• ENG-99 — Plan the Q4 offsite (hx)")
                        ]
                    },
                )
            )
        return wrongs

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for issue in expected.get("issues", []) + expected.get("distractors", []):
            await world.linear.issue_delete(issue["id"])
        await world.linear.delete_tagged(expected["tag"])
        if expected.get("distractors"):
            await world.linear.delete_tagged(f"({ns})")
        for m in await world.slack.history(oldest=expected["since_ts"]):
            if expected["tag"] in m.get("text", ""):
                await world.slack.delete(m["ts"])
        await world.slack.delete(expected["since_ts"])


register(LinearToSlackDigest())
