#!/usr/bin/env python3
"""
Generate Instagram workout summary image from VirtuaGym JSON data.
Creates a 1080x1350 portrait image with workout text overlaid on a styled background.
"""

import json
import sys
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────
WIDTH = 1080
HEIGHT = 1350

# Color palette (dark athletic theme)
BG_TOP = (12, 12, 20)
BG_BOT = (22, 25, 40)
ACCENT = (0, 200, 150)
WHITE = (255, 255, 255)
LIGHT = (185, 195, 210)
MID = (110, 120, 135)
DIM = (60, 68, 85)

# Fonts
import os as _os
FONT_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "fonts") + "/"

def font(weight, size):
    return ImageFont.truetype(f"{FONT_DIR}Poppins-{weight}.ttf", size)

# Pre-load fonts
F_TITLE = font("Bold", 38)
F_SECTION = font("Bold", 24)
F_DATE = font("Medium", 22)
F_STAT_VAL = font("Bold", 34)
F_STAT_LBL = font("Regular", 15)
F_EX_NAME = font("Medium", 22)
F_EX_DETAIL = font("Light", 18)
F_CAL = font("Regular", 17)
F_STEPS = font("Medium", 17)
F_SMALL = font("Light", 15)
F_WM = font("Light", 13)


def vertical_gradient(width, height, top, bot):
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for y in range(height):
        r = top[0] + (bot[0] - top[0]) * y // height
        g = top[1] + (bot[1] - top[1]) * y // height
        b = top[2] + (bot[2] - top[2]) * y // height
        for x in range(width):
            pixels[x, y] = (r, g, b)
    return img


def right_align(draw, text, y, font, fill, margin=60):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text((WIDTH - margin - w, y), text, fill=fill, font=font)


def generate_workout_image(json_path, output_path=None):
    with open(json_path, "r") as f:
        data = json.load(f)

    if output_path is None:
        output_path = json_path.replace(".json", "_ig.png")

    # ── Base image ──
    img = vertical_gradient(WIDTH, HEIGHT, BG_TOP, BG_BOT)
    draw = ImageDraw.Draw(img)

    # ── Accent bars ──
    draw.rectangle([(0, 0), (WIDTH, 5)], fill=ACCENT)
    draw.rectangle([(0, HEIGHT - 5), (WIDTH, HEIGHT)], fill=ACCENT)

    y = 35

    # ── HEADER ──
    dt = datetime.strptime(data["workout_date"], "%Y-%m-%d")
    date_str = dt.strftime("%A, %B %d, %Y").upper()
    draw.text((60, y), date_str, fill=ACCENT, font=F_DATE)
    y += 40

    draw.text((60, y), data["workout_title"], fill=WHITE, font=F_TITLE)
    y += 58

    # Divider
    draw.line([(60, y), (WIDTH - 60, y)], fill=DIM, width=2)
    y += 25

    # ── STATS ROW ──
    summary = data["summary"]
    stats = [
        (f"{summary['total_workout_calories']}", "CALORIES"),
        (f"{summary['total_volume_lbs']:,}", "VOLUME (lbs)"),
        (f"{data['total_exercises']}", "EXERCISES"),
    ]
    col_w = (WIDTH - 120) // 3
    for i, (val, label) in enumerate(stats):
        sx = 60 + i * col_w
        draw.text((sx, y), val, fill=WHITE, font=F_STAT_VAL)
        draw.text((sx, y + 42), label, fill=MID, font=F_STAT_LBL)
    y += 82

    # ── Steps pill ──
    if data.get("activity"):
        act = data["activity"]
        steps_txt = f"  {act['value']:,} steps   |   {act['duration']}   |   {act['calories']} Kcal"
        # Draw a subtle pill background
        draw.rounded_rectangle(
            [(56, y - 2), (WIDTH - 56, y + 32)],
            radius=6, fill=(0, 50, 40)
        )
        draw.text((68, y + 3), "STEPS" + steps_txt, fill=ACCENT, font=F_STEPS)
        y += 48

    # Divider
    draw.line([(60, y), (WIDTH - 60, y)], fill=DIM, width=1)
    y += 20

    # ── GROUP EXERCISES ──
    by_type = {}
    for ex in data["exercises"]:
        t = ex["type"]
        by_type.setdefault(t, []).append(ex)

    section_colors = {
        "warmup":       (100, 180, 230),
        "strength":     (255, 160, 50),
        "conditioning": (230, 65, 85),
    }

    for stype in ["warmup", "strength", "conditioning"]:
        if stype not in by_type:
            continue

        color = section_colors[stype]
        label = stype.upper()

        # Section header
        draw.ellipse([(60, y + 4), (74, y + 18)], fill=color)
        draw.text((84, y - 2), label, fill=color, font=F_SECTION)
        y += 38

        for ex in by_type[stype]:
            # Exercise name (left) + calories (right)
            draw.text((80, y), ex["name"], fill=WHITE, font=F_EX_NAME)
            cal_str = f"{ex['total_calories']} Kcal"
            right_align(draw, cal_str, y + 3, F_CAL, MID)
            y += 30

            # Set details line
            sets = ex["sets"]
            if ex["exercise_mode"] == "time-based":
                parts = [s["duration"] for s in sets]
                detail = " / ".join(parts)
                wts = [s["weight_lbs"] for s in sets if s.get("weight_lbs")]
                if wts:
                    detail += f"  @ {wts[0]} lbs"
            else:
                reps = [s["reps"] for s in sets]
                wts = [s["weight_lbs"] for s in sets if s.get("weight_lbs")]

                if len(reps) == 1:
                    detail = f"{reps[0]} reps"
                elif len(set(reps)) == 1:
                    detail = f"{len(reps)} x {reps[0]} reps"
                else:
                    detail = " / ".join(str(r) for r in reps) + " reps"

                if wts:
                    if len(set(wts)) == 1:
                        detail += f"  @ {wts[0]} lbs"
                    else:
                        detail += f"  @ " + " / ".join(str(w) for w in wts) + " lbs"

            draw.text((100, y), detail, fill=LIGHT, font=F_EX_DETAIL)
            y += 30

        y += 12  # section gap

    # ── BOTTOM SUMMARY ──
    # Push to bottom area
    bottom_y = max(y + 20, HEIGHT - 140)
    draw.line([(60, bottom_y), (WIDTH - 60, bottom_y)], fill=DIM, width=2)
    bottom_y += 18

    # Top lifts
    vol = summary.get("volume_breakdown", {})
    if vol:
        items = sorted(vol.items(), key=lambda x: x[1], reverse=True)[:3]
        draw.text((60, bottom_y), "TOP LIFTS (lbs)", fill=MID, font=F_STAT_LBL)
        bottom_y += 22
        parts = [f"{k.replace('_', ' ').title()}: {v:,}" for k, v in items]
        draw.text((60, bottom_y), "  |  ".join(parts), fill=LIGHT, font=F_SMALL)
        bottom_y += 30

    # Total volume
    draw.text((60, bottom_y), "TOTAL VOLUME", fill=MID, font=F_STAT_LBL)
    draw.text((210, bottom_y - 5), f"{summary['total_volume_lbs']:,} lbs",
              fill=ACCENT, font=font("Bold", 26))

    # Watermark
    wm = "THRIVE & CONQUER"
    wm_bbox = draw.textbbox((0, 0), wm, font=F_WM)
    wm_w = wm_bbox[2] - wm_bbox[0]
    draw.text((WIDTH - wm_w - 30, HEIGHT - 28), wm, fill=DIM, font=F_WM)

    # ── Save ──
    img.save(output_path, "PNG")
    print(f"Saved: {output_path} ({img.size[0]}x{img.size[1]})")
    return output_path


if __name__ == "__main__":
    json_file = sys.argv[1] if len(sys.argv) > 1 else "workout_2026-02-06.json"
    generate_workout_image(json_file)
