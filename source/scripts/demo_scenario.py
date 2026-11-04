"""Build reproducible synthetic patients and calendars without filesystem access."""

from __future__ import annotations

import calendar
import csv
import io
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from src.planning_schema import (
    DEFAULT_COMPLEXITIES_BY_TRAINING_LEVEL,
    DEFAULT_MAX_WAIT_DAYS,
    OPTIMIZATION_KEY,
    default_patient_optimization,
    default_schedule_optimization,
)

JsonObject = dict[str, Any]

DEMO_RESIDENT_NAMES = (
    ("Antonio", "Gasparri"),
    ("Mandringo", "Bello"),
    ("Verde", "Verdone"),
    ("Pino", "Silvestre"),
    ("Antonia", "Massima"),
    ("Spirulina", "Alga"),
    ("BAZZ", "JAZZ"),
    ("Lorenzo", "Parco"),
)

ROTATION_ROLES = (
    "Reparto I",
    "Reparto II",
    "Sala Op. I",
    "Sala Op. II",
    "Giro Visite",
    "Day Hospital",
    "Day Surgery",
)

_ROTATION_ORIGIN = date(2024, 1, 1)
_SESSION_START_MINUTE = 8 * 60
_SESSION_CAPACITY_MINUTES = 600
_CHANGEOVER_MINUTES = 11
_MAX_OPERATIONS_PER_SESSION = 12
_DURATIONS_MINUTES = (45, 60, 90, 120, 150, 180)
_URGENCIES = ("Alta", "Media", "Bassa")


@dataclass(frozen=True, slots=True)
class _PatientGroup:
    """A weighted cohort; empty days identify patients still on the waiting list."""

    days: tuple[date, ...]
    weight: int
    completed: bool = False


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _month_shift(month: date, offset: int) -> date:
    year, month_index = divmod(month.year * 12 + month.month - 1 + offset, 12)
    return date(year, month_index + 1, 1)


def _weekly_roles(monday: date, names: list[str]) -> dict[str, str]:
    """Rotate seven roles across eight residents continuously across month boundaries."""
    week = (monday - _ROTATION_ORIGIN).days // 7
    return {
        role: names[(position + week) % len(names)] for position, role in enumerate(ROTATION_ROLES)
    }


def _validated_months(
    reference: date, start_month: date | None, end_month: date | None, patient_count: int
) -> tuple[date, ...]:
    if not isinstance(reference, date) or isinstance(reference, datetime):
        raise ValueError("reference must be a date without a time component.")
    if not isinstance(patient_count, int) or isinstance(patient_count, bool) or patient_count <= 0:
        raise ValueError("patient_count must be a positive integer.")
    current = reference.replace(day=1)
    first = _month_shift(current, -1) if start_month is None else start_month
    last = _month_shift(current, 2) if end_month is None else end_month
    for boundary in (first, last):
        if not isinstance(boundary, date) or isinstance(boundary, datetime) or boundary.day != 1:
            raise ValueError("Month boundaries must be dates on the first day of their month.")
    if first > last:
        raise ValueError("start_month must not follow end_month.")
    if not first <= current <= last:
        raise ValueError("The reference month must be inside the requested interval.")
    count = (last.year - first.year) * 12 + last.month - first.month + 1
    return tuple(_month_shift(first, offset) for offset in range(count))


def _working_days(month: date) -> tuple[date, ...]:
    return tuple(
        month.replace(day=number)
        for number in range(1, calendar.monthrange(month.year, month.month)[1] + 1)
        if month.replace(day=number).weekday() < 5
    )


def _residents() -> list[JsonObject]:
    return [
        {
            "id": f"SP{index:03d}",
            "nome": first_name,
            "cognome": surname,
            "matricola": f"DEMO-{index:03d}",
            "livello": ("Junior", "Senior", "Intermediate")[(index - 1) % 3],
            "stato": "Molinette",
            "dati_sintetici": True,
            "attivita": [],
            "attivita_extra": [],
            "meta_giorni": {},
        }
        for index, (first_name, surname) in enumerate(DEMO_RESIDENT_NAMES, 1)
    ]


def _base_calendars(
    months: tuple[date, ...], reference: date, names: list[str]
) -> tuple[dict[str, JsonObject], dict[str, JsonObject], dict[str, JsonObject]]:
    rosters: dict[str, JsonObject] = {}
    actual_rosters: dict[str, JsonObject] = {}
    rooms: dict[str, JsonObject] = {}
    current = reference.replace(day=1)
    # A confirmed operating week can cross into the next roster month.
    confirmed_through = max(current, (_monday(reference) + timedelta(days=4)).replace(day=1))
    for month in months:
        key = f"{month:%Y-%m}"
        roster: JsonObject = {
            "metadata": {
                "stato": "CONVALIDATO" if month <= confirmed_through else "BOZZA",
                "dati_sintetici": True,
            },
            "turni": {},
            "giro_visite": {},
            OPTIMIZATION_KEY: default_schedule_optimization(),
        }
        room: JsonObject = {
            "metadata": {"stato": "BOZZA", "settimane": {}, "dati_sintetici": True},
            "turni": {},
        }
        for day in _working_days(month):
            monday = _monday(day)
            weekly = _weekly_roles(monday, names)
            roster["turni"][day.isoformat()] = {
                "Tipo Guardia": ("118", "PI", "L")[day.weekday() % 3],
                **{role: weekly[role] for role in ROTATION_ROLES if role != "Giro Visite"},
            }
            roster["giro_visite"][monday.isoformat()] = weekly["Giro Visite"]
            room["turni"][day.isoformat()] = {
                "specializzandi": {"OR I": weekly["Sala Op. I"], "OR II": weekly["Sala Op. II"]},
                "operazioni": [],
            }
        rosters[key] = roster
        rooms[key] = room
        if month <= confirmed_through:
            actual_rosters[key] = deepcopy(roster)
            actual_rosters[key]["metadata"]["stato"] = "CONVALIDATO" if month < current else "BOZZA"
    return rosters, actual_rosters, rooms


def _patient_groups(months: tuple[date, ...], reference: date) -> tuple[_PatientGroup, ...]:
    last_day = months[-1].replace(day=calendar.monthrange(months[-1].year, months[-1].month)[1])
    current = reference.replace(day=1)
    current_monday = _monday(reference)
    groups: list[_PatientGroup] = []
    for month in months:
        days = tuple(
            day
            for day in _working_days(month)
            if _monday(day) >= months[0] and _monday(day) + timedelta(days=4) <= last_day
        )
        if month == current:
            completed = tuple(day for day in days if day < current_monday)
            planned = tuple(day for day in days if day >= current_monday)
            if completed:
                groups.append(_PatientGroup(completed, 18, completed=True))
            if planned:
                groups.append(_PatientGroup(planned, 6))
        elif days and month < current:
            completed = tuple(day for day in days if day < current_monday)
            planned = tuple(day for day in days if day >= current_monday)
            planned_weight = max(1, 20 * len(planned) // len(days)) if planned else 0
            if completed:
                groups.append(_PatientGroup(completed, 20 - planned_weight, completed=True))
            if planned:
                groups.append(_PatientGroup(planned, planned_weight))
        elif days:
            groups.append(_PatientGroup(days, 28))
    groups.append(_PatientGroup((), 20))
    return tuple(groups)


def _cohort_counts(groups: tuple[_PatientGroup, ...], total: int) -> tuple[int, ...]:
    """Apportion integer counts by largest remainder, without losing any patient."""
    weight = sum(group.weight for group in groups)
    counts = [total * group.weight // weight for group in groups]
    remainder_order = sorted(
        range(len(groups)), key=lambda index: (-(total * groups[index].weight % weight), index)
    )
    for index in remainder_order[: total - sum(counts)]:
        counts[index] += 1
    return tuple(counts)


def _patient(
    index: int,
    reference: date,
    first_day: date,
    day: date | None,
    completed: bool,
    resident: JsonObject | None,
) -> JsonObject:
    urgency = _URGENCIES[(index - 1) % len(_URGENCIES)]
    if day is None:
        wait_days = min(DEFAULT_MAX_WAIT_DAYS[urgency] - 1, 7 + index % 60)
        inserted = max(first_day, reference - timedelta(days=wait_days))
        complexity = ("Bassa", "Media", "Alta")[(index - 1) % 3]
    else:
        minimum_wait = max(0, (day - reference).days)
        if minimum_wait >= DEFAULT_MAX_WAIT_DAYS[urgency]:
            available = [
                label for label in _URGENCIES if DEFAULT_MAX_WAIT_DAYS[label] > minimum_wait
            ]
            if not available:
                raise ValueError(
                    "The requested interval exceeds the demo's maximum waiting-time horizon."
                )
            urgency = available[0]
        desired_wait = {"Alta": 7, "Media": 20, "Bassa": 35}[urgency] + index % 14
        inserted = max(first_day, min(reference, day - timedelta(days=desired_wait)))
        qualifications = DEFAULT_COMPLEXITIES_BY_TRAINING_LEVEL[resident["livello"]]
        complexity = qualifications[(index - 1) % len(qualifications)]
    duration = _DURATIONS_MINUTES[(index - 1) % len(_DURATIONS_MINUTES)]
    durations = (duration // 2, duration - duration // 2) if index % 8 == 0 else (duration,)
    interventions = [
        {
            "codice": f"DEMO-{index:04d}-{part}",
            "descrizione": f"Procedura sintetica {index:04d}, parte {part}",
            "durata": minutes,
        }
        for part, minutes in enumerate(durations, 1)
    ]
    diagnosis_code = f"D{index:04d}"
    diagnosis = f"Diagnosi sintetica {index:04d}"
    return {
        "id": f"PZ{index:04d}",
        "nome": "Paziente",
        "cognome": f"Demo {index:04d}",
        "codice_diagnosi": diagnosis_code,
        "descrizione_diagnosi": diagnosis,
        "diagnosi": f"[{diagnosis_code}] {diagnosis}",
        "interventi": interventions,
        "codice_intervento": interventions[0]["codice"],
        "descrizione_intervento": interventions[0]["descrizione"],
        "durata_intervento": duration,
        "tipo_chirurgia": "Aperta" if index % 2 else "Endovascolare",
        "complessita": complexity,
        "urgenza": urgency,
        "stato": "Completato" if completed else "Pianificato" if day is not None else "In Attesa",
        "data_inserimento": inserted.strftime("%d/%m/%Y"),
        "note": "Dati inventati per la demo; nessuna persona o procedura reale.",
        "dati_sintetici": True,
        OPTIMIZATION_KEY: default_patient_optimization(urgency),
    }


def _time_label(minute: int) -> str:
    hour, remaining = divmod(minute, 60)
    return f"{hour:02d}:{remaining:02d}"


def _operation(
    patient: JsonObject, resident: JsonObject, room_number: int, start_minute: int
) -> JsonObject:
    duration = patient["durata_intervento"]
    return {
        "id_paziente": patient["id"],
        "nome_paziente": f"{patient['cognome']} {patient['nome']}",
        "diagnosi": patient["diagnosi"],
        "codice_diagnosi": patient["codice_diagnosi"],
        "descrizione_diagnosi": patient["descrizione_diagnosi"],
        "intervento": "; ".join(part["descrizione"] for part in patient["interventi"]),
        "codice_intervento": patient["codice_intervento"],
        "interventi": deepcopy(patient["interventi"]),
        "durata": duration,
        "ora_inizio": _time_label(start_minute),
        "ora_fine": _time_label(start_minute + duration),
        "sala_operatoria": f"OR-{room_number}",
        "chirurgo": "Chirurgo demo",
        "complessita": patient["complessita"],
        "tipo_chirurgia": patient["tipo_chirurgia"],
        "specializzando": f"{resident['cognome']} {resident['nome'][0]}.",
        "id_specializzando": resident["id"],
        "ruolo_specializzando": "OR I" if room_number == 1 else "OR II",
    }


def _performed_activity(day: date, operation: JsonObject) -> JsonObject:
    """Match the activity shape written by actual operating-week confirmation."""
    return {
        "data": day.isoformat(),
        "slot": operation["ora_inizio"],
        **{
            key: deepcopy(operation[key])
            for key in (
                "nome_paziente",
                "id_paziente",
                "diagnosi",
                "intervento",
                "codice_intervento",
                "chirurgo",
                "interventi",
                "complessita",
                "tipo_chirurgia",
                "ora_inizio",
                "ora_fine",
                "durata",
            )
        },
        "ruolo": operation["ruolo_specializzando"],
    }


def _populate_patients(
    groups: tuple[_PatientGroup, ...],
    patient_count: int,
    reference: date,
    first_day: date,
    residents: list[JsonObject],
    rooms: dict[str, JsonObject],
) -> list[JsonObject]:
    names = [f"{resident['cognome']} {resident['nome'][0]}." for resident in residents]
    resident_by_name = dict(zip(names, residents, strict=True))
    patients: list[JsonObject] = []
    for group, count in zip(groups, _cohort_counts(groups, patient_count), strict=True):
        for offset in range(count):
            index = len(patients) + 1
            day = group.days[offset * len(group.days) // count] if group.days else None
            room_number = 1 + (index - 1) % 2
            row = "Sala Op. I" if room_number == 1 else "Sala Op. II"
            resident = resident_by_name[_weekly_roles(_monday(day), names)[row]] if day else None
            patient = _patient(index, reference, first_day, day, group.completed, resident)
            patients.append(patient)
            if day is None:
                continue
            operations = rooms[f"{day:%Y-%m}"]["turni"][day.isoformat()]["operazioni"]
            preceding = [op for op in operations if op["sala_operatoria"] == f"OR-{room_number}"]
            start = _SESSION_START_MINUTE + sum(op["durata"] for op in preceding)
            start += _CHANGEOVER_MINUTES * len(preceding)
            if (
                start + patient["durata_intervento"]
                > _SESSION_START_MINUTE + _SESSION_CAPACITY_MINUTES
                or len(preceding) >= _MAX_OPERATIONS_PER_SESSION
            ):
                raise ValueError("The requested patient count exceeds the demo session capacity.")
            operation = _operation(patient, resident, room_number, start)
            operations.append(operation)
            operations.sort(
                key=lambda op: (op["ora_inizio"], op["sala_operatoria"], op["id_paziente"])
            )
            if group.completed:
                resident["attivita"].append(_performed_activity(day, operation))
    return patients


def _actual_room_calendars(rooms: dict[str, JsonObject], reference: date) -> dict[str, JsonObject]:
    """Copy complete confirmed planned weeks; leave the current actual week editable."""
    actual: dict[str, JsonObject] = {}
    days = {date.fromisoformat(day_text) for month in rooms.values() for day_text in month["turni"]}
    for monday in sorted({_monday(day) for day in days}):
        week = tuple(monday + timedelta(days=offset) for offset in range(5))
        if not set(week).issubset(days):
            continue
        key = f"{monday:%Y-%m}"
        state = "CONVALIDATO" if monday <= _monday(reference) else "BOZZA"
        rooms[key]["metadata"]["settimane"][monday.isoformat()] = state
        if state == "BOZZA":
            continue
        for day in week:
            day_key = f"{day:%Y-%m}"
            target = actual.setdefault(
                day_key,
                {
                    "metadata": {"stato": "BOZZA", "settimane": {}, "dati_sintetici": True},
                    "turni": {},
                },
            )
            target["turni"][day.isoformat()] = deepcopy(rooms[day_key]["turni"][day.isoformat()])
        actual[key]["metadata"]["settimane"][monday.isoformat()] = (
            "CONVALIDATO" if monday < _monday(reference) else "BOZZA"
        )
    return actual


def _completed_ward_rounds(
    residents: list[JsonObject], rosters: dict[str, JsonObject], reference: date
) -> None:
    resident_by_name = {
        f"{resident['cognome']} {resident['nome'][0]}.": resident for resident in residents
    }
    for roster in rosters.values():
        for day_text in roster["turni"]:
            day = date.fromisoformat(day_text)
            if day >= _monday(reference):
                continue
            label = roster["giro_visite"][_monday(day).isoformat()]
            resident_by_name[label]["attivita_extra"].append(
                {
                    "data": day_text,
                    "ora_inizio": "08:00",
                    "ora_fine": "18:00",
                    "sede": "Reparto",
                    "attivita": "Giro Visite",
                    "ruolo": "Giro Visite",
                    "note": "Attività sintetica confermata per la demo.",
                }
            )
    for resident in residents:
        resident["attivita"].sort(key=lambda activity: (activity["data"], activity["slot"]))
        resident["attivita_extra"].sort(key=lambda activity: (activity["data"], activity["sede"]))


def _csv_examples() -> dict[str, str]:
    files: dict[str, str] = {}
    for filename, trackcare in (
        ("template_bulk_pazienti_A.csv", False),
        ("template_bulk_pazienti_B.csv", False),
        ("test_inserimento_bulk.csv", True),
    ):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";" if trackcare else ",", lineterminator="\n")
        writer.writerow(
            [
                "Nome",
                "Cognome",
                "Diagnosi ICD9",
                "codice intervento",
                "Intervento/procedura ICD9",
                "Priorità",
            ]
            if trackcare
            else [
                "nome",
                "cognome",
                "diagnosi",
                "codice_intervento",
                "descrizione_intervento",
                "tipo_chirurgia",
                "complessita",
                "urgenza",
                "durata_intervento",
            ]
        )
        for index in range(1, 9):
            multiple = index == 2
            values = [
                "Paziente import",
                f"Demo CSV {index:03d}",
                "Diagnosi sintetica (D001)",
                "DEMO-A;DEMO-B" if multiple else "DEMO-A",
                "Procedura demo A;Procedura demo B" if multiple else "Procedura demo A",
            ]
            values += (
                ["Classe B"]
                if trackcare
                else ["Aperta", "Alta", "Media", "90;60" if multiple else "90"]
            )
            writer.writerow(values)
        files[filename] = stream.getvalue()
    return files


def build_demo_snapshot(
    reference: date,
    *,
    start_month: date | None = None,
    end_month: date | None = None,
    patient_count: int = 120,
) -> dict[str, str]:
    """Return deterministic UTF-8 JSON/CSV texts for a synthetic demo interval.

    Defaults span the previous month through the second month after ``reference``.
    Explicit month boundaries must be first-of-month dates enclosing the reference
    month. At 2026-10-27, the default 120 patients comprise 38 completed, 62 planned
    and 20 waiting cases. Only complete Monday-Friday weeks receive operations;
    no calendar files outside the requested interval are created. Durations use
    integer minutes. All insertion dates are no later than the reference date.

    Raises ValueError for invalid dates/counts or a cohort exceeding room capacity.
    This function reads no files or clock and neither creates nor modifies files.
    """
    months = _validated_months(reference, start_month, end_month, patient_count)
    residents = _residents()
    names = [f"{resident['cognome']} {resident['nome'][0]}." for resident in residents]
    rosters, actual_rosters, rooms = _base_calendars(months, reference, names)
    patients = _populate_patients(
        _patient_groups(months, reference), patient_count, reference, months[0], residents, rooms
    )
    actual_rooms = _actual_room_calendars(rooms, reference)
    _completed_ward_rounds(residents, rosters, reference)
    payloads = {
        **{f"libretti/{record['id']}.json": record for record in residents},
        **{f"pazienti/{record['id']}.json": record for record in patients},
        **{f"scadenzario/{key}.json": value for key, value in rosters.items()},
        **{f"scadenzario/effettivo/{key}.json": value for key, value in actual_rosters.items()},
        **{f"sale_operatorie/{key}.json": value for key, value in rooms.items()},
        **{f"sale_operatorie/effettivo/{key}.json": value for key, value in actual_rooms.items()},
    }
    return {
        **{
            path: json.dumps(payload, ensure_ascii=False, indent=4) + "\n"
            for path, payload in sorted(payloads.items())
        },
        **_csv_examples(),
    }
