#!/usr/bin/env bash
# Avvio da sorgente: crea (o ripara) l'ambiente virtuale in source/venv, installa le
# dipendenze e avvia l'applicazione. Non usa mai il Python di sistema né sudo.
set -euo pipefail

QUI="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$QUI/source"
VENV="$SOURCE/venv"

errore() {
    echo "ERRORE: $*" >&2
    exit 1
}

command -v python3 >/dev/null \
    || errore "python3 non trovato. Su Ubuntu/Debian: sudo apt install python3 python3-venv"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || errore "serve Python 3.10 o superiore (trovato $(python3 --version 2>&1))."

# Un ambiente creato a metà (per esempio senza il pacchetto python3-venv) non ha pip:
# va ricreato, altrimenti l'app partirebbe senza dipendenze.
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
    rm -rf "$VENV"
    echo "[setup] Creo l'ambiente virtuale in source/venv..."
    if ! python3 -m venv "$VENV"; then
        rm -rf "$VENV"
        errore "manca il modulo venv di Python. Su Ubuntu/Debian: sudo apt install python3-venv
       poi rilancia ./run.sh"
    fi
fi

# Le dipendenze si reinstallano se requirements.txt cambia o se non si importano.
TIMBRO="$VENV/.requirements.sha256"
ATTESO="$(sha256sum "$SOURCE/requirements.txt" | cut -d' ' -f1)"
if [ "$(cat "$TIMBRO" 2>/dev/null)" != "$ATTESO" ] \
    || ! "$VENV/bin/python" -c 'import PySide6, pyomo, highspy' 2>/dev/null; then
    echo "[setup] Installo le dipendenze (la prima volta può richiedere qualche minuto)..."
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet -r "$SOURCE/requirements.txt"
    echo "$ATTESO" >"$TIMBRO"
fi

# Su X11 Qt (dalla 6.5) richiede libxcb-cursor0, assente in alcune installazioni.
# L'eseguibile ./ScadenzarioCV la include già.
if [ -z "${WAYLAND_DISPLAY:-}" ] && command -v ldconfig >/dev/null \
    && ! ldconfig -p 2>/dev/null | grep -q 'libxcb-cursor\.so\.0'; then
    echo "ATTENZIONE: manca libxcb-cursor0, necessaria a Qt su X11." >&2
    echo "            Su Ubuntu/Debian: sudo apt install libxcb-cursor0" >&2
fi

cd "$SOURCE"
exec "$VENV/bin/python" main.py "$@"
