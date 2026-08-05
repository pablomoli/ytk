#!/bin/sh
# Reinstall the ytk tool and restart the hub after a merge to master.
# The hub restart is skipped while an ingest is running — killing the worker
# mid-item is exactly the silent-loss class E5 measured (#148).
set -e
cd "$(dirname "$0")/.."

uv tool install --reinstall . >/dev/null 2>&1
echo "post-merge: ytk + ytk-mcp reinstalled"

status=$(curl -s --max-time 5 http://127.0.0.1:6969/api/ingest/status 2>/dev/null || echo "")
case "$status" in
*'"running":true'* | *'"running": true'*)
    echo "post-merge: ingest running — hub restart skipped."
    echo "post-merge: run when idle: launchctl kickstart -k gui/501/com.ytk.hub"
    ;;
*)
    launchctl kickstart -k gui/501/com.ytk.hub
    echo "post-merge: hub restarted"
    ;;
esac
