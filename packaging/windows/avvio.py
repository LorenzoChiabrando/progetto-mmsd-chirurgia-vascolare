"""Avvio da sorgente senza console, usato da run.bat con pythonw.exe.

Collega stdout e stderr mancanti (vedi flussi_standard.py), poi esegue source/main.py
come se fosse stato lanciato direttamente.
"""

import runpy
import sys
from pathlib import Path

import flussi_standard  # noqa: F401  (stessa cartella di questo file)

SOURCE = Path(__file__).resolve().parents[2] / "source"
MAIN = SOURCE / "main.py"

sys.path[0] = str(SOURCE)
sys.argv[0] = str(MAIN)
runpy.run_path(str(MAIN), run_name="__main__")
