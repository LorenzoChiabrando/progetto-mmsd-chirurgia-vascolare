"""Apertura di un file con il programma predefinito del sistema (es. il PDF esportato)."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QUrl
from PySide6.QtGui import QDesktopServices

_ORIGINAL_SUFFIX = "_ORIG"


def external_environment(
    environ: Mapping[str, str], bundle_directory: str | None
) -> dict[str, str]:
    """Variabili d'ambiente per un programma del sistema avviato dall'app.

    L'eseguibile di PyInstaller fa puntare alcune variabili (``LD_LIBRARY_PATH`` e
    simili) alla propria cartella temporanea ``bundle_directory``: ereditate, farebbero
    caricare al visualizzatore PDF le librerie Qt dell'app invece delle sue, e il
    programma non partirebbe. Ogni variabile di questo tipo torna al valore salvato in
    ``<NOME>_ORIG`` oppure viene tolta. Senza ``bundle_directory`` (avvio da sorgente)
    l'ambiente resta com'è.
    """

    result = dict(environ)
    if not bundle_directory:
        return result
    for name, value in environ.items():
        if name.endswith(_ORIGINAL_SUFFIX) or bundle_directory not in value:
            continue
        original = environ.get(name + _ORIGINAL_SUFFIX)
        if original:
            result[name] = original
        else:
            result.pop(name, None)
    for name in environ:
        if name.endswith(_ORIGINAL_SUFFIX) and name[: -len(_ORIGINAL_SUFFIX)] in environ:
            result.pop(name, None)
    return result


def _start_detached(program: str, arguments: list[str]) -> bool:
    process = QProcess()
    process.setProgram(program)
    process.setArguments(arguments)
    environment = QProcessEnvironment()
    for name, value in external_environment(
        os.environ, getattr(sys, "_MEIPASS", None)
    ).items():
        environment.insert(name, value)
    process.setProcessEnvironment(environment)
    # Secondo la versione di PySide6 restituisce l'esito o la coppia (esito, pid).
    started = process.startDetached()
    if isinstance(started, tuple):
        started = started[0]
    return bool(started)


def open_in_default_app(path: str | Path) -> None:
    """Apre ``path`` con il programma che il sistema associa a quel tipo di file.

    Su Windows lo apre la shell; su Linux ``xdg-open``, con l'ambiente del sistema e
    non quello dell'eseguibile (vedi :func:`external_environment`).

    Raises:
        FileNotFoundError: se il file non esiste più.
        OSError: se il sistema non riesce ad avviare nessun programma.
    """

    target = Path(path).resolve()
    if not target.is_file():
        raise FileNotFoundError(f"Il file «{target}» non esiste più.")
    if sys.platform.startswith("win"):
        os.startfile(target)  # type: ignore[attr-defined]  # solo su Windows
        return
    program = "open" if sys.platform == "darwin" else "xdg-open"
    if _start_detached(program, [str(target)]):
        return
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
        raise OSError(
            "Nessun programma del sistema ha aperto il file. "
            f"Puoi aprirlo dalla cartella «{target.parent}»."
        )
