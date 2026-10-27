from __future__ import annotations

import random
from collections.abc import Callable
from datetime import date, timedelta

import pyomo.core as pyo
import pytest

from src.optimization import (
    HighsConfig,
    HighsSolver,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
    SolveStatus,
    build_platform_model,
)

pytestmark = pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")


@pytest.mark.parametrize("patient_count", [20, 100, 300])
def test_synthetic_week_capacity_roster_and_objective_at_larger_sizes(
    patient_count: int,
    record_property: Callable[[str, object], None],
) -> None:
    rng = random.Random(20260917)
    monday = date(2026, 9, 21)
    patients = tuple(
        Patient(
            patient_id=f"P{index:04}",
            category=(
                PatientCategory.MANDATORY
                if index < 4
                else PatientCategory.RESCHEDULED
                if index < 8
                else PatientCategory.WAITING_LIST
            ),
            duration_minutes=rng.choice((30, 45, 60, 90, 120, 180, 240)),
            procedure_level=rng.choice(("low", "high")),
            waiting_time_days=rng.randrange(1, 181),
            max_wait_days=rng.choice((30, 60, 180)),
        )
        for index in range(patient_count)
    )
    residents = tuple(
        Resident(f"R{index}", frozenset({"high"} if index % 2 else {"low", "high"}))
        for index in range(8)
    )
    sessions = tuple(
        Session(
            f"OR-{room + 1}",
            monday + timedelta(days=offset),
            600,
            available_resident_ids=frozenset({f"R{(2 * offset + room) % 8}"}),
            assigned_resident_ids=frozenset({f"R{(2 * offset + room) % 8}"}),
        )
        for offset in range(5)
        for room in range(2)
    )
    data = SchedulingInput(patients, residents, sessions, changeover_minutes=11)
    built = build_platform_model(data, max_operations_per_session=12)
    result = HighsSolver(HighsConfig(time_limit_seconds=10)).solve(built)
    record_property("solver_status", result.status.value)
    record_property("scheduled_count", len(result.schedule))
    record_property("elapsed_seconds", result.elapsed_seconds)
    record_property("relative_gap", result.relative_gap)

    assert result.status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}
    assert result.objective is not None
    assert len({item.patient_id for item in result.schedule}) == len(result.schedule)
    assert {patient.patient_id for patient in patients[:8]} <= {
        item.patient_id for item in result.schedule
    }
    by_patient = {patient.patient_id: patient for patient in patients}
    for session in sessions:
        selected = [
            item
            for item in result.schedule
            if (item.room_id, item.day) == (session.room_id, session.day)
        ]
        assert len(selected) <= 12
        assert (
            sum(by_patient[item.patient_id].duration_minutes for item in selected)
            + max(0, len(selected) - 1) * 11
            <= session.capacity_minutes
        )
        assert all(item.resident_id in session.assigned_resident_ids for item in selected)
    for constraint in built.model.component_data_objects(pyo.Constraint, active=True):
        value = pyo.value(constraint.body)
        if constraint.lower is not None:
            assert value >= pyo.value(constraint.lower) - 1e-6, constraint.name
        if constraint.upper is not None:
            assert value <= pyo.value(constraint.upper) + 1e-6, constraint.name
    reconstructed = (
        data.efficiency_scale * result.objective.treatment_efficiency
        + result.objective.fairness_floor
        - result.objective.unassigned_count
    )
    assert reconstructed == pytest.approx(result.objective.weighted_total, abs=1e-6)
