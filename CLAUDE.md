# virtualgym-agent

## Overview

Automated workout extraction from VirtuaGym Activity Calendar using Vercel's `agent-browser` CLI. Generates structured JSON, text reports, and Instagram-ready images (1080x1350).

## Project Structure

```
workouts/
├── requirements.txt          # Python dependencies (pip)
├── extract_workout.py        # Main extraction script (run this)
├── browser_session.py        # Persistent Chrome profile + CDP connect/login
├── generate_ig_workout.py    # Pillow-based IG image generator
├── fonts/                    # Poppins font files
├── data/                     # JSON + text reports
│   ├── workout_YYYY-MM-DD.json
│   └── workout_YYYY-MM-DD_report.txt
├── images/                   # Generated Instagram images
│   └── workout_YYYY-MM-DD_ig.png
└── prompts/                  # Archived Cowork/Chrome MCP prompts
```

## Python Environment

Uses micromamba with the `workout` env at `~/.local/share/mamba/envs/workout`.

```bash
micromamba create -n workout python=3.12 -c conda-forge -y
micromamba activate workout
pip install -r requirements.txt
```

## Quick Start

```bash
micromamba activate workout

# Extract today's workout (default)
python3 extract_workout.py

# Extract the most recent workout on the calendar
python3 extract_workout.py last

# Extract a specific date
python3 extract_workout.py 2026-03-21

# Other formats: today, yesterday, "Mar 21", "3/21"
```

## Authentication

Login URL: `https://thriveandconquer.virtuagym.com/signin`
Calendar URL: `https://thriveandconquer.virtuagym.com/user/troys2005/exercise`
User: `troys2005` (signs in via "Sign in with Google")

Auth is handled by `browser_session.py`, which drives a **dedicated, persistent Chrome profile**
(`~/.virtuagym-chrome`) over CDP. The live profile keeps its Google SSO refreshed, so manual login is
rare. Chrome 136+ forbids a debug port on the default profile, hence the separate `--user-data-dir`.

```bash
# One-time headed Google sign-in (also auto-triggered when a session dies)
python3 browser_session.py --login

# Automated runs: extract_workout.py calls ensure_connected(), which launches the
# profile headless, connects via `agent-browser connect 9222`, and verifies login.
```

Config lives in `config.json` (committed, no secrets); resolution is env var > `config.json` >
default. Keys: `CHROME_BIN`, `CHROME_PROFILE_DIR` (default `~/.virtuagym-chrome`), `CDP_PORT`
(default `9222`), plus the VirtuaGym URLs / Google account.

## Running from iPhone (Cowork Dispatch)

Dispatch sessions run on this Mac mini, but their shell is a **sandboxed Linux VM**: no
`launchctl`, no macOS binaries, and the network allowlist blocks `localhost:9222`. What the
sandbox DOES have is a **read/write mount of this repo**. The bridge is launchd's `WatchPaths`:
the job watches `.dispatch-trigger`, so any write to that file — including one made through the
Cowork mount — fires the extraction natively on the Mac.

```
phone → Dispatch (sandbox) → write .dispatch-trigger → launchd (Mac) → extract.sh → tail logs/ via mount
```

`extract.sh` is the single entry point for terminal and launchd use:

```bash
./extract.sh                  # most recent workout (default)
./extract.sh today
./extract.sh 2026-06-05
./extract.sh --from-trigger   # launchd entry point: reads the date arg from .dispatch-trigger
```

`scripts/launchd.sh` subcommands, by where they can run:

```bash
# Sandbox-safe (pure file I/O — works from Cowork Dispatch)
scripts/launchd.sh trigger [last|today|YYYY-MM-DD]   # write .dispatch-trigger -> launchd fires
scripts/launchd.sh logs [N]                          # tail logs/extract.{out,err}.log

# Mac terminal only (need launchctl)
scripts/launchd.sh install     # register the job (one-time; re-run after plist changes)
scripts/launchd.sh run-now     # launchctl kickstart
scripts/launchd.sh status      # load state / last exit code / pid
scripts/launchd.sh uninstall
```

`extract.sh` never writes `.dispatch-trigger` (that would re-fire WatchPaths and loop); it reads
it only when invoked with `--from-trigger`, so manual runs are unaffected by stale trigger content.

**Status dashboard (live artifact):** `scripts/status.py` emits JSON for every `com.troyscott.*`
launchd job (load state, last exit code, last run, log tail) plus the latest workout summary.
`scripts/dashboard.sh` injects that JSON into `scripts/dashboard.html` and writes a self-contained
`logs/dashboard.html` — open it, send it to the phone, or surface it as a Cowork live artifact.
`extract.sh` re-renders the dashboard at the end of every run, so Dispatch just reads the file
(`dashboard.sh`/`status.py` themselves need `launchctl`, so they only run on the Mac).

**Image delivery:** on success `extract.sh` copies the IG image to **`outputs/`** (git-tracked folder,
visible in the Dispatch repo mount → agent attaches `outputs/latest_ig.png` to the Outputs panel)
**and** to `~/Dropbox/virtuagym/` (override `VIRTUAGYM_DROPBOX_DIR`). Dropbox is the guaranteed channel
(view via the Dropbox app/connector), independent of Dispatch's file-sharing. `outputs/` is tracked via
`.gitkeep`; its images are gitignored.

**Trigger de-dup:** one `.dispatch-trigger` write emits several FSEvents; `extract.sh --from-trigger`
fingerprints the trigger (mtime + content via `.dispatch-trigger.processed`) and skips duplicate fires,
plus a `.extract.lock` mkdir lock prevents overlapping runs. One write → exactly one extraction.

**Phone recipe:** dispatch something like *"In virtualgym-agent, run `scripts/launchd.sh trigger`,
then `scripts/launchd.sh logs` until it prints Done!, then **attach the file** `outputs/latest_ig.png`
so it appears in Outputs (share the actual file, not just a description)."* The explicit "attach the
file" matters — Dispatch only surfaces files the agent actively shares; narrating "here's your image"
leaves Outputs empty. Fallback: pull the image from the Dropbox `virtuagym/` folder.

Requirements: the Mac mini stays awake/networked and Claude Desktop is running and signed in. If the
Google session ever dies, the headless run can't solve the login unattended — re-run
`python browser_session.py --login` once at the machine.

## Extraction Workflow

The `extract_workout.py` script automates the full pipeline:

1. **Connect to the persistent profile** (`ensure_connected()`) and navigate to Activity Calendar
2. **Click target date** on the calendar (JS-based, handles month navigation)
3. **Read sidebar** for workout title and exercise list
4. **Click each exercise** to read detail panel (mode, reps/time, weight, calories)
5. **Classify exercises** by position (1-5 warmup, 6-7 strength, 8+ conditioning)
6. **Calculate volume** (reps x weight; time-based uses seconds as reps)
7. **Generate outputs**: JSON to `data/`, report to `data/`, IG image to `images/`

## Exercise Classification

| Position | Type | Category | Indicators |
|----------|------|----------|------------|
| 1-5 | `warmup` | `activation` | Single set, bodyweight or light weight |
| 6-7 | `strength` | `compound_lift` or `isolation` | Multi-set with progressive weight |
| 8+ | `conditioning` | `amrap_circuit` | Time-based (40s), high-rep, or intervals |

## Volume Calculation

**CRITICAL**: VirtuaGym treats seconds as reps for time-based exercises.

```
Rep-based with weight:   volume = sum(reps × weight_lbs) per set
Time-based with weight:  volume = sum(seconds × weight_lbs) per set
No weight:               volume = 0
```

## JSON Schema

```json
{
  "workout_date": "YYYY-MM-DD",
  "day_of_week": "DayName",
  "workout_title": "Troy Scott AV – X – Name",
  "total_exercises": 12,
  "extraction_timestamp": "ISO-8601",
  "source": "thriveandconquer.virtuagym.com",
  "activity": { "name": "Steps", "value": 12944, "unit": "steps", "duration": "HH:MM:SS", "calories": 614 },
  "additional_activities": [{ "name": "Activity", "duration": "HH:MM:SS", "calories": 205 }],
  "exercises": [{
    "order": 1, "name": "Exercise Name", "type": "warmup", "category": "activation",
    "exercise_mode": "repetition-based",
    "sets": [{ "set_number": 1, "reps": 10, "duration": null, "weight_lbs": null, "rest": null }],
    "total_calories": 7
  }],
  "summary": {
    "total_workout_calories": 278, "total_with_steps": 892,
    "warmup_count": 5, "strength_count": 2, "conditioning_count": 5,
    "total_volume_lbs": 10155, "volume_breakdown": { "Exercise": 3660 }
  }
}
```

- Time-based sets: `"reps": null, "duration": "40s"`
- Rep-based sets: `"reps": 10, "duration": null`

## Workout Rotation

Two alternating programs, typically 2-3x/week:

**AV-1 Squat/Pull**: Dead bug, Scapular pull up, Side pivot, Horizontal row exorotation, Sumo squat stretch > Squat (Barbell), Hammer curl (DBs) > Step up high (DBs), Bent-over row (DBs), Crunch crossed toe touch, Rowing machine, Wall ball (MB)

**AV-2 Press/Hinge**: Neck pull (EB), Hand walk plyo pushup, Pallof press R/L (Pulley), Goodmorning > Bench press wide grip (Barbell), Deadlift stiffed legs (DBs) > Push-up incline (PB), Swing (KB), Sit-up overhead throw (Wall MB), Assault bike, Push press alternated (LM)

## Troubleshooting

- **Auth expired**: Runs auto-open a headed window; or run `python3 browser_session.py --login`
- **CAPTCHA on login**: Use "Sign in with Google" in the headed window — Google SSO skips the CAPTCHA
- **CDP won't connect**: Ensure no stale Chrome holds port 9222; the default profile can't be used (Chrome 136+)
- **Exercise detail not loading**: Script waits 1.5s after each click; increase if needed
- **Sidebar not scrolling**: Script uses `scrollintoview` before clicking each exercise
- **Volume mismatch**: Verify time-based exercises use seconds x weight
