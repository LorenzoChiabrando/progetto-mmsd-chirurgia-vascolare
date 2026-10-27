"""Release checks using disposable JSON catalogs, including known integration gaps."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from src.models import data_manager_pazienti
from src.models.data_manager_pazienti import DataManagerPazienti
from src.optimization import HighsSolver, SolveStatus, platform_io
from src.optimization.exceptions import PlatformDataError, PlatformPersistenceError
from src.optimization.platform_io import load_platform_context, persist_platform_week_plan
from src.optimization.platform_service import plan_platform_week
from src.planning_schema import OPTIMIZATION_KEY, default_schedule_optimization

MONDAY = date(2026, 9, 21)
NEXT_MONDAY = MONDAY + timedelta(days=7)
requires_highs = pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def synthetic_root(tmp_path: Path) -> Path:
    root = tmp_path / "platform"
    for resident_id, surname in (("R1", "Alpha"), ("R2", "Beta")):
        _write_json(
            root / "mock_data/libretti" / f"{resident_id}.json",
            {
                "id": resident_id,
                "nome": "Test",
                "cognome": surname,
                "livello": "Junior",
                "stato": "Molinette",
            },
        )
    for index in range(2):
        _write_json(
            root / "mock_data/pazienti" / f"P{index}.json",
            {
                "id": f"P{index}",
                "nome": "Synthetic",
                "cognome": f"Case{index}",
                "stato": "In Attesa",
                "data_inserimento": "01/09/2026",
                "durata_intervento": 60,
                "complessita": "Bassa",
                "urgenza": "Alta",
                "interventi": [{"codice": "TEST", "descrizione": "Synthetic", "durata": 60}],
                OPTIMIZATION_KEY: {
                    "versione_schema": 1,
                    "categoria_paper": "I'",
                    "attesa_massima_giorni": 30,
                },
            },
        )
    months: dict[str, dict] = {}
    for monday in (MONDAY, NEXT_MONDAY):
        for offset in range(5):
            day = monday + timedelta(days=offset)
            month = months.setdefault(
                day.strftime("%Y-%m"),
                {
                    "metadata": {"stato": "CONVALIDATO"},
                    "turni": {},
                    OPTIMIZATION_KEY: default_schedule_optimization(),
                },
            )
            month["turni"][day.isoformat()] = {
                "Sala Op. I": "Alpha T.",
                "Sala Op. II": "Beta T.",
            }
    for key, payload in months.items():
        _write_json(root / "mock_data/scadenzario" / f"{key}.json", payload)
        _write_json(
            root / "mock_data/sale_operatorie" / f"{key}.json",
            {"metadata": {"stato": "BOZZA", "settimane": {}}, "turni": {}},
        )
    return root


@requires_highs
@pytest.mark.parametrize("monday", [MONDAY, NEXT_MONDAY])
def test_full_pipeline_updates_patient_state_and_preserves_other_fields(
    synthetic_root: Path,
    monday: date,
) -> None:
    patient_paths = sorted((synthetic_root / "mock_data/pazienti").glob("*.json"))
    originals = {path: path.read_bytes() for path in patient_paths}
    run = plan_platform_week(synthetic_root, monday, persist=True)

    assert run.result.status is SolveStatus.OPTIMAL
    assert {item.patient_id for item in run.result.schedule} == {"P0", "P1"}
    assert run.write_receipt is not None
    assert len(run.write_receipt.updated_paths) == (4 if monday == NEXT_MONDAY else 3)
    for path in patient_paths:
        assert _read_json(path) == {**json.loads(originals[path]), "stato": "Pianificato"}
    for day in run.plan.days:
        saved = _read_json(synthetic_root / "mock_data/sale_operatorie" / f"{day.day:%Y-%m}.json")[
            "turni"
        ][day.day.isoformat()]["operazioni"]
        assert saved == list(day.operations)
        roster_ids = {assignment.room_id: assignment.resident_id for assignment in day.roster}
        for operation in saved:
            assert operation["id_specializzando"] == roster_ids[operation["sala_operatoria"]]
            assert operation["durata"] == 60


def test_numerical_solver_inputs_come_from_json_not_displayed_priority(
    synthetic_root: Path,
) -> None:
    source = synthetic_root / "mock_data/pazienti/P0.json"
    record = _read_json(source)
    record["durata_intervento"] = 73
    record["interventi"][0]["durata"] = 73
    record["urgenza"] = "Bassa"
    record[OPTIMIZATION_KEY]["attesa_massima_giorni"] = 40
    _write_json(source, record)

    context = load_platform_context(synthetic_root, MONDAY)
    patient = next(p for p in context.scheduling_input.patients if p.patient_id == "P0")
    assert patient.duration_minutes == 73
    assert patient.waiting_time_days == 20
    assert patient.max_wait_days == 40
    assert patient.urgency == pytest.approx(0.5)


def test_patient_creation_uses_import_day_as_the_waiting_time_origin(
    synthetic_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ImportClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 17)

    monkeypatch.setattr(data_manager_pazienti, "datetime", ImportClock)
    record = _read_json(synthetic_root / "mock_data/pazienti/P0.json")
    assert record["data_inserimento"] == "01/09/2026"
    manager = DataManagerPazienti(str(synthetic_root / "mock_data/pazienti"))
    saved = manager.crea_nuovo_paziente(record)
    assert saved["data_inserimento"] == "17/09/2026"
    context = load_platform_context(synthetic_root, MONDAY)
    patient = next(p for p in context.scheduling_input.patients if p.patient_id == saved["id"])
    assert patient.waiting_time_days == 4
    assert patient.urgency == pytest.approx(4 / 30)


@pytest.mark.parametrize(("insertion_offset", "expected_wait"), [(-5, 5), (0, 0), (2, -2), (7, -7)])
def test_recent_patients_keep_signed_wait_without_blocking_the_week(
    synthetic_root: Path,
    insertion_offset: int,
    expected_wait: int,
) -> None:
    source = synthetic_root / "mock_data/pazienti/P0.json"
    record = _read_json(source)
    record["data_inserimento"] = (MONDAY + timedelta(days=insertion_offset)).strftime("%d/%m/%Y")
    _write_json(source, record)
    target = synthetic_root / "mock_data/sale_operatorie/2026-09.json"
    before = target.read_bytes()

    context = load_platform_context(synthetic_root, MONDAY)
    assert len(context.scheduling_input.patients) == 2
    patient = next(p for p in context.scheduling_input.patients if p.patient_id == "P0")
    assert patient.waiting_time_days == expected_wait
    assert patient.urgency == pytest.approx(expected_wait / 30)
    assert patient.earliest_surgery_date == MONDAY + timedelta(days=insertion_offset)
    assert target.read_bytes() == before


@requires_highs
def test_normal_sequential_planning_excludes_patients_in_other_drafts(
    synthetic_root: Path,
) -> None:
    plan_platform_week(synthetic_root, MONDAY, persist=True)
    with pytest.raises(
        PlatformDataError, match="Non ci sono pazienti in lista d'attesa pianificabili"
    ):
        load_platform_context(synthetic_root, NEXT_MONDAY)


@requires_highs
@pytest.mark.parametrize("monday", [MONDAY, NEXT_MONDAY])
def test_regeneration_keeps_current_week_planned_patients_eligible(
    synthetic_root: Path,
    monday: date,
) -> None:
    first = plan_platform_week(synthetic_root, monday, persist=True)
    context = load_platform_context(synthetic_root, monday)
    assert {patient.patient_id for patient in context.scheduling_input.patients} == {"P0", "P1"}
    second = plan_platform_week(synthetic_root, monday, persist=True, overwrite=True)
    assert {item.patient_id for item in second.result.schedule} == {
        item.patient_id for item in first.result.schedule
    }
    assert all(
        _read_json(path)["stato"] == "Pianificato"
        for path in (synthetic_root / "mock_data/pazienti").glob("*.json")
    )


@requires_highs
def test_replacing_a_plan_releases_removed_patients_for_the_next_week(
    synthetic_root: Path,
) -> None:
    run = plan_platform_week(synthetic_root, MONDAY, persist=True)
    reduced_plan = replace(
        run.plan,
        days=tuple(
            replace(
                day,
                operations=tuple(
                    operation for operation in day.operations if operation["id_paziente"] != "P0"
                ),
            )
            for day in run.plan.days
        ),
    )
    persist_platform_week_plan(synthetic_root, reduced_plan, overwrite=True)
    assert _read_json(synthetic_root / "mock_data/pazienti/P0.json")["stato"] == "In Attesa"
    assert _read_json(synthetic_root / "mock_data/pazienti/P1.json")["stato"] == "Pianificato"
    next_context = load_platform_context(synthetic_root, NEXT_MONDAY)
    assert {patient.patient_id for patient in next_context.scheduling_input.patients} == {"P0"}
    assert next_context.excluded_other_draft_count == 1


@pytest.mark.parametrize("linked", [False, True])
def test_a_planned_patient_requires_a_reservation_in_the_selected_week(
    synthetic_root: Path,
    linked: bool,
) -> None:
    source = synthetic_root / "mock_data/pazienti/P0.json"
    record = _read_json(source)
    record["stato"] = "Pianificato"
    _write_json(source, record)
    if linked:
        target = synthetic_root / "mock_data/sale_operatorie/2026-09.json"
        month = _read_json(target)
        month["turni"][MONDAY.isoformat()] = {"operazioni": [{"id_paziente": "P0"}]}
        _write_json(target, month)
    context = load_platform_context(synthetic_root, MONDAY)
    assert {patient.patient_id for patient in context.scheduling_input.patients} == (
        {"P0", "P1"} if linked else {"P1"}
    )


@requires_highs
def test_solve_without_persistence_does_not_mark_patients_planned(synthetic_root: Path) -> None:
    paths = list((synthetic_root / "mock_data").rglob("*.json"))
    originals = {path: path.read_bytes() for path in paths}
    run = plan_platform_week(synthetic_root, MONDAY, persist=False)
    assert run.result.has_solution
    assert {path: path.read_bytes() for path in paths} == originals


@requires_highs
def test_patient_write_failure_rolls_back_plan_and_already_updated_patients(
    synthetic_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = plan_platform_week(synthetic_root, NEXT_MONDAY, persist=False)
    paths = list((synthetic_root / "mock_data").rglob("*.json"))
    originals = {path: path.read_bytes() for path in paths}
    real_replace = platform_io.os.replace
    failed = False

    def fail_last_patient_once(source, destination) -> None:
        nonlocal failed
        if Path(destination).name == "P1.json" and not failed:
            failed = True
            raise OSError("synthetic patient write failure")
        real_replace(source, destination)

    monkeypatch.setattr(platform_io.os, "replace", fail_last_patient_once)
    with pytest.raises(PlatformPersistenceError, match="dati precedenti sono stati ripristinati"):
        persist_platform_week_plan(synthetic_root, run.plan, overwrite=False)
    assert failed
    assert {path: path.read_bytes() for path in paths} == originals
    assert not list((synthetic_root / "mock_data").rglob("*.tmp"))


@requires_highs
def test_negative_wait_patient_does_not_block_real_solver(synthetic_root: Path) -> None:
    source = synthetic_root / "mock_data/pazienti/P0.json"
    record = _read_json(source)
    record["data_inserimento"] = (MONDAY + timedelta(days=2)).strftime("%d/%m/%Y")
    _write_json(source, record)
    run = plan_platform_week(synthetic_root, MONDAY, persist=True)
    assert run.result.status is SolveStatus.OPTIMAL
    patient = next(p for p in run.context.scheduling_input.patients if p.patient_id == "P0")
    assert patient.waiting_time_days == -2
    assert patient.urgency == pytest.approx(-2 / 30)
    assert all(
        item.day >= patient.earliest_surgery_date
        for item in run.result.schedule
        if item.patient_id == "P0"
    )
    assert _read_json(source)["stato"] == (
        "Pianificato"
        if any(item.patient_id == "P0" for item in run.result.schedule)
        else "In Attesa"
    )


@requires_highs
@pytest.mark.parametrize("changed_input", ["roster", "capacity", "patient_status", "duration"])
def test_commit_should_reject_a_stale_input_snapshot(
    synthetic_root: Path,
    changed_input: str,
) -> None:
    run = plan_platform_week(synthetic_root, MONDAY, persist=False)
    if changed_input in {"roster", "capacity"}:
        source = synthetic_root / "mock_data/scadenzario/2026-09.json"
        record = _read_json(source)
        if changed_input == "roster":
            for daily in record["turni"].values():
                daily["Sala Op. I"], daily["Sala Op. II"] = (
                    daily["Sala Op. II"],
                    daily["Sala Op. I"],
                )
        else:
            for room in record[OPTIMIZATION_KEY]["sale_operatorie"].values():
                room["capacita_minuti"] = 1
    else:
        source = synthetic_root / "mock_data/pazienti/P0.json"
        record = _read_json(source)
        if changed_input == "patient_status":
            record["stato"] = "Completato"
        else:
            record["durata_intervento"] = 1000
    _write_json(source, record)
    target = synthetic_root / "mock_data/sale_operatorie/2026-09.json"
    before = target.read_bytes()

    with pytest.raises((PlatformDataError, PlatformPersistenceError)):
        persist_platform_week_plan(synthetic_root, run.plan, overwrite=False)
    assert target.read_bytes() == before


@requires_highs
def test_commit_should_recheck_other_week_reservations_under_the_lock(
    synthetic_root: Path,
) -> None:
    first = plan_platform_week(synthetic_root, MONDAY, persist=False)
    second = plan_platform_week(synthetic_root, NEXT_MONDAY, persist=False)
    assert {item.patient_id for item in first.result.schedule} == {"P0", "P1"}
    assert {item.patient_id for item in second.result.schedule} == {"P0", "P1"}
    persist_platform_week_plan(synthetic_root, first.plan, overwrite=False)

    with pytest.raises((PlatformDataError, PlatformPersistenceError)):
        persist_platform_week_plan(synthetic_root, second.plan, overwrite=False)


def test_input_validation_should_reject_conflicting_duration_fields(
    synthetic_root: Path,
) -> None:
    source = synthetic_root / "mock_data/pazienti/P0.json"
    record = _read_json(source)
    record["interventi"][0]["durata"] = 120
    assert record["durata_intervento"] == 60
    _write_json(source, record)
    with pytest.raises(PlatformDataError):
        load_platform_context(synthetic_root, MONDAY)


@requires_highs
def test_h_zero_does_not_prevent_platform_assignment(synthetic_root: Path) -> None:
    for source in (synthetic_root / "mock_data/libretti").glob("*.json"):
        resident = _read_json(source)
        resident["livello"] = "Senior"
        _write_json(source, resident)

    run = plan_platform_week(synthetic_root, MONDAY, persist=False)
    assert all(
        "Bassa" not in resident.qualified_levels
        for resident in run.context.scheduling_input.residents
    )
    assert len(run.result.schedule) == 2
    assert all(item.resident_id is not None for item in run.result.schedule)
    assert run.result.objective is not None
    assert run.result.objective.unassigned_count == 0
