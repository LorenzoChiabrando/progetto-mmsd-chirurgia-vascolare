"""Standard output ed errori per l'avvio senza console su Windows.

Senza console (pythonw.exe da run.bat, oppure ScadenzarioCV.exe compilato senza console)
il processo non ha stdout e stderr: sys.stdout e sys.stderr sono None e i descrittori 1 e
2 non esistono. Quando avvia HiGHS, Pyomo cattura l'output del solver duplicando proprio
quei descrittori e la pianificazione fallisce ("'NoneType' object has no attribute
'flush'"). Qui, prima che parta l'applicazione, si collegano a os.devnull.

Si usa come runtime hook di PyInstaller (ScadenzarioCV.spec) e da avvio.py (run.bat).
Con una console vera non cambia nulla.
"""

import os
import sys


def collega_flussi_mancanti() -> None:
    for fd, nome in ((1, "stdout"), (2, "stderr")):
        if getattr(sys, nome) is not None:
            continue
        try:
            os.fstat(fd)
        except OSError:
            nullo = os.open(os.devnull, os.O_RDWR)
            if nullo != fd:
                os.dup2(nullo, fd)
                os.close(nullo)
        setattr(sys, nome, open(fd, "w", encoding="utf-8", errors="replace", closefd=False))


collega_flussi_mancanti()
