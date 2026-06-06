#!/usr/bin/env bash
#
# Manage the VirtuaGym extraction as an on-demand launchd job (LaunchAgent).
#
# The job has no timed trigger — it runs on demand, two ways:
#
#   1. launchctl kickstart (`run-now`) — requires a real Mac shell.
#   2. WatchPaths on .dispatch-trigger — ANY process that can write to the repo
#      (incl. Cowork's sandboxed Linux shell, which has no launchctl and no
#      localhost access but mounts the repo read/write) fires the job by
#      writing the trigger file. This is the Cowork Dispatch path.
#
# Sandbox-safe (pure file I/O):
#     scripts/launchd.sh trigger [ARG]   # write .dispatch-trigger (ARG: last|today|YYYY-MM-DD)
#     scripts/launchd.sh logs [N]        # tail the last N log lines (default 40)
#
# Mac-terminal only (need launchctl):
#     scripts/launchd.sh install         # register the job with launchd
#     scripts/launchd.sh run-now         # kickstart an extraction now
#     scripts/launchd.sh status          # show load state / last exit code / pid
#     scripts/launchd.sh uninstall       # remove the job
#
set -euo pipefail

LABEL="com.troyscott.virtualgym.extract"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO/logs"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
TRIGGER="$REPO/.dispatch-trigger"

gen_plist() {
    mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"
    cat > "$PLIST_DST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$REPO/extract.sh</string>
        <string>--from-trigger</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO</string>
    <key>RunAtLoad</key>
    <false/>
    <key>WatchPaths</key>
    <array>
        <string>$TRIGGER</string>
    </array>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/extract.out.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/extract.err.log</string>
</dict>
</plist>
PLIST
}

case "${1:-}" in
    install)
        # Pre-create the trigger file so loading the job doesn't fire it.
        [ -f "$TRIGGER" ] || : > "$TRIGGER"
        gen_plist
        launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
        launchctl bootstrap "$DOMAIN" "$PLIST_DST"
        echo "Installed $LABEL (on-demand)."
        echo "Trigger it with: $0 run-now  (or, from a sandbox: $0 trigger [last|today|DATE])"
        ;;
    uninstall)
        launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
        rm -f "$PLIST_DST"
        echo "Uninstalled $LABEL."
        ;;
    run-now)
        launchctl kickstart -k "$DOMAIN/$LABEL"
        echo "Triggered $LABEL. Follow output with: $0 logs"
        ;;
    trigger)
        # Sandbox-safe trigger: a write to the watched file makes launchd run
        # the job. No launchctl needed — works from Cowork Dispatch.
        echo "${2:-last}" > "$TRIGGER"
        echo "Wrote $TRIGGER (${2:-last}). launchd will start the job; follow with: $0 logs"
        ;;
    status)
        if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
            launchctl print "$DOMAIN/$LABEL" \
                | grep -E "^\s*(state|pid|last exit code) " || true
        else
            echo "$LABEL is not loaded (run: $0 install)"
        fi
        ;;
    logs)
        n="${2:-40}"
        for f in "$LOG_DIR/extract.out.log" "$LOG_DIR/extract.err.log"; do
            echo "=== ${f##*/} ==="
            tail -n "$n" "$f" 2>/dev/null || echo "(none yet)"
        done
        ;;
    *)
        echo "Usage: $0 {install|uninstall|run-now|trigger [ARG]|status|logs [N]}" >&2
        exit 1
        ;;
esac
