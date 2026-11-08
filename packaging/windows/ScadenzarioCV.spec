# PyInstaller: ScadenzarioCV.exe in un unico file. Si compila con packaging\windows\build.bat.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

SOURCE = Path(SPECPATH).resolve().parents[1] / "source"

# Plugin Qt che l'app non usa e le librerie che si portano dietro: tastiera virtuale QML
# (QtQuick e QtQml), anteprima PDF fra i formati immagine (QtPdf; l'export usa QPdfWriter
# di QtGui), TLS e stato della rete (l'app non usa la rete).
NON_USATI = (
    "qtvirtualkeyboardplugin.dll", "qpdf.dll",
    "Qt6Quick", "Qt6Qml", "Qt6VirtualKeyboard", "Qt6Pdf",
)
CARTELLE_NON_USATE = (
    "/plugins/generic/", "/plugins/tls/", "/plugins/networkinformation/",
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
    if not Path(entry[0]).name.startswith(NON_USATI)
    and not any(cartella in "/" + entry[0].replace("\\", "/") for cartella in CARTELLE_NON_USATE)
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
