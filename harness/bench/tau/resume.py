"""Run ``run.py`` until it finishes, waiting out the model provider's limits.

    python resume.py -- --model claude-sonnet --domain airline,retail --split base \\
        --tasks 0 --arms stock,charter_rules --trials 4 --workers 4 --out <run>

``run.py`` exits with code 3 when the provider refuses the account (a Claude
subscription limit, or Fireworks out of credit), having written every episode that
finished and none that was cut off. This reruns it, which resumes from its records,
once the provider answers again: it waits until the reset time the provider gave,
if it gave one, and otherwise asks every 15 minutes with the smallest request there
is, through the same endpoint the run uses. A refusal that is not the Claude
subscription's (Fireworks, which plays the customer, out of credit or suspended),
the spending cap (code 4) and any other exit are for a person to read, and stop
the loop.

Every stop and resume is logged with its time to ``resume.log`` beside the run's
records.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent.parent / "results" / "bench" / "tau"
PROBE = {
    "model": "sonnet",
    "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
}
_RESET = re.compile(
    r"resets\s+(?:(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2}),?\s+(?:at\s+)?)?"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)",
    re.I,
)


def reset_time(message: str, now: datetime) -> datetime | None:
    """When the provider says the limit lifts, in local time, if it says so.

    The CLI wrote "You've hit your session limit · resets 5:40am" on 2026-10-25.
    """
    match = _RESET.search(message)
    if not match:
        return None
    hour = int(match["hour"]) % 12 + (12 if match["ampm"].lower() == "pm" else 0)
    minute = int(match["minute"] or 0)
    if match["month"]:
        try:
            day = datetime.strptime(f"{match['month']} {match['day']} {now.year}", "%b %d %Y")
        except ValueError:
            return None
        at = day.replace(hour=hour, minute=minute)
        return at if at >= now - timedelta(days=1) else at.replace(year=now.year + 1)
    at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return at if at > now else at + timedelta(days=1)


def probe(base_url: str) -> tuple[bool, str]:
    """``(answered, detail)`` for one tiny request through the provider."""
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(PROBE).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status == 200, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read()[:300].decode(errors='replace')}"
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return False, f"no answer: {exc}"


class Log:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    def __call__(self, event: str) -> None:
        line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {event}"
        print(f"[resume] {line}", flush=True)
        with self.path.open("a") as f:
            f.write(line + "\n")


def run_once(command: list[str]) -> tuple[int, str]:
    """Run it with its output passed through; ``(exit code, what the provider said)``."""
    said = ""
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            if line.startswith("provider said: "):
                said = line[len("provider said: ") :].strip()
    return process.returncode, said


def wait_for_provider(said: str, base_url: str, every: float, log: Log) -> None:
    lifts = reset_time(said, datetime.now())
    when = f"at {lifts.isoformat(timespec='minutes')}" if lifts else "not given"
    log(f"waiting: provider reset {when}")
    while True:
        now = datetime.now()
        pause = every
        if lifts is not None and lifts > now:
            pause = min(every, (lifts - now).total_seconds() + 60)
        time.sleep(max(pause, 1))
        answered, detail = probe(base_url)
        if answered:
            log(f"provider answers again ({detail})")
            return
        log(f"still refused: {detail[:200]}")


def main() -> None:
    ap = argparse.ArgumentParser(usage="resume.py [options] -- <run.py arguments>")
    ap.add_argument("--provider", default="http://127.0.0.1:8799/v1", help="what to probe")
    ap.add_argument("--probe-every", type=float, default=900, help="seconds between probes")
    ap.add_argument("run_args", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    run_args = args.run_args[1:] if args.run_args[:1] == ["--"] else args.run_args
    out = run_args[run_args.index("--out") + 1] if "--out" in run_args else ""
    log = Log((OUT_DIR / out if out else OUT_DIR) / "resume.log")
    command = [sys.executable, str(HERE / "run.py"), *run_args]

    attempt = 0
    while True:
        attempt += 1
        log(f"start {attempt}: run.py {' '.join(run_args)}")
        code, said = run_once(command)
        if code == 0:
            log("finished: every episode is recorded")
            return
        if code != 3:
            log(f"run.py exited with {code}; not a provider limit, so not retried")
            raise SystemExit(code)
        log(f"stopped by the provider: {said[:300]}")
        if "claude subscription limit" not in said.lower():
            log("not the Claude subscription's limit (Fireworks?); a person has to fix the account")
            raise SystemExit(code)
        wait_for_provider(said, args.provider, args.probe_every, log)


if __name__ == "__main__":
    main()
