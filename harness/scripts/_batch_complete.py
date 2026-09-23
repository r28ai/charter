"""Has a batch finished? Exit 0 when every arm has all its samples.

`run_batched.sh` used to ask whether an ``.eval`` file existed per arm. A batch
killed mid-stall still writes one, so partial batches were marked done and the
runner moved on - the GLM breadth run finished "14/14" with 65 of 110 scenario
pairs, and the gaps clustered in exactly the batches that stalled.

Counting distinct scored sample ids per arm is the honest check, but only over
the logs the report will actually read. This file used to union ids across every
log in the directory, including the "started" ones a killed try leaves behind,
while ``report.collect`` skipped those, so the two could in principle disagree
about whether a batch was done. No run is known to have hit that: the rule is
shared with :mod:`charter_harness.report` rather than restated here so that it
cannot start to.

    _batch_complete.py <dir> <expected-per-arm> <arm> [<arm> ...]
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

from charter_harness.report import reportable_logs


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("usage: _batch_complete.py <dir> <expected> <arm> [...]", file=sys.stderr)
        return 2
    directory, expected, arms = argv[1], int(argv[2]), argv[3:]
    if not Path(directory).is_dir():
        return 1

    seen: dict[str, set[str]] = collections.defaultdict(set)
    try:
        logs = reportable_logs(directory)
    except Exception:
        return 1
    for log in logs:
        name = str(log.eval.task)
        arm = next((a for a in arms if f"harness-{a}" in name), None)
        if arm is None:
            continue
        for sample in log.samples or []:
            # A sample with no score never reached the judge: it was cut short.
            if sample.scores:
                seen[arm].add(f"{sample.id}#{sample.epoch}")

    for arm in arms:
        if len(seen[arm]) < expected:
            print(f"{arm}: {len(seen[arm])}/{expected}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
