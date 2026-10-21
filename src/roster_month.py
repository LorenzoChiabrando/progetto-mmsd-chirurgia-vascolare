"""Fotografia di un mese dello scadenzario, indipendente da Qt e dai file JSON.

È l'unico dato da cui partono la vista per attività, la vista per specializzando e
l'export PDF.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from types import MappingProxyType

from src.calendar_presentation import resolve_resident_name
from src.roster_assignment import ACTIVE_RESIDENT_STATUS, resident_label

GUARD_ROLE = "Tipo Guardia"
WARD_ROUND_ROLE = "Giro Visite"
ROLE_KEYS: tuple[str, ...] = (
    GUARD_ROLE,
    "Reparto I",
    "Reparto II",
    "Sala Op. I",
    "Sala Op. II",
    WARD_ROUND_ROLE,
    "Day Hospital",
    "Day Surgery",
)
"""Ruoli dello scadenzario nell'ordine delle righe; sono le chiavi dei file JSON."""


@dataclass(frozen=True, slots=True)
class RosterMonth:
    """Assegnazioni di un mese: ``values[(giorno, ruolo)]`` per i soli giorni feriali.

    ``state`` è lo stato del mese (``BOZZA`` o ``CONVALIDATO``). Il giro visite è già
    risolto per ciascun giorno feriale della propria settimana.
    """

    year: int
    month: int
    state: str
    values: Mapping[tuple[date, str], str] = field(default_factory=dict)

    @property
    def dates(self) -> tuple[date, ...]:
        _, days = calendar.monthrange(self.year, self.month)
        return tuple(date(self.year, self.month, day) for day in range(1, days + 1))

    @staticmethod
    def is_workday(day: date) -> bool:
        return day.weekday() < 5

    def value(self, day: date, role: str) -> str:
        """Valore della cella; stringa vuota se non assegnata o se il giorno è festivo."""

        return self.values.get((day, role), "")


def load_roster_month(data_manager, year: int, month: int) -> RosterMonth:
    """Legge il mese dal ``DataManager`` dello scadenzario (nessuna scrittura)."""

    _, days = calendar.monthrange(year, month)
    values: dict[tuple[date, str], str] = {}
    for day in (date(year, month, number) for number in range(1, days + 1)):
        if not RosterMonth.is_workday(day):
            continue
        monday = day - timedelta(days=day.weekday())
        for role in ROLE_KEYS:
            if role == WARD_ROUND_ROLE:
                raw = data_manager.get_giro_visite_settimana(monday.isoformat(), year, month)
            else:
                raw = data_manager.get_valore_cella(day.isoformat(), role)
            if isinstance(raw, str) and raw.strip():
                values[day, role] = raw.strip()
    return RosterMonth(
        year=year,
        month=month,
        state=data_manager.get_stato_mese(year, month),
        values=MappingProxyType(values),
    )


RESIDENT_ROLE_CODES: Mapping[str, str] = MappingProxyType(
    {
        "Reparto I": "R1",
        "Reparto II": "R2",
        "Sala Op. I": "S1",
        "Sala Op. II": "S2",
        "Giro Visite": "GV",
        "Day Hospital": "DH",
        "Day Surgery": "DS",
    }
)
"""Sigle dei ruoli nella vista per specializzando (il tipo di guardia non è una persona)."""


@dataclass(frozen=True, slots=True)
class ResidentRow:
    """Turni di uno specializzando nel mese: un codice per giorno (vuoto se libero)."""

    label: str
    full_name: str
    codes: tuple[str, ...]
    total: int


def resident_rows(
    roster: RosterMonth, residents: Iterable[Mapping[str, object]]
) -> tuple[ResidentRow, ...]:
    """Righe della vista per specializzando, ordinate per sigla.

    Comprende gli specializzandi in sede e chiunque compaia nel mese (anche se non più
    in sede). Più ruoli nello stesso giorno sono uniti con ``+`` e contano tutti.
    """

    people = tuple(residents)
    labels: dict[str, str] = {}
    for resident in people:
        if resident.get("stato") == ACTIVE_RESIDENT_STATUS:
            label = resident_label(resident)
            labels.setdefault(label.casefold(), label)
    for (_day, role), value in roster.values.items():
        if role in RESIDENT_ROLE_CODES:
            labels.setdefault(value.casefold(), value)

    rows: list[ResidentRow] = []
    for key, label in sorted(labels.items(), key=lambda item: item[1].casefold()):
        codes: list[str] = []
        total = 0
        for day in roster.dates:
            day_codes = [
                RESIDENT_ROLE_CODES[role]
                for role in ROLE_KEYS
                if role in RESIDENT_ROLE_CODES and roster.value(day, role).casefold() == key
            ]
            total += len(day_codes)
            codes.append("+".join(day_codes))
        rows.append(
            ResidentRow(
                label=label,
                full_name=resolve_resident_name(label, people),
                codes=tuple(codes),
                total=total,
            )
        )
    return tuple(rows)
