from __future__ import annotations

import calendar
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta

ROW_DISPLAY_LABELS: Mapping[str, str] = {
    "Reparto I": "I Reperibilità",
    "Reparto II": "II Reperibilità",
}

ROW_COMPACT_LABELS: Mapping[str, str] = {
    "Reparto I": "I Rep",
    "Reparto II": "II Rep",
}


def row_display_label(row_key: str, *, compact: bool = False) -> str:
    """Restituisce l'etichetta mostrata senza cambiare la chiave JSON."""

    if compact:
        return ROW_COMPACT_LABELS.get(row_key, ROW_DISPLAY_LABELS.get(row_key, row_key))
    return ROW_DISPLAY_LABELS.get(row_key, row_key)


def person_initials(value: str) -> str:
    """Ricava le iniziali da un nome."""

    stripped = value.strip()
    if not stripped or stripped == "-":
        return stripped
    parts = [part for part in re.split(r"\s+", stripped) if part]
    initials = "".join(part[0].upper() for part in parts if part[0].isalnum())
    return initials[:3] or stripped[:3]


def resolve_resident_name(value: str, residents: Iterable[Mapping[str, object]]) -> str:
    """Ricava il nome completo dal formato ``Cognome N.``."""

    target = value.strip().casefold()
    if not target or target == "-":
        return value
    for resident in residents:
        surname = str(resident.get("cognome", "")).strip()
        name = str(resident.get("nome", "")).strip()
        if not surname or not name:
            continue
        abbreviated = f"{surname} {name[0]}."
        if abbreviated.casefold() == target:
            return f"{surname} {name}"
    return value


def resident_legend(residents: Iterable[Mapping[str, object]]) -> dict[str, str]:
    """Prepara la legenda iniziali-nome."""

    legend: dict[str, str] = {}
    for resident in sorted(
        residents,
        key=lambda item: (
            str(item.get("cognome", "")).casefold(),
            str(item.get("nome", "")).casefold(),
        ),
    ):
        surname = str(resident.get("cognome", "")).strip()
        name = str(resident.get("nome", "")).strip()
        if not surname or not name:
            continue
        initials = person_initials(f"{surname} {name}")
        full_name = f"{surname} {name}"
        if initials in legend and legend[initials] != full_name:
            legend[initials] = f"{legend[initials]} / {full_name}"
        else:
            legend[initials] = full_name
    return legend


def month_dates(year: int, month: int) -> tuple[date, ...]:
    """Restituisce tutte le date del mese."""

    _, number_of_days = calendar.monthrange(year, month)
    return tuple(date(year, month, day) for day in range(1, number_of_days + 1))


def month_weeks(year: int, month: int, *, days: int = 7) -> tuple[tuple[date, ...], ...]:
    """Settimane intere del mese, da lunedì, con i primi ``days`` giorni (7 o 5 feriali).

    Un mese comprende le settimane che hanno almeno un suo giorno feriale; quelle a
    cavallo di due mesi restano intere, con i giorni del mese vicino, e compaiono in
    entrambi i mesi. Così non nascono settimane di un giorno solo: domenica 1 novembre
    2026 appartiene alla settimana di ottobre, non a una «settimana 1» di novembre.
    """

    if not 1 <= days <= 7:
        raise ValueError("Una settimana ha da 1 a 7 giorni.")
    dates = month_dates(year, month)
    first_workday = next(day for day in dates if day.weekday() < 5)
    last_workday = next(day for day in reversed(dates) if day.weekday() < 5)
    monday = first_workday - timedelta(days=first_workday.weekday())
    weeks: list[tuple[date, ...]] = []
    while monday <= last_workday:
        weeks.append(tuple(monday + timedelta(days=offset) for offset in range(days)))
        monday += timedelta(weeks=1)
    return tuple(weeks)


def fit_resident_label(label: str, fits: Callable[[str], bool]) -> str:
    """Sceglie il testo più completo che entra nella cella.

    Prova nell'ordine ``Cognome N.``, il solo cognome e infine le iniziali.
    """

    tokens = label.split()
    surname = " ".join(tokens[:-1]) if len(tokens) > 1 and tokens[-1].endswith(".") else label
    for candidate in dict.fromkeys((label, surname)):
        if fits(candidate):
            return candidate
    return person_initials(label)


ROLE_CELL_COLORS: Mapping[str, str] = {
    "Tipo Guardia": "#e0e7ff",
    "Reparto I": "#e0e7ff",
    "Reparto II": "#e0e7ff",
    "Sala Op. I": "#dcfce7",
    "Sala Op. II": "#dcfce7",
    "Giro Visite": "#fef9c3",
    "Day Hospital": "#fae8ff",
    "Day Surgery": "#fae8ff",
}
"""Sfondo delle celle per ruolo, usato a schermo e nel PDF."""

ROLE_HEADER_COLORS: Mapping[str, str] = {
    "Giorno": "#e2e8f0",
    "Tipo Guardia": "#c7d2fe",
    "Reparto I": "#c7d2fe",
    "Reparto II": "#c7d2fe",
    "Sala Op. I": "#bbf7d0",
    "Sala Op. II": "#bbf7d0",
    "Giro Visite": "#fde68a",
    "Day Hospital": "#e9d5ff",
    "Day Surgery": "#e9d5ff",
}
"""Colore più intenso del ruolo: intestazioni di riga e celle della vista per specializzando."""

ROOM_COLORS: Mapping[str, Mapping[str, str]] = {
    "OR-1": {
        "intestazione": "#bae6fd", "etichetta": "#e0f2fe", "sfondo": "#f0f9ff",
        "accento": "#0284c7",
    },
    "OR-2": {
        "intestazione": "#99f6e4", "etichetta": "#ccfbf1", "sfondo": "#f0fdfa",
        "accento": "#0d9488",
    },
}
"""Colori delle sale operatorie nel calendario a blocchi e nel PDF: intestazione del
blocco, etichette delle sue righe, sfondo delle celle libere, accento delle schede."""

GUARD_TEXT_COLORS: Mapping[str, str] = {"118": "#b91c1c", "PI": "#c2410c", "L": "#15803d"}
