"""slack + github — file a bug report thread as an issue and link it back in the thread."""

from __future__ import annotations

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check
from charter_harness.scenarios.registry import register
from charter_harness.world import World

TITLE = "Export job silently drops rows over 10k"
REPLIES = [
    "Repro: export the 'all customers' view on a workspace with 12,400 rows; the file has 10,000.",
    "Confirmed on staging too — looks like the paginator stops after page 100.",
    "Expected: every row, or a visible error. Got: a truncated file and a success toast.",
]


MORE_REPLIES = [
    "Workaround for now: export in two halves with a date filter.",
    "Logs show the paginator's cursor resets to null when page_size * page > 10000.",
]
LOGIN_TITLE = "Login loops back to the sign-in page on Safari"
LOGIN_REPLIES = [
    "Repro: Safari 17.4, private window, sign in with Google; lands back on /login with no error.",
    "Chrome and Firefox are fine. Clearing cookies does not help.",
    "The session cookie is set with SameSite=None but without Secure on the staging domain.",
]
INVOICE_TITLE = "Invoice PDF shows the wrong currency symbol for CHF accounts"
INVOICE_REPLIES = [
    "Repro: any account with billing currency CHF; the PDF prints € instead of CHF.",
    "The HTML invoice is correct, only the PDF renderer is wrong.",
    "Probably the locale fallback in the PDF template; it defaults to de-DE.",
    "Affects 38 accounts as of this morning.",
]


class SlackThreadToGitHub(Scenario):
    id = "slack_thread_to_github"
    packs = ("slack", "github")
    summary = "Turn a Slack bug-report thread into a GitHub issue and reply in-thread with the issue URL."
    # title: the bug report. replies: the thread's follow-ups, all of which
    # must appear in the issue body.
    defaults = {"title": TITLE, "replies": REPLIES}
    variants = {
        "two_replies": {"replies": REPLIES[:2]},
        "four_replies": {"replies": REPLIES + MORE_REPLIES[:1]},
        "five_replies": {"replies": REPLIES + MORE_REPLIES},
        "login_bug": {"title": LOGIN_TITLE, "replies": LOGIN_REPLIES},
        "invoice_bug": {"title": INVOICE_TITLE, "replies": INVOICE_REPLIES},
        "one_reply": {"replies": REPLIES[:1]},
    }

    async def seed(self, world: World, ns: str) -> Expected:
        await world.github.ensure_sandbox()
        channel_id = await world.slack.channel_id()
        title, replies = self.params["title"], list(self.params["replies"])
        parent = await world.slack.post(f"[{ns}] Bug report: {title}")
        for reply in replies:
            await world.slack.post(reply, thread_ts=parent["ts"])
        return {
            "tag": f"[{ns}]",
            "channel": world.slack.channel_name,
            "channel_id": channel_id,
            "thread_ts": parent["ts"],
            "title": title,
            "replies": replies,
            "repo": world.github.full_name,
            "issue_title": f"[{ns}] {title}",
            "owned": {"slack.channel": [channel_id, world.slack.channel_name]},
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"In the Slack channel #{expected['channel']} there is a thread whose first message starts with "
            f"\"{expected['tag']} Bug report:\". Open an issue in the GitHub repository {expected['repo']} titled "
            f"\"{expected['issue_title']}\" whose body contains the full text of every message in that thread. "
            f"Then reply in the same Slack thread with the URL of the issue you opened."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        issues = await world.github.issues_search_in_sandbox(expected["issue_title"], state="open", expect=1)
        replies = await world.slack.replies(expected["thread_ts"])
        return {
            "issues": [{"number": i["number"], "title": i["title"], "body": i.get("body") or "", "url": i["html_url"]} for i in issues],
            "thread": [m.get("text", "") for m in replies if m.get("ts") != expected["thread_ts"]],
        }

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        issues = observed["issues"]
        if len(issues) != 1:
            return Verdict.fail(f"expected exactly one open issue titled {expected['issue_title']!r}, found {len(issues)}")
        issue = issues[0]
        body = " ".join(issue["body"].split()).casefold()
        conditions = [
            (" ".join(r.split()).casefold()[:60] in body, f"reply {r[:40]!r}... is missing from the issue body") for r in expected["replies"]
        ]
        thread = " ".join(observed["thread"])
        conditions.append((issue["url"] in thread, "no reply in the thread carries the issue URL"))
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "tag": "[hx]",
            "channel": "harness",
            "channel_id": "C1",
            "thread_ts": "1.0",
            "title": TITLE,
            "replies": REPLIES,
            "repo": "o/harness-sandbox",
            "issue_title": f"[hx] {TITLE}",
        }
        url = "https://github.com/o/harness-sandbox/issues/9"
        observed = {
            "issues": [{"number": 9, "title": f"[hx] {TITLE}", "body": "From Slack:\n\n" + "\n\n".join(REPLIES), "url": url}],
            "thread": REPLIES + [f"Filed as {url}"],
        }
        return expected, observed

    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]:
        issue = observed["issues"][0]
        return [
            ("the thread was not replied to with the URL", {**observed, "thread": list(REPLIES)}),
            ("a reply is missing from the issue body", {**observed, "issues": [dict(issue, body="\n\n".join(REPLIES[:2]))]}),
            ("the reply links a different issue", {**observed, "thread": REPLIES + ["Filed as https://github.com/o/harness-sandbox/issues/8"]}),
            ("no issue was opened", {**observed, "issues": []}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for issue in await world.github.issues_search_in_sandbox(expected["issue_title"], state="open"):
            await world.github.issue_close(issue["number"])
        await world.slack.delete_thread(expected["thread_ts"])


register(SlackThreadToGitHub())
