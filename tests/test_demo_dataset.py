"""Acceptance checks for the generated, mutually consistent demo dataset."""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path, PurePosixPath

import pytest
from demo_helpers import (
    FIRST_MONTH,
    MONTH_KEYS,
    REFERENCE,
    JsonRecord,
    catalog,
    decode_files,
    minute,
    monday,
    months,
    operations,
    scenario_files,
)

from src.optimization.platform_mapping import PlatformPlanningPolicy
from src.patient_fields import parse_patient_insertion_date
from src.planning_schema import (
    DEFAULT_COMPLEXITIES_BY_TRAINING_LEVEL,
    DEFAULT_MAX_WAIT_DAYS,
    OPTIMIZATION_KEY,
    PAPER_CATEGORIES,
    SCHEMA_VERSION,
)


@pytest.fixture(scope="module")
def records() -> dict[str, JsonRecord]:
    return decode_files(scenario_files())


def test_generation_is_deterministic_and_does_not_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    first = scenario_files()
    assert first == scenario_files()
    assert not list(tmp_path.iterdir())
    assert all(not PurePosixPath(name).is_absolute() for name in first)
    assert all(".." not in PurePosixPath(name).parts for name in first)


def test_catalog_identifiers_counts_and_synthetic_markers(records: dict[str, JsonRecord]) -> None:
    patients = catalog(records, "pazienti")
    residents = catalog(records, "libretti")
    assert len(patients) == 120
    assert len(residents) == 8
    assert Counter(patient["stato"] for patient in patients.values()) == {
        "Completato": 38,
        "Pianificato": 62,
        "In Attesa": 20,
    }
    for directory, entries in (("pazienti", patients), ("libretti", residents)):
        paths = [name for name in records if PurePosixPath(name).parent == PurePosixPath(directory)]
        assert len(paths) == len(entries)
        for name in paths:
            record = records[name]
            assert record["id"] == PurePosixPath(name).stem
            assert record["dati_sintetici"] is True
    labels = [f"{record['cognome']} {record['nome'][0]}." for record in residents.values()]
    assert len(set(labels)) == len(residents)
    assert all(resident["stato"] == "Molinette" for resident in residents.values())


def test_patient_fields_have_valid_units_and_scenario_dates(records: dict[str, JsonRecord]) -> None:
    patients = catalog(records, "pazienti")
    for patient in patients.values():
        assert parse_patient_insertion_date(patient["data_inserimento"]) <= REFERENCE
        interventions = patient["interventi"]
        assert interventions
        assert all(type(item["durata"]) is int and item["durata"] > 0 for item in interventions)
        assert patient["durata_intervento"] == sum(item["durata"] for item in interventions)
        assert patient["codice_intervento"] == interventions[0]["codice"]
        assert patient["descrizione_intervento"] == interventions[0]["descrizione"]
        assert patient["urgenza"] in DEFAULT_MAX_WAIT_DAYS
        assert patient["complessita"] in {"Alta", "Media", "Bassa"}
        assert patient["tipo_chirurgia"] in {"Aperta", "Endovascolare"}
        settings = patient[OPTIMIZATION_KEY]
        assert settings["versione_schema"] == SCHEMA_VERSION
        assert settings["categoria_paper"] in PAPER_CATEGORIES
        assert settings["attesa_massima_giorni"] == DEFAULT_MAX_WAIT_DAYS[patient["urgenza"]]
    assert {patient["urgenza"] for patient in patients.values()} == {"Alta", "Media", "Bassa"}
    assert {patient["tipo_chirurgia"] for patient in patients.values()} == {
        "Aperta",
        "Endovascolare",
    }


@pytest.mark.parametrize("month_number,expected_count", [(9, 22), (10, 22), (11, 21), (12, 23)])
def test_rosters_cover_every_weekday_and_no_weekends(
    records: dict[str, JsonRecord], month_number: int, expected_count: int
) -> None:
    planned = months(records, "scadenzario")
    month_key = f"2026-{month_number:02d}"
    expected = {
        date(2026, month_number, day).isoformat()
        for day in range(1, calendar.monthrange(2026, month_number)[1] + 1)
        if date(2026, month_number, day).weekday() < 5
    }
    assert len(expected) == expected_count
    assert set(planned[month_key]["turni"]) == expected
    assert planned[month_key][OPTIMIZATION_KEY]["versione_schema"] == SCHEMA_VERSION


def test_monthly_dates_and_week_markers_are_canonical(records: dict[str, JsonRecord]) -> None:
    for directory in ("scadenzario", "sale_operatorie"):
        for actual in (False, True):
            for month_key, month in months(records, directory, actual=actual).items():
                for day_text in month.get("turni", {}):
                    day = date.fromisoformat(day_text)
                    assert day.strftime("%Y-%m") == month_key
                    assert day.weekday() < 5
                for week_text in month.get("metadata", {}).get("settimane", {}):
                    week = date.fromisoformat(week_text)
                    assert week.weekday() == 0
                    assert week.strftime("%Y-%m") == month_key


def test_roster_assignments_are_unique_and_rounds_continue_across_months(
    records: dict[str, JsonRecord],
) -> None:
    residents = catalog(records, "libretti")
    labels = {f"{record['cognome']} {record['nome'][0]}." for record in residents.values()}
    expected_roles = {
        "Reparto I",
        "Reparto II",
        "Sala Op. I",
        "Sala Op. II",
        "Day Hospital",
        "Day Surgery",
    }
    planned = months(records, "scadenzario")
    rounds: dict[str, str] = {}
    for month_key in MONTH_KEYS:
        month = planned[month_key]
        for week_text, label in month["giro_visite"].items():
            assert label in labels
            assert date.fromisoformat(week_text).weekday() == 0
            assert rounds.setdefault(week_text, label) == label
        for day_text, daily in month["turni"].items():
            assert expected_roles <= daily.keys()
            assert daily["Tipo Guardia"] in {"118", "PI", "L"}
            week_text = monday(date.fromisoformat(day_text)).isoformat()
            assigned = [daily[role] for role in expected_roles] + [month["giro_visite"][week_text]]
            assert set(assigned) <= labels
            assert len(set(assigned)) == 7
    for boundary in (date(2026, 9, 28), date(2026, 11, 30)):
        first_key = boundary.strftime("%Y-%m")
        last_key = (boundary + timedelta(days=4)).strftime("%Y-%m")
        assert (
            planned[first_key]["giro_visite"][boundary.isoformat()]
            == planned[last_key]["giro_visite"][boundary.isoformat()]
        )


@pytest.mark.parametrize("actual", [False, True])
def test_operations_match_catalogs_rosters_and_room_capacity(
    records: dict[str, JsonRecord], actual: bool
) -> None:
    patients = catalog(records, "pazienti")
    residents = catalog(records, "libretti")
    rosters = months(records, "scadenzario", actual=actual)
    rooms = months(records, "sale_operatorie", actual=actual)
    policy = PlatformPlanningPolicy()
    used: Counter[str] = Counter()
    sessions: dict[tuple[date, str], list[JsonRecord]] = defaultdict(list)
    for day, operation, daily in operations(rooms):
        assert FIRST_MONTH <= day <= date(2026, 12, 31)
        assert day.weekday() < 5
        patient = patients[operation["id_paziente"]]
        resident = residents[operation["id_specializzando"]]
        assert parse_patient_insertion_date(patient["data_inserimento"]) <= day
        used[patient["id"]] += 1
        month = rosters[day.strftime("%Y-%m")]
        config = month[OPTIMIZATION_KEY]
        room_id = operation["sala_operatoria"]
        room = config["sale_operatorie"][room_id]
        resident_label = f"{resident['cognome']} {resident['nome'][0]}."
        assert operation["specializzando"] == resident_label
        assert operation["ruolo_specializzando"] == room["ruolo_specializzando"]
        assert daily["specializzandi"][room["ruolo_specializzando"]] == resident_label
        assert month["turni"][day.isoformat()][room["riga_turno"]] == resident_label
        assert (
            operation["complessita"] in DEFAULT_COMPLEXITIES_BY_TRAINING_LEVEL[resident["livello"]]
        )
        assert operation["complessita"] == patient["complessita"]
        assert operation["tipo_chirurgia"] == patient["tipo_chirurgia"]
        assert operation["nome_paziente"] == f"{patient['cognome']} {patient['nome']}"
        assert operation["durata"] == patient["durata_intervento"]
        assert (
            minute(operation["ora_fine"]) - minute(operation["ora_inizio"]) == operation["durata"]
        )
        sessions[day, room_id].append(operation)
    assert used and max(used.values()) == 1
    assert {room_id for _, room_id in sessions} == set(policy.room_ids)
    for (day, room_id), scheduled in sessions.items():
        scheduled.sort(key=lambda operation: minute(operation["ora_inizio"]))
        config = rosters[day.strftime("%Y-%m")][OPTIMIZATION_KEY]
        capacity = (
            config.get("capacita_sessioni", {})
            .get(day.isoformat(), {})
            .get(room_id, config["sale_operatorie"][room_id]["capacita_minuti"])
        )
        assert len(scheduled) <= policy.max_operations_per_session
        assert minute(scheduled[0]["ora_inizio"]) >= policy.session_start_minute
        assert minute(scheduled[-1]["ora_fine"]) <= policy.session_start_minute + capacity
        assert (
            sum(operation["durata"] for operation in scheduled)
            + policy.changeover_minutes * (len(scheduled) - 1)
            <= capacity
        )
        for previous, current in zip(scheduled, scheduled[1:], strict=False):
            assert (
                minute(current["ora_inizio"])
                >= minute(previous["ora_fine"]) + policy.changeover_minutes
            )


def test_completed_cases_and_logbooks_only_follow_confirmed_actual_weeks(
    records: dict[str, JsonRecord],
) -> None:
    patients = catalog(records, "pazienti")
    residents = catalog(records, "libretti")
    actual = months(records, "sale_operatorie", actual=True)
    performed: dict[str, tuple[date, JsonRecord]] = {}
    by_month: Counter[str] = Counter()
    for day, operation, _ in operations(actual):
        week = monday(day)
        state = actual[week.strftime("%Y-%m")]["metadata"]["settimane"][week.isoformat()]
        if state != "CONVALIDATO":
            continue
        assert day < REFERENCE
        assert day <= date(2026, 10, 23)
        identifier = operation["id_paziente"]
        assert patients[identifier]["stato"] == "Completato"
        assert identifier not in performed
        performed[identifier] = (day, operation)
        by_month[day.strftime("%Y-%m")] += 1
    assert by_month == {"2026-09": 20, "2026-10": 18}
    assert set(performed) == {
        identifier for identifier, patient in patients.items() if patient["stato"] == "Completato"
    }
    recorded: Counter[str] = Counter()
    for resident in residents.values():
        keys = set()
        for activity in resident["attivita"]:
            day, operation = performed[activity["id_paziente"]]
            recorded[activity["id_paziente"]] += 1
            assert activity["data"] == day.isoformat()
            assert operation["id_specializzando"] == resident["id"]
            assert activity["ora_inizio"] == operation["ora_inizio"]
            assert activity["ora_fine"] == operation["ora_fine"]
            key = (activity["data"], activity.get("slot", activity["ora_inizio"]))
            assert key not in keys
            keys.add(key)
        for activity in resident.get("attivita_extra", []):
            assert date.fromisoformat(activity["data"]) < REFERENCE
    assert recorded == Counter({identifier: 1 for identifier in performed})


def test_month_states_keep_current_actual_editable_and_future_drafts(
    records: dict[str, JsonRecord],
) -> None:
    planned = months(records, "scadenzario")
    actual = months(records, "scadenzario", actual=True)
    assert planned["2026-09"]["metadata"]["stato"] == "CONVALIDATO"
    assert planned["2026-10"]["metadata"]["stato"] == "CONVALIDATO"
    assert actual["2026-09"]["metadata"]["stato"] == "CONVALIDATO"
    assert actual["2026-10"]["metadata"]["stato"] == "BOZZA"
    for key in ("2026-11", "2026-12"):
        assert planned[key]["metadata"]["stato"] == "BOZZA"
        assert key not in actual
    planned_rooms = months(records, "sale_operatorie")
    actual_rooms = months(records, "sale_operatorie", actual=True)
    assert planned_rooms["2026-10"]["metadata"]["settimane"]["2026-10-26"] == "CONVALIDATO"
    assert actual_rooms["2026-10"]["metadata"]["settimane"]["2026-10-26"] == "BOZZA"
    assert Counter(day.strftime("%Y-%m") for day, _, _ in operations(planned_rooms)) == {
        "2026-09": 20,
        "2026-10": 24,
        "2026-11": 28,
        "2026-12": 28,
    }
