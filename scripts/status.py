#!/usr/bin/env python3
"""
Emit JSON status for launchd job(s) so a live artifact (or any UI) can render it.

Usage:
    scripts/status.py [LABEL ...]

With no args, reports every ``com.troyscott.*`` LaunchAgent found in
~/Library/LaunchAgents. Output is JSON on stdout — pair it with dashboard.sh to
render the HTML dashboard, or consume it directly from Cowork Dispatch.
"""

import os
import re
import sys
import glob
import json
import plistlib
import subprocess
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCH_AGENTS = os.path.expanduser("~/Library/LaunchAgents")
DOMAIN = f"gui/{os.getuid()}"


def _launchctl_print(label):
    """Return raw `launchctl print` output for a label, or None if not loaded."""
    try:
        out = subprocess.run(
            ["launchctl", "print", f"{DOMAIN}/{label}"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return out.stdout if out.returncode == 0 else None


def _first(pattern, text, cast=str):
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return cast(m.group(1))
    except (ValueError, TypeError):
        return m.group(1)


def _log_info(path):
    """Modification time (ISO) and last few lines of a log file."""
    if not path or not os.path.exists(path):
        return None, None
    mtime = datetime.fromtimestamp(
        os.path.getmtime(path), tz=timezone.utc
    ).isoformat()
    try:
        with open(path, errors="replace") as f:
            tail = "".join(f.readlines()[-10:]).strip()
    except OSError:
        tail = None
    return mtime, tail


def job_status(label):
    plist_path = os.path.join(LAUNCH_AGENTS, f"{label}.plist")
    stdout_path = stderr_path = None
    if os.path.exists(plist_path):
        try:
            with open(plist_path, "rb") as f:
                pl = plistlib.load(f)
            stdout_path = pl.get("StandardOutPath")
            stderr_path = pl.get("StandardErrorPath")
        except (OSError, plistlib.InvalidFileException):
            pass

    info = _launchctl_print(label)
    log_mtime, log_tail = _log_info(stdout_path)
    return {
        "label": label,
        "loaded": info is not None,
        "state": _first(r"\bstate = (\S+.*)", info) if info else None,
        "pid": _first(r"\bpid = (\d+)", info, int) if info else None,
        "last_exit_code": _first(r"last exit code = (-?\d+)", info, int) if info else None,
        "plist_path": plist_path if os.path.exists(plist_path) else None,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "last_run": log_mtime,
        "log_tail": log_tail,
    }


def latest_workout():
    """Newest workout JSON in data/, summarised for the dashboard."""
    files = sorted(glob.glob(os.path.join(REPO, "data", "workout_*.json")))
    if not files:
        return None
    path = files[-1]
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    date = d.get("workout_date")
    image = os.path.join(REPO, "images", f"workout_{date}_ig.png") if date else None
    summary = d.get("summary", {})
    return {
        "date": date,
        "day_of_week": d.get("day_of_week"),
        "title": d.get("workout_title"),
        "total_exercises": d.get("total_exercises"),
        "total_calories": summary.get("total_workout_calories"),
        "total_volume_lbs": summary.get("total_volume_lbs"),
        "json_path": path,
        "image_path": image if image and os.path.exists(image) else None,
    }


def discover_labels():
    labels = []
    for path in sorted(glob.glob(os.path.join(LAUNCH_AGENTS, "com.troyscott.*.plist"))):
        labels.append(os.path.basename(path)[: -len(".plist")])
    return labels


def main():
    labels = sys.argv[1:] or discover_labels()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": os.uname().nodename,
        "jobs": [job_status(label) for label in labels],
        "latest_workout": latest_workout(),
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
