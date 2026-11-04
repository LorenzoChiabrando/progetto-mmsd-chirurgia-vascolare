"""Piano originale del modello di una settimana, salvato a parte rispetto al calendario.

Il calendario (``sale_operatorie/AAAA-MM.json``) contiene il piano attuale, con le
eventuali modifiche manuali; ``sale_operatorie/piani_modello/<lunedì>.json`` conserva il
piano come l'ha prodotto l'ottimizzazione, per poterci tornare in qualsiasi momento.
Esiste solo per il Previsto: il modello non pianifica l'Effettivo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from src.models.json_files import read_json_object

CARTELLA_PIANI_MODELLO = "piani_modello"
VERSIONE_SCHEMA = 1


def percorso_piano_modello(cartella_sale: str | Path, lunedi: date) -> Path:
    return Path(cartella_sale) / CARTELLA_PIANI_MODELLO / f"{lunedi.isoformat()}.json"


def crea_piano_modello(
    lunedi: date, operazioni_per_giorno: Mapping[date, Iterable[Mapping[str, Any]]]
) -> dict[str, Any]:
    """Contenuto del file: gli interventi di ogni giorno, come li ha scritti il modello."""
    return {
        "versione_schema": VERSIONE_SCHEMA,
        "settimana": lunedi.isoformat(),
        "giorni": {
            giorno.isoformat(): {"operazioni": [deepcopy(dict(op)) for op in operazioni]}
            for giorno, operazioni in sorted(operazioni_per_giorno.items())
        },
    }


def leggi_piano_modello(cartella_sale: str | Path, lunedi: date) -> dict[str, Any] | None:
    """Il piano del modello della settimana, oppure ``None`` se non c'è.

    Un file danneggiato solleva ``CorruptedDataError``, come per gli altri dati.
    """
    percorso = percorso_piano_modello(cartella_sale, lunedi)
    if not percorso.is_file():
        return None
    piano = read_json_object(percorso)
    return piano if isinstance(piano.get("giorni"), dict) else None


def operazioni_del_piano(piano: Mapping[str, Any]) -> dict[date, list[dict[str, Any]]]:
    return {
        date.fromisoformat(giorno): list(dati.get("operazioni", []))
        for giorno, dati in piano.get("giorni", {}).items()
    }
