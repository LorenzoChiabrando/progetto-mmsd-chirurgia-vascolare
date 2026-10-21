#!/bin/sh
# Eseguito da verifica.sh dentro un container pulito: avvia ./ScadenzarioCV su un display
# X11 virtuale e controlla che la finestra compaia e che i dati demo vengano creati.
set -eu

export HOME=/tmp/utente DISPLAY=:99
mkdir -p "$HOME"
Xvfb :99 -screen 0 1600x900x24 >/dev/null 2>&1 &
sleep 2

/repo/ScadenzarioCV >/tmp/app.log 2>&1 &
APP=$!
secondi=0
while [ "$secondi" -lt 60 ]; do
    if xwininfo -root -tree 2>/dev/null | grep -q "MMSD CV"; then
        kill "$APP" 2>/dev/null || true
        if [ ! -d "$HOME/.local/share/ScadenzarioCV/v2/dati/scadenzario" ]; then
            echo "KO: finestra aperta ma dati demo non creati"
            exit 1
        fi
        echo "OK: finestra aperta in ${secondi}s, dati in ~/.local/share/ScadenzarioCV/v2"
        exit 0
    fi
    kill -0 "$APP" 2>/dev/null || break
    sleep 1
    secondi=$((secondi + 1))
done
echo "KO: nessuna finestra"
cat /tmp/app.log
exit 1
