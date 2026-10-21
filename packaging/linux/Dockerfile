# Ambiente di compilazione di ScadenzarioCV: AlmaLinux 8, glibc 2.28.
# Un eseguibile Linux parte solo dove la glibc è almeno quella di compilazione: con 2.28
# gira su Ubuntu 20.04+, Debian 10+, RHEL/Alma/Rocky 8+ e Fedora recenti.
FROM almalinux:8

# Librerie che Qt usa su X11 e Wayland: PyInstaller le include nell'eseguibile, così
# non servono sul sistema di chi lo avvia (xcb-util-cursor arriva da EPEL).
RUN dnf -y install epel-release \
    && dnf -y install \
        python3.11 python3.11-devel binutils \
        glib2 dbus-libs libxkbcommon libxkbcommon-x11 \
        libX11 libX11-xcb libxcb xcb-util xcb-util-cursor xcb-util-image \
        xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
        libwayland-client libwayland-cursor libwayland-egl \
        fontconfig freetype libglvnd-egl libglvnd-opengl \
    && dnf clean all

COPY requirements.txt /tmp/requirements.txt
RUN python3.11 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
        pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8
ENV PATH=/opt/venv/bin:$PATH
