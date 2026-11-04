#!/bin/bash
# Double-click to open the saved-decision workspace on this computer.
set -e
cd -- "$(dirname -- "$0")"
workspace_url='http://127.0.0.1:8765'
if /usr/bin/curl --silent --fail --max-time 2 "$workspace_url/api/state" > /dev/null; then
    exec /usr/bin/open "$workspace_url"
fi
if [ ! -x .venv/bin/python ]; then
    echo 'The project Python environment is missing. Please ask for help setting it up.'
    read -r -p 'Press Return to close.'
    exit 1
fi
.venv/bin/python -m valuation.workspace_service &
workspace_pid=$!
trap 'kill "$workspace_pid" 2>/dev/null || true' EXIT
for attempt in {1..30}; do
    if /usr/bin/curl --silent --fail --max-time 1 "$workspace_url/api/state" > /dev/null; then
        /usr/bin/open "$workspace_url"
        echo 'Keep this window open while using the library. Your decisions are saved as you work.'
        break
    fi
    sleep 0.2
done
wait "$workspace_pid"
