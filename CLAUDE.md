# virtualgym-agent

## Overview

Automated workout extraction from VirtuaGym Activity Calendar using Vercel's `agent-browser` CLI. Generates structured JSON, text reports, and Instagram-ready images (1080x1350).

> For the system design, data flow, and the rationale behind key decisions (persistent CDP profile, WatchPaths trigger, sandbox/mount constraints, delivery), see [ARCHITECTURE.md](ARCHITECTURE.md).

## Project Structure

```
virtualgym-agent/
├── ARCHITECTURE.md           # System design, data flow, decision rationale
├── extract.sh                # Single entry point (terminal + launchd); dedup, delivery
├── extract_workout.py        # Main extraction pipeline
├── browser_session.py        # Persistent Chrome profile + CDP connect/login
├── generate_ig_workout.py    # Pillow-based IG image generator
├── config.json               # Browser/VirtuaGym settings (committed, no secrets)
├── requirements.txt          # Python dependencies (pip)
├── scripts/
│   ├── launchd.sh            # LaunchAgent manager (install/run-now/trigger/status/logs)
│   ├── status.py             # JSON status for com.troyscott.* jobs + latest workout
│   └── dashboard.{html,sh}   # Live-artifact status dashboard -> logs/dashboard.html
├── fonts/                    # Poppins font files
├── data/                     # JSON + text reports (gitignored)
├── images/                   # Generated Instagram images (gitignored)
├── outputs/                  # Delivery folder for Dispatch (tracked dir, ignored contents)
└── logs/                     # launchd job logs + dashboard.html (gitignored)
```

## Python Environment

Uses micromamba with the `workout` env at `/opt/homebrew/Cellar/micromamba/2.5.0_4/envs/workout`
(Homebrew Cellar path — it moves on micromamba upgrades; `extract.sh` hardcodes it but honors a
`WORKOUT_PYTHON` env override pointing at the env's `python`).

```bash
micromamba create -n workout python=3.12 -c conda-forge -y
micromamba run -n workout pip install -r requirements.txt

# Run scripts via the env without activating:
micromamba run -n workout python extract_workout.py last
```

## Quick Start

```bash
# Simplest: the wrapper resolves the env python and PATH itself
./extract.sh                  # most recent workout (default)
./extract.sh today
./extract.sh 2026-03-21

# Or call the pipeline directly via the env
micromamba run -n workout python extract_workout.py        # today (default)
micromamba run -n workout python extract_workout.py last
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
  "workout_title": "Troy Scott AX - 1 - Squat/Pull",
  "total_exercises": 14,
  "extraction_timestamp": "ISO-8601",
  "source": "thriveandconquer.virtuagym.com",
  "activity": null,
  "additional_activities": [],
  "exercises": [{
    "order": 1, "name": "Exercise Name", "type": "warmup", "category": "activation",
    "exercise_mode": "repetition-based",
    "sets": [{ "set_number": 1, "reps": 10, "duration": null, "weight_lbs": null, "rest": null }],
    "total_calories": 7
  }],
  "summary": {
    "total_workout_calories": 222, "total_with_steps": 222,
    "steps_calories": 0, "additional_activity_calories": 0,
    "warmup_count": 5, "strength_count": 2, "conditioning_count": 7,
    "total_volume_lbs": 4258, "volume_breakdown": { "Exercise": 3060 },
    "volume_note": "Time-based exercises use seconds as reps per VirtuaGym"
  }
}
```

- Time-based sets: `"reps": null, "duration": "40s"`
- Rep-based sets: `"reps": 10, "duration": null`
- `activity` is currently always `null` — "Steps" comes through as exercise 1 (with no sets); the
  reserved `activity`/`additional_activities` fields are kept for future use
- VirtuaGym session activity rows (names starting `"Fitness,"`) are dropped during extraction —
  they have no detail panel and would duplicate the previous exercise's sets (see #23)

## Workout Rotation

Two alternating programs, typically 2-3x/week:

**AX-1 Squat/Pull**: Dead bug, Scapular pull up (Rig), Side pivot (MRB), Horizontal row exorotation (EBs), Sumo squat stretch rotation > Squat (Barbell) > Plank jacks (Flowin), Assisted standing pull up wide grip, Split front squat L/R (Barbell), Squat to hammer curl (DBs), Wide back row (ST), Slam ball (MB)

**AX-2 Press/Hinge**: Neck pull (EB), Hand walk plyo pushup, Pallof press R/L (Pulley) > Goodmorning, Bench press wide grip (Barbell) > Knee raise side (Captains chair), Assisted dipping machine, Stiff legged deadlift (Barbell), Side raise seated (DBs), Hang clean press L/R (KB), Forward push (Sled)

(Earlier AV-1/AV-2 programs are retired; "Steps" appears as entry 1 on every workout as the day's
step-count activity.)

## Troubleshooting

- **Auth expired**: Runs auto-open a headed window; or run `python3 browser_session.py --login`
- **CAPTCHA on login**: Use "Sign in with Google" in the headed window — Google SSO skips the CAPTCHA
- **CDP won't connect**: Ensure no stale Chrome holds port 9222; the default profile can't be used (Chrome 136+)
- **Exercise detail not loading**: Script waits 1.5s after each click; increase if needed
- **Sidebar not scrolling**: Script uses `scrollintoview` before clicking each exercise
- **Volume mismatch**: Verify time-based exercises use seconds x weight
