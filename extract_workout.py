#!/usr/bin/env python3
"""
Automated VirtuaGym workout extraction using agent-browser.
Usage: python3 extract_workout.py [YYYY-MM-DD]
       Defaults to yesterday's date if no argument given.
"""

import subprocess
import json
import sys
import re
import os
from datetime import datetime, timedelta

WORKDIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(WORKDIR, "data")
IMAGES_DIR = os.path.join(WORKDIR, "images")
AUTH_FILE = os.path.join(WORKDIR, "virtuagym-auth.json")
BASE_URL = "https://thriveandconquer.virtuagym.com/user/troys2005/exercise"


def run(cmd, timeout=30):
    """Run an agent-browser command and return stdout."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip()


def snapshot_interactive():
    return run("agent-browser snapshot -i")


def snapshot_full():
    return run("agent-browser snapshot")


def click_ref(ref):
    run(f"agent-browser click {ref}")
    run("agent-browser wait 1500")


def get_value(ref):
    return run(f"agent-browser get value {ref}")


def js_eval(code):
    return run(f"agent-browser eval --stdin <<'EVALEOF'\n{code}\nEVALEOF")


def navigate_to_date(target_date):
    """Load auth, open calendar, and click the target date."""
    print(f"Loading auth from {AUTH_FILE}")
    run(f"agent-browser state load {AUTH_FILE}")

    print(f"Opening {BASE_URL}")
    run(f"agent-browser open {BASE_URL}")
    run("agent-browser wait --load networkidle")

    # Check which month is displayed and navigate if needed
    snap = snapshot_full()
    current_month_match = re.search(r'StaticText "(\w+ \d{4})"', snap)
    if current_month_match:
        displayed = current_month_match.group(1)
        print(f"Calendar showing: {displayed}")

        target_month_str = target_date.strftime("%B %Y")
        # Navigate forward/back if needed
        if displayed != target_month_str:
            snap_i = snapshot_interactive()
            # Find nav arrows (links before/after month name)
            nav_links = re.findall(r'link \[ref=(e\d+)\]', snap_i)
            # Try clicking through months (simplified - assumes we need to go back)
            for _ in range(12):
                snap_full = snapshot_full()
                if target_month_str in snap_full:
                    break
                # Click previous month arrow (typically first nav link near calendar)
                snap_i = snapshot_interactive()
                prev_match = re.search(r'link \[ref=(e\d+)\]\n.*link \[ref=(e\d+)\].*\n.*StaticText "\w+ \d{4}"', snap_i)
                if prev_match:
                    run(f"agent-browser click @{prev_match.group(1)}")
                    run("agent-browser wait 1000")

    # Click the target day using JS
    day = target_date.day
    js = f"""
    const days = document.querySelectorAll('.day .calender_day_nr');
    let clicked = false;
    for (const d of days) {{
      if (d.textContent.trim() === '{day}') {{
        const parent = d.closest('.day');
        const classes = parent.className;
        if (!classes.includes('inactive') && !classes.includes('other_month') && !classes.includes('grey')) {{
          parent.click();
          clicked = true;
          break;
        }}
      }}
    }}
    JSON.stringify({{clicked}});
    """
    result = js_eval(js)
    print(f"Clicked date {target_date.strftime('%B %d')}: {result}")
    run("agent-browser wait 2000")


def get_sidebar_overview():
    """Read the sidebar to get workout title and exercise list with refs."""
    snap_i = snapshot_interactive()
    snap_full = snapshot_full()

    # Extract workout title
    title_match = re.search(r'link "(Troy Scott.*?)" \[ref=(e\d+)\]', snap_i)
    workout_title = title_match.group(1) if title_match else "Unknown Workout"

    # Extract exercise refs from sidebar
    exercises = []
    for m in re.finditer(r'listitem "(.*?)" \[level=1, ref=(e\d+)\]', snap_i):
        exercises.append({"name": m.group(1), "ref": m.group(2)})

    # Extract sidebar summary (reps + calories per exercise)
    lines = snap_full.split("\n")
    sidebar_data = []
    i = 0
    while i < len(lines):
        for ex in exercises:
            if f'StaticText "{ex["name"]}"' in lines[i]:
                reps_line = ""
                cal_line = ""
                for j in range(i + 1, min(i + 5, len(lines))):
                    if "StaticText" in lines[j] and ("x" in lines[j] or "s" in lines[j]):
                        reps_match = re.search(r'StaticText "(.*?)"', lines[j])
                        if reps_match:
                            reps_line = reps_match.group(1)
                    if "Kcal" in lines[j]:
                        cal_match = re.search(r'StaticText "(\d+) Kcal"', lines[j])
                        if cal_match:
                            cal_line = cal_match.group(1)
                sidebar_data.append({"name": ex["name"], "sidebar_reps": reps_line, "sidebar_cal": cal_line})
                break
        i += 1

    return workout_title, exercises, sidebar_data


def extract_exercise_detail(ref, name, order):
    """Click an exercise and read its detail panel."""
    # Scroll into view first, then click
    run(f"agent-browser scrollintoview @{ref}")
    run("agent-browser wait 300")
    click_ref(f"@{ref}")

    snap = snapshot_interactive()

    # Determine mode (rep-based vs time-based)
    is_time_based = 'radio "Time-based" [checked=true' in snap

    # Extract reps/time values from textboxes
    # The detail panel has cells with values
    if is_time_based:
        mode = "time-based"
        reps_match = re.search(r'cell "Reps \(s\)(.*?)"', snap)
    else:
        mode = "repetition-based"
        reps_match = re.search(r'cell "Reps \(x\)(.*?)"', snap)

    # Parse all textbox values for reps
    reps_values = []
    in_reps = False
    in_weight = False
    weight_values = []
    calories = 0

    # Find reps textboxes (they come after the Reps cell)
    reps_refs = []
    weight_refs = []
    cal_ref = None

    lines = snap.split("\n")
    section = None
    for line in lines:
        if 'cell "Reps' in line:
            section = "reps"
        elif 'cell "Weight' in line:
            section = "weight"
        elif 'cell "Calories' in line:
            section = "cal"
            cal_match = re.search(r'Calories \(Kcal\) (\d+)', line)
            if cal_match:
                calories = int(cal_match.group(1))
        elif "textbox" in line and section:
            ref_match = re.search(r'ref=(e\d+)\]: ?(.*)', line)
            if ref_match:
                val = ref_match.group(2).strip()
                if section == "reps":
                    reps_refs.append(val)
                elif section == "weight":
                    weight_refs.append(val)
                elif section == "cal":
                    calories = int(val) if val else 0
                    section = None
            else:
                # textbox without displayed value (empty weight fields)
                ref_match2 = re.search(r'textbox \[ref=(e\d+)\]$', line)
                if ref_match2 and section == "weight":
                    weight_refs.append("")

    # Filter non-zero reps
    sets = []
    for i, r in enumerate(reps_refs):
        try:
            rv = int(r) if r else 0
        except ValueError:
            rv = int(float(r)) if r else 0
        if rv == 0:
            break
        wv = None
        if i < len(weight_refs) and weight_refs[i]:
            try:
                wv = float(weight_refs[i])
                if wv == 0:
                    wv = None
            except ValueError:
                wv = None

        if is_time_based:
            sets.append({
                "set_number": i + 1,
                "reps": None,
                "duration": f"{rv}s",
                "weight_lbs": wv,
                "rest": None
            })
        else:
            sets.append({
                "set_number": i + 1,
                "reps": rv,
                "duration": None,
                "weight_lbs": wv,
                "rest": None
            })

    # Classify exercise based on order (per CLAUDE.md rules)
    if order <= 5:
        ex_type = "warmup"
        category = "activation"
    elif order <= 7:
        ex_type = "strength"
        # compound if barbell/multi-set with progressive weight
        has_weight = any(s.get("weight_lbs") for s in sets)
        category = "compound_lift" if has_weight and len(sets) >= 3 else "isolation"
    else:
        ex_type = "conditioning"
        category = "amrap_circuit"

    return {
        "order": order,
        "name": name,
        "type": ex_type,
        "category": category,
        "exercise_mode": mode,
        "sets": sets,
        "total_calories": calories
    }


def calculate_volume(exercises):
    """Calculate total volume per CLAUDE.md rules."""
    volume_breakdown = {}
    total_volume = 0

    for ex in exercises:
        ex_volume = 0
        for s in ex["sets"]:
            weight = s.get("weight_lbs")
            if not weight:
                continue
            if ex["exercise_mode"] == "time-based":
                # seconds as reps
                dur = s.get("duration", "0s")
                secs = int(dur.replace("s", "")) if dur else 0
                ex_volume += secs * weight
            else:
                reps = s.get("reps", 0) or 0
                ex_volume += reps * weight

        if ex_volume > 0:
            volume_breakdown[ex["name"]] = ex_volume
            total_volume += ex_volume

    return total_volume, volume_breakdown


def generate_report(data, output_path):
    """Generate text report from workout data."""
    dt = datetime.strptime(data["workout_date"], "%Y-%m-%d")
    date_str = dt.strftime("%A, %B %d, %Y")

    lines = []
    lines.append(f"WORKOUT SUMMARY - {date_str}")
    lines.append("=" * 45)
    lines.append(f"Program: {data['workout_title']}")
    lines.append(f"Source:  {data['source']}")
    lines.append("")

    if data.get("activity"):
        act = data["activity"]
        lines.append("ACTIVITY")
        lines.append("-" * 8)
        lines.append(f"Steps: {act['value']:,} steps | {act['duration']} | {act['calories']} Kcal")
        for aa in data.get("additional_activities", []):
            lines.append(f"{aa['name']}: {aa['duration']} | {aa['calories']} Kcal")
        lines.append("")

    # Group by type
    by_type = {}
    for ex in data["exercises"]:
        by_type.setdefault(ex["type"], []).append(ex)

    for section, label in [("warmup", "WARM-UP / ACTIVATION"), ("strength", "STRENGTH"), ("conditioning", "CONDITIONING / AMRAP CIRCUIT")]:
        exs = by_type.get(section, [])
        if not exs:
            continue
        lines.append(f"{label} ({len(exs)} exercise{'s' if len(exs) != 1 else ''})")
        lines.append("-" * (len(label) + 15))

        for ex in exs:
            sets = ex["sets"]
            has_weight = any(s.get("weight_lbs") for s in sets)

            if len(sets) == 1 and not has_weight:
                if ex["exercise_mode"] == "time-based":
                    detail = f"{sets[0]['duration']}"
                else:
                    detail = f"{sets[0]['reps']} reps"
                w_str = f" @ {sets[0]['weight_lbs']} lbs" if sets[0].get("weight_lbs") else ""
                lines.append(f"{ex['order']:>2}. {ex['name']:<40} - {detail}{w_str} ({ex['total_calories']} Kcal)")
            elif has_weight and section == "strength":
                lines.append(f"{ex['order']:>2}. {ex['name']}")
                for s in sets:
                    if ex["exercise_mode"] == "time-based":
                        r = s["duration"]
                    else:
                        r = f"{s['reps']} reps"
                    w = f" @ {s['weight_lbs']} lbs" if s.get("weight_lbs") else ""
                    lines.append(f"    Set {s['set_number']}: {r}{w}")
                vol = data["summary"]["volume_breakdown"].get(ex["name"], 0)
                if vol:
                    lines.append(f"    Volume: {vol:,} lbs | {ex['total_calories']} Kcal")
                else:
                    lines.append(f"    {ex['total_calories']} Kcal")
            else:
                lines.append(f"{ex['order']:>2}. {ex['name']}")
                reps = [s.get("reps") or s.get("duration") for s in sets]
                if len(set(str(r) for r in reps)) == 1:
                    detail = f"    {len(sets)} x {reps[0]} reps"
                else:
                    detail = "    " + " / ".join(str(r) for r in reps) + " reps"
                w = ""
                wts = [s["weight_lbs"] for s in sets if s.get("weight_lbs")]
                if wts:
                    w = f" @ {wts[0]} lbs"
                else:
                    w = " (bodyweight)"
                lines.append(f"{detail}{w}")
                lines.append(f"    {ex['total_calories']} Kcal")

            if section != "warmup":
                lines.append("")

    lines.append("=" * 38)
    lines.append("TOTALS")
    lines.append("=" * 38)
    s = data["summary"]
    lines.append(f"Total Workout Calories:  {s['total_workout_calories']} Kcal")
    if s.get("steps_calories"):
        lines.append(f"Total w/ Steps:          {s['total_with_steps']} Kcal")
    lines.append(f"Total Volume (weighted): {s['total_volume_lbs']:,} lbs")
    for name, vol in sorted(s["volume_breakdown"].items(), key=lambda x: -x[1]):
        short = name.split(" - ")[0].split(",")[0]
        lines.append(f"  - {short:<22} {vol:,} lbs")
    counts = f"{s['warmup_count']} warmup, {s['strength_count']} strength, {s['conditioning_count']} conditioning"
    lines.append(f"Exercises:               {data['total_exercises']} ({counts})")
    lines.append("=" * 38)

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved: {output_path}")


def find_last_workout_date():
    """Navigate to calendar and find the most recent date with a workout."""
    print("Finding last workout date...")
    run(f"agent-browser state load {AUTH_FILE}")
    run(f"agent-browser open {BASE_URL}")
    run("agent-browser wait --load networkidle")

    # Use JS to find calendar days that have workout indicators
    js = """
    const days = document.querySelectorAll('.day');
    const results = [];
    for (const d of days) {
      const nr = d.querySelector('.calender_day_nr');
      const hasWorkout = d.querySelector('.cal_exercise_dot, .exercise_indicator, a, .cal_has_exercise');
      const classes = d.className;
      if (nr && !classes.includes('inactive') && !classes.includes('other_month')) {
        results.push({
          day: nr.textContent.trim(),
          hasContent: d.querySelectorAll('*').length > 3,
          classes: classes
        });
      }
    }
    JSON.stringify(results);
    """
    result = js_eval(js)
    try:
        days_info = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        days_info = []

    # Get the current month/year from calendar
    snap = snapshot_full()
    month_match = re.search(r'StaticText "(\w+) (\d{4})"', snap)
    if not month_match:
        return None

    month_name = month_match.group(1)
    year = int(month_match.group(2))
    month_num = datetime.strptime(month_name, "%B").month

    # Try clicking days in reverse order to find the most recent one with exercises
    today = datetime.now()
    max_day = today.day if today.month == month_num and today.year == year else 31

    for day_info in reversed(days_info):
        day_num = int(day_info["day"])
        if day_num > max_day:
            continue
        if not day_info["hasContent"]:
            continue

        # Click this day and check if sidebar shows exercises
        test_js = f"""
        const days = document.querySelectorAll('.day .calender_day_nr');
        for (const d of days) {{
          if (d.textContent.trim() === '{day_num}') {{
            const parent = d.closest('.day');
            const classes = parent.className;
            if (!classes.includes('inactive') && !classes.includes('other_month')) {{
              parent.click();
              break;
            }}
          }}
        }}
        JSON.stringify({{clicked: true}});
        """
        js_eval(test_js)
        run("agent-browser wait 2000")

        snap_i = snapshot_interactive()
        if re.search(r'listitem ".*" \[level=1, ref=e\d+\]', snap_i):
            target = datetime(year, month_num, day_num)
            print(f"Found last workout: {target.strftime('%A, %B %d, %Y')}")
            return target

    return None


def parse_date_arg(arg):
    """Parse flexible date argument: 'today', 'last', 'yesterday', or YYYY-MM-DD."""
    arg = arg.strip().lower()

    if arg == "today":
        return datetime.now(), False
    elif arg == "yesterday":
        return datetime.now() - timedelta(days=1), False
    elif arg == "last":
        return None, True  # Signal to find last workout
    else:
        # Try YYYY-MM-DD
        try:
            return datetime.strptime(arg, "%Y-%m-%d"), False
        except ValueError:
            pass
        # Try "Mar 21", "March 21", etc.
        for fmt in ["%b %d", "%B %d", "%m/%d"]:
            try:
                d = datetime.strptime(arg, fmt).replace(year=datetime.now().year)
                return d, False
            except ValueError:
                continue
        print(f"Error: Could not parse date '{arg}'")
        print("Usage: python3 extract_workout.py [today|last|yesterday|YYYY-MM-DD|'Mar 21']")
        sys.exit(1)


def main():
    # Parse target date
    if len(sys.argv) > 1:
        target_date, find_last = parse_date_arg(sys.argv[1])
    else:
        target_date, find_last = datetime.now(), False  # Default: today

    if find_last:
        target_date = find_last_workout_date()
        if not target_date:
            print("No recent workout found on the calendar.")
            sys.exit(1)
        # find_last_workout_date already navigated and clicked the date
    else:
        navigate_to_date(target_date)

    date_str = target_date.strftime("%Y-%m-%d")
    day_name = target_date.strftime("%A")
    print(f"Extracting workout for {day_name}, {target_date.strftime('%B %d, %Y')}")

    # Step 2: Read sidebar
    workout_title, exercise_list, sidebar_data = get_sidebar_overview()
    print(f"Workout: {workout_title}")
    print(f"Found {len(exercise_list)} exercises")

    if not exercise_list:
        print("No exercises found for this date. Exiting.")
        sys.exit(1)

    # Step 3: Click through each exercise for details
    exercises = []
    for i, ex in enumerate(exercise_list):
        order = i + 1
        print(f"  [{order}/{len(exercise_list)}] {ex['name']}...", end=" ", flush=True)
        detail = extract_exercise_detail(ex["ref"], ex["name"], order)
        exercises.append(detail)
        sets_desc = f"{len(detail['sets'])} sets"
        print(f"{sets_desc}, {detail['total_calories']} Kcal")

    # Step 4: Calculate volume
    total_volume, volume_breakdown = calculate_volume(exercises)

    # Step 5: Build JSON
    total_cal = sum(e["total_calories"] for e in exercises)
    warmup_count = sum(1 for e in exercises if e["type"] == "warmup")
    strength_count = sum(1 for e in exercises if e["type"] == "strength")
    conditioning_count = sum(1 for e in exercises if e["type"] == "conditioning")

    data = {
        "workout_date": date_str,
        "day_of_week": day_name,
        "workout_title": workout_title,
        "total_exercises": len(exercises),
        "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "thriveandconquer.virtuagym.com",
        "activity": None,
        "additional_activities": [],
        "exercises": exercises,
        "summary": {
            "total_workout_calories": total_cal,
            "total_with_steps": total_cal,
            "steps_calories": 0,
            "additional_activity_calories": 0,
            "warmup_count": warmup_count,
            "strength_count": strength_count,
            "conditioning_count": conditioning_count,
            "total_volume_lbs": int(total_volume),
            "volume_breakdown": {k: int(v) for k, v in sorted(volume_breakdown.items(), key=lambda x: -x[1])},
            "volume_note": "Time-based exercises use seconds as reps per VirtuaGym"
        }
    }

    # Step 6: Write files
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    json_path = os.path.join(DATA_DIR, f"workout_{date_str}.json")
    report_path = os.path.join(DATA_DIR, f"workout_{date_str}_report.txt")
    ig_path = os.path.join(IMAGES_DIR, f"workout_{date_str}_ig.png")

    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved: {json_path}")

    # Step 7: Generate text report
    generate_report(data, report_path)

    # Step 8: Generate IG image
    try:
        from generate_ig_workout import generate_workout_image
        generate_workout_image(json_path, ig_path)
    except Exception as e:
        print(f"IG image generation failed: {e}")
        print("Run manually: python3 generate_ig_workout.py " + json_path)

    print(f"\nDone! Files in {WORKDIR}/")


if __name__ == "__main__":
    main()
