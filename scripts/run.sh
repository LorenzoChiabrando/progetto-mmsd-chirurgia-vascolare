#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

VENV_DIR="$PROJECT_DIR/venv"
PYTHON="$VENV_DIR/bin/python3"
PIP="$VENV_DIR/bin/pip"

# Ricrea il venv se mancante o rotto
if [ ! -f "$PYTHON" ]; then
    echo "Creazione/riparazione virtual environment..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# Assicura pip disponibile nel venv
if [ ! -f "$PIP" ]; then
    "$PYTHON" -m ensurepip --upgrade
fi

echo "Installazione dipendenze..."
"$PIP" install -r requirements.txt --quiet

echo "Avvio applicazione..."
"$PYTHON" main.py
