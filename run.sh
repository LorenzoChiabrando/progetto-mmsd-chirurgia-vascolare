#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/source"
VENV="$SOURCE/venv"

if [ ! -d "$VENV" ]; then
    echo "[setup] Creating virtual environment..."
    python3 -m venv "$VENV"
    echo "[setup] Installing dependencies..."
    "$VENV/bin/pip" install -q -r "$SOURCE/requirements.txt"
    echo "[setup] Ready."
fi

cd "$SOURCE"
exec "$VENV/bin/python3" main.py
