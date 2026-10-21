#!/usr/bin/env bash
# Ricompila ./ScadenzarioCV dentro un container AlmaLinux 8 (glibc 2.28). Serve Docker.
#
#   packaging/linux/build.sh
set -euo pipefail

QUI="$(cd "$(dirname "$0")" && pwd)"
RADICE="$(cd "$QUI/../.." && pwd)"
IMMAGINE="scadenzariocv-build:alma8"

docker build -t "$IMMAGINE" -f "$QUI/Dockerfile" "$RADICE/source"
docker run --rm \
    --user "$(id -u):$(id -g)" \
    -e PYINSTALLER_CONFIG_DIR=/tmp/pyinstaller \
    -v "$RADICE:/repo" -w /repo \
    "$IMMAGINE" \
    pyinstaller --noconfirm --clean \
        --distpath /repo/packaging/linux/dist --workpath /tmp/build \
        packaging/linux/ScadenzarioCV.spec

cp "$QUI/dist/ScadenzarioCV" "$RADICE/ScadenzarioCV"
chmod +x "$RADICE/ScadenzarioCV"
echo "Eseguibile aggiornato: $RADICE/ScadenzarioCV ($(du -h "$RADICE/ScadenzarioCV" | cut -f1))"
