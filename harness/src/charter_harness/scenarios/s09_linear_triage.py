"""linear — move the urgent issues to In Progress with a comment; leave the rest."""

from __future__ import annotations

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check
from charter_harness.scenarios.registry import register
from charter_harness.world import World

ISSUES = [
    ("Update onboarding copy", False),
    ("URGENT: checkout returns 500 for EU cards", True),
    ("Refactor date helpers", False),
    ("URGENT: password reset emails not delivered", True),
    ("Add dark mode toggle", False),
]
COMMENT = "Triaged: escalated"


class LinearTriage(Scenario):
    id = "linear_triage"
    packs = ("linear",)
    summary = "Move URGENT issues to In Progress and comment on them; leave non-urgent issues untouched."
    # issues: (title, urgent) — urgent iff the title contains "URGENT"
    defaults = {"issues": ISSUES}
    variants = {
        "one_urgent": {"issues": [("Update onboarding copy", False), ("URGENT: checkout returns 500 for EU cards", True), ("Refactor date helpers", False)]},
        "three_urgent_of_six": {
            "issues": [
                ("Update onboarding copy", False),
                ("URGENT: checkout returns 500 for EU cards", True),
                ("Refactor date helpers", False),
                ("URGENT: password reset emails not delivered", True),
                ("Add dark mode toggle", False),
                ("URGENT: nightly backup job failing", True),
            ]
        },
        "urgent_mid_title": {
            "issues": [
                ("Payments: URGENT — checkout returns 500 for EU cards", True),
                ("Update onboarding copy", False),
                ("Auth (URGENT) password reset emails not delivered", True),
                ("Add dark mode toggle", False),
            ]
        },
        "all_urgent": {"issues": [("URGENT: API latency spike", True), ("URGENT: login loop on mobile", True), ("URGENT: invoices double-sent", True)]},
        "none_urgent": {"issues": [("Update onboarding copy", False), ("Refactor date helpers", False), ("Add dark mode toggle", False)]},
        "eight": {
            "issues": [
                ("Update onboarding copy", False),
                ("URGENT: checkout returns 500 for EU cards", True),
                ("Refactor date helpers", False),
                ("Tidy the changelog", False),
                ("URGENT: password reset emails not delivered", True),
                ("Add dark mode toggle", False),
                ("Document the export API", False),
                ("URGENT: nightly backup job failing", True),
            ]
        },
    }

    async def seed(self, world: World, ns: str) -> Expected:
        backlog = await world.linear.state_by_type("backlog")
        target = await world.linear.state_by_name("In Progress") or await world.linear.state_by_type("started")
        created = []
        for title, urgent in self.params["issues"]:
            issue = await world.linear.issue_create(title=f"[{ns}] {title}", description="Seeded by the harness.", state_id=backlog["id"])
            created.append({"id": issue["id"], "identifier": issue["identifier"], "title": f"[{ns}] {title}", "urgent": urgent})
        # Linear's title filter lags creation; the model must be able to find these.
        await world.linear.await_tagged(f"[{ns}]", [c["id"] for c in created])
        return {
            "tag": f"[{ns}]",
            "team_key": world.linear.team_key,
            "issues": created,
            "initial_state": backlog["name"],
            "target_state": target["name"],
            "comment": COMMENT,
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"In the Linear team {expected['team_key']}, the issues whose title starts with \"{expected['tag']}\" "
            f"need triage. Every one of them whose title contains \"URGENT\" must be moved to the "
            f"\"{expected['target_state']}\" state and get a comment saying exactly \"{expected['comment']}\". "
            f"Do not change the other {expected['tag']} issues in any way."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        # By id: direct lookups are consistent, and the ids are ours to know.
        issues = await world.linear.issues_by_ids([i["id"] for i in expected["issues"]])
        return {
            "issues": {
                i["id"]: {
                    "state": (i.get("state") or {}).get("name", ""),
                    "comments": [c.get("body", "") for c in (i.get("comments") or {}).get("nodes", [])],
                }
                for i in issues
            }
        }

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        conditions = []
        for issue in expected["issues"]:
            got = observed["issues"].get(issue["id"])
            if got is None:
                conditions.append((False, f"{issue['identifier']} disappeared"))
                continue
            if issue["urgent"]:
                conditions.append((got["state"] == expected["target_state"], f"{issue['identifier']} is in {got['state']!r}, expected {expected['target_state']!r}"))
                conditions.append((any(expected["comment"].casefold() in c.casefold() for c in got["comments"]), f"{issue['identifier']} has no triage comment"))
            else:
                conditions.append((got["state"] == expected["initial_state"], f"non-urgent {issue['identifier']} was moved to {got['state']!r}"))
                conditions.append((not got["comments"], f"non-urgent {issue['identifier']} was commented on"))
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "tag": "[hx]",
            "team_key": "ENG",
            "issues": [
                {"id": "i1", "identifier": "ENG-1", "title": "[hx] Update onboarding copy", "urgent": False},
                {"id": "i2", "identifier": "ENG-2", "title": "[hx] URGENT: checkout returns 500 for EU cards", "urgent": True},
                {"id": "i3", "identifier": "ENG-3", "title": "[hx] URGENT: password reset emails not delivered", "urgent": True},
            ],
            "initial_state": "Backlog",
            "target_state": "In Progress",
            "comment": COMMENT,
        }
        observed = {
            "issues": {
                "i1": {"state": "Backlog", "comments": []},
                "i2": {"state": "In Progress", "comments": ["Triaged: escalated"]},
                "i3": {"state": "In Progress", "comments": ["triaged: Escalated"]},
            }
        }
        return expected, observed

    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]:
        o = observed["issues"]
        return [
            ("a non-urgent issue was moved", {"issues": {**o, "i1": {"state": "In Progress", "comments": []}}}),
            ("an urgent issue was moved but not commented", {"issues": {**o, "i3": {"state": "In Progress", "comments": []}}}),
            ("an urgent issue was commented but not moved", {"issues": {**o, "i2": {"state": "Backlog", "comments": ["Triaged: escalated"]}}}),
            ("an urgent issue went to the wrong state", {"issues": {**o, "i2": {"state": "Done", "comments": ["Triaged: escalated"]}}}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for issue in expected.get("issues", []):
            await world.linear.issue_delete(issue["id"])
        await world.linear.delete_tagged(expected["tag"])  # anything the model added


register(LinearTriage())
