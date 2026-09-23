#!/usr/bin/env bash
# Run a campaign in small batches so progress survives a stall.
#
# `run_campaign.sh` supervised one enormous task - all 110 scenarios per arm.
# Inspect persists samples when a *task* completes, so killing a stalled run
# threw away everything since the last completion, and a short stall timer meant
# no task ever reached one: nine kills, zero net progress.
#
# Batching inverts that. Each batch is its own campaign over a handful of
# scenarios, finishing in a few minutes and writing its own .eval. A stall now
# costs one batch, and a completed batch is done permanently - so the run is
# restartable without a watchdog being load-bearing.
#
#   scripts/run_batched.sh --name stage2 --size 8 \
#     --arms progressive,raw --models lightning
#
# Re-running skips batches that already finished. Env: SIZE, STALL_SECONDS
# (default 420), MAX_RETRIES (per batch, default 2), POLL (default 20).

set -uo pipefail

SIZE="${SIZE:-8}"
STALL_SECONDS="${STALL_SECONDS:-420}"
MAX_RETRIES="${MAX_RETRIES:-2}"
POLL="${POLL:-20}"
BUFFER="$HOME/Library/Application Support/inspect_ai/samplebuffer"

NAME=""
ONLY=""
PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --size) SIZE="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    *) PASS+=("$1"); shift ;;
  esac
done
if [ -z "$NAME" ]; then echo "run_batched.sh: --name is required" >&2; exit 2; fi

# --only takes an explicit comma-separated list; otherwise batch the whole suite.
SCENARIOS=()
if [ -n "$ONLY" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && SCENARIOS+=("$line")
  done < <(echo "$ONLY" | tr ',' '\n')
else
  while IFS= read -r line; do
    [ -n "$line" ] && SCENARIOS+=("$line")
  done < <(.venv/bin/python -m charter_harness.campaign list --scenarios all --variants \
    | awk 'NF && $0 !~ /scenario\(s\);/ {print $1}')
fi
TOTAL=${#SCENARIOS[@]}
if [ "$TOTAL" -eq 0 ]; then echo "no scenarios resolved" >&2; exit 2; fi
BATCHES=$(( (TOTAL + SIZE - 1) / SIZE ))
echo "$TOTAL scenarios in $BATCHES batches of $SIZE"

# A batch is done when every arm has judged every sample it was given. Checking
# only that an .eval exists marks a batch killed mid-stall as complete - that is
# how a "14/14" run came back with 65 of 110 scenario pairs.
batch_done() {
  local dir="$1" arms="$2" expected="$3"
  .venv/bin/python scripts/_batch_complete.py "$dir" "$expected" ${arms//,/ } >/dev/null 2>&1
}

fingerprint() {
  echo "$(du -sk "$BUFFER" 2>/dev/null | awk '{print $1}'):$(du -sk "$1" 2>/dev/null | awk '{print $1}')"
}

ARMS="progressive,raw"
EPOCHS=1
for i in $(seq 0 $(( ${#PASS[@]} - 1 ))); do
  [ "${PASS[$i]}" = "--arms" ] && ARMS="${PASS[$((i+1))]}"
  [ "${PASS[$i]}" = "--epochs" ] && EPOCHS="${PASS[$((i+1))]}"
done

ok=0; failed=()
for b in $(seq 1 "$BATCHES"); do
  start=$(( (b - 1) * SIZE ))
  slice=("${SCENARIOS[@]:$start:$SIZE}")
  list=$(IFS=,; echo "${slice[*]}")
  dir="results/${NAME}-b$(printf '%02d' "$b")"

  want=$(( ${#slice[@]} * EPOCHS ))
  if batch_done "$dir" "$ARMS" "$want"; then
    echo "[$b/$BATCHES] already done — skipping"
    ok=$((ok + 1)); continue
  fi

  done_this=0
  for try in $(seq 1 $((MAX_RETRIES + 1))); do
    echo "[$b/$BATCHES] try $try  $(date '+%H:%M:%S')  ${#slice[@]} scenarios"
    .venv/bin/python -u -m charter_harness.campaign run \
      --name "${NAME}-b$(printf '%02d' "$b")" --scenarios "$list" ${PASS[@]+"${PASS[@]}"} >/dev/null 2>&1 &
    pid=$!
    last=$(fingerprint "$dir"); stalled=0
    while kill -0 "$pid" 2>/dev/null; do
      sleep "$POLL"
      now=$(fingerprint "$dir")
      if [ "$now" = "$last" ]; then
        stalled=$((stalled + POLL))
        if [ "$stalled" -ge "$STALL_SECONDS" ]; then
          echo "[$b/$BATCHES] stalled ${stalled}s — killing"
          kill -9 "$pid" 2>/dev/null; pkill -9 -f "charter_harness.campaign run" 2>/dev/null
          sleep 4; break
        fi
      else
        stalled=0; last="$now"
      fi
    done
    wait "$pid" 2>/dev/null

    if batch_done "$dir" "$ARMS" "$want"; then
      echo "[$b/$BATCHES] done  $(date '+%H:%M:%S')"
      ok=$((ok + 1)); done_this=1; break
    fi
  done
  [ "$done_this" -eq 0 ] && { echo "[$b/$BATCHES] FAILED after $((MAX_RETRIES + 1)) tries"; failed+=("$b"); }
  echo "--- progress: $ok/$BATCHES batches"
done

echo
echo "complete: $ok/$BATCHES batches"
[ ${#failed[@]} -gt 0 ] && echo "failed batches: ${failed[*]}"

# One directory Inspect's report can read, since each batch wrote its own.
agg="results/${NAME}-all"; mkdir -p "$agg"
cp results/"${NAME}"-b*/*.eval "$agg"/ 2>/dev/null
echo "aggregated $(ls "$agg"/*.eval 2>/dev/null | wc -l | tr -d ' ') logs into $agg"
