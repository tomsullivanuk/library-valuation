#!/bin/bash
# Double-click to start the library independently of this launcher window.
set -e
cd -- "$(dirname -- "$0")"
if [ -f data/production_moved.json ]; then
    if ! /bin/launchctl kickstart "gui/$(id -u)/local.library-valuation.tunnel"; then
        echo 'The private Mac Mini connection is not installed. Please ask for help reconnecting.'
        read -r -p 'Press Return to close.'
        exit 1
    fi
    /usr/bin/open 'http://127.0.0.1:8765'
    echo 'Opened the Mac Mini library through your private connection.'
    exit 0
fi
if [ ! -x .venv/bin/python ]; then
    echo 'The project Python environment is missing. Please ask for help setting it up.'
    read -r -p 'Press Return to close.'
    exit 1
fi
if ! .venv/bin/python -m valuation.workspace_service --background; then
    read -r -p 'The library could not start. Press Return to close.'
    exit 1
fi
/usr/bin/open 'http://127.0.0.1:8765'
echo 'The library is running in the background. You can close this window.'
