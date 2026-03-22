# virtualgym-agent

## Overview

Automated workout extraction from VirtuaGym Activity Calendar using Vercel's `agent-browser` CLI. Generates structured JSON, text reports, and Instagram-ready images (1080x1350).

## Project Structure

```
workouts/
├── requirements.txt          # Python dependencies (pip)
├── extract_workout.py        # Main extraction script (run this)
├── generate_ig_workout.py    # Pillow-based IG image generator
├── virtuagym-auth.json       # Saved auth state (do NOT commit)
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
User: `troys2005`

```bash
# First time / refresh: headed login
agent-browser --headed open https://thriveandconquer.virtuagym.com/signin
agent-browser state save ./virtuagym-auth.json

# Automated runs load saved state
agent-browser state load ./virtuagym-auth.json
```

## Extraction Workflow

The `extract_workout.py` script automates the full pipeline:

1. **Load auth** and navigate to Activity Calendar
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

- **Auth expired**: Re-run headed login and `state save` a fresh `virtuagym-auth.json`
- **CAPTCHA on login**: Use `--headed` mode to solve manually, then save state
- **Exercise detail not loading**: Script waits 1.5s after each click; increase if needed
- **Sidebar not scrolling**: Script uses `scrollintoview` before clicking each exercise
- **Volume mismatch**: Verify time-based exercises use seconds x weight
