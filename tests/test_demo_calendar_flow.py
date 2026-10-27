"""Exercise calendar transitions against the complete generated demo dataset."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest
from demo_helpers import JsonRecord, json_bytes, materialize, read_json

from src.calendar_versions import CalendarVersion, CalendarVersionError
from src.models import patient_plan_state
from src.models.data_manager import DataManager
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.models.patient_plan_state import draft_patient_ids_by_week, read_operational_plan_months
from src.optimization.exceptions import PlatformDataError
from src.optimization.platform_io import load_platform_context

CURRENT_WEEK = date(2026, 10, 26)


@pytest.fixture
def demo_data(tmp_path: Path) -> Path:
    return materialize(tmp_path / "mock_data")


def _rooms(root: Path, *, actual: bool = False) -> DataManagerSaleOperatorie:
    return DataManagerSaleOperatorie(
        root / "sale_operatorie",
        dir_pazienti=root / "pazienti",
        version=CalendarVersion.EFFETTIVO if actual else CalendarVersion.PREVISTO,
    )


def _week_operations(
    manager: DataManagerSaleOperatorie, week: date
) -> list[tuple[str, JsonRecord]]:
    return [
        (day.isoformat(), operation)
        for day in (week + timedelta(days=offset) for offset in range(5))
        for operation in manager.get_operazioni(day.isoformat())
    ]


def _patient_states(root: Path) -> dict[str, str]:
    return {path.stem: read_json(path)["stato"] for path in (root / "pazienti").glob("*.json")}


def _activity_count(root: Path) -> int:
    return sum(len(read_json(path)["attivita"]) for path in (root / "libretti").glob("*.json"))


def _planned_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for folder in ("scadenzario", "sale_operatorie")
        for path in (root / folder).glob("*.json")
    }


def test_operational_view_has_exactly_one_reservation_per_planned_patient(demo_data: Path) -> None:
    before = json_bytes(demo_data)
    operational = read_operational_plan_months(demo_data / "sale_operatorie")
    reservations = draft_patient_ids_by_week(operational)
    counts = Counter(
        identifier for identifiers in reservations.values() for identifier in identifiers
    )
    expected = {
        identifier
        for identifier, state in _patient_states(demo_data).items()
        if state == "Pianificato"
    }
    assert set(counts) == expected
    assert len(expected) == 62
    assert set(counts.values()) == {1}
    dates = _rooms(demo_data).get_pianificazioni_pazienti()
    assert set(dates) == expected
    assert all(len(values) == 1 for values in dates.values())
    assert json_bytes(demo_data) == before


def test_removing_and_restoring_actual_booking_updates_only_its_patient(demo_data: Path) -> None:
    actual = _rooms(demo_data, actual=True)
    day_text, operation = _week_operations(actual, CURRENT_WEEK)[0]
    identifier = operation["id_paziente"]
    original_operations = actual.get_operazioni(day_text)
    original_patients = json_bytes(demo_data / "pazienti")
    original_planned = _planned_bytes(demo_data)
    original_logbooks = json_bytes(demo_data / "libretti")
    actual.set_operazioni(
        day_text, [item for item in original_operations if item["id_paziente"] != identifier]
    )
    assert _patient_states(demo_data)[identifier] == "In Attesa"
    assert identifier not in _rooms(demo_data).get_pianificazioni_pazienti()
    assert _planned_bytes(demo_data) == original_planned
    assert json_bytes(demo_data / "libretti") == original_logbooks
    changed = json_bytes(demo_data / "pazienti")
    assert {name for name in changed if changed[name] != original_patients[name]} == {
        f"{identifier}.json"
    }
    actual.set_operazioni(day_text, original_operations)
    assert _patient_states(demo_data)[identifier] == "Pianificato"
    assert identifier in _rooms(demo_data).get_pianificazioni_pazienti()
    assert _activity_count(demo_data) == 38


@pytest.mark.parametrize("remove_one", [False, True])
def test_actual_confirmation_records_only_retained_cases_once(
    demo_data: Path, remove_one: bool
) -> None:
    actual = _rooms(demo_data, actual=True)
    planned_before = _planned_bytes(demo_data)
    initial = _week_operations(actual, CURRENT_WEEK)
    assert len(initial) == 6
    removed_id = None
    if remove_one:
        day_text, operation = initial[0]
        removed_id = operation["id_paziente"]
        actual.set_operazioni(
            day_text,
            [item for item in actual.get_operazioni(day_text) if item["id_paziente"] != removed_id],
        )
    retained = {operation["id_paziente"] for _, operation in _week_operations(actual, CURRENT_WEEK)}
    states_before = _patient_states(demo_data)
    activities_before = _activity_count(demo_data)
    actual.convalida_settimana(CURRENT_WEEK, dir_libretti=demo_data / "libretti")
    assert actual.get_stato_settimana(CURRENT_WEEK) == "CONVALIDATO"
    states_after = _patient_states(demo_data)
    assert {
        identifier
        for identifier in states_after
        if states_after[identifier] != states_before[identifier]
    } == retained
    assert all(states_after[identifier] == "Completato" for identifier in retained)
    if removed_id:
        assert states_after[removed_id] == "In Attesa"
    assert _activity_count(demo_data) == activities_before + len(retained)
    assert not (retained & _rooms(demo_data).get_pianificazioni_pazienti().keys())
    assert _planned_bytes(demo_data) == planned_before
    confirmed_bytes = json_bytes(demo_data)
    with pytest.raises(CalendarVersionError, match="già convalidata"):
        actual.convalida_settimana(CURRENT_WEEK, dir_libretti=demo_data / "libretti")
    assert json_bytes(demo_data) == confirmed_bytes


@pytest.mark.parametrize("week", [date(2026, 11, 2), date(2026, 11, 30), date(2026, 12, 28)])
def test_planned_week_confirmation_copies_all_five_days_without_completing_patients(
    demo_data: Path, week: date
) -> None:
    planned = _rooms(demo_data)
    actual = _rooms(demo_data, actual=True)
    assert not actual.has_settimana(week)
    original_logbooks = json_bytes(demo_data / "libretti")
    original_states = _patient_states(demo_data)
    previous_actual = (demo_data / "sale_operatorie" / "effettivo" / "2026-10.json").read_bytes()
    planned.convalida_settimana(week)
    assert planned.get_stato_settimana(week) == "CONVALIDATO"
    assert actual.has_settimana(week)
    assert actual.get_stato_settimana(week) == "BOZZA"
    for offset in range(5):
        day = week + timedelta(days=offset)
        assert actual.get_operazioni(day.isoformat()) == planned.get_operazioni(day.isoformat())
        actual_month = actual.load_mese(day.year, day.month)
        assert day.isoformat() in actual_month["turni"]
        if (day.year, day.month) != (week.year, week.month):
            assert week.isoformat() not in actual_month.get("metadata", {}).get("settimane", {})
    assert _patient_states(demo_data) == original_states
    assert json_bytes(demo_data / "libretti") == original_logbooks
    assert (
        demo_data / "sale_operatorie" / "effettivo" / "2026-10.json"
    ).read_bytes() == previous_actual


def test_cross_month_actual_change_releases_only_the_removed_booking(demo_data: Path) -> None:
    week = date(2026, 11, 30)
    planned = _rooms(demo_data)
    planned.convalida_settimana(week)
    actual = _rooms(demo_data, actual=True)
    candidates = [item for item in _week_operations(actual, week) if item[0].startswith("2026-12")]
    assert candidates, "The demo must exercise the December side of the November 30 week."
    day_text, removed = candidates[0]
    planned_before = _planned_bytes(demo_data)
    states_before = _patient_states(demo_data)
    actual.set_operazioni(
        day_text,
        [
            operation
            for operation in actual.get_operazioni(day_text)
            if operation["id_paziente"] != removed["id_paziente"]
        ],
    )
    states_after = _patient_states(demo_data)
    assert states_after[removed["id_paziente"]] == "In Attesa"
    assert {
        identifier
        for identifier in states_after
        if states_after[identifier] != states_before[identifier]
    } == {removed["id_paziente"]}
    assert _planned_bytes(demo_data) == planned_before
    assert actual.get_stato_settimana(week) == "BOZZA"


@pytest.mark.parametrize(
    "field,bad_identifier", [("id_paziente", "PZ-MISSING"), ("id_specializzando", "SP-MISSING")]
)
def test_invalid_actual_reference_blocks_confirmation_without_partial_updates(
    demo_data: Path, field: str, bad_identifier: str
) -> None:
    actual = _rooms(demo_data, actual=True)
    day_text, original = _week_operations(actual, CURRENT_WEEK)[0]
    operations = deepcopy(actual.get_operazioni(day_text))
    replacement = next(
        item for item in operations if item["id_paziente"] == original["id_paziente"]
    )
    replacement[field] = bad_identifier
    actual.set_operazioni(day_text, operations)
    before = json_bytes(demo_data)
    with pytest.raises(CalendarVersionError):
        actual.convalida_settimana(CURRENT_WEEK, dir_libretti=demo_data / "libretti")
    assert json_bytes(demo_data) == before
    assert actual.get_stato_settimana(CURRENT_WEEK) == "BOZZA"
    assert not list(demo_data.rglob("*.tmp"))


def test_failed_logbook_write_rolls_back_plan_patients_and_activities(
    demo_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual = _rooms(demo_data, actual=True)
    _, operation = _week_operations(actual, CURRENT_WEEK)[0]
    failure_path = demo_data / "libretti" / f"{operation['id_specializzando']}.json"
    before = json_bytes(demo_data)
    real_replace = patient_plan_state.os.replace
    failed = False

    def fail_one_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal failed
        if Path(destination) == failure_path and not failed:
            failed = True
            raise OSError("Synthetic logbook write failure")
        real_replace(source, destination)

    monkeypatch.setattr(patient_plan_state.os, "replace", fail_one_replace)
    with pytest.raises(OSError, match="Synthetic logbook"):
        actual.convalida_settimana(CURRENT_WEEK, dir_libretti=demo_data / "libretti")
    assert failed
    assert json_bytes(demo_data) == before
    assert actual.get_stato_settimana(CURRENT_WEEK) == "BOZZA"
    assert not list(demo_data.rglob("*.tmp"))


def test_recreating_actual_never_overwrites_existing_corrections(demo_data: Path) -> None:
    actual = _rooms(demo_data, actual=True)
    day_text, _ = _week_operations(actual, CURRENT_WEEK)[0]
    actual.set_operazioni(day_text, [])
    before = json_bytes(demo_data)
    with pytest.raises(CalendarVersionError, match="esiste già"):
        _rooms(demo_data).crea_effettivo_settimana(CURRENT_WEEK)
    assert json_bytes(demo_data) == before


def test_current_actual_roster_is_editable_while_confirmed_rosters_are_preserved(
    demo_data: Path,
) -> None:
    planned = DataManager(demo_data / "scadenzario", demo_data / "libretti")
    actual = planned.for_version(CalendarVersion.EFFETTIVO)
    original = _planned_bytes(demo_data)
    month = actual.load_mese(2026, 10)
    day_text = CURRENT_WEEK.isoformat()
    used = set(month["turni"][day_text].values()) | {month["giro_visite"][day_text]}
    available = next(label for label in planned.get_specializzandi_attivi() if label not in used)
    actual.set_valore_cella(day_text, "Reparto I", available)
    assert actual.get_valore_cella(day_text, "Reparto I") == available
    assert _planned_bytes(demo_data) == original
    with pytest.raises(CalendarVersionError):
        planned.set_valore_cella(day_text, "Reparto I", available)
    with pytest.raises(CalendarVersionError):
        actual.set_valore_cella("2026-09-28", "Reparto I", available)


def test_round_crossing_confirmed_september_cannot_be_partially_changed(demo_data: Path) -> None:
    planned = DataManager(demo_data / "scadenzario", demo_data / "libretti")
    actual = planned.for_version(CalendarVersion.EFFETTIVO)
    before = json_bytes(demo_data)
    with pytest.raises(ValueError, match="convalidato"):
        actual.set_giro_visite_settimana("2026-09-28", 2026, 9, "")
    assert json_bytes(demo_data) == before


def test_planning_requires_confirmed_roster_then_excludes_other_week_reservations(
    demo_data: Path,
) -> None:
    week = date(2026, 11, 2)
    before = json_bytes(demo_data)
    with pytest.raises(PlatformDataError, match="convalidare"):
        load_platform_context(demo_data.parent, week, data_directory=demo_data)
    assert json_bytes(demo_data) == before
    planned = DataManager(demo_data / "scadenzario", demo_data / "libretti")
    planned.convalida_mese(2026, 11)
    assert planned.for_version(CalendarVersion.EFFETTIVO).get_stato_mese(2026, 11) == "BOZZA"
    context = load_platform_context(demo_data.parent, week, data_directory=demo_data)
    waiting = {
        identifier
        for identifier, state in _patient_states(demo_data).items()
        if state == "In Attesa"
    }
    current = {
        operation["id_paziente"] for _, operation in _week_operations(_rooms(demo_data), week)
    }
    assert {
        patient.patient_id for patient in context.scheduling_input.patients
    } == waiting | current
    assert len(context.scheduling_input.sessions) == 10
    assert _activity_count(demo_data) == 38
