#!/usr/bin/env python3
"""
Persistent Chrome session management for VirtuaGym extraction.

Instead of a static cookie snapshot (virtuagym-auth.json) that expires every
~30 days, this module drives a dedicated, persistent Chrome profile over CDP.
A live profile keeps its Google SSO silently refreshed, so a manual
"Sign in with Google" is needed only once (and rarely again).

Chrome >= 136 refuses --remote-debugging-port on the default profile, so we
always use a separate --user-data-dir.

Usage:
    from browser_session import ensure_connected
    ensure_connected()          # launch (headless) + connect + verify login

    python3 browser_session.py --login   # one-time headed Google sign-in
"""

import os
import sys
import json
import time
import shlex
import subprocess
import urllib.request
import urllib.error

# --- Config ------------------------------------------------------------------
# Values resolve in this order: environment variable > config.json > default.
# config.json lives next to this file and holds no secrets (safe to commit).

WORKDIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(WORKDIR, "config.json")


def _load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


_CFG = _load_config()


def _cfg(key, default):
    """Resolve a setting: env var wins, then config.json, then default."""
    return os.environ.get(key, _CFG.get(key, default))


CHROME_BIN = _cfg(
    "CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
PROFILE_DIR = os.path.expanduser(_cfg("CHROME_PROFILE_DIR", "~/.virtuagym-chrome"))
DEBUG_PORT = int(_cfg("CDP_PORT", 9222))

SIGNIN_URL = _cfg(
    "VIRTUAGYM_SIGNIN_URL", "https://thriveandconquer.virtuagym.com/signin"
)
CALENDAR_URL = _cfg(
    "VIRTUAGYM_CALENDAR_URL",
    "https://thriveandconquer.virtuagym.com/user/troys2005/exercise",
)
GOOGLE_ACCOUNT = _cfg("VIRTUAGYM_GOOGLE_ACCOUNT", "troys2005@gmail.com")

# How long to poll for the CDP endpoint / a completed login.
CDP_WAIT_SECONDS = 20
LOGIN_WAIT_SECONDS = 300


def _run(cmd, timeout=30, critical=False):
    """Run an agent-browser command and return stdout (kept independent of
    extract_workout.run to avoid a circular import)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            print(f"  STDERR: {stderr[:200]}")
        if critical:
            raise RuntimeError(f"Command failed (exit {result.returncode}): {cmd[:60]}")
    return result.stdout.strip()


def cdp_ready(port=DEBUG_PORT):
    """True if a Chrome CDP endpoint is listening on the given port."""
    try:
        with urllib.request.urlopen(
            f"http://localhost:{port}/json/version", timeout=2
        ) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def launch_chrome(headless=True, url=None):
    """Launch the dedicated Chrome profile with remote debugging enabled.

    Detached so it survives this process; polls until the CDP port is ready.
    No-op (returns True) if an instance is already listening on DEBUG_PORT.
    """
    if cdp_ready(DEBUG_PORT):
        return True

    os.makedirs(PROFILE_DIR, exist_ok=True)
    args = [
        CHROME_BIN,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        args.append("--headless=new")
    if url:
        args.append(url)

    mode = "headless" if headless else "headed"
    print(f"Launching Chrome ({mode}) with profile {PROFILE_DIR}")
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.time() + CDP_WAIT_SECONDS
    while time.time() < deadline:
        if cdp_ready(DEBUG_PORT):
            return True
        time.sleep(0.5)
    raise RuntimeError(
        f"Chrome CDP endpoint not ready on port {DEBUG_PORT} after {CDP_WAIT_SECONDS}s"
    )


def connect():
    """Attach the agent-browser session to the running Chrome over CDP."""
    _run(f"agent-browser connect {DEBUG_PORT}", critical=True)


def is_logged_in():
    """Open the calendar and decide whether we have an authenticated session.

    When logged out, VirtuaGym does not redirect — the calendar URL renders a
    public landing page exposing "Login" / "Register" links (and no calendar).
    A live session instead shows the exercise calendar with month navigation.
    """
    _run(f"agent-browser open {shlex.quote(CALENDAR_URL)}", critical=True)
    _run("agent-browser wait --load networkidle")
    url = _run("agent-browser get url").lower()
    if "signin" in url or "login" in url:
        return False
    snap = _run("agent-browser snapshot -i")
    # Logged-out landing page advertises these; an authed calendar never does.
    if 'link "Login"' in snap or 'link "Register"' in snap:
        return False
    if 'textbox "Password"' in snap or 'button "Sign in"' in snap:
        return False
    return True


def _wait_for_login():
    """Block until the user completes the headed Google sign-in."""
    print()
    print("=" * 60)
    print(f"  Sign in with Google as {GOOGLE_ACCOUNT} in the Chrome window.")
    print("  This login persists in the dedicated profile for future runs.")
    print("=" * 60)
    if sys.stdin.isatty():
        input("  Press Enter once you've signed in... ")
        return is_logged_in()
    # Non-interactive (e.g. cron): poll until logged in or timeout.
    deadline = time.time() + LOGIN_WAIT_SECONDS
    while time.time() < deadline:
        if is_logged_in():
            return True
        time.sleep(5)
    return False


def ensure_connected():
    """Single entry point: guarantee an authenticated, connected browser.

    Launches the dedicated profile headless, connects over CDP, and verifies
    login. If the session is dead, relaunches headed so the user can sign in
    once via Google, then re-verifies.
    """
    launch_chrome(headless=True)
    connect()
    if is_logged_in():
        return

    print("No active VirtuaGym session — opening a window for one-time login.")
    # Close the headless instance so we can reopen the same profile headed.
    _run("agent-browser close")
    if cdp_ready(DEBUG_PORT):
        # Headless Chrome still holding the port/profile; ask it to quit.
        try:
            urllib.request.urlopen(
                f"http://localhost:{DEBUG_PORT}/json/close", timeout=2
            )
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)

    launch_chrome(headless=False, url=SIGNIN_URL)
    connect()
    if not _wait_for_login():
        raise RuntimeError(
            "Login was not completed. Re-run and sign in with Google "
            f"as {GOOGLE_ACCOUNT}."
        )
    print("Login confirmed; session is now persisted in the profile.")


def login():
    """One-time headed sign-in helper (python3 browser_session.py --login)."""
    launch_chrome(headless=False, url=SIGNIN_URL)
    connect()
    if is_logged_in():
        print(f"Already signed in (profile: {PROFILE_DIR}).")
        return
    if _wait_for_login():
        print(f"Signed in and persisted to {PROFILE_DIR}.")
    else:
        print("Login not completed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--login":
        login()
    else:
        ensure_connected()
        print("Connected and authenticated.")
