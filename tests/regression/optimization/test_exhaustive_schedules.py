"""Compare the MILP with direct enumeration of small, synthetic weekly schedules."""

from __future__ import annotations

import random
from datetime import date, timedelta
from itertools import product

import pyomo.core as pyo
import pytest

from src.optimization import (
    HighsSolver,
    InputValidationError,
    ObjectiveWeights,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
    SolveStatus,
    build_paper_model,
    build_platform_model,
)

pytestmark = pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")


def _instance(seed: int, platform: bool) -> tuple[SchedulingInput, int | None]:
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
        )
        for index in range(3)
    )
    sessions = tuple(
        Session(
            room_id,
            date(2026, 9, 21) + timedelta(days=offset),
            rng.choice((90, 120, 180)),
            available_resident_ids=(
                frozenset(resident.resident_id for resident in residents if rng.randrange(2))
                if platform
                else None
            ),
            assigned_resident_ids=frozenset(
                resident.resident_id for resident in residents if rng.randrange(2)
            ),
        )
        for room_id in ("OR-1", "OR-2")
        for offset in range(2)
    )
    return SchedulingInput(
        patients,
        residents,
        sessions,
        objective_weights=(
            ObjectiveWeights(
                efficiency_scale=7.0,
                fairness=rng.choice((0.0, 1.0, 2.0)),
                unassigned_penalty=rng.choice((0.5, 1.0, 3.0)),
            )
            if platform
            else ObjectiveWeights()
        ),
        changeover_minutes=rng.choice((0, 11)) if platform else 0,
    ), rng.choice((1, 2, 3)) if platform else None


def _enumerated_optimum(data: SchedulingInput, row_limit: int | None) -> float | None:
    """Enumerate assignments without using any Pyomo components or solver helpers."""
    choices: list[list[tuple[int, str | None] | None]] = []
    for patient in data.patients:
        allowed: list[tuple[int, str | None] | None] = []
        if patient.category is PatientCategory.WAITING_LIST:
            allowed.append(None)
        for session_index, session in enumerate(data.sessions):
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
                allowed.append((session_index, selected))
        choices.append(allowed)

    best: float | None = None
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
    for combination in product(*choices):
        occupied = [0] * len(data.sessions)
        counts = [0] * len(data.sessions)
        workloads = {resident.resident_id: 0 for resident in data.residents}
        efficiency = 0.0
        unassigned = 0
        for patient, assignment in zip(data.patients, combination, strict=True):
            if assignment is None:
                continue
            session_index, resident_id = assignment
            occupied[session_index] += patient.duration_minutes
            counts[session_index] += 1
            if patient.category is PatientCategory.WAITING_LIST:
                efficiency += patient.waiting_time_days / patient.max_wait_days
            if resident_id is None:
                unassigned += 1
            elif patient.category is not PatientCategory.RESCHEDULED:
                workloads[resident_id] += 1
        if any(
            occupied[index] + max(0, counts[index] - 1) * data.changeover_minutes
            > session.capacity_minutes
            or (row_limit is not None and counts[index] > row_limit)
            for index, session in enumerate(data.sessions)
        ):
            continue
        value = (
            scale * efficiency
            + data.objective_weights.fairness * min(workloads.values())
            - data.objective_weights.unassigned_penalty * unassigned
        )
        best = value if best is None else max(best, value)
    return best


@pytest.mark.parametrize("platform", [False, True], ids=["paper", "platform"])
@pytest.mark.parametrize("seed", range(40))
def test_solver_matches_exhaustive_enumeration(seed: int, platform: bool) -> None:
    data, row_limit = _instance(seed, platform)
    expected = _enumerated_optimum(data, row_limit)
    try:
        built = (
            build_platform_model(data, max_operations_per_session=row_limit)
            if platform
            else build_paper_model(data)
        )
    except InputValidationError:
        assert expected is None
        return
    result = HighsSolver().solve(built)
    if expected is None:
        assert result.status is SolveStatus.INFEASIBLE
        assert result.objective is None
        assert result.schedule == ()
        return

    assert result.status is SolveStatus.OPTIMAL
    assert result.objective is not None
    assert result.objective.weighted_total == pytest.approx(expected, abs=1e-7)
    for variable in built.model.component_data_objects(pyo.Var):
        value = pyo.value(variable)
        assert value == pytest.approx(round(value), abs=1e-7)
    for constraint in built.model.component_data_objects(pyo.Constraint, active=True):
        value = pyo.value(constraint.body)
        if constraint.lower is not None:
            assert value >= pyo.value(constraint.lower) - 1e-7, constraint.name
        if constraint.upper is not None:
            assert value <= pyo.value(constraint.upper) + 1e-7, constraint.name
