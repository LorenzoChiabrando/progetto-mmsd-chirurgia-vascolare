"""Lettura e scrittura dei file JSON dei dati, condivise dai data manager.

La scrittura è atomica: un salvataggio interrotto lascia il file precedente intatto.
La lettura distingue un file danneggiato da uno assente, così un file illeggibile non
viene mai scambiato per dati vuoti e poi sovrascritto.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.models.patient_plan_state import write_json_batch

JsonObject = dict[str, Any]


class CorruptedDataError(ValueError):
    """Un file dei dati esiste ma non contiene un oggetto JSON valido.

    Il messaggio, in italiano, indica solo cartella e nome del file: mai il contenuto
    né il percorso completo. Il percorso è disponibile in :attr:`path`.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"Il file {path.parent.name}/{path.name} è danneggiato o incompleto. "
            "Ripristinalo da una copia di sicurezza oppure rigenera i dati demo "
            "con scripts/reset_demo_data.py."
        )


def read_json_object(path: str | Path) -> JsonObject:
    """Legge un file JSON in UTF-8 che deve contenere un oggetto.

    Raises:
        CorruptedDataError: file troncato, vuoto, non UTF-8 o non un oggetto JSON.
        OSError: file assente o non leggibile (non è considerato danneggiato).
    """

    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CorruptedDataError(path) from error
    if not isinstance(data, dict):
        raise CorruptedDataError(path)
    return data


def write_json_atomic(path: str | Path, data: Mapping[str, Any]) -> None:
    """Salva ``data`` in ``path`` (indentazione 4, come i file esistenti) in modo atomico.

    Raises:
        OSError: scrittura non riuscita; il file precedente resta invariato.
        TypeError, ValueError: ``data`` non è serializzabile; nessun file viene toccato.
    """

    write_json_batch({Path(path): dict(data)})
