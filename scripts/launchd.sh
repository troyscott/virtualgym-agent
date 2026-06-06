#!/usr/bin/env bash
#
# Manage the VirtuaGym extraction as an on-demand launchd job (LaunchAgent).
#
# The job has no timed trigger — it runs only when you kick it off, which is
# ideal for triggering from the phone via Cowork Dispatch. Dispatch runs
# locally, so it can call any of these subcommands:
#
#     scripts/launchd.sh install     # register the job with launchd
#     scripts/launchd.sh run-now     # trigger an extraction now
#     scripts/launchd.sh status      # show load state / last exit code / pid
#     scripts/launchd.sh logs [N]    # tail the last N log lines (default 40)
#     scripts/launchd.sh uninstall   # remove the job
#
set -euo pipefail

LABEL="com.troyscott.virtualgym.extract"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO/logs"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

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
        <string>last</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO</string>
    <key>RunAtLoad</key>
    <false/>
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
        gen_plist
        launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
        launchctl bootstrap "$DOMAIN" "$PLIST_DST"
        echo "Installed $LABEL (on-demand)."
        echo "Trigger it with: $0 run-now"
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
        echo "Usage: $0 {install|uninstall|run-now|status|logs [N]}" >&2
        exit 1
        ;;
esac
