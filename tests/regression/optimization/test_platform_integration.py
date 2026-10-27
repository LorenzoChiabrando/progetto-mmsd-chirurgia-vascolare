from __future__ import annotations

import json
import stat
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pyomo.core as pyo
import pytest

from src.optimization import (
    HighsSolver,
    SolveStatus,
    build_platform_model,
    platform_io,
    platform_service,
)
from src.optimization.domain import PatientCategory
from src.optimization.exceptions import (
    PlanningCancelledError,
    PlatformDataError,
    PlatformPersistenceError,
)
from src.optimization.platform_io import load_platform_context, persist_platform_week_plan
from src.optimization.platform_mapping import (
    PlatformPlanningPolicy,
    map_result_to_platform_plan,
)
from src.optimization.platform_service import plan_platform_week
from src.optimization.results import ObjectiveBreakdown, ScheduledSurgery, SolveResult
from src.planning_schema import (
    OPTIMIZATION_KEY,
    default_schedule_optimization,
)

MONDAY = date(2026, 5, 4)
CROSS_MONTH_MONDAY = date(2026, 6, 29)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")


def _build_platform_root(
    tmp_path: Path,
    *,
    monday: date = MONDAY,
    week_state: str = "BOZZA",
) -> Path:
    root = tmp_path / "platform"
    residents = (
        {
            "id": "R1",
            "nome": "Resident",
            "cognome": "Alpha",
            "livello": "Junior",
            "stato": "Molinette",
        },
        {
            "id": "R2",
            "nome": "Resident",
            "cognome": "Beta",
            "livello": "Senior",
            "stato": "Molinette",
        },
    )
    for resident in residents:
        _write_json(root / "mock_data" / "libretti" / f"{resident['id']}.json", resident)

    patients = (
        {
            "id": "P1",
            "nome": "One",
            "cognome": "Synthetic",
            "diagnosi": "Synthetic diagnosis",
            "codice_intervento": "SYN-A",
            "descrizione_intervento": "Synthetic procedure A",
            "interventi": [],
            "durata_intervento": 120,
            "tipo_chirurgia": "Aperta",
            "complessita": "Alta",
            "urgenza": "Alta",
            "stato": "In Attesa",
            "data_inserimento": "01/05/2026",
            OPTIMIZATION_KEY: {
                "versione_schema": 1,
                "categoria_paper": "I'",
                "attesa_massima_giorni": 30,
                "specializzandi_abilitati": ["R2"],
            },
        },
        {
            "id": "P2",
            "nome": "Two",
            "cognome": "Synthetic",
            "diagnosi": "Synthetic diagnosis",
            "codice_intervento": "SYN-B",
            "descrizione_intervento": "Synthetic procedure B",
            "interventi": [],
            "durata_intervento": 90,
            "tipo_chirurgia": "Aperta",
            "complessita": "Media",
            "urgenza": "Media",
            "stato": "In Attesa",
            "data_inserimento": "01/05/2026",
            OPTIMIZATION_KEY: {
                "versione_schema": 1,
                "categoria_paper": "I'",
                "attesa_massima_giorni": 60,
                "specializzandi_abilitati": ["R1"],
            },
        },
    )
    for patient in patients:
        _write_json(root / "mock_data" / "pazienti" / f"{patient['id']}.json", patient)

    scadenzario_by_month: dict[str, dict] = {}
    sale_by_month: dict[str, dict] = {}
    for offset in range(5):
        current_day = monday + timedelta(days=offset)
        day = current_day.isoformat()
        month_key = current_day.strftime("%Y-%m")
        scadenzario = scadenzario_by_month.setdefault(
            month_key,
            {
                "metadata": {"stato": "CONVALIDATO"},
                "turni": {},
                OPTIMIZATION_KEY: default_schedule_optimization(),
            },
        )
        sale = sale_by_month.setdefault(
            month_key,
            {"metadata": {"stato": "BOZZA", "settimane": {}}, "turni": {}},
        )
        scadenzario["turni"][day] = {
            "Sala Op. I": "Alpha R.",
            "Sala Op. II": "Beta R.",
        }
        sale["turni"][day] = {
            "specializzandi": {"OR I": "Alpha R.", "OR II": "Beta R."},
            "operazioni": ([{"id_paziente": "OLD"}] if offset == 0 else []),
        }
    canonical_month = monday.strftime("%Y-%m")
    sale_by_month[canonical_month]["metadata"]["settimane"][monday.isoformat()] = week_state
    unrelated_day = monday + timedelta(days=16)
    unrelated_month = unrelated_day.strftime("%Y-%m")
    sale_by_month.setdefault(
        unrelated_month,
        {"metadata": {"stato": "BOZZA", "settimane": {}}, "turni": {}},
    )["turni"][unrelated_day.isoformat()] = {"preserved": True}

    for month_key, payload in scadenzario_by_month.items():
        _write_json(root / "mock_data" / "scadenzario" / f"{month_key}.json", payload)
    for month_key, payload in sale_by_month.items():
        _write_json(root / "mock_data" / "sale_operatorie" / f"{month_key}.json", payload)
    return root


def _manual_result(monday: date = MONDAY) -> SolveResult:
    return SolveResult(
        status=SolveStatus.OPTIMAL,
        termination_condition="optimal",
        solver_name="HiGHS",
        solver_version="test",
        elapsed_seconds=0.0,
        schedule=(
            ScheduledSurgery("P2", "OR-1", monday, "R1"),
            ScheduledSurgery("P1", "OR-2", monday, "R2"),
        ),
        objective=ObjectiveBreakdown(
            treatment_efficiency=0.15,
            fairness_floor=1,
            unassigned_count=0,
            weighted_total=28.0,
        ),
    )


def test_real_json_mapper_uses_roster_and_changeover(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path)
    context = load_platform_context(root, MONDAY)

    plan = map_result_to_platform_plan(context, _manual_result())

    first_day = plan.days[0]
    assert [operation["id_paziente"] for operation in first_day.operations] == ["P2", "P1"]
    assert first_day.operations[0]["ora_inizio"] == "08:00"
    assert first_day.operations[0]["ora_fine"] == "09:30"
    assert first_day.operations[1]["ora_inizio"] == "08:00"
    assert first_day.operations[1]["ora_fine"] == "10:00"
    assert first_day.operations[0]["sala_operatoria"] == "OR-1"
    assert first_day.operations[1]["sala_operatoria"] == "OR-2"
    assert first_day.operations[0]["id_specializzando"] == "R1"
    assert first_day.operations[1]["ruolo_specializzando"] == "OR II"
    assert first_day.operations[0]["chirurgo"] == ""


def test_loader_builds_two_physical_rooms_and_honours_daily_capacity_override(
    tmp_path: Path,
) -> None:
    root = _build_platform_root(tmp_path)
    source = root / "mock_data" / "scadenzario" / "2026-05.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload[OPTIMIZATION_KEY]["capacita_sessioni"] = {MONDAY.isoformat(): {"OR-2": 480}}
    _write_json(source, payload)

    context = load_platform_context(root, MONDAY)
    sessions = {
        (session.day, session.room_id): session for session in context.scheduling_input.sessions
    }

    assert len(sessions) == 10
    assert sessions[MONDAY, "OR-1"].capacity_minutes == 600
    assert sessions[MONDAY, "OR-2"].capacity_minutes == 480
    assert sessions[MONDAY, "OR-1"].available_resident_ids == frozenset({"R1"})
    assert sessions[MONDAY, "OR-2"].available_resident_ids == frozenset({"R2"})


def test_loader_infers_h_jl_from_resident_training_level(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path)

    context = load_platform_context(root, MONDAY)
    qualifications = {
        resident.resident_id: resident.qualified_levels
        for resident in context.scheduling_input.residents
    }

    assert qualifications == {
        "R1": frozenset({"Bassa", "Media", "Alta"}),
        "R2": frozenset({"Alta"}),
    }


@pytest.mark.parametrize("monday", [MONDAY, CROSS_MONTH_MONDAY])
def test_roster_parameter_tracks_the_exact_room_and_day_from_calendar(
    tmp_path: Path,
    monday: date,
) -> None:
    root = _build_platform_root(tmp_path, monday=monday)
    swapped_day = monday + timedelta(days=2)
    source = root / "mock_data" / "scadenzario" / f"{swapped_day:%Y-%m}.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["turni"][swapped_day.isoformat()] = {
        "Sala Op. I": "Beta R.",
        "Sala Op. II": "Alpha R.",
    }
    _write_json(source, payload)

    context = load_platform_context(root, monday)
    model = build_platform_model(context.scheduling_input).model

    for session in context.scheduling_input.sessions:
        expected_id = "R1" if session.room_id == "OR-1" else "R2"
        if session.day == swapped_day:
            expected_id = "R2" if expected_id == "R1" else "R1"
        assert session.assigned_resident_ids == frozenset({expected_id})
        for resident_id in ("R1", "R2"):
            value = model.resident_roster_assignment[(resident_id, *session.key)]
            assert pyo.value(value) == int(resident_id == expected_id)


@pytest.mark.parametrize("legacy_ids", [None, [], ["UNKNOWN"], ["R2"]])
def test_mapper_does_not_require_or_use_obsolete_patient_qualifications(
    tmp_path: Path,
    legacy_ids: list[str] | None,
) -> None:
    root = _build_platform_root(tmp_path)
    source = root / "mock_data" / "pazienti" / "P1.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    if legacy_ids is None:
        payload[OPTIMIZATION_KEY].pop("specializzandi_abilitati")
    else:
        payload[OPTIMIZATION_KEY]["specializzandi_abilitati"] = legacy_ids
    _write_json(source, payload)
    before = source.read_bytes()

    context = load_platform_context(root, MONDAY)
    model = build_platform_model(context.scheduling_input).model

    assert not hasattr(model, "patient_resident_qualification")
    key = ("P1", "R1", "OR-1", MONDAY.isoformat())
    model.x["P1", "OR-1", MONDAY.isoformat()].set_value(1)
    model.y[key].set_value(0)
    assert pyo.value(model.rostered_resident_requirement[key].body) == 1
    assert source.read_bytes() == before


def test_loader_refuses_unknown_resident_training_level(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path)
    source = root / "mock_data" / "libretti" / "R2.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["livello"] = "Non configurato"
    _write_json(source, payload)

    with pytest.raises(PlatformDataError, match="livello formativo non gestito"):
        load_platform_context(root, MONDAY)


def test_loader_refuses_unclassified_patient_complexity(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path)
    source = root / "mock_data" / "pazienti" / "P1.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["complessita"] = "Da classificare"
    _write_json(source, payload)

    with pytest.raises(PlatformDataError, match="complessità non gestita"):
        load_platform_context(root, MONDAY)


def test_json_mapper_populates_all_three_patient_partitions_from_the_paper(
    tmp_path: Path,
) -> None:
    root = _build_platform_root(tmp_path)
    patients_directory = root / "mock_data" / "pazienti"
    first_path = patients_directory / "P1.json"
    second_path = patients_directory / "P2.json"
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    first[OPTIMIZATION_KEY]["categoria_paper"] = "I'"
    second[OPTIMIZATION_KEY]["categoria_paper"] = "I''"
    rescheduled = {
        **first,
        "id": "P3",
        OPTIMIZATION_KEY: {
            **first[OPTIMIZATION_KEY],
            "categoria_paper": "I'''",
        },
    }
    _write_json(first_path, first)
    _write_json(second_path, second)
    _write_json(patients_directory / "P3.json", rescheduled)

    context = load_platform_context(root, MONDAY)
    categories = {
        patient.patient_id: patient.category for patient in context.scheduling_input.patients
    }

    assert categories == {
        "P1": PatientCategory.WAITING_LIST,
        "P2": PatientCategory.MANDATORY,
        "P3": PatientCategory.RESCHEDULED,
    }


@pytest.mark.parametrize(
    "source_state",
    ("BOZZA", "convalidato", None),
    ids=("draft", "lowercase", "missing"),
)
def test_loader_refuses_non_convalidated_scadenzario_without_touching_target(
    tmp_path: Path,
    source_state: str | None,
) -> None:
    root = _build_platform_root(tmp_path)
    source = root / "mock_data" / "scadenzario" / "2026-05.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    if source_state is None:
        payload["metadata"].pop("stato")
    else:
        payload["metadata"]["stato"] = source_state
    _write_json(source, payload)
    target = root / "mock_data" / "sale_operatorie" / "2026-05.json"
    before = target.read_bytes()

    with pytest.raises(PlatformDataError, match=r"convalidare lo scadenzario.*maggio 2026"):
        load_platform_context(root, MONDAY)

    assert target.read_bytes() == before


@pytest.mark.parametrize("unconfirmed_month", ("2026-06", "2026-07"))
def test_cross_month_week_requires_both_scadenzario_months(
    tmp_path: Path,
    unconfirmed_month: str,
) -> None:
    root = _build_platform_root(tmp_path, monday=CROSS_MONTH_MONDAY)
    source = root / "mock_data" / "scadenzario" / f"{unconfirmed_month}.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["metadata"]["stato"] = "BOZZA"
    _write_json(source, payload)
    target_directory = root / "mock_data" / "sale_operatorie"
    before = {path.name: path.read_bytes() for path in target_directory.glob("*.json")}

    expected_month = {"2026-06": "giugno 2026", "2026-07": "luglio 2026"}[unconfirmed_month]
    with pytest.raises(PlatformDataError, match=rf"convalidare lo scadenzario.*{expected_month}"):
        load_platform_context(root, CROSS_MONTH_MONDAY)

    assert before == {path.name: path.read_bytes() for path in target_directory.glob("*.json")}


def test_writer_rechecks_scadenzario_state_immediately_before_commit(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path)
    context = load_platform_context(root, MONDAY)
    plan = map_result_to_platform_plan(context, _manual_result())
    source = root / "mock_data" / "scadenzario" / "2026-05.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["metadata"]["stato"] = "BOZZA"
    _write_json(source, payload)
    target = root / "mock_data" / "sale_operatorie" / "2026-05.json"
    before = target.read_bytes()

    with pytest.raises(PlatformDataError, match=r"convalidare lo scadenzario.*maggio 2026"):
        persist_platform_week_plan(root, plan, overwrite=True)

    assert target.read_bytes() == before


def test_cross_month_writer_refuses_any_convalidated_target_month(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path, monday=CROSS_MONTH_MONDAY)
    context = load_platform_context(root, CROSS_MONTH_MONDAY)
    plan = map_result_to_platform_plan(
        context,
        _manual_result(CROSS_MONTH_MONDAY),
    )
    july_target = root / "mock_data" / "sale_operatorie" / "2026-07.json"
    payload = json.loads(july_target.read_text(encoding="utf-8"))
    payload["metadata"]["stato"] = "CONVALIDATO"
    _write_json(july_target, payload)
    target_directory = root / "mock_data" / "sale_operatorie"
    before = {path.name: path.read_bytes() for path in target_directory.glob("*.json")}

    with pytest.raises(
        PlatformPersistenceError, match=r"sale operatorie.*convalidate.*luglio 2026"
    ):
        persist_platform_week_plan(root, plan, overwrite=True)

    assert before == {path.name: path.read_bytes() for path in target_directory.glob("*.json")}


def test_atomic_writer_requires_explicit_overwrite(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path)
    context = load_platform_context(root, MONDAY)
    plan = map_result_to_platform_plan(context, _manual_result())
    target = root / "mock_data" / "sale_operatorie" / "2026-05.json"
    before = target.read_bytes()

    with pytest.raises(PlatformPersistenceError, match="conferma la sovrascrittura"):
        persist_platform_week_plan(root, plan, overwrite=False)

    assert target.read_bytes() == before


def test_atomic_writer_preserves_metadata_roster_and_unrelated_days(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path)
    context = load_platform_context(root, MONDAY)
    plan = map_result_to_platform_plan(context, _manual_result())
    backup_directory = tmp_path / "private-backup"

    receipt = persist_platform_week_plan(
        root,
        plan,
        overwrite=True,
        backup_directory=backup_directory,
    )

    stored = json.loads(receipt.updated_paths[0].read_text(encoding="utf-8"))
    assert stored["metadata"]["settimane"][MONDAY.isoformat()] == "BOZZA"
    assert stored["turni"]["2026-05-20"] == {"preserved": True}
    assert stored["turni"][MONDAY.isoformat()]["specializzandi"] == {
        "OR I": "Alpha R.",
        "OR II": "Beta R.",
    }
    assert len(stored["turni"][MONDAY.isoformat()]["operazioni"]) == 2
    assert len(receipt.backup_paths) == 3
    assert receipt.backup_paths[0].exists()
    assert stat.S_IMODE(backup_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(receipt.backup_paths[0].stat().st_mode) == 0o600


def test_atomic_writer_refuses_convalidated_week_without_changes(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path, week_state="CONVALIDATO")
    context = load_platform_context(root, MONDAY)
    plan = map_result_to_platform_plan(context, _manual_result())
    target = root / "mock_data" / "sale_operatorie" / "2026-05.json"
    before = target.read_bytes()

    with pytest.raises(PlatformPersistenceError, match="settimana è già convalidata"):
        persist_platform_week_plan(root, plan, overwrite=True)

    assert target.read_bytes() == before


def test_atomic_writer_rolls_back_after_temporary_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _build_platform_root(tmp_path)
    context = load_platform_context(root, MONDAY)
    plan = map_result_to_platform_plan(context, _manual_result())
    target = root / "mock_data" / "sale_operatorie" / "2026-05.json"
    before = target.read_bytes()

    def fail_write(*_args: object, **_kwargs: object) -> Path:
        raise OSError("synthetic temporary write failure")

    monkeypatch.setattr(platform_io, "_write_json_temporary", fail_write)

    with pytest.raises(PlatformPersistenceError, match="dati precedenti sono stati ripristinati"):
        persist_platform_week_plan(
            root,
            plan,
            overwrite=True,
            backup_directory=tmp_path / "backup",
        )

    assert target.read_bytes() == before


def test_platform_service_cancellation_after_solve_does_not_persist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _build_platform_root(tmp_path)
    target = root / "mock_data" / "sale_operatorie" / "2026-05.json"
    before = target.read_bytes()
    cancellation = {"requested": False}

    class CancellingSolver:
        def __init__(self, _config: object) -> None:
            pass

        def solve(self, _built: object, *, cancel_requested: object) -> SolveResult:
            assert cancel_requested is not None
            cancellation["requested"] = True
            return _manual_result()

    monkeypatch.setattr(platform_service, "HighsSolver", CancellingSolver)

    with pytest.raises(
        PlanningCancelledError, match="Pianificazione annullata prima del salvataggio"
    ):
        plan_platform_week(
            root,
            MONDAY,
            overwrite=True,
            persist=True,
            cancel_requested=lambda: cancellation["requested"],
        )

    assert cancellation["requested"] is True
    assert target.read_bytes() == before


@pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")
def test_platform_service_solves_and_persists_end_to_end(tmp_path: Path) -> None:
    root = _build_platform_root(tmp_path)
    patient_bytes = {
        path.name: path.read_bytes() for path in (root / "mock_data" / "pazienti").glob("*.json")
    }

    run = plan_platform_week(
        root,
        MONDAY,
        overwrite=True,
        persist=True,
        backup_directory=tmp_path / "backup",
        policy=PlatformPlanningPolicy(),
    )

    assert run.result.status is SolveStatus.OPTIMAL
    assert len(run.result.schedule) == 2
    assert run.write_receipt is not None
    stored = json.loads(
        (root / "mock_data" / "sale_operatorie" / "2026-05.json").read_text(encoding="utf-8")
    )
    operations = [
        operation
        for offset in range(5)
        for operation in stored["turni"][(MONDAY + timedelta(days=offset)).isoformat()][
            "operazioni"
        ]
    ]
    assert len(operations) == 2
    assert all("id_specializzando" in operation for operation in operations)
    for path in (root / "mock_data" / "pazienti").glob("*.json"):
        assert json.loads(path.read_text()) == {
            **json.loads(patient_bytes[path.name]),
            "stato": "Pianificato",
        }


def test_windows_lock_branch_uses_msvcrt_without_opening_a_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    fake_msvcrt = SimpleNamespace(
        LK_LOCK=1,
        LK_UNLCK=2,
        locking=lambda _descriptor, mode, _length: calls.append(mode),
    )
    monkeypatch.setattr(platform_io.os, "name", "nt")
    monkeypatch.setattr(platform_io, "msvcrt", fake_msvcrt, raising=False)

    with platform_io._directory_lock(tmp_path):
        assert (tmp_path / ".mmsd-planning.lock").is_file()

    assert calls == [fake_msvcrt.LK_LOCK, fake_msvcrt.LK_UNLCK]
