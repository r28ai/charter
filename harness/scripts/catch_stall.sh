#!/usr/bin/env bash
# Dump the Python stack of a campaign the moment it stops making progress.
#
# The stall has been diagnosed all night from the outside - socket states, buffer
# mtimes - which produced a wrong theory (pool starvation) and a fix that did not
# work. A stack dump says which await is actually blocked, and in whose code:
# charter_harness (the harness) or charter (the SDK) or httpx/inspect below both.
#
# Writes /tmp/stall-<ts>.txt each time it catches one. Runs until killed.

set -uo pipefail
BUFFER="$HOME/Library/Application Support/inspect_ai/samplebuffer"
SPY="$HOME/.local/bin/py-spy"
QUIET="${QUIET:-120}"   # seconds of no buffer growth before we call it stalled
POLL=15

last=""; quiet=0
while true; do
  pid=$(pgrep -f "charter_harness.campaign run" | head -1)
  if [ -z "$pid" ]; then last=""; quiet=0; sleep "$POLL"; continue; fi
  now=$(du -sk "$BUFFER" 2>/dev/null | awk '{print $1}')
  if [ "$now" = "$last" ]; then
    quiet=$((quiet + POLL))
    if [ "$quiet" -ge "$QUIET" ]; then
      # SIGUSR1 rather than py-spy: py-spy needs root on macOS, faulthandler
      # does not. The campaign registers the handler at startup and appends to
      # /tmp/charter-stacks.txt.
      echo "[$(date '+%H:%M:%S')] no growth ${quiet}s — SIGUSR1 to pid $pid"
      echo "----- $(date '+%H:%M:%S') pid $pid stalled ${quiet}s" >> /tmp/charter-stacks.txt
      kill -USR1 "$pid" 2>/dev/null
      quiet=0
    fi
  else
    quiet=0; last="$now"
  fi
  sleep "$POLL"
done
