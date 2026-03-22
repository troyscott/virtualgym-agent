# virtualgym-agent

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

VirtuaGym requires a one-time manual login because the signin page uses CAPTCHA which cannot be solved automatically. The `--headed` flag opens a visible browser window so you can complete the login yourself:

```bash
agent-browser --headed open https://thriveandconquer.virtuagym.com/signin
# Log in manually and solve CAPTCHA if prompted
agent-browser state save ./virtuagym-auth.json
```

This creates `virtuagym-auth.json` which caches your session cookies. The auth state persists for an extended period — all future runs are fully headless with no browser window needed.

This file is **gitignored** — each user must create their own locally.

> **Note:** VirtuaGym does not offer a public API — web scraping via agent-browser is the only extraction method available without a business account.

### 4. Refresh auth (if expired)

If your session eventually expires, re-run the headed login:

```bash
agent-browser --headed open https://thriveandconquer.virtuagym.com/signin
agent-browser state save ./virtuagym-auth.json
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
├── generate_ig_workout.py    # Pillow-based IG image generator
├── virtuagym-auth.json       # Saved auth state (do not commit)
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
