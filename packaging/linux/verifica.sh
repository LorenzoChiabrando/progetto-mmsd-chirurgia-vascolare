#!/usr/bin/env bash
# Prova ./ScadenzarioCV in container puliti di più distribuzioni. Ogni container ha solo ciò
# che un desktop Linux ha sempre (X11, font, OpenGL): il resto deve essere nell'eseguibile.
#
#   packaging/linux/verifica.sh                 # tutte le distribuzioni, X11 e Wayland
#   packaging/linux/verifica.sh ubuntu:22.04    # una sola, su X11
set -uo pipefail

QUI="$(cd "$(dirname "$0")" && pwd)"
RADICE="$(cd "$QUI/../.." && pwd)"
IMMAGINI=("$@")
WAYLAND=0
if [ ${#IMMAGINI[@]} -eq 0 ]; then
    IMMAGINI=(ubuntu:20.04 ubuntu:22.04 ubuntu:24.04 debian:12 fedora:42)
    WAYLAND=1
fi

APT="apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
--no-install-recommends xvfb x11-utils libx11-6 libx11-xcb1 libxcb1 libfontconfig1 \
libfreetype6 libgl1 libegl1 fonts-dejavu-core >/dev/null"
DNF="dnf -y -q install xorg-x11-server-Xvfb xwininfo libX11 libX11-xcb libxcb fontconfig \
freetype libglvnd-glx libglvnd-egl dejavu-sans-fonts >/dev/null"

esito=0
for immagine in "${IMMAGINI[@]}"; do
    case "$immagine" in
        fedora*|almalinux*|rockylinux*) preparazione="$DNF" ;;
        *) preparazione="$APT" ;;
    esac
    if risultato="$(docker run --rm -v "$RADICE:/repo:ro" "$immagine" \
        sh -c "$preparazione && sh /repo/packaging/linux/prova_avvio.sh" 2>&1)"; then
        riuscita=1
    else
        riuscita=0
        esito=1
    fi
    glibc="$(docker run --rm "$immagine" sh -c 'ldd --version | head -1 | grep -o "[0-9.]*$"')"
    printf '%-14s glibc %-5s %s\n' "$immagine" "$glibc" "$(echo "$risultato" | tail -1)"
    [ "$riuscita" -eq 1 ] || echo "$risultato" | tail -20
done

if [ "$WAYLAND" -eq 1 ]; then
    if risultato="$(docker run --rm -v "$RADICE:/repo:ro" ubuntu:24.04 \
        sh /repo/packaging/linux/prova_wayland.sh 2>&1)"; then
        printf '%-26s %s\n' "ubuntu:24.04 Wayland" "$(echo "$risultato" | tail -1)"
    else
        esito=1
        printf '%-26s %s\n' "ubuntu:24.04 Wayland" "KO"
        echo "$risultato" | tail -20
    fi
fi
exit "$esito"
