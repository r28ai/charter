"""Write ``graded_passes.md``: each call that broke a rule and ran, in a conversation
τ²-bench graded as a pass, with what was said before it, for reading by hand.

    python graded_passes.py --run sonnet5-2026-10-25 claude-sonnet

Retail only. The calls are found the way ``run.broken_rules`` finds them: the
authenticated user is the first id a lookup returned, and the confirmation is the
user's last message before the call. Rule 2 needs the database's order owners,
which the saved conversations do not carry; it was never broken on stock retail,
and a row that says otherwise is reported rather than skipped.

The tags under each call are mechanical, read off the words, to speed the reading.
The verdict is the reader's.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report import OUT_DIR, conversations, grade, load  # noqa: E402

# retail_api imports tau2, which only the bench's own venv has; the sets are copied.
LOOKUPS = {"find_user_id_by_email", "find_user_id_by_name_zip"}
OPEN = LOOKUPS | {"list_all_product_types", "calculate", "transfer_to_human_agents"}
WRITES = {
    "cancel_pending_order",
    "modify_pending_order_address",
    "modify_pending_order_items",
    "modify_pending_order_payment",
    "modify_user_address",
    "return_delivered_order_items",
    "exchange_delivered_order_items",
}
CONSENT = [
    "go ahead",
    "proceed",
    "please do",
    "do it",
    "sure",
    "sounds good",
    "that's right",
    "that's correct",
    "correct",
    "confirm",
    "okay",
    "ok",
    "perfect",
    "great",
]
CONTEXT = 4  # text messages shown before each call
# A call the agent wrote as text, which reached the customer instead of the tools.
AS_TEXT = re.compile(r'"name":\s*"\w+",\s*"arguments"')


def words(text: str) -> list[str]:
    return re.sub(r"[^\w\s']", " ", text.lower()).split()


def is_yes(text: str) -> bool:
    w = re.sub(r"[^\w\s]", " ", text.lower()).split()
    return bool(w) and w[0] == "yes"


def tags(said: str) -> list[str]:
    out = []
    w = words(said)
    if "yes" in w:
        out.append("a yes later in the message")
    low = " ".join(w)
    hits = [c for c in CONSENT if re.search(rf"\b{re.escape(c)}\b", low)]
    if hits:
        out.append("consent words: " + ", ".join(f'"{h}"' for h in hits))
    if "?" in said:
        out.append("the customer asked a question")
    if re.search(r"\bbefore (you|we|that|it)\b", low):
        out.append('"before you/we …"')
    if not out:
        out.append("no yes and no consent words")
    return out


def walk(messages: list[dict]) -> list[dict[str, Any]]:
    """Each executed call that breaks rule 1 or 3, with the text before it."""
    pending: dict[str, tuple[dict, str, str | None, int]] = {}
    user_id: str | None = None
    last_user = ""
    out = []
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            if m.get("content"):
                last_user = m["content"]
            continue
        for tc in m.get("tool_calls") or []:
            pending[tc["id"]] = (tc, last_user, user_id, i)
        if m.get("role") != "tool":
            continue
        if m["id"] not in pending or m.get("error") or m.get("execution_status") != "executed":
            continue
        tc, said, authed, at = pending.pop(m["id"])
        name = tc["name"]
        if name in LOOKUPS and user_id is None:
            user_id = m.get("content")
        broke = []
        if name not in OPEN and authed is None:
            broke.append(1)
        if name in WRITES and not is_yes(said):
            broke.append(3)
        if broke:
            before = [
                x
                for x in messages[:at]
                if x.get("role") in ("user", "assistant") and x.get("content")
            ][-CONTEXT:]
            as_text = any(
                x.get("role") == "assistant"
                and not x.get("tool_calls")
                and AS_TEXT.search(x.get("content") or "")
                for x in messages[:at]
            )
            out.append(
                {"call": tc, "rules": broke, "said": said, "before": before, "as_text": as_text}
            )
    return out


def quote(text: str) -> str:
    return "\n".join("> " + line if line else ">" for line in text.strip().splitlines())


def main() -> None:
    args = sys.argv[1:]
    run = ""
    if args[:1] == ["--run"]:
        run, args = args[1], args[2:]
    model = args[0] if args else "claude-sonnet"
    run_dir = OUT_DIR / run if run else OUT_DIR
    rows = [r for r in load(run_dir, model) if r["domain"] == "retail" and r["arm"] == "stock"]
    convs = conversations(run_dir, model)
    judged = any("full_reward" in r for r in rows)
    passes = sorted(
        (r for r in rows if r.get("broken") and grade(r, judged) == 1.0),
        key=lambda r: (r["trial"], int(r["task"])),
    )

    entries: list[tuple[dict, list[dict]]] = []
    mismatched = []
    for r in passes:
        found = walk(convs.get(("retail", "stock", r["task"], r["trial"])) or [])
        want = [(b["tool"], b["rules"]) for b in r["broken"]]
        got = [(f["call"]["name"], f["rules"]) for f in found]
        if want != got:
            mismatched.append((r, want, got))
        entries.append((r, found))

    scored = [r for r in rows if grade(r, judged) is not None]
    lines = [
        f"# Graded passes with a rule broken: {model}, retail, stock",
        "",
        f"Run `{run or '.'}`. Generated by `bench/tau/graded_passes.py`. "
        f"Pass is τ²-bench's {'DB check times its assertions' if judged else 'DB check'}.",
        "",
    ]
    for trial in sorted({r["trial"] for r in scored}):
        sc = [r for r in scored if r["trial"] == trial]
        with_one = [r for r in sc if r.get("broken")]
        passed = [r for r in with_one if grade(r, judged) == 1.0]
        calls = sum(len(r["broken"]) for r in passed)
        lines.append(
            f"- Trial {trial}: {len(sc)} conversations scored, {len(with_one)} with a call that "
            f"broke a rule and ran, {len(passed)} of those graded a pass ({calls} calls)."
        )
    lines += [
        "",
        "Rule 1: refused until a lookup has authenticated the customer. Rule 3: a write "
        "needs the customer's last message to be, or begin with, yes. Both are τ²-bench's "
        "own policy; RULES.md has the wording.",
        "",
        "For each call: the last few messages before it, the call, and tags read off the "
        "customer's last message. Mark one verdict per call.",
        "",
    ]
    if mismatched:
        lines += ["**Rows whose recorded calls differ from this walk:**", ""]
        for r, want, got in mismatched:
            lines.append(f"- task {r['task']} trial {r['trial']}: recorded {want}, walked {got}")
        lines.append("")

    for r, found in entries:
        lines += [f"## Task {r['task']}, trial {r['trial']}", ""]
        for n, f in enumerate(found, 1):
            tc = f["call"]
            rules = ", ".join(map(str, f["rules"]))
            lines += [f"### {n}. `{tc['name']}`, rule {rules}", ""]
            for m in f["before"]:
                who = "Customer" if m["role"] == "user" else "Agent"
                lines += [f"**{who}:**", "", quote(m["content"]), ""]
            lines += [
                "**Call:**",
                "",
                "```json",
                json.dumps({tc["name"]: tc.get("arguments") or {}}, indent=1, ensure_ascii=False),
                "```",
                "",
            ]
            if 3 in f["rules"]:
                lines.append("Tags: " + "; ".join(tags(f["said"])))
            if 1 in f["rules"]:
                lines.append("Tags: ran before any lookup authenticated the customer")
            if f["as_text"]:
                lines.append(
                    "Harness: earlier in this conversation a tool call reached the customer as "
                    "text instead of running"
                )
            lines += [
                "",
                "- [ ] a real break: the customer had not agreed (rule 3) / was not authenticated (rule 1)",
                "- [ ] agreed in other words, or earlier in the conversation",
                "- [ ] the rule misread it",
                "",
            ]

    out = run_dir / "graded_passes.md"
    out.write_text("\n".join(lines))
    print(f"{out}: {len(entries)} conversations, {sum(len(f) for _, f in entries)} calls")
    if mismatched:
        print(f"{len(mismatched)} rows differ from the walk; listed at the top")


if __name__ == "__main__":
    main()
