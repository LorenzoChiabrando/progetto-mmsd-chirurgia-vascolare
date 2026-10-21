# PyInstaller: ScadenzarioCV in un unico file. Si compila con packaging/linux/build.sh.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

SOURCE = Path(SPECPATH).resolve().parents[1] / "source"

# Presenti su ogni desktop Linux e legate alla macchina (driver grafici, configurazione
# dei font, server X): si usano quelle del sistema, non le copie del container.
DAL_SISTEMA = (
    "libGL.", "libEGL.", "libGLX", "libGLdispatch.", "libOpenGL.", "libdrm.", "libgbm.",
    "libfontconfig.", "libfreetype.", "libX11.", "libX11-xcb.", "libxcb.",
)
# Plugin Qt che l'app non usa e le librerie che si portano dietro: tema GTK (tutto GTK 3;
# l'app usa lo stile Fusion), tastiera virtuale QML (QtQuick e QtQml), anteprima PDF fra i
# formati immagine (QtPdf; l'export usa QPdfWriter di QtGui), schermi embedded e VNC,
# TLS e stato della rete (l'app non usa la rete; il backend TLS vorrebbe OpenSSL 3).
NON_USATI = (
    "libqgtk3.so", "libqtvirtualkeyboardplugin.so", "libqpdf.so",
    "libqeglfs.so", "libqlinuxfb.so", "libqminimal.so", "libqminimalegl.so",
    "libqvkkhrdisplay.so", "libqvnc.so",
    "libQt6Quick", "libQt6Qml", "libQt6VirtualKeyboard", "libQt6Pdf",
)
CARTELLE_NON_USATE = (
    "/plugins/egldeviceintegrations/", "/plugins/generic/", "/plugins/tls/",
    "/plugins/networkinformation/",
)

a = Analysis(
    [str(SOURCE / "main.py")],
    pathex=[str(SOURCE)],
    datas=[(str(SOURCE / "asset"), "asset"), (str(SOURCE / "mock_data"), "mock_data")],
    # APPSI importa highspy solo quando serve: l'analisi statica non lo vede.
    hiddenimports=[
        "highspy",
        *collect_submodules("pyomo.contrib.appsi", filter=lambda name: ".tests" not in name),
    ],
    excludes=["tkinter", "pytest"],
)
a.binaries = [
    entry
    for entry in a.binaries
    if not Path(entry[0]).name.startswith(DAL_SISTEMA + NON_USATI)
    and not any(cartella in f"/{entry[0]}" for cartella in CARTELLE_NON_USATE)
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ScadenzarioCV",
    strip=False,
    upx=False,
    console=False,
)
