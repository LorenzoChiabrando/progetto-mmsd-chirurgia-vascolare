#!/bin/sh
# Eseguito da verifica.sh in ubuntu:24.04: ./ScadenzarioCV su Wayland (Weston headless, niente X11).
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends weston libfontconfig1 libfreetype6 libgl1 \
    libegl1 fonts-dejavu-core >/dev/null
export HOME=/tmp/utente XDG_RUNTIME_DIR=/tmp/xdg
mkdir -p "$HOME" && mkdir -m 0700 "$XDG_RUNTIME_DIR"
weston --backend=headless --socket=wayland-test >/tmp/weston.log 2>&1 &
sleep 3
WAYLAND_DISPLAY=wayland-test QT_QPA_PLATFORM=wayland /repo/ScadenzarioCV >/tmp/app.log 2>&1 &
APP=$!
sleep 25
if kill -0 "$APP" 2>/dev/null && [ -d "$HOME/.local/share/ScadenzarioCV/v2/dati" ] \
    && ! grep -qi "could not\|failed\|error" /tmp/app.log; then
    echo "OK: app in esecuzione su Wayland da 25s, nessun errore Qt"
    kill "$APP"; exit 0
fi
echo "KO"; cat /tmp/app.log; tail -5 /tmp/weston.log; exit 1
