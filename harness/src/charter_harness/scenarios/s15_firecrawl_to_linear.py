"""firecrawl + linear — scrape a page and file its heading as an issue."""

from __future__ import annotations

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check, norm
from charter_harness.scenarios.registry import register
from charter_harness.world import World

BODY = (
    "## Purpose\n\nThis runbook covers the steps to deploy the billing service to production.\n\n"
    "## Steps\n\n1. Freeze merges.\n2. Tag the release.\n3. Run the migration.\n4. Roll out by region.\n"
)
PHRASE = "deploy the billing service"

POSTMORTEM_BODY = (
    "## Summary\n\nFor 41 minutes the checkout API returned 502s for customers routed through the EU load balancer.\n\n"
    "## Timeline\n\n- 03:02 alerts fire\n- 03:15 rollback started\n- 03:43 recovered\n\n## Action items\n\n- Add a canary to the EU pool.\n"
)
POSTMORTEM_PHRASE = "returned 502s for customers routed through the EU load balancer"

ROADMAP_BODY = (
    "## Themes\n\nThe quarter is about payments reliability and billing transparency.\n\n"
    "## Bets\n\n- Retry failed card payments automatically\n- Itemised invoices\n- Usage alerts before overage\n"
)
ROADMAP_PHRASE = "payments reliability and billing transparency"

DECOY_H2_BODY = (
    "## Deployment Runbook (superseded)\n\nThe old procedure is kept for reference only.\n\n"
    "## Current procedure\n\nThis runbook covers the steps to deploy the billing service to production.\n\n"
    "1. Freeze merges.\n2. Tag the release.\n3. Run the migration.\n"
)

CODE_BLOCK_BODY = (
    "## Overview\n\nThis runbook covers the steps to deploy the billing service to production.\n\n"
    "## Example\n\n```bash\n# Not a heading: this is a shell comment\ndeploy --service billing --region eu\n```\n"
)


class FirecrawlToLinear(Scenario):
    id = "firecrawl_to_linear"
    packs = ("firecrawl", "linear")
    seed_only = ("github",)  # the scrape target is a file in the sandbox repository
    summary = "Scrape a page and create a Linear issue whose title is the page's top-level heading."
    # heading: the H1 (after the namespace). body: the rest of the page.
    # phrase: a sentence from the body the issue description must carry.
    defaults = {"heading": "Deployment Runbook v3", "body": BODY, "phrase": PHRASE}
    variants = {
        "postmortem": {
            "heading": "Incident 2026-09-03 Postmortem",
            "body": POSTMORTEM_BODY,
            "phrase": POSTMORTEM_PHRASE,
        },
        "roadmap": {
            "heading": "Q4 Roadmap: Payments & Billing",
            "body": ROADMAP_BODY,
            "phrase": ROADMAP_PHRASE,
        },
        "decoy_h2": {"heading": "Deployment Runbook v4", "body": DECOY_H2_BODY, "phrase": PHRASE},
        "code_block": {
            "heading": "Deployment Runbook v3",
            "body": CODE_BLOCK_BODY,
            "phrase": PHRASE,
        },
        "long_heading": {
            "heading": "Runbook for deploying the billing service to production without customer-visible downtime",
            "body": BODY,
            "phrase": PHRASE,
        },
    }

    async def seed(self, world: World, ns: str) -> Expected:
        gh = world.github
        await gh.ensure_sandbox()
        base = await gh.default_branch()
        heading = f"{ns} {self.params['heading']}"
        path = f"{ns}/RUNBOOK.md"
        await gh.content_put(
            path=path,
            content=f"# {heading}\n\n{self.params['body']}",
            message=f"{ns}: add runbook",
            branch=base,
        )
        return {
            "tag": f"[{ns}]",
            "team_key": world.linear.team_key,
            "url": gh.blob_url(path=path, branch=base) + "?plain=1",
            "path": path,
            "branch": base,
            "heading": heading,
            "phrase": self.params["phrase"],
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"Read the page at {expected['url']} and create one issue in the Linear team {expected['team_key']} "
            f'whose title is "{expected["tag"]} " followed by the page\'s top-level heading (its H1) exactly as '
            f"written, and whose description contains the page's content."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        issues = await world.linear.issues_tagged_eventually(expected["tag"], at_least=1)
        return {
            "issues": [
                {
                    "identifier": i["identifier"],
                    "title": i["title"],
                    "description": i.get("description") or "",
                }
                for i in issues
            ]
        }

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        issues = observed["issues"]
        if len(issues) != 1:
            return Verdict.fail(f"expected exactly one tagged Linear issue, found {len(issues)}")
        title = norm(issues[0]["title"])
        wanted = norm(f"{expected['tag']} {expected['heading']}")
        phrase = expected.get("phrase", PHRASE)
        return check(
            [
                (
                    title == wanted,
                    f"title is {issues[0]['title']!r}, expected {expected['tag']} {expected['heading']!r}",
                ),
                (
                    norm(phrase) in norm(issues[0]["description"]),
                    "description does not carry the page content",
                ),
            ]
        )

    def example(self) -> tuple[Expected, Observed]:
        heading = f"hx {self.params['heading']}"
        expected = {
            "tag": "[hx]",
            "team_key": "ENG",
            "url": "https://github.com/o/harness-sandbox/blob/main/hx/RUNBOOK.md?plain=1",
            "path": "hx/RUNBOOK.md",
            "branch": "main",
            "heading": heading,
            "phrase": self.params["phrase"],
        }
        observed = {
            "issues": [
                {
                    "identifier": "ENG-50",
                    "title": f"[hx] {heading}",
                    "description": f"# {heading}\n\n" + self.params["body"],
                }
            ]
        }
        return expected, observed

    def wrong_observations(
        self, expected: Expected, observed: Observed
    ) -> list[tuple[str, Observed]]:
        i = observed["issues"][0]
        return [
            (
                "the title differs from the H1",
                {"issues": [dict(i, title="[hx] Deployment Runbook")]},
            ),
            ("an H2 was used as the title", {"issues": [dict(i, title="[hx] Purpose")]}),
            ("the description is empty", {"issues": [dict(i, description="")]}),
            ("two issues were created", {"issues": [i, dict(i, identifier="ENG-51")]}),
            ("no issue was created", {"issues": []}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        await world.linear.delete_tagged(expected["tag"])
        await world.github.content_delete(
            path=expected["path"], branch=expected["branch"], message=f"{ns}: remove runbook"
        )


register(FirecrawlToLinear())
