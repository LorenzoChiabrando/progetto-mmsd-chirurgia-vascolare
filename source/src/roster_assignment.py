"""Regole di disponibilità per assegnare gli specializzandi nello scadenzario.

Il modulo non dipende da Qt: riceve i dati già letti dal data manager e
restituisce opzioni pronte per i dialog di assegnazione.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from src.calendar_presentation import row_display_label

GUARD_TYPE_ROLE = "Tipo Guardia"
WARD_ROUND_ROLE = "Giro Visite"
ACTIVE_RESIDENT_STATUS = "Molinette"

GUARD_TYPES: tuple[tuple[str, str], ...] = (
    ("118", "Emergenza territoriale"),
    ("PI", "Pronto Intervento"),
    ("L", "Liscia (routinaria)"),
)
"""Codici ammessi nella riga Tipo Guardia, con la descrizione mostrata all'utente."""

_WEEKDAY_LABELS = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
_NON_RESIDENT_ROLES = frozenset({GUARD_TYPE_ROLE, WARD_ROUND_ROLE})


@dataclass(frozen=True, slots=True)
class ResidentOption:
    """Uno specializzando proponibile per una cella dello scadenzario.

    ``label`` è il valore salvato nel JSON (``Cognome N.``); ``conflict`` contiene
    il motivo per cui non è assegnabile, oppure ``None`` se è disponibile.
    """

    label: str
    full_name: str
    level: str
    conflict: str | None = None

    @property
    def available(self) -> bool:
        return self.conflict is None

    def matches(self, query: str) -> bool:
        """Confronta la ricerca, senza distinguere maiuscole, con nome e sigla."""

        needle = query.strip().casefold()
        return not needle or needle in self.full_name.casefold() or needle in self.label.casefold()


def resident_label(resident: Mapping[str, object]) -> str:
    """Restituisce la sigla ``Cognome N.`` usata nei file dello scadenzario."""

    surname = str(resident.get("cognome", "")).strip()
    name = str(resident.get("nome", "")).strip()
    return f"{surname} {name[:1]}." if name else surname


def _assigned(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def busy_residents_for_day(
    daily: Mapping[str, object], role: str, ward_round: str = ""
) -> dict[str, str]:
    """Specializzandi già impegnati nel giorno, esclusa la cella ``role``.

    Restituisce ``{sigla.casefold(): motivo}``. Il giro visite della settimana
    conta come impegno per tutti gli altri ruoli.
    """

    busy: dict[str, str] = {}
    for other_role, value in daily.items():
        assigned = _assigned(value)
        if other_role == role or other_role in _NON_RESIDENT_ROLES or not assigned:
            continue
        busy.setdefault(assigned.casefold(), f"Già in {row_display_label(other_role)}")
    ward = _assigned(ward_round)
    if role != WARD_ROUND_ROLE and ward:
        busy.setdefault(ward.casefold(), "Già nel Giro Visite")
    return busy


def busy_residents_for_week(days: Mapping[date, Mapping[str, object]]) -> dict[str, str]:
    """Specializzandi impegnati in almeno un giorno della settimana del giro visite.

    Il motivo riporta il primo giorno, in ordine di data, in cui c'è il conflitto.
    """

    busy: dict[str, str] = {}
    for day in sorted(days):
        for role, value in days[day].items():
            assigned = _assigned(value)
            if role in _NON_RESIDENT_ROLES or not assigned:
                continue
            busy.setdefault(
                assigned.casefold(),
                f"Impegnato il {day:%d/%m} in {row_display_label(role)}",
            )
    return busy


def resident_options(
    residents: Iterable[Mapping[str, object]],
    busy: Mapping[str, str],
    current: str = "",
) -> tuple[ResidentOption, ...]:
    """Prepara le opzioni ordinate per cognome e nome.

    Considera solo gli specializzandi in sede (``stato == "Molinette"``). Il valore
    già assegnato alla cella resta sempre selezionabile; se non corrisponde a
    nessuno specializzando attivo viene proposto come prima opzione.
    """

    current_key = current.strip().casefold()
    active = sorted(
        (resident for resident in residents if resident.get("stato") == ACTIVE_RESIDENT_STATUS),
        key=lambda resident: (
            str(resident.get("cognome", "")).casefold(),
            str(resident.get("nome", "")).casefold(),
        ),
    )
    options: list[ResidentOption] = []
    for resident in active:
        label = resident_label(resident)
        key = label.casefold()
        full_name = f"{resident.get('cognome', '')} {resident.get('nome', '')}".strip()
        options.append(
            ResidentOption(
                label=label,
                full_name=full_name,
                level=str(resident.get("livello", "")),
                conflict=None if key == current_key else busy.get(key),
            )
        )
    if current_key and all(option.label.casefold() != current_key for option in options):
        options.insert(
            0, ResidentOption(label=current.strip(), full_name=current.strip(), level="")
        )
    return tuple(options)


def assignment_context(day: date, role: str) -> str:
    """Descrive giorno e ruolo nel sottotitolo del dialog.

    Per il giro visite descrive l'intera settimana lavorativa (lunedì–venerdì).
    """

    if role == WARD_ROUND_ROLE:
        monday = day - timedelta(days=day.weekday())
        friday = monday + timedelta(days=4)
        return f"Settimana {monday:%d/%m} – {friday:%d/%m/%Y} · {row_display_label(role)}"
    return f"{_WEEKDAY_LABELS[day.weekday()]} {day:%d/%m/%Y} · {row_display_label(role)}"
