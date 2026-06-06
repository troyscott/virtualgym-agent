# Architecture

How `virtualgym-agent` works end to end, and **why** it's built this way. For *how to run it* see
[README.md](README.md); for operating conventions and gotchas see [CLAUDE.md](CLAUDE.md).

## Overview

The project turns an always-on **Mac mini** into a small personal automation server. One "command" —
extract the latest VirtuaGym workout and produce an Instagram-ready image — can be triggered from a
phone via Claude **Cowork Dispatch**, runs natively on the Mac, and delivers the image back. There is
no public VirtuaGym API, so extraction is browser automation (`agent-browser`/CDP) against a logged-in
Chrome session.

```
phone (Cowork Dispatch)
  │  "run scripts/launchd.sh trigger … attach outputs/latest_ig.png"
  ▼
Dispatch session  ── sandboxed Linux VM: no launchctl, no localhost; repo mounted r/w ──┐
  │  writes .dispatch-trigger (via the repo mount)                                        │
  ▼                                                                                       │
launchd (macOS, native)  ── WatchPaths on .dispatch-trigger ──▶ extract.sh --from-trigger │
  │                                                                                       │
  ▼                                                                                       │
extract_workout.py ──▶ browser_session.py ──▶ Chrome (persistent profile, headless, CDP) │
  │   reads VirtuaGym calendar + exercise detail panels                                   │
  ▼                                                                                       │
data/*.json + *_report.txt   images/workout_<date>_ig.png                                 │
  │                                                                                       │
  ├─▶ outputs/latest_ig.png        (git-tracked dir → visible in the repo mount) ─────────┘
  │        └─ Dispatch agent copies repo mount → /mnt/outputs → image appears in chat
  └─▶ ~/Dropbox/virtuagym/         (guaranteed channel, viewable in the Dropbox app)
```

## Components

| Component | File / location | Role |
|-----------|-----------------|------|
| Extraction pipeline | `extract_workout.py` | Navigate the calendar, read each exercise detail, classify, compute volume, write JSON + text report, generate the IG image |
| Browser session | `browser_session.py` | Launch/connect a **persistent** Chrome profile over CDP; detect login; one-time headed Google sign-in |
| IG image generator | `generate_ig_workout.py` | Pillow renderer → 1080×1350 image |
| Entry-point wrapper | `extract.sh` | Single command for terminal + launchd; trigger de-dup + lock; image delivery to `outputs/` and Dropbox |
| launchd job | `scripts/launchd.sh` → `~/Library/LaunchAgents/com.troyscott.virtualgym.extract.plist` | On-demand LaunchAgent; `WatchPaths` trigger; `install`/`run-now`/`status`/`logs`/`trigger` |
| Status dashboard | `scripts/status.py` + `scripts/dashboard.{html,sh}` | JSON job status + latest-workout summary rendered as a live-artifact HTML page |
| Delivery targets | `outputs/` (tracked dir, ignored contents), `~/Dropbox/virtuagym/` | Where the IG image lands for retrieval |

## Data flow (step by step)

1. **Trigger.** From the phone, a Dispatch task runs `scripts/launchd.sh trigger [date]`, which writes
   the date into `.dispatch-trigger`. Dispatch can't run `launchctl`, but it can write the file through
   the repo mount.
2. **launchd reacts.** `WatchPaths` on `.dispatch-trigger` starts `extract.sh --from-trigger` natively
   on the Mac (where Chrome and `localhost:9222` exist).
3. **De-dup + lock.** A single write emits several FSEvents; `extract.sh` fingerprints the trigger
   (mtime + content in `.dispatch-trigger.processed`) and skips duplicate fires, with a `.extract.lock`
   mkdir lock preventing overlap. One write → exactly one run.
4. **Connect.** `browser_session.ensure_connected()` launches the dedicated Chrome profile headless,
   connects over CDP, and verifies the VirtuaGym session is alive (headed re-login only if it's dead).
5. **Extract.** `extract_workout.py` clicks the target date, reads the exercise list and each detail
   panel, classifies by position, and computes volume (reps×weight; seconds×weight for time-based).
6. **Outputs.** Writes `data/workout_<date>.json`, the text report, and the IG image. On success
   `extract.sh` copies the image to `outputs/latest_ig.png` (+ dated) and `~/Dropbox/virtuagym/`, then
   re-renders `logs/dashboard.html`.
7. **Deliver.** The Dispatch agent reads `outputs/latest_ig.png` from the repo mount, copies it to the
   `/mnt/outputs` mount, and the image appears inline in the chat. Dropbox is the parallel channel.

## Key design decisions (the *why*)

- **Persistent CDP Chrome profile, not a cookie snapshot.** The original `virtuagym-auth.json` was a
  ~30-day cookie export that silently expired, forcing manual re-logins. A live, on-disk profile keeps
  its Google SSO refreshed, so sign-in is a rare one-time step. Login is "Sign in with Google," which
  sidesteps the signin page's reCAPTCHA while a Google session is alive.
- **A dedicated `--user-data-dir`, not the default profile.** Chrome 136+ refuses
  `--remote-debugging-port` on the default profile, so automation requires its own profile
  (`~/.virtuagym-chrome`).
- **WatchPaths trigger, not `launchctl` from Dispatch.** Cowork Dispatch runs in a **sandboxed Linux
  VM** — no `launchctl`, no macOS binaries, and `localhost:9222` is blocked — but it mounts the repo
  read/write. launchd `WatchPaths` turns a plain file write (which the sandbox *can* do) into a native
  job start. This is the bridge between the sandbox and the Mac.
- **Trigger de-dup + lock.** WatchPaths fires on raw FSEvents, so one write can start the job several
  times. Fingerprint + lock collapse that to a single run.
- **Dual delivery (`outputs/` + Dropbox), and why the mount matters.** The sandbox can read the **repo
  mount** but not `~/Dropbox`. So the in-repo `outputs/` folder (git-tracked via `.gitkeep`, images
  gitignored) is what the Dispatch agent can actually reach and surface to `/mnt/outputs`. Dropbox is a
  guaranteed out-of-band channel for the human, independent of Dispatch's file-sharing.
- **Activity-row filtering.** VirtuaGym logs a session activity row (e.g. "Fitness, strength
  training/bodybuilding") with no detail panel; the click-through read stale values from the previous
  exercise, double-counting volume/calories. These rows are dropped after extraction so totals stay
  accurate.

## Constraints & gotchas

- **Mac mini must stay awake and networked**, with Claude Desktop running and signed in, for Dispatch
  to land.
- **Dispatch sandbox:** no `launchctl`, no `localhost`, repo mounted read/write, outputs via
  `/mnt/outputs`. Anything needing the Mac natively must go through the WatchPaths trigger.
- **Chrome 136+** blocks remote debugging on the default profile — the dedicated profile is mandatory.
- **Auth death:** if the Google session truly dies, an unattended headless run can't solve the login;
  run `python browser_session.py --login` once at the machine.
- **Classification is position-based** (1–5 warmup, 6–7 strength, 8+ conditioning) and assumes the
  usual program shape; unusual orderings can misclassify.

## Extending it

The launchd + `outputs/` pattern generalizes to any "command" you want to drive from the phone:

1. Add a script that does the work and writes its result into `outputs/` (and/or Dropbox).
2. Register a LaunchAgent for it with a `WatchPaths` trigger file (mirror `scripts/launchd.sh`), or
   reuse the existing job with a different trigger argument.
3. From Dispatch, write the trigger file and have the agent read the result from the repo mount.

Each new command reuses the solved hard parts — auth, triggering, de-dup, delivery — so the Mac mini
grows into a general personal automation server, not a single-purpose script.
