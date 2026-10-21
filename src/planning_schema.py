"""Versioned JSON conventions shared by the platform and optimization mapper."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

OPTIMIZATION_KEY = "modello_ottimizzazione"
SCHEMA_VERSION = 1

PAPER_CATEGORIES = ("I'", "I''", "I'''")
DEFAULT_MAX_WAIT_DAYS = {"Alta": 30, "Media": 60, "Bassa": 180}
DEFAULT_COMPLEXITIES_BY_TRAINING_LEVEL = {
    "Junior": ("Bassa", "Media", "Alta"),
    "Intermediate": ("Media", "Alta"),
    "Senior": ("Alta",),
}

_DEFAULT_ROOMS: dict[str, dict[str, Any]] = {
    "OR-1": {
        "riga_turno": "Sala Op. I",
        "ruolo_specializzando": "OR I",
        "capacita_minuti": 600,
    },
    "OR-2": {
        "riga_turno": "Sala Op. II",
        "ruolo_specializzando": "OR II",
        "capacita_minuti": 600,
    },
}


def default_patient_optimization(urgency: str) -> dict[str, Any]:
    """Return v1 fields; unclassified urgency leaves the maximum waiting time unset."""

    max_wait = DEFAULT_MAX_WAIT_DAYS.get(urgency)
    if max_wait is None and urgency != "Da classificare":
        raise ValueError(f"unsupported urgency label: {urgency!r}")
    return {
        "versione_schema": SCHEMA_VERSION,
        "categoria_paper": "I'",
        "attesa_massima_giorni": max_wait,
    }


def default_schedule_optimization() -> dict[str, Any]:
    """Return the v1 two-room configuration for one monthly schedule JSON."""

    return {
        "versione_schema": SCHEMA_VERSION,
        "sale_operatorie": deepcopy(_DEFAULT_ROOMS),
        "capacita_sessioni": {},
    }
