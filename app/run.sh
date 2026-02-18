#!/usr/bin/env bash
# Start the TEE Hub web app locally.
#
# Usage:
#   ./app/run.sh              # Start on port 5001
#   ./app/run.sh --port 8080  # Custom port
#   ./app/run.sh --debug      # Debug mode (auto-reload on file changes)

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q -r "$APP_DIR/requirements.txt"
    echo ""
fi

# Run the server
exec "$VENV_DIR/bin/python" "$APP_DIR/server.py" "$@"

