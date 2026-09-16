#!/usr/bin/env bash
# Run stage 2 and stage 3 end to end, on the post-$ref-fix build.
#
# This is the rerun of the two campaigns behind docs/guarantees/measured-results.mdx.
# Those ran at eddbd6cb, before ae1939c8 handed Inspect the SDK's own schema, so
# the Charter arm was carrying flattened $ref/$defs and every token figure in them
# is void. Pre-fix and post-fix rows are not the same experiment, which drives two
# things below: the old results are moved aside rather than merged into, and the
# campaign names are new. run_batched.sh skips any batch whose directory already
# looks complete, so reusing `glm2-breadth` / `stage3-depth` would skip all of
# them and re-report the void run.
#
# firecrawl_to_linear stays in. An earlier night quarantined it after its batch
# stalled on all four attempts, and this header still said so while TEMPLATES
# listed all sixteen; the header was the stale half. It went 7/7 on the Charter
# arm last run, and dropping it now would make the rerun non-comparable with the
# record it replaces. Its seeds are the flaky part, not its agent turns - three of
# the four harness errors last run were GitHub 409s writing RUNBOOK.md into the
# sandbox repo - so expect a retried batch rather than a clean sweep.
#
# Concurrency is 8 rather than the harness default of 2. That default is marked
# "quota-bound" and predates the account's limits doubling; the dashboard shows
# 14-28% ceiling utilisation, so this is the cheapest speedup available.
#
# STALL_SECONDS is 900, not the 300/420 it was. At concurrency 8 a batch seeds
# sixteen fixtures at once (8 samples x 2 arms), and the Google-heavy batch -
# six calendar_to_doc variants plus two doc_to_gmail_draft - draws the burst
# quota that world/_http.py retries: `min(2**attempt, 20)` plus jitter over four
# retries against a 30s timeout, which is minutes of silence per throttled call
# and nothing written to the sample buffer while it waits. The watchdog reads
# that silence as a stall. It killed that one batch five times across three runs
# on 2026-09-15/16, each kill costing five minutes and leaving the fixtures of a
# killed teardown behind - a share of the 441 orphans cleaned that night. The
# batch is not hung: a stack dump during a "stall" showed 0.3% CPU, seven
# ESTABLISHED sockets to Google and the loop parked in select, and the batch
# completed on its own on try 3 both times it was allowed one. The watchdog is
# still worth having for a true hang; it just has to be slower than a throttled
# seed phase, and MAX_RETRIES still bounds the damage if something really does
# wedge.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

FAST=(--max-samples 8 --max-connections 16)

# All sixteen templates.
TEMPLATES="calendar_cleanup,calendar_to_doc,doc_to_gmail_draft,firecrawl_to_linear,github_to_linear,gmail_label_sweep,inbox_to_sheet,linear_to_slack_digest,linear_triage,pr_to_doc,sheet_to_calendar,sheet_to_stripe_refunds,shopify_customer_to_stripe,shopify_low_stock_to_github,slack_thread_to_github,stripe_to_sheet"

# Archive the pre-fix record before anything writes. Keep it - a void run is
# still evidence of what the bug cost - but never let a post-fix .eval land in a
# directory holding pre-fix ones, because `report` would average across both.
mkdir -p results/_prefix-archive
for d in FINAL-breadth FINAL-depth; do
  [ -d "results/$d" ] || continue
  dest="results/_prefix-archive/$d"
  [ -e "$dest" ] && dest="$dest-$(date '+%Y%m%dT%H%M%S')"
  mv "results/$d" "$dest" || { echo "could not archive results/$d" >&2; exit 1; }
  echo "archived results/$d -> $dest"
done
for d in FINAL-breadth FINAL-depth; do
  [ -e "results/$d" ] && { echo "results/$d still present after archiving; refusing to mix runs" >&2; exit 1; }
done

echo "=== stage 2: full breadth, 110 instances, concurrency 8  $(date '+%H:%M:%S')"
SIZE=8 STALL_SECONDS=900 POLL=20 MAX_RETRIES=3 scripts/run_batched.sh \
  --name postfix-breadth --arms progressive,raw --models glm --epochs 1 \
  "${FAST[@]}" --no-report

echo "=== stage 3: 16 templates x 10 epochs  $(date '+%H:%M:%S')"
SIZE=2 STALL_SECONDS=900 POLL=20 MAX_RETRIES=3 scripts/run_batched.sh \
  --name postfix-depth --only "$TEMPLATES" --arms progressive,raw --models glm \
  --epochs 10 "${FAST[@]}" --no-report

# One directory per phase for the report; batches wrote their own.
mkdir -p results/FINAL-breadth results/FINAL-depth
cp results/postfix-breadth-b*/[0-9]*.eval results/FINAL-breadth/ 2>/dev/null
cp results/postfix-depth-b*/[0-9]*.eval    results/FINAL-depth/   2>/dev/null
.venv/bin/python -m charter_harness.campaign report results/FINAL-breadth 2>/dev/null
.venv/bin/python -m charter_harness.campaign report results/FINAL-depth   2>/dev/null
echo "=== all done  $(date '+%H:%M:%S')"
