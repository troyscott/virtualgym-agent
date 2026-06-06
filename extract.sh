#!/usr/bin/env bash
#
# Thin wrapper so the phone (Cowork Dispatch) and launchd can run the
# extraction with a single, environment-independent command:
#
#     ./extract.sh            # most recent workout (default)
#     ./extract.sh today
#     ./extract.sh 2026-06-05
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# launchd runs jobs with a minimal PATH; agent-browser lives in Homebrew's bin.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

# Python from the micromamba `workout` env. Override with WORKOUT_PYTHON if this
# path changes (e.g. after a micromamba upgrade recreates the env).
PYTHON="${WORKOUT_PYTHON:-/opt/homebrew/Cellar/micromamba/2.5.0_4/envs/workout/bin/python}"

if [ ! -x "$PYTHON" ]; then
    echo "Python interpreter not found: $PYTHON" >&2
    echo "Set WORKOUT_PYTHON to the 'workout' env python and retry." >&2
    exit 1
fi

exec "$PYTHON" extract_workout.py "${1:-last}"
