# PyInstaller: ScadenzarioCV.exe in un unico file. Si compila con packaging\windows\build.bat.
import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

QUI = Path(SPECPATH).resolve()
SOURCE = QUI.parents[1] / "source"

# highspy (come numpy) porta msvcp140-<hash>.dll in highspy.libs e all'import aggiunge solo
# quella cartella alla ricerca delle DLL. PyInstaller tiene una sola copia della DLL, in
# numpy.libs: senza questa riga _core.pyd non si carica e il solver risulta non disponibile.
HIGHSPY_LIBS = Path(importlib.util.find_spec("highspy").origin).parents[1] / "highspy.libs"

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
    binaries=[(str(dll), "highspy.libs") for dll in HIGHSPY_LIBS.glob("*.dll")],
    # Senza console stdout e stderr non esistono e Pyomo non può avviare HiGHS.
    runtime_hooks=[str(QUI / "flussi_standard.py")],
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
