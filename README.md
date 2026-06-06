# virtualgym-agent

![Version](https://img.shields.io/badge/version-0.2-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/github/license/troyscott/virtualgym-agent)
![Issues](https://img.shields.io/github/issues/troyscott/virtualgym-agent)
![PRs](https://img.shields.io/github/issues-pr/troyscott/virtualgym-agent)

Automated workout data extraction from [VirtuaGym](https://virtuagym.com) using Vercel's [agent-browser](https://github.com/vercel-labs/agent-browser). Extracts exercises, sets, reps, and weights — then generates structured JSON, text reports, and Instagram-ready images (1080x1350).

Works standalone via CLI, or integrated with Claude Channels, OpenClaw, and other AI agent frameworks.

## Prerequisites

- Python 3.x
- Node.js / npm
- [agent-browser](https://github.com/vercel-labs/agent-browser) (Vercel CLI)

## Setup

### 1. Python environment (micromamba)

Create and activate the `workout` environment:

```bash
micromamba create -n workout python=3.12 -c conda-forge -y
micromamba activate workout
pip install -r requirements.txt
```

The environment lives at `~/.local/share/mamba/envs/workout`. Activate it before running any scripts:

```bash
micromamba activate workout
```

### 2. Install agent-browser

```bash
npm install -g agent-browser
agent-browser install
```

### 3. Authenticate with VirtuaGym

Authentication uses a **dedicated, persistent Chrome profile** driven over CDP (Chrome DevTools
Protocol). You sign in once via "Sign in with Google"; the live profile keeps its Google SSO
refreshed, so re-login is rare. (This replaces the old `virtuagym-auth.json` cookie snapshot, which
expired roughly every 30 days.)

```bash
python3 browser_session.py --login
# A visible Chrome window opens — choose "Sign in with Google" as your VirtuaGym account
```

This creates a profile at `~/.virtuagym-chrome`. All future runs launch that profile **headless** and
connect automatically — no browser window, no manual step.

> **Why a separate profile?** Chrome 136+ refuses to enable remote debugging on your normal default
> profile, so automation requires its own `--user-data-dir`. The profile lives outside the repo and is
> never committed.

> **Note:** VirtuaGym does not offer a public API — web scraping via agent-browser is the only
> extraction method available without a business account.

#### Optional configuration

Settings live in `config.json` (committed, no secrets). Each value resolves as
**environment variable > `config.json` > built-in default**, so you can override any of them per-run
with an env var without editing the file.

| Key | Default | Purpose |
|-----|---------|---------|
| `CHROME_BIN` | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` | Chrome executable |
| `CHROME_PROFILE_DIR` | `~/.virtuagym-chrome` | Dedicated automation profile |
| `CDP_PORT` | `9222` | Remote debugging port |
| `VIRTUAGYM_SIGNIN_URL` / `VIRTUAGYM_CALENDAR_URL` | thriveandconquer.virtuagym.com URLs | VirtuaGym endpoints |
| `VIRTUAGYM_GOOGLE_ACCOUNT` | `troys2005@gmail.com` | Account shown in the sign-in prompt |

### 4. Refresh auth (if expired)

If the session ever dies, runs detect it and automatically open a headed window for you to sign in
again. You can also trigger the one-time login manually:

```bash
python3 browser_session.py --login
```

## Usage

```bash
# Extract today's workout (default)
python3 extract_workout.py

# Extract the most recent workout on the calendar
python3 extract_workout.py last

# Extract a specific date
python3 extract_workout.py 2026-03-21

# Other date formats
python3 extract_workout.py today
python3 extract_workout.py yesterday
python3 extract_workout.py "Mar 21"
```

### Run from your phone (Cowork Dispatch)

Cowork Dispatch runs in a **sandboxed Linux VM** — no `launchctl`, no macOS binaries, and
`localhost:9222` is blocked — but it has a **read/write mount of this repo**. The bridge is launchd's
`WatchPaths`: the on-demand job watches `.dispatch-trigger`, so writing that file (which the sandbox
can do through the mount) fires `extract.sh` **natively on the Mac**, where Chrome lives.

```
phone → Dispatch (sandbox) → write .dispatch-trigger → launchd (Mac) → extract.sh → outputs + logs via mount
```

`scripts/launchd.sh` subcommands, by where they can run:

```bash
# Sandbox-safe (pure file I/O — works from Cowork Dispatch)
scripts/launchd.sh trigger [last|today|YYYY-MM-DD]   # write .dispatch-trigger -> launchd fires
scripts/launchd.sh logs [N]                          # tail logs/extract.{out,err}.log

# Mac terminal only (need launchctl)
scripts/launchd.sh install     # register the on-demand job (one-time; re-run after plist changes)
scripts/launchd.sh run-now     # launchctl kickstart
scripts/launchd.sh status      # load state / last exit code / pid
scripts/launchd.sh uninstall
```

`extract.sh` re-renders `logs/dashboard.html` at the end of every run (`scripts/status.py` +
`scripts/dashboard.sh`, which themselves need `launchctl` so they only run on the Mac), so Dispatch
can read a current status dashboard straight from the mount.

**Phone recipe:** *"In virtualgym-agent, run `scripts/launchd.sh trigger`, then `scripts/launchd.sh
logs` until it prints Done!, then **attach the file** `images/workout_<date>_ig.png` so it appears in
Outputs (share the actual file, not just a description)."* The explicit "attach the file" matters —
Dispatch only surfaces files the agent actively shares.

The script will:
1. Load saved auth and open the VirtuaGym Activity Calendar
2. Navigate to the target date
3. Click through each exercise to read detailed set/rep/weight data
4. Generate three output files in `data/` and `images/`

## Output Files

| File | Location | Description |
|------|----------|-------------|
| `workout_YYYY-MM-DD.json` | `data/` | Structured workout data with exercises, sets, volume |
| `workout_YYYY-MM-DD_report.txt` | `data/` | Human-readable text summary |
| `workout_YYYY-MM-DD_ig.png` | `images/` | Instagram image (1080x1350, dark theme) |

## Project Structure

```
workouts/
├── README.md                 # This file
├── CLAUDE.md                 # Claude Code project context
├── requirements.txt          # Python dependencies (pip)
├── extract_workout.py        # Main extraction script (agent-browser)
├── browser_session.py        # Persistent Chrome profile + CDP connect/login
├── generate_ig_workout.py    # Pillow-based IG image generator
├── fonts/                    # Poppins font files for image generation
├── data/                     # JSON reports and text summaries (gitignored)
└── images/                   # Generated Instagram images (gitignored)
```

## Workout Programs

Two alternating programs, typically 2-3x/week:

- **AV-1 Squat/Pull**: Dead bug, Scapular pull up, Side pivot, Horizontal row exorotation, Sumo squat stretch > Squat (Barbell), Hammer curl (DBs) > Step up high (DBs), Bent-over row (DBs), Crunch crossed toe touch, Rowing machine, Wall ball (MB)

- **AV-2 Press/Hinge**: Neck pull (EB), Hand walk plyo pushup, Pallof press R/L (Pulley), Goodmorning > Bench press wide grip (Barbell), Deadlift stiffed legs (DBs) > Push-up incline (PB), Swing (KB), Sit-up overhead throw (Wall MB), Assault bike, Push press alternated (LM)

## Volume Calculation

Per VirtuaGym convention:
- **Rep-based with weight**: `reps x weight_lbs` per set
- **Time-based with weight**: `seconds x weight_lbs` per set (seconds treated as reps)
- **No weight**: volume = 0
