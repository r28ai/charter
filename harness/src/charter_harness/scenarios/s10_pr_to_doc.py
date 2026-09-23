"""github + gdocs — a Google Doc summarising the files a pull request touches."""

from __future__ import annotations

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check, norm
from charter_harness.scenarios.registry import register
from charter_harness.world import World

FILES = [
    ("src/billing/invoice.py", "def total(lines):\n    return sum(l.amount for l in lines)\n"),
    ("docs/billing.md", "# Billing\n\nInvoices are totalled server-side.\n"),
    ("tests/test_invoice.py", "def test_total():\n    assert True\n"),
]


MORE_FILES = [
    ("src/billing/__init__.py", "from .invoice import total\n"),
    ("CHANGELOG.md", "## Unreleased\n\n- Server-side invoice totals.\n"),
]


class PullRequestToDoc(Scenario):
    id = "pr_to_doc"
    packs = ("github", "gdocs")
    summary = "Create a Google Doc listing every file changed in a pull request."
    # files: (path relative to the run's folder, content) committed on the PR branch
    defaults = {"files": FILES}
    variants = {
        "two": {"files": FILES[:2]},
        "four": {"files": FILES + MORE_FILES[:1]},
        "five": {"files": FILES + MORE_FILES},
        "deep_paths": {
            "files": [
                (
                    "services/billing/app/domain/invoice/total.py",
                    "def total(lines):\n    return sum(l.amount for l in lines)\n",
                ),
                ("services/billing/app/domain/invoice/__init__.py", "from .total import total\n"),
                (
                    "services/billing/tests/domain/test_total.py",
                    "def test_total():\n    assert True\n",
                ),
            ]
        },
        "similar_names": {
            "files": [
                ("src/invoice.py", "# invoice\n"),
                ("src/invoices.py", "# invoices\n"),
                ("src/invoice_test.py", "# invoice test\n"),
                ("src/invoice.md", "# invoice notes\n"),
            ]
        },
        "six": {
            "files": FILES + MORE_FILES + [("scripts/backfill_totals.py", "print('backfill')\n")]
        },
    }

    async def seed(self, world: World, ns: str) -> Expected:
        gh = world.github
        await gh.ensure_sandbox()
        base = await gh.default_branch()
        branch = f"{ns}/billing-totals"
        await gh.branch_create(branch, from_branch=base)
        paths = []
        for rel, content in self.params["files"]:
            path = f"{ns}/{rel}"
            await gh.content_put(
                path=path, content=content, message=f"{ns}: add {rel}", branch=branch
            )
            paths.append(path)
        pr = await gh.pull_create(
            title=f"[{ns}] Server-side invoice totals",
            head=branch,
            base=base,
            body="Seeded by the harness.",
        )
        return {
            "repo": gh.full_name,
            "branch": branch,
            "pr_number": pr["number"],
            "pr_title": pr["title"],
            "paths": paths,
            "doc_title": f"{ns} PR summary",
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"Pull request #{expected['pr_number']} in the GitHub repository {expected['repo']} needs a review "
            f'note. Create a Google Doc titled exactly "{expected["doc_title"]}" that states the pull '
            f"request's title and then lists the full path of every file the pull request changes, one per line."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        files = await world.drive.files_list_eventually(name_contains=expected["doc_title"])
        docs = []
        for f in files:
            if f.get("mimeType") != "application/vnd.google-apps.document":
                continue
            doc = await world.docs.document_get(f["id"])
            if doc:
                docs.append(
                    {"id": f["id"], "title": doc.get("title", ""), "text": world.docs.text_of(doc)}
                )
        return {"docs": docs}

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        docs = [d for d in observed["docs"] if norm(d["title"]) == norm(expected["doc_title"])]
        if len(docs) != 1:
            return Verdict.fail(
                f"expected exactly one document titled {expected['doc_title']!r}, found {len(docs)}"
            )
        text = docs[0]["text"].casefold()
        return check(
            [(p.casefold() in text, f"file {p} is not listed") for p in expected["paths"]]
            + [(norm(expected["pr_title"]) in norm(text), "the pull request title is missing")]
        )

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "repo": "o/harness-sandbox",
            "branch": "hx/billing-totals",
            "pr_number": 7,
            "pr_title": "[hx] Server-side invoice totals",
            "paths": [
                "hx/src/billing/invoice.py",
                "hx/docs/billing.md",
                "hx/tests/test_invoice.py",
            ],
            "doc_title": "hx PR summary",
        }
        observed = {
            "docs": [
                {
                    "id": "d",
                    "title": "hx PR summary",
                    "text": "PR #7: [hx] Server-side invoice totals\n\nFiles changed:\n- hx/src/billing/invoice.py\n- hx/docs/billing.md\n- hx/tests/test_invoice.py\n",
                }
            ]
        }
        return expected, observed

    def wrong_observations(
        self, expected: Expected, observed: Observed
    ) -> list[tuple[str, Observed]]:
        doc = observed["docs"][0]
        return [
            (
                "a changed file is missing",
                {"docs": [dict(doc, text=doc["text"].replace("- hx/docs/billing.md\n", ""))]},
            ),
            (
                "the PR title is missing",
                {
                    "docs": [
                        dict(
                            doc,
                            text="Files changed:\n- hx/src/billing/invoice.py\n- hx/docs/billing.md\n- hx/tests/test_invoice.py\n",
                        )
                    ]
                },
            ),
            ("the document was not created", {"docs": []}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        gh = world.github
        await gh.pull_close(expected["pr_number"])
        await gh.branch_delete(expected["branch"])
        for f in await world.drive.files_list(name_contains=expected["doc_title"]):
            await world.drive.file_delete(f["id"])


register(PullRequestToDoc())
