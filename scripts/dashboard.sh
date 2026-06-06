#!/usr/bin/env bash
#
# Render the launchd status dashboard by injecting live status.py JSON into the
# dashboard.html template. The result is a self-contained HTML file you can open,
# send to your phone, or surface as a Cowork live artifact.
#
#     scripts/dashboard.sh                 # -> logs/dashboard.html
#     scripts/dashboard.sh /tmp/dash.html  # custom output path
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO/logs/dashboard.html}"
mkdir -p "$(dirname "$OUT")"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
python3 "$REPO/scripts/status.py" > "$TMP"

python3 - "$REPO/scripts/dashboard.html" "$TMP" "$OUT" <<'PY'
import sys, pathlib
template, datafile, out = sys.argv[1], sys.argv[2], sys.argv[3]
data = pathlib.Path(datafile).read_text().strip()
html = pathlib.Path(template).read_text().replace("__STATUS_JSON__", data)
pathlib.Path(out).write_text(html)
PY

echo "Wrote $OUT"
