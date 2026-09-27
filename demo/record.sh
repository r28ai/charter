#!/usr/bin/env bash
# Render the Charter demo. Usage: ./demo/record.sh [stem]
# Phase 1 runs the beats for real under the project venv; phase 2 renders
# frames under demo/.venv and encodes with ffmpeg. No brew, no vhs.
set -euo pipefail
cd "$(dirname "$0")/.."

STEM="${1:-charter-demo}"
command -v ffmpeg >/dev/null || { echo "ffmpeg not found"; exit 1; }

[[ -d demo/.venv ]] || { python3 -m venv demo/.venv && demo/.venv/bin/pip install -q pillow; }

echo "==> phase 1: executing beats (real output, no mocks)"
.venv/bin/python demo/capture.py

echo "==> phase 2: rendering"
demo/.venv/bin/python demo/render.py "$STEM"

echo
echo "Reference it from the README with an absolute URL so PyPI renders it too:"
echo "  https://raw.githubusercontent.com/r28ai/charter/main/docs/images/$STEM.gif"
