#!/usr/bin/env bash
#
# Thin wrapper so the phone (Cowork Dispatch) and launchd can run the
# extraction with a single, environment-independent command:
#
#     ./extract.sh                  # most recent workout (default)
#     ./extract.sh today
#     ./extract.sh 2026-06-05
#     ./extract.sh --from-trigger   # launchd WatchPaths entry point: read the
#                                   # date arg from .dispatch-trigger
#
# On success it copies the generated IG image to a stable path
# (outputs/latest_ig.png) and to ~/Dropbox/virtuagym/ so it can be retrieved
# from the phone regardless of Dispatch's file-sharing.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
REPO="$SCRIPT_DIR"
TRIGGER="$REPO/.dispatch-trigger"
PROCESSED="$REPO/.dispatch-trigger.processed"
LOCK="$REPO/.extract.lock"

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

# Resolve the date argument. --from-trigger (the launchd WatchPaths job) reads
# it from .dispatch-trigger so the Cowork sandbox can pass a date by writing
# the file. READ-ONLY here: writing the trigger from this script would re-fire
# WatchPaths and loop.
FROM_TRIGGER=0
ARG="${1:-last}"
if [ "$ARG" = "--from-trigger" ]; then
    FROM_TRIGGER=1
    ARG="$(head -n1 "$TRIGGER" 2>/dev/null | xargs || true)"
    ARG="${ARG:-last}"
fi

# Single-run lock (atomic mkdir — macOS has no flock). Prevents overlapping runs
# from a near-simultaneous WatchPaths multi-fire or a manual run colliding with
# a triggered one on the same Chrome profile.
if mkdir "$LOCK" 2>/dev/null; then
    trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT
else
    [ "$FROM_TRIGGER" = 1 ] && exit 0   # another run in progress; this fire is redundant
    echo "Another extraction is already running (lock: $LOCK). Exiting." >&2
    exit 1
fi

# Dedup duplicate WatchPaths fires: a single write to .dispatch-trigger emits
# several FSEvents, so launchd may start the job more than once. Fingerprint the
# trigger (mtime + content); if it matches the last processed one, this is a
# duplicate fire — skip. A genuine re-trigger is a new write (new mtime), so it
# still runs. (Writing .dispatch-trigger.processed does NOT re-fire WatchPaths:
# the plist watches the exact .dispatch-trigger path, not the directory.)
if [ "$FROM_TRIGGER" = 1 ]; then
    fp="$(stat -f '%m' "$TRIGGER" 2>/dev/null || true)|$(head -n1 "$TRIGGER" 2>/dev/null || true)"
    if [ -f "$PROCESSED" ] && [ "$fp" = "$(cat "$PROCESSED" 2>/dev/null || true)" ]; then
        echo "Duplicate trigger fire (unchanged $TRIGGER); skipping."
        exit 0
    fi
    printf '%s\n' "$fp" > "$PROCESSED"
fi

rc=0
"$PYTHON" extract_workout.py "$ARG" || rc=$?

# Deliver the freshest IG image so the phone can always retrieve it (best-effort
# — never fail the run on a copy error). Two channels:
#   1. outputs/ — a git-tracked folder, so it's visible in the Dispatch repo
#      mount; the agent attaches outputs/latest_ig.png to the Outputs panel.
#   2. ~/Dropbox/virtuagym/ — guaranteed channel, viewable in the Dropbox app.
if [ "$rc" -eq 0 ]; then
    newest="$(ls -t images/workout_*_ig.png 2>/dev/null | head -1 || true)"
    if [ -n "$newest" ]; then
        mkdir -p outputs 2>/dev/null || true
        cp -f "$newest" "outputs/$(basename "$newest")" 2>/dev/null || true
        cp -f "$newest" outputs/latest_ig.png 2>/dev/null || true

        dropbox_dir="${VIRTUAGYM_DROPBOX_DIR:-$HOME/Dropbox/virtuagym}"
        if [ -d "$HOME/Dropbox" ]; then
            mkdir -p "$dropbox_dir" 2>/dev/null || true
            cp -f "$newest" "$dropbox_dir/" 2>/dev/null || true
            cp -f "$newest" "$dropbox_dir/latest_ig.png" 2>/dev/null || true
        fi
    fi
fi

# Refresh the status dashboard (best-effort) so Dispatch can read a current
# logs/dashboard.html without needing launchctl.
scripts/dashboard.sh >/dev/null 2>&1 || true

exit "$rc"
