# virtualgym-agent — Operational Document

**Version:** 0.2 · **Owner:** Troy Scott · **Last reviewed:** 2026-04-13

Operational reference for running, debugging, and extending the VirtuaGym
extraction pipeline. Assumes you've read `README.md` and `CLAUDE.md`.

---

## 1. System overview

Two processes, two artifacts:

| Stage | Driver | Inputs | Outputs |
|---|---|---|---|
| Extract | `extract_workout.py` → `agent-browser` CLI | date arg, `virtuagym-auth.json` | workout dict |
| Report | inline Python | workout dict | `data/*.json`, `data/*_report.txt` |
| Image | `generate_ig_workout.py` (Pillow) | JSON path, Poppins fonts | `images/*_ig.png` (1080×1350) |

---

## 2. Runtime dependencies

| Dep | Version | Install | Notes |
|---|---|---|---|
| Python | 3.12 | `micromamba create -n workout python=3.12` | env at `~/.local/share/mamba/envs/workout` |
| Pillow | pinned in `requirements.txt` | `pip install -r requirements.txt` | only runtime Python dep |
| Node.js | LTS | system | needed for `agent-browser` |
| agent-browser | latest | `npm i -g agent-browser && agent-browser install` | Vercel's Playwright wrapper |
| Poppins fonts | Bold / Medium / Regular / Light | bundled in `fonts/` | required by IG generator |

Always `micromamba activate workout` before running scripts.

---

## 3. Authentication model

VirtuaGym has no public API on this tenant. Access is via cookie-based session
replay.

| Step | Command | Frequency |
|---|---|---|
| First login | `agent-browser --headed open https://thriveandconquer.virtuagym.com/signin` | once, manual (CAPTCHA) |
| Save state | `agent-browser state save ./virtuagym-auth.json` | after every fresh login |
| Headless load | done automatically by `extract_workout.py` via `state load` | every run |
| Refresh | repeat steps 1–2 | when session expires (weeks → months) |

`virtuagym-auth.json` contains cookies + localStorage. **Gitignored.** If it
leaks, log out of VirtuaGym to invalidate the session, then re-login.

---

## 4. Extraction flow (detailed)

### 4.1 Date resolution (`parse_date_arg`)

| Arg | Behaviour |
|---|---|
| *(none)* | `datetime.now()` |
| `today` / `yesterday` | as named |
| `last` | scans calendar for most recent day with exercise content (`find_last_workout_date`) |
| `YYYY-MM-DD` | strict ISO |
| `Mar 21`, `March 21`, `3/21` | current-year fallback parse |

### 4.2 Calendar navigation (`navigate_to_date`)

1. `agent-browser state load` → `open` → `wait --load networkidle`.
2. Read `snapshot` for displayed month string (regex on `StaticText "Month YYYY"`).
3. If mismatch, click prev-month arrow up to 12 times using the ref before the
   month StaticText in the interactive snapshot.
4. Inject JS to click the matching `.day .calender_day_nr`, filtering out
   `inactive`, `other_month`, `grey` classes.
5. Fixed `wait 2000` for sidebar render.

**Known fragility:** only navigates *backward*; jumping forward months isn't
implemented. Safe today because extractions are always for past/current dates.

### 4.3 Sidebar parse (`get_sidebar_overview`)

- Title from `link "Troy Scott..." [ref=eNN]` in interactive snapshot.
- Exercise list from `listitem "..." [level=1, ref=eNN]`.
- Sidebar reps/cals parsed from full snapshot `StaticText` adjacent lines.

### 4.4 Exercise detail (`extract_exercise_detail`)

Per exercise:

1. `scrollintoview @ref` → `click` → `wait 1500`.
2. Mode detected via presence of `radio "Time-based" [checked=true`.
3. Walk snapshot lines, tracking section = `reps` | `weight` | `cal` based on
   `cell "Reps"` / `cell "Weight"` / `cell "Calories"` markers.
4. Collect textbox values under each section; break reps on first zero
   (trailing empty sets).
5. Build `sets[]`, applying the time-based vs rep-based shape.

### 4.5 Classification & volume

| Order | Type | Category | Rule |
|---|---|---|---|
| 1–5 | `warmup` | `activation` | fixed by position |
| 6–7 | `strength` | `compound_lift` if ≥3 sets w/ weight, else `isolation` | fixed by position |
| 8+ | `conditioning` | `amrap_circuit` | fixed by position |

Volume (`calculate_volume`):

```
rep-based  : Σ (reps × weight_lbs)     # per set, only if weight present
time-based : Σ (seconds × weight_lbs)  # VirtuaGym stores secs in the reps field
no weight  : 0
```

`summary.volume_breakdown` is sorted desc; top 3 surface on the IG image.

### 4.6 File writes

| Path | Content |
|---|---|
| `data/workout_YYYY-MM-DD.json` | full dict, schema in `CLAUDE.md` |
| `data/workout_YYYY-MM-DD_report.txt` | text report from `generate_report()` |
| `images/workout_YYYY-MM-DD_ig.png` | IG image from `generate_ig_workout.py` |

---

## 5. IG image generator

| Property | Value |
|---|---|
| Canvas | 1080 × 1350 (Instagram portrait) |
| Background | vertical gradient `#0C0C14` → `#161928` |
| Accent | teal `#00C896` |
| Fonts | Poppins Bold / Medium / Regular / Light |
| Section dots | warmup blue, strength orange, conditioning red |

Layout, top to bottom: date header → workout title → 3-stat row (calories /
volume / exercises) → optional steps pill → sectioned exercise list → bottom
block (top-3 lifts, total volume, watermark).

**Overflow handling:** `generate_ig_workout.py` estimates required height; if
`> HEIGHT - 160`, it switches to a compact font/step profile. If content still
overflows mid-draw, remaining exercises collapse to `+ more exercises...`.

---

## 6. Standard operating procedures

### 6.1 Daily extract

```bash
micromamba activate workout
cd ~/path/to/virtualgym-agent
python3 extract_workout.py           # today
# or
python3 extract_workout.py last      # most recent on calendar
```

Check the three output files, then post the PNG.

### 6.2 Backfill a missed day

```bash
python3 extract_workout.py 2026-04-10
```

If the date is in a prior month, calendar navigation will click back
month-by-month (up to 12 iterations).

### 6.3 Re-render IG image from existing JSON

```bash
python3 generate_ig_workout.py data/workout_2026-04-12.json
```

Useful when tweaking the image without re-scraping.

### 6.4 Auth refresh

```bash
agent-browser --headed open https://thriveandconquer.virtuagym.com/signin
# log in manually
agent-browser state save ./virtuagym-auth.json
```

---

## 7. Troubleshooting

| Symptom | Likely cause | Remedy |
|---|---|---|
| `Command failed` on `state load` | corrupt/missing `virtuagym-auth.json` | re-run headed login |
| Script runs but `Found 0 exercises` | logged out / session expired / wrong date | check with `--headed open`; refresh auth |
| Calendar stuck on wrong month | navigation hit 12-iter cap or forward-only requirement | manually pass exact `YYYY-MM-DD`; check `navigate_to_date` logs |
| Exercise detail returns empty sets | detail panel hadn't rendered | bump the `wait 1500` in `click_ref` |
| Volume looks wrong for time-based | seconds-as-reps rule not applied | verify `exercise_mode == "time-based"` in JSON |
| IG image clips exercises | too many exercises for canvas | compact mode already auto-triggers; edit `max_exercise_y` in generator |
| CAPTCHA blocks login | expected — VirtuaGym signin has CAPTCHA | use `--headed`, solve by hand, then `state save` |
| Font error on image gen | missing Poppins TTF | confirm `fonts/Poppins-*.ttf` present |

---

## 8. File & data contracts

**JSON schema** — authoritative copy in `CLAUDE.md §JSON Schema`. Key
invariants the IG generator depends on:

- `summary.total_workout_calories` (int)
- `summary.total_volume_lbs` (int)
- `summary.volume_breakdown` (dict, sorted desc in write order)
- `total_exercises` (int)
- `activity` — may be `None`; generator checks before drawing steps pill
- each exercise has `type ∈ {warmup, strength, conditioning}` and `exercise_mode ∈ {repetition-based, time-based}`
- each set has either `reps` (int) + `duration: null`, or `reps: null` + `duration: "Ns"`

Breaking any of these will silently corrupt the IG image.

---

## 9. Security & privacy

- `virtuagym-auth.json` grants full account access; never commit, never share.
- `data/` and `images/` contain personal training data — gitignored.
- No credentials stored in code or environment; auth is cookie-based.
- Outbound traffic: only `thriveandconquer.virtuagym.com` during extract and
  `fonts/` local reads during image gen.

---

## 10. Extension points

| Want to… | Touch |
|---|---|
| Add a 4th exercise section (e.g. cooldown) | classification block in `extract_exercise_detail`, `section_colors` + loop in `generate_ig_workout.py`, report sections in `generate_report` |
| Post to Instagram automatically | new module consuming `images/*_ig.png`; Graph API or 3rd-party scheduler |
| Push JSON to a data warehouse | append after `json.dump` in `main()`; Fabric Lakehouse or similar |
| Multi-user support | parameterise `BASE_URL` (`/user/<handle>/exercise`) and auth file path |
| Weekly/monthly roll-up image | new generator consuming glob of `data/*.json` |
| Switch off agent-browser | replace `run()` shell calls with direct Playwright Python; preserve snapshot-parsing contract |

---

## 11. Known limitations

- Classification is **positional**, not semantic — reordering the program will
  mis-tag exercises.
- Calendar navigation is backward-only and capped at 12 months.
- Snapshot parsing is regex-based; any `agent-browser` snapshot format change
  will break extraction silently.
- No unit tests; verification is visual (inspect JSON + PNG after each run).
- `find_last_workout_date` scans only the currently-displayed month.
