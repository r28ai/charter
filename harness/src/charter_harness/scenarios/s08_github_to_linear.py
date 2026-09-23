"""github + linear — mirror labelled GitHub issues into Linear and link back."""

from __future__ import annotations

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check, norm
from charter_harness.scenarios.registry import register
from charter_harness.world import World
from charter_harness.world._http import eventually

ISSUES = [
    ("Login page flashes white before render", "Seen on Safari 17 and Firefox."),
    ("CSV export drops the header row", "Only when the filter is non-empty."),
    ("Webhook retries never stop on 410", "Should give up after the first 410."),
]
MORE_ISSUES = [
    ("Search ignores accented characters", '"cafe" should match "café".'),
    ("Timezone picker lists UTC twice", "Both entries map to the same zone."),
]
DISTRACTORS = [
    ("Bump dependencies for Q4", "Housekeeping; not user-facing."),
    ("Rename internal module `legacy_auth`", "Refactor only."),
    ("Draft: pricing page copy", "Marketing owns this."),
]


class GitHubToLinear(Scenario):
    id = "github_to_linear"
    packs = ("github", "linear")
    summary = (
        "Create a Linear issue per labelled GitHub issue and comment the Linear identifier back."
    )
    # issues: (title, body) carrying the label. distractors: open issues in the
    # same repository without the label, which must not be mirrored.
    defaults = {"issues": ISSUES, "distractors": 0}
    variants = {
        "two": {"issues": ISSUES[:2]},
        "four": {"issues": ISSUES + MORE_ISSUES[:1]},
        "five": {"issues": ISSUES + MORE_ISSUES},
        "with_distractors": {"issues": ISSUES, "distractors": 2},
        "two_with_distractors": {"issues": ISSUES[:2], "distractors": 3},
        "awkward_titles": {
            "issues": [
                ('Crash when title contains "quotes" and a trailing space ', "Reproducible."),
                ("500 on POST /api/v2/orders?dry_run=true", "Only with the query flag."),
                ("Émoji in usernames breaks the sidebar 🚀", "Unicode width miscount."),
            ]
        },
    }

    async def seed(self, world: World, ns: str) -> Expected:
        gh = world.github
        await gh.ensure_sandbox()
        await gh.label_ensure(ns)
        created = []
        for title, body in self.params["issues"]:
            issue = await gh.issue_create(title=title, body=body, labels=[ns])
            created.append({"number": issue["number"], "title": title, "url": issue["html_url"]})
        distractors = []
        for i in range(self.params["distractors"]):
            title, body = DISTRACTORS[i % len(DISTRACTORS)]
            issue = await gh.issue_create(title=f"{title} ({ns})", body=body, labels=[])
            distractors.append({"number": issue["number"], "title": f"{title} ({ns})"})
        # The agent's first move is to list open issues by this label; GitHub's
        # listing can trail a fresh write by a few seconds, and an agent that is
        # shown one issue of three cannot be blamed for mirroring one.
        await gh.await_issues_listed(label=ns, numbers=[c["number"] for c in created])
        return {
            "repo": gh.full_name,
            "label": ns,
            "issues": created,
            "distractors": distractors,
            "team_key": world.linear.team_key,
            "tag": f"[{ns}]",
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f'In the GitHub repository {expected["repo"]}, the open issues labelled "{expected["label"]}" '
            f"need to be tracked in Linear. For each of them, create an issue in the Linear team with key "
            f'{expected["team_key"]} titled "{expected["tag"]} " followed by the GitHub issue\'s exact title, '
            f"with the GitHub issue URL in its description. Then comment on each GitHub issue with the "
            f'identifier of the Linear issue you created for it (for example "Tracked in {expected["team_key"]}-123").'
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        # The model created these, so only the (lagging) title filter can find them.
        linear_issues = await world.linear.issues_tagged_eventually(
            expected["tag"], at_least=len(expected["issues"])
        )
        # Same lag on the comments the agent just posted: wait, bounded, until
        # every seeded issue shows at least one, then take whatever is there.
        numbers = [issue["number"] for issue in expected["issues"]]

        async def read_comments() -> dict[str, list[str]]:
            out = {}
            for number in numbers:
                items = await world.github.issue_comments(number)
                out[str(number)] = [c.get("body", "") for c in items]
            return out

        comments = await eventually(
            read_comments, lambda c: all(c[str(n)] for n in numbers), timeout=20.0
        )
        return {
            "linear": [{"identifier": i["identifier"], "title": i["title"]} for i in linear_issues],
            "comments": comments,
        }

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        conditions = []
        by_title = {}
        for li in observed["linear"]:
            by_title.setdefault(norm(li["title"]), []).append(li["identifier"])
        for issue in expected["issues"]:
            wanted = norm(f"{expected['tag']} {issue['title']}")
            ids = by_title.get(wanted, [])
            conditions.append(
                (len(ids) == 1, f"expected one Linear issue titled {wanted!r}, found {len(ids)}")
            )
            bodies = " ".join(observed["comments"].get(str(issue["number"]), [])).upper()
            conditions.append(
                (
                    any(i.upper() in bodies for i in ids),
                    f"GitHub #{issue['number']} has no comment naming its Linear issue",
                )
            )
        conditions.append(
            (
                len(observed["linear"]) == len(expected["issues"]),
                f"{len(observed['linear'])} Linear issues carry the tag, expected {len(expected['issues'])}",
            )
        )
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "repo": "o/harness-sandbox",
            "label": "hx",
            "issues": [
                {"number": 1, "title": "Login page flashes white before render", "url": "u1"},
                {"number": 2, "title": "CSV export drops the header row", "url": "u2"},
            ],
            "team_key": "ENG",
            "tag": "[hx]",
        }
        observed = {
            "linear": [
                {"identifier": "ENG-10", "title": "[hx] Login page flashes white before render"},
                {"identifier": "ENG-11", "title": "[hx] CSV export drops the header row"},
            ],
            "comments": {"1": ["Tracked in ENG-10"], "2": ["Mirrored to Linear as eng-11."]},
        }
        return expected, observed

    def wrong_observations(
        self, expected: Expected, observed: Observed
    ) -> list[tuple[str, Observed]]:
        return [
            (
                "a GitHub issue has no link-back comment",
                {**observed, "comments": {**observed["comments"], "2": []}},
            ),
            ("a Linear issue is missing", {**observed, "linear": observed["linear"][:1]}),
            (
                "a comment names the wrong Linear issue",
                {**observed, "comments": {**observed["comments"], "2": ["Tracked in ENG-10"]}},
            ),
            (
                "a Linear title was paraphrased",
                {
                    **observed,
                    "linear": [
                        observed["linear"][0],
                        {"identifier": "ENG-11", "title": "[hx] CSV export missing header"},
                    ],
                },
            ),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        await world.linear.delete_tagged(expected["tag"])
        if expected.get("distractors"):
            await world.linear.delete_tagged(f"({ns})")  # a distractor mirrored without the tag
        for issue in expected.get("issues", []) + expected.get("distractors", []):
            await world.github.issue_close(issue["number"])
        await world.github.label_delete(expected["label"])


register(GitHubToLinear())
