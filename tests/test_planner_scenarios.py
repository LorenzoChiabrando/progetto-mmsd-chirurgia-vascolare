"""Independent feasibility checks and end-to-end solves for the four-month demo."""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from itertools import product
from pathlib import Path
from types import SimpleNamespace

import pyomo.core as pyo
import pytest
from pyomo.contrib.appsi.base import TerminationCondition

from scripts.reset_demo_data import build_demo_snapshot
from src.models.data_manager import DataManager
from src.optimization import (
    HighsConfig,
    HighsSolver,
    ObjectiveWeights,
    Patient,
    PatientCategory,
    PlanningCancelledError,
    PlatformDataError,
    PlatformPersistenceError,
    Resident,
    SchedulingInput,
    Session,
    SolveResult,
    SolveStatus,
    build_platform_model,
    plan_platform_week,
)
from src.optimization import solver as solver_module

pytestmark = pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")

MONDAY = date(2026, 11, 2)
REFERENCE = date(2026, 10, 27)
EXACT_CONFIG = HighsConfig(time_limit_seconds=20, mip_relative_gap=0)


def _assert_feasible(data: SchedulingInput, result: SolveResult, row_limit: int = 12) -> None:
    """Recompute feasibility and objective using only domain records, never Pyomo."""
    assert result.has_solution
    assert result.objective is not None
    patients = {patient.patient_id: patient for patient in data.patients}
    residents = {resident.resident_id: resident for resident in data.residents}
    sessions = {(session.day, session.room_id): session for session in data.sessions}
    seen: set[str] = set()
    counts: Counter[tuple[date, str]] = Counter()
    occupied: Counter[tuple[date, str]] = Counter()
    workloads = dict.fromkeys(residents, 0)
    efficiency = 0.0
    unassigned = 0
    for record in result.schedule:
        assert record.patient_id in patients
        assert record.patient_id not in seen
        seen.add(record.patient_id)
        patient = patients[record.patient_id]
        key = (record.day, record.room_id)
        assert key in sessions
        session = sessions[key]
        assert patient.earliest_surgery_date is None or record.day >= patient.earliest_surgery_date
        counts[key] += 1
        occupied[key] += patient.duration_minutes
        forced = {
            resident_id
            for resident_id in session.assigned_resident_ids
            if patient.procedure_level in residents[resident_id].qualified_levels
        }
        # The implemented (1d) is a lower bound, not a qualification upper bound.
        assert not forced or forced == {record.resident_id}
        if record.resident_id is None:
            unassigned += 1
        else:
            assert record.resident_id in residents
            assert (
                session.available_resident_ids is None
                or record.resident_id in session.available_resident_ids
            )
            if patient.category is not PatientCategory.RESCHEDULED:
                workloads[record.resident_id] += 1
        if patient.category is PatientCategory.WAITING_LIST:
            assert patient.waiting_time_days is not None and patient.max_wait_days is not None
            efficiency += patient.waiting_time_days / patient.max_wait_days
    assert {
        patient.patient_id
        for patient in data.patients
        if patient.category is not PatientCategory.WAITING_LIST
    } <= seen
    for key, session in sessions.items():
        assert counts[key] <= row_limit
        assert occupied[key] + max(0, counts[key] - 1) * data.changeover_minutes <= (
            session.capacity_minutes
        )
    fairness = min(workloads.values())
    scale = data.objective_weights.efficiency_scale
    if scale is None:
        scale = max(
            (
                patient.max_wait_days
                for patient in data.patients
                if patient.category is PatientCategory.WAITING_LIST
            ),
            default=1,
        )
    expected = (
        scale * efficiency
        + data.objective_weights.fairness * fairness
        - data.objective_weights.unassigned_penalty * unassigned
    )
    assert result.objective.treatment_efficiency == pytest.approx(efficiency, abs=1e-7)
    assert result.objective.fairness_floor == fairness
    assert result.objective.unassigned_count == unassigned
    assert result.objective.weighted_total == pytest.approx(expected, abs=1e-7)
    assert result.schedule == tuple(
        sorted(result.schedule, key=lambda record: (record.day, record.room_id, record.patient_id))
    )
    if result.status is SolveStatus.OPTIMAL:
        assert result.best_objective_bound == pytest.approx(expected, abs=1e-7)
        assert result.relative_gap == pytest.approx(0, abs=1e-7)


def _enumerated_optimum(data: SchedulingInput, row_limit: int) -> float | None:
    """Brute-force tiny instances independently of the solver and model builder."""
    choices = []
    for patient in data.patients:
        allowed = [None] if patient.category is PatientCategory.WAITING_LIST else []
        for index, session in enumerate(data.sessions):
            if patient.earliest_surgery_date and session.day < patient.earliest_surgery_date:
                continue
            forced = {
                resident.resident_id
                for resident in data.residents
                if resident.resident_id in session.assigned_resident_ids
                and patient.procedure_level in resident.qualified_levels
            }
            for selected in (None, *(resident.resident_id for resident in data.residents)):
                if forced and forced != {selected}:
                    continue
                if (
                    selected is not None
                    and session.available_resident_ids is not None
                    and selected not in session.available_resident_ids
                ):
                    continue
                allowed.append((index, selected))
        choices.append(allowed)
    best = None
    for assignments in product(*choices):
        occupied = [0] * len(data.sessions)
        counts = [0] * len(data.sessions)
        workloads = dict.fromkeys((resident.resident_id for resident in data.residents), 0)
        efficiency = 0.0
        unassigned = 0
        for patient, assignment in zip(data.patients, assignments, strict=True):
            if assignment is None:
                continue
            index, resident = assignment
            occupied[index] += patient.duration_minutes
            counts[index] += 1
            if patient.category is PatientCategory.WAITING_LIST:
                efficiency += patient.waiting_time_days / patient.max_wait_days
            if resident is None:
                unassigned += 1
            elif patient.category is not PatientCategory.RESCHEDULED:
                workloads[resident] += 1
        if any(
            occupied[index] + max(0, counts[index] - 1) * data.changeover_minutes
            > session.capacity_minutes
            or counts[index] > row_limit
            for index, session in enumerate(data.sessions)
        ):
            continue
        value = (
            data.efficiency_scale * efficiency
            + data.objective_weights.fairness * min(workloads.values())
            - data.objective_weights.unassigned_penalty * unassigned
        )
        best = value if best is None else max(best, value)
    return best


def _small_instance(seed: int) -> tuple[SchedulingInput, int]:
    rng = random.Random(seed)
    residents = tuple(
        Resident(f"R{index}", frozenset(level for level in ("low", "high") if rng.randrange(2)))
        for index in range(2)
    )
    patients = tuple(
        Patient(
            f"P{index}",
            rng.choice(tuple(PatientCategory)),
            rng.choice((30, 60, 90)),
            rng.choice(("low", "high")),
            waiting_time_days=rng.randrange(21),
            max_wait_days=rng.choice((10, 20)),
            earliest_surgery_date=MONDAY + timedelta(days=rng.choice((-1, 0, 1, 2))),
        )
        for index in range(3)
    )
    sessions = tuple(
        Session(
            room,
            MONDAY + timedelta(days=offset),
            rng.choice((60, 90, 131, 180)),
            available_resident_ids=frozenset(
                resident.resident_id for resident in residents if rng.randrange(2)
            ),
            assigned_resident_ids=frozenset(
                resident.resident_id for resident in residents if rng.randrange(2)
            ),
        )
        for room in ("OR-1", "OR-2")
        for offset in range(2)
    )
    return SchedulingInput(
        patients,
        residents,
        sessions,
        objective_weights=ObjectiveWeights(
            efficiency_scale=7,
            fairness=rng.choice((0, 1, 2)),
            unassigned_penalty=rng.choice((0.5, 1, 3)),
        ),
        changeover_minutes=rng.choice((0, 11)),
    ), rng.choice((1, 2, 3))


@pytest.mark.parametrize("seed", range(32))
def test_tiny_models_match_exhaustive_search(seed: int) -> None:
    data, limit = _small_instance(seed)
    expected = _enumerated_optimum(data, limit)
    built = build_platform_model(data, max_operations_per_session=limit)
    result = HighsSolver(EXACT_CONFIG).solve(built)
    if expected is None:
        assert result.status is SolveStatus.INFEASIBLE
        assert result.objective is None and result.schedule == ()
        assert all(variable.value is None for variable in built.model.x.values())
    else:
        assert result.status is SolveStatus.OPTIMAL
        _assert_feasible(data, result, limit)
        assert result.objective.weighted_total == pytest.approx(expected, abs=1e-7)


def _single_room(*, capacity: int = 60, count: int = 2, duration: int = 60) -> SchedulingInput:
    return SchedulingInput(
        tuple(
            Patient(f"P{index}", PatientCategory.WAITING_LIST, duration, "low", 9 - index, 10)
            for index in range(count)
        ),
        (Resident("R1", frozenset({"low"})),),
        (Session("OR-1", MONDAY, capacity, frozenset({"R1"}), frozenset({"R1"})),),
        changeover_minutes=11,
    )


def test_capacity_selects_the_more_urgent_patient_and_correct_objective() -> None:
    data = _single_room()
    result = HighsSolver(EXACT_CONFIG).solve(build_platform_model(data))
    _assert_feasible(data, result)
    assert [record.patient_id for record in result.schedule] == ["P0"]
    assert result.objective.weighted_total == pytest.approx(10)


@pytest.mark.parametrize(("capacity", "expected_count"), [(130, 1), (131, 2)])
def test_changeover_capacity_boundary(capacity: int, expected_count: int) -> None:
    data = _single_room(capacity=capacity)
    result = HighsSolver(EXACT_CONFIG).solve(build_platform_model(data))
    _assert_feasible(data, result)
    assert len(result.schedule) == expected_count


def test_operation_row_limit_is_active_even_when_time_is_available() -> None:
    data = _single_room(capacity=600, count=3, duration=1)
    result = HighsSolver(EXACT_CONFIG).solve(
        build_platform_model(data, max_operations_per_session=2)
    )
    _assert_feasible(data, result, 2)
    assert len(result.schedule) == 2


def test_required_patient_after_the_horizon_is_infeasible_without_loading_values() -> None:
    data = _single_room(count=1)
    data = replace(
        data,
        patients=(
            replace(
                data.patients[0],
                category=PatientCategory.MANDATORY,
                earliest_surgery_date=MONDAY + timedelta(days=1),
            ),
        ),
    )
    built = build_platform_model(data)
    result = HighsSolver(EXACT_CONFIG).solve(built)
    assert result.status is SolveStatus.INFEASIBLE
    assert not result.has_solution and result.objective is None and result.schedule == ()
    assert all(variable.value is None for variable in built.model.component_data_objects(pyo.Var))


def test_optional_patient_after_the_horizon_is_not_scheduled() -> None:
    data = _single_room(count=1)
    data = replace(
        data,
        patients=(replace(data.patients[0], earliest_surgery_date=MONDAY + timedelta(days=1)),),
    )
    result = HighsSolver(EXACT_CONFIG).solve(build_platform_model(data))
    _assert_feasible(data, result)
    assert result.schedule == ()


def test_solver_pre_solve_cancellation_returns_no_solution() -> None:
    built = build_platform_model(_single_room())
    result = HighsSolver(EXACT_CONFIG).solve(built, cancel_requested=lambda: True)
    assert result.status is SolveStatus.INTERRUPTED
    assert result.schedule == () and result.objective is None
    assert all(variable.value is None for variable in built.model.x.values())


@pytest.mark.parametrize("incumbent", [None, math.inf, math.nan])
def test_time_limit_without_finite_incumbent_does_not_load_values(
    monkeypatch: pytest.MonkeyPatch,
    incumbent: float | None,
) -> None:
    def forbidden_load() -> None:
        pytest.fail("A result without an incumbent must never load solver values")

    fake = SimpleNamespace(
        config=SimpleNamespace(),
        highs_options={},
        available=lambda: True,
        version=lambda: (1, 15, 1),
        solve=lambda _: SimpleNamespace(
            termination_condition=TerminationCondition.maxTimeLimit,
            best_feasible_objective=incumbent,
            best_objective_bound=10,
            solution_loader=SimpleNamespace(load_vars=forbidden_load),
        ),
    )
    monkeypatch.setattr(solver_module, "Highs", lambda: fake)
    built = build_platform_model(_single_room())
    result = HighsSolver(EXACT_CONFIG).solve(built)
    assert result.status is SolveStatus.LIMIT_REACHED
    assert result.objective is None and result.schedule == () and not result.has_solution
    assert all(variable.value is None for variable in built.model.x.values())


def test_time_limit_with_incumbent_is_feasible_but_not_declared_optimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _single_room()
    built = build_platform_model(data)
    known = HighsSolver(EXACT_CONFIG).solve(built)
    assert known.objective is not None
    loaded = []
    fake = SimpleNamespace(
        config=SimpleNamespace(),
        highs_options={},
        available=lambda: True,
        version=lambda: (1, 15, 1),
        solve=lambda _: SimpleNamespace(
            termination_condition=TerminationCondition.maxTimeLimit,
            best_feasible_objective=known.objective.weighted_total,
            best_objective_bound=known.objective.weighted_total + 1,
            solution_loader=SimpleNamespace(load_vars=lambda: loaded.append(True)),
        ),
    )
    monkeypatch.setattr(solver_module, "Highs", lambda: fake)
    result = HighsSolver(EXACT_CONFIG).solve(built)
    assert loaded == [True]
    assert result.status is SolveStatus.FEASIBLE
    assert result.relative_gap is not None and result.relative_gap > 0
    _assert_feasible(data, result)


@pytest.mark.parametrize("backend_status", ["kInterrupt", "kHighsInterrupt"])
def test_interrupted_backend_discards_an_incumbent(
    monkeypatch: pytest.MonkeyPatch,
    backend_status: str,
) -> None:
    def forbidden_load() -> None:
        pytest.fail("An interrupted result must not load or expose partial assignments")

    fake = SimpleNamespace(
        config=SimpleNamespace(),
        highs_options={},
        available=lambda: True,
        version=lambda: (1, 15, 1),
        _solver_model=SimpleNamespace(
            getModelStatus=lambda: SimpleNamespace(name=backend_status),
        ),
        solve=lambda _: SimpleNamespace(
            termination_condition=TerminationCondition.interrupted,
            best_feasible_objective=10,
            best_objective_bound=11,
            solution_loader=SimpleNamespace(load_vars=forbidden_load),
        ),
    )
    monkeypatch.setattr(solver_module, "Highs", lambda: fake)
    built = build_platform_model(_single_room())
    result = HighsSolver(EXACT_CONFIG).solve(built)
    assert result.status is SolveStatus.INTERRUPTED
    assert result.schedule == () and result.objective is None and not result.has_solution
    assert all(variable.value is None for variable in built.model.x.values())


def _json_snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*.json"))}


@pytest.fixture
def demo_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "data"
    files = build_demo_snapshot(
        REFERENCE,
        start_month=date(2026, 9, 1),
        end_month=date(2026, 12, 1),
        patient_count=120,
    )
    for name, text in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return directory


def _confirm_rosters(directory: Path, monday: date) -> None:
    manager = DataManager(directory / "scadenzario", directory / "libretti")
    for year, month in sorted(
        {
            ((monday + timedelta(days=offset)).year, (monday + timedelta(days=offset)).month)
            for offset in range(5)
        }
    ):
        if manager.get_stato_mese(year, month) != "CONVALIDATO":
            manager.convalida_mese(year, month)


def _reserved_elsewhere(directory: Path, monday: date) -> set[str]:
    """Resolve effective reservations without calling the production overlay helpers."""
    planned = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in (directory / "sale_operatorie").glob("????-??.json")
    }
    actual = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in (directory / "sale_operatorie" / "effettivo").glob("????-??.json")
    }
    states = {}
    days = {}
    for month in planned.values():
        states.update(month.get("metadata", {}).get("settimane", {}))
        days.update(month.get("turni", {}))
    for month in actual.values():
        for start, state in month.get("metadata", {}).get("settimane", {}).items():
            states[start] = state
            for offset in range(5):
                day = date.fromisoformat(start) + timedelta(days=offset)
                days[day.isoformat()] = (
                    actual.get(f"{day:%Y-%m}", {})
                    .get("turni", {})
                    .get(
                        day.isoformat(),
                        {},
                    )
                )
    reserved = set()
    for day_text, daily in days.items():
        day = date.fromisoformat(day_text)
        start = day - timedelta(days=day.weekday())
        if start != monday and states.get(start.isoformat(), "BOZZA") != "CONVALIDATO":
            reserved.update(operation["id_paziente"] for operation in daily.get("operazioni", []))
    return reserved


def _assert_mapped_plan(run) -> None:
    patients = {patient.patient_id: patient for patient in run.context.scheduling_input.patients}
    count = 0
    for day in run.plan.days:
        for room in ("OR-1", "OR-2"):
            operations = [op for op in day.operations if op["sala_operatoria"] == room]
            previous_end = None
            for operation in operations:
                start = sum(
                    int(part) * scale
                    for part, scale in zip(
                        operation["ora_inizio"].split(":"),
                        (60, 1),
                        strict=True,
                    )
                )
                end = sum(
                    int(part) * scale
                    for part, scale in zip(
                        operation["ora_fine"].split(":"),
                        (60, 1),
                        strict=True,
                    )
                )
                assert start >= 480 and end <= 1080
                assert end - start == patients[operation["id_paziente"]].duration_minutes
                if previous_end is not None:
                    assert start - previous_end >= 11
                previous_end = end
                count += 1
    assert count == len(run.result.schedule)


@pytest.mark.parametrize(
    "monday",
    [date(2026, 9, 7) + timedelta(weeks=index) for index in range(16)],
)
def test_demo_multiweek_dry_run_is_feasible_and_never_changes_files(
    demo_directory: Path,
    monday: date,
) -> None:
    _confirm_rosters(demo_directory, monday)
    before = _json_snapshot(demo_directory)
    other_reserved = _reserved_elsewhere(demo_directory, monday)
    run = plan_platform_week(
        demo_directory.parent,
        monday,
        data_directory=demo_directory,
        solver_config=EXACT_CONFIG,
    )
    assert run.result.status is SolveStatus.OPTIMAL
    _assert_feasible(run.context.scheduling_input, run.result)
    _assert_mapped_plan(run)
    assert not {record.patient_id for record in run.result.schedule} & other_reserved
    completed = {
        json.loads(content)["id"]
        for name, content in before.items()
        if name.startswith("pazienti/") and json.loads(content)["stato"] == "Completato"
    }
    assert not {patient.patient_id for patient in run.context.scheduling_input.patients} & completed
    if monday >= date(2026, 10, 26):
        assert run.result.schedule
    assert run.write_receipt is None
    assert _json_snapshot(demo_directory) == before


def test_cross_month_persistence_replanning_and_reservation_exclusion(
    demo_directory: Path,
    tmp_path: Path,
) -> None:
    monday = date(2026, 11, 30)
    _confirm_rosters(demo_directory, monday)
    before = _json_snapshot(demo_directory)
    run = plan_platform_week(
        tmp_path,
        monday,
        data_directory=demo_directory,
        solver_config=EXACT_CONFIG,
        overwrite=True,
        persist=True,
        backup_directory=tmp_path / "backups",
    )
    _assert_feasible(run.context.scheduling_input, run.result)
    assert run.write_receipt is not None
    assert {path.name for path in run.write_receipt.updated_paths} >= {
        "2026-11.json",
        "2026-12.json",
    }
    affected_days = {(monday + timedelta(days=offset)).isoformat() for offset in range(5)}
    after = _json_snapshot(demo_directory)
    for name, old_content in before.items():
        if name.startswith("pazienti/"):
            old_record, new_record = json.loads(old_content), json.loads(after[name])
            assert {k: v for k, v in old_record.items() if k != "stato"} == {
                k: v for k, v in new_record.items() if k != "stato"
            }
        elif name in {"sale_operatorie/2026-11.json", "sale_operatorie/2026-12.json"}:
            old, new = json.loads(old_content), json.loads(after[name])
            for day, daily in old.get("turni", {}).items():
                if day not in affected_days:
                    assert new["turni"][day] == daily
        else:
            assert after[name] == old_content
    with pytest.raises(PlatformPersistenceError, match="già degli interventi"):
        plan_platform_week(
            tmp_path,
            monday,
            data_directory=demo_directory,
            solver_config=EXACT_CONFIG,
            persist=True,
            overwrite=False,
        )
    assert _json_snapshot(demo_directory) == after
    following = plan_platform_week(
        tmp_path,
        date(2026, 12, 7),
        data_directory=demo_directory,
        solver_config=EXACT_CONFIG,
    )
    assert not {record.patient_id for record in run.result.schedule} & {
        patient.patient_id for patient in following.context.scheduling_input.patients
    }


def test_confirmed_week_cannot_be_overwritten(demo_directory: Path, tmp_path: Path) -> None:
    before = _json_snapshot(demo_directory)
    with pytest.raises(PlatformPersistenceError, match="già convalidata"):
        plan_platform_week(
            tmp_path,
            date(2026, 10, 19),
            data_directory=demo_directory,
            solver_config=EXACT_CONFIG,
            overwrite=True,
            persist=True,
        )
    assert _json_snapshot(demo_directory) == before


def test_pipeline_cancellation_never_persists(demo_directory: Path, tmp_path: Path) -> None:
    before = _json_snapshot(demo_directory)
    with pytest.raises(PlanningCancelledError):
        plan_platform_week(
            tmp_path,
            MONDAY,
            data_directory=demo_directory,
            persist=True,
            cancel_requested=lambda: True,
        )
    assert _json_snapshot(demo_directory) == before


def test_infeasible_demo_request_cannot_persist_a_partial_plan(
    demo_directory: Path,
    tmp_path: Path,
) -> None:
    _confirm_rosters(demo_directory, MONDAY)
    for path in sorted((demo_directory / "pazienti").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["stato"] == "In Attesa":
            record["modello_ottimizzazione"]["categoria_paper"] = "I''"
            record["data_inserimento"] = "01/12/2026"
            path.write_text(json.dumps(record), encoding="utf-8")
            break
    else:
        pytest.fail("The demo must include waiting-list candidates")
    before = _json_snapshot(demo_directory)
    with pytest.raises(PlatformDataError, match="ammissibile"):
        plan_platform_week(
            tmp_path,
            MONDAY,
            data_directory=demo_directory,
            solver_config=EXACT_CONFIG,
            persist=True,
            overwrite=True,
        )
    assert _json_snapshot(demo_directory) == before


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("durata_intervento", 0),
        ("durata_intervento", -1),
        ("durata_intervento", True),
        ("complessita", "Da classificare"),
        ("data_inserimento", "not-a-date"),
    ],
)
def test_invalid_candidate_fails_before_any_persistence(
    demo_directory: Path,
    tmp_path: Path,
    field: str,
    invalid: object,
) -> None:
    _confirm_rosters(demo_directory, MONDAY)
    for path in sorted((demo_directory / "pazienti").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["stato"] == "In Attesa":
            record[field] = invalid
            path.write_text(json.dumps(record), encoding="utf-8")
            break
    else:
        pytest.fail("The demo must include waiting-list candidates")
    before = _json_snapshot(demo_directory)
    with pytest.raises(PlatformDataError):
        plan_platform_week(
            tmp_path,
            MONDAY,
            data_directory=demo_directory,
            solver_config=EXACT_CONFIG,
            persist=True,
            overwrite=True,
        )
    assert _json_snapshot(demo_directory) == before
