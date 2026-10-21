"""Generate synthetic demo data around a date, backing up the previous dataset."""

from __future__ import annotations

import argparse
import calendar
import csv
import io
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.planning_schema import (  # noqa: E402
    OPTIMIZATION_KEY,
    default_patient_optimization,
    default_schedule_optimization,
)

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

DEMO_PATIENT_NAMES = (
    ("Pippo", "VerdeScuro"),
    ("Massimo", "Serra"),
    ("Giovanni", "Ferretti"),
    ("Luisa", "Marchetti"),
    ("Roberto", "Conti"),
    ("Carla", "Esposito"),
    ("Stefano", "Rizzo"),
    ("Marina", "Greco"),
    ("Franco", "Lombardi"),
    ("Elena", "Barbieri"),
    ("Giuseppe", "Fontana"),
    ("Sara", "Cattaneo"),
    ("Paolo", "Mancini"),
    ("Giovanna", "Ferraro"),
    ("Pietro", "Mancini"),
    ("Valeria", "Fontana"),
    ("Giorgio", "Caruso"),
    ("Anna", "Pellegrini"),
    ("Stefano", "Gallo"),
    ("Laura", "Vitale"),
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
"""Ruoli coperti a rotazione: 7 ruoli e 8 specializzandi, quindi uno libero a settimana."""

_ROTATION_ORIGIN = date(2024, 1, 1)
"""Lunedì da cui si contano le settimane della rotazione."""


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _weekly_roles(monday: date, names: list[str]) -> dict[str, str]:
    """Assegnazioni della settimana: ogni settimana tutti scalano di un ruolo.

    La settimana si conta da un lunedì fisso, così la rotazione prosegue tra mesi e anni
    e una settimana a cavallo di due mesi ha gli stessi turni in entrambi i file.
    """
    week = (monday - _ROTATION_ORIGIN).days // 7
    return {
        role: names[(position + week) % len(names)]
        for position, role in enumerate(ROTATION_ROLES)
    }


def build_demo_snapshot(reference: date) -> dict[str, str]:
    """Return UTF-8 JSON/CSV texts for three months of synthetic demo data.

    All dates derive from reference; generation is deterministic and performs no I/O.
    """
    current = reference.replace(day=1)
    previous = (current - timedelta(days=1)).replace(day=1)
    following = (current + timedelta(days=32)).replace(day=1)
    months = (previous, current, following)
    residents = [
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
    names = [f"{resident['cognome']} {resident['nome'][0]}." for resident in residents]
    rosters: dict[str, dict] = {}
    rooms: dict[str, dict] = {}
    for month in months:
        key = f"{month:%Y-%m}"
        roster = {
            "metadata": {
                "stato": "CONVALIDATO" if month < current else "BOZZA",
                "dati_sintetici": True,
            },
            "turni": {},
            "giro_visite": {},
            OPTIMIZATION_KEY: default_schedule_optimization(),
        }
        room = {"metadata": {"stato": "BOZZA", "settimane": {}}, "turni": {}}
        for day_number in range(1, calendar.monthrange(month.year, month.month)[1] + 1):
            day = month.replace(day=day_number)
            if day.weekday() >= 5:
                continue
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

    last_week = _monday(reference) - timedelta(days=7)
    upcoming = [
        reference + timedelta(days=offset)
        for offset in range(7)
        if (reference + timedelta(days=offset)).weekday() < 5
    ]
    operation_days = [last_week + timedelta(days=offset) for offset in range(5)]
    next_operation = _monday(reference) + timedelta(days=7)
    while next_operation in upcoming[:2]:
        next_operation += timedelta(days=1)
    operation_days += upcoming[:2] + [next_operation]
    patients = []
    for index, (first_name, surname) in enumerate(DEMO_PATIENT_NAMES, 1):
        duration = (45, 60, 90, 120)[index % 4]
        urgency = ("Alta", "Media", "Bassa")[index % 3]
        diagnosis_code = f"D{index:03d}"
        intervention = {
            "codice": f"DEMO-{index:03d}",
            "descrizione": f"Procedura sintetica {index:02d}",
            "durata": duration,
        }
        patient = {
            "id": f"PZ{index:04d}",
            "nome": first_name,
            "cognome": surname,
            "codice_diagnosi": diagnosis_code,
            "descrizione_diagnosi": f"Diagnosi sintetica {index:02d}",
            "diagnosi": f"[{diagnosis_code}] Diagnosi sintetica {index:02d}",
            "interventi": [intervention],
            "codice_intervento": intervention["codice"],
            "descrizione_intervento": intervention["descrizione"],
            "durata_intervento": duration,
            "tipo_chirurgia": "Aperta" if index % 2 else "Endovascolare",
            "complessita": ("Alta", "Media", "Bassa")[index % 3],
            "urgenza": urgency,
            "stato": "Completato" if index <= 5 else "In Attesa",
            "data_inserimento": (last_week - timedelta(days=14 + index)).strftime("%d/%m/%Y"),
            "note": "Dati inventati per la demo.",
            "dati_sintetici": True,
            OPTIMIZATION_KEY: default_patient_optimization(urgency),
        }
        patients.append(patient)
        if index > len(operation_days):
            continue
        day = operation_days[index - 1]
        # L'intervento va a chi è in Sala Op. I quel giorno secondo lo scadenzario.
        surgeon_label = _weekly_roles(_monday(day), names)["Sala Op. I"]
        resident = residents[names.index(surgeon_label)]
        operation = {
            "id_paziente": patient["id"],
            "nome_paziente": f"{patient['cognome']} {patient['nome']}",
            "diagnosi": patient["diagnosi"],
            "codice_diagnosi": diagnosis_code,
            "descrizione_diagnosi": patient["descrizione_diagnosi"],
            "intervento": intervention["descrizione"],
            "codice_intervento": intervention["codice"],
            "interventi": [intervention.copy()],
            "durata": duration,
            "ora_inizio": "08:00",
            "ora_fine": f"{8 + duration // 60:02d}:{duration % 60:02d}",
            "sala_operatoria": "OR-1",
            "chirurgo": "Chirurgo demo",
            "complessita": patient["complessita"],
            "tipo_chirurgia": patient["tipo_chirurgia"],
            "specializzando": surgeon_label,
            "id_specializzando": resident["id"],
            "ruolo_specializzando": "OR I",
        }
        rooms[f"{day:%Y-%m}"]["turni"][day.isoformat()]["operazioni"].append(operation)
        week = _monday(day)
        rooms[f"{week:%Y-%m}"]["metadata"]["settimane"][week.isoformat()] = (
            "CONVALIDATO" if index <= 5 else "BOZZA"
        )
        if index <= 5:
            resident["attivita"].append(
                {
                    **operation,
                    "data": day.isoformat(),
                    "slot": "08:00-10:00",
                    "ruolo": "OR I",
                }
            )

    ward_round_label = _weekly_roles(last_week, names)["Giro Visite"]
    residents[names.index(ward_round_label)]["attivita_extra"] = [
        {
            "data": (last_week + timedelta(days=offset)).isoformat(),
            "ora_inizio": "08:00",
            "ora_fine": "18:00",
            "sede": "Reparto",
            "attivita": "Giro Visite",
            "ruolo": "Giro Visite",
            "note": "Attività demo.",
        }
        for offset in range(5)
    ]
    payloads = {
        **{f"libretti/{record['id']}.json": record for record in residents},
        **{f"pazienti/{record['id']}.json": record for record in patients},
        **{f"scadenzario/{key}.json": value for key, value in rosters.items()},
        **{f"sale_operatorie/{key}.json": value for key, value in rooms.items()},
    }
    files = {
        path: json.dumps(payload, ensure_ascii=False, indent=4) + "\n"
        for path, payload in payloads.items()
    }
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
            first_name, surname = DEMO_PATIENT_NAMES[index - 1]
            values = [
                first_name,
                surname,
                "Diagnosi sintetica (D001)",
                "DEMO-A;DEMO-B" if multiple else "DEMO-A",
                "Procedura demo A;Procedura demo B" if multiple else "Procedura demo A",
            ]
            values += (
                ["Classe B"]
                if trackcare
                else [
                    "Aperta",
                    "Alta",
                    "Media",
                    "90;60" if multiple else "90",
                ]
            )
            writer.writerow(values)
        files[filename] = stream.getvalue()
    return files


def reset_demo_data(project_root: Path, reference: date) -> Path | None:
    """Replace mock_data and return its backup path, or None for an initial dataset.

    The caller must close the application and authorize replacement before calling.
    """
    root = project_root.resolve()
    target = root / "mock_data"
    backup_root = root / ".demo_backups"
    if target.is_symlink() or backup_root.is_symlink():
        raise ValueError("Demo data and backup directories must not be symbolic links.")
    snapshot = build_demo_snapshot(reference)
    staging = root / f".demo-stage-{uuid4().hex}"
    staging.mkdir(mode=0o700)
    try:
        for name, text in snapshot.items():
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text, encoding="utf-8")
        backup = None
        if target.exists():
            backup_root.mkdir(mode=0o700, exist_ok=True)
            backup = backup_root / f"{reference.isoformat()}-{uuid4().hex}"
            target.rename(backup)
        try:
            staging.rename(target)
        except OSError:
            if backup is not None:
                backup.rename(target)
            raise
        return backup
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> None:
    """Reset the local demo on explicit --write; otherwise report generation counts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--reference-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    files = build_demo_snapshot(args.reference_date)
    print(
        f"Demo sintetica al {args.reference_date}: {len(files)} file, "
        "20 pazienti, 8 specializzandi."
    )
    if args.write:
        backup = reset_demo_data(args.project_root, args.reference_date)
        print(f"Dati aggiornati. Backup precedente: {backup or 'nessuno'}")
    else:
        print("Anteprima: usare --write ad applicazione chiusa per sostituire i dati.")


if __name__ == "__main__":
    main()
