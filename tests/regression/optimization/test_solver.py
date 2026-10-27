from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from pyomo.contrib.appsi.base import TerminationCondition

from src.optimization import (
    HighsConfig,
    HighsSolver,
    ObjectiveWeights,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
    SolutionValidationError,
    SolveStatus,
    build_paper_model,
    build_platform_model,
)
from src.optimization.results import ObjectiveBreakdown, ScheduledSurgery
from src.optimization.solver import (
    _interrupt_if_requested,
    _status_without_solution,
    _validate_solution,
)

pytestmark = pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")


def _roster_input(
    *,
    assigned: frozenset[str] = frozenset({"R1"}),
    qualified: bool = True,
) -> SchedulingInput:
    return SchedulingInput(
        patients=(Patient("P1", PatientCategory.MANDATORY, 60, "low"),),
        residents=(
            Resident("R1", frozenset({"low"}) if qualified else frozenset({"high"})),
            Resident("R2", frozenset({"low"})),
        ),
        sessions=(Session("OR-1", date(2026, 8, 10), 60, assigned_resident_ids=assigned),),
    )


@pytest.mark.parametrize("builder", [build_paper_model, build_platform_model])
def test_rostered_qualified_resident_is_required_for_a_scheduled_patient(builder) -> None:
    built = builder(_roster_input())
    result = HighsSolver().solve(built)

    assert result.status is SolveStatus.OPTIMAL
    assert result.schedule == (ScheduledSurgery("P1", "OR-1", date(2026, 8, 10), "R1"),)
    assert result.objective is not None
    assert result.objective.unassigned_count == 0
    assert result.objective.weighted_total == pytest.approx(0.0)


def test_removing_equation_1d_would_allow_omitting_the_rostered_resident() -> None:
    built = build_paper_model(_roster_input())
    built.model.y["P1", "R1", "OR-1", "2026-08-10"].fix(0)
    assert HighsSolver().solve(built).status is SolveStatus.INFEASIBLE

    built.model.rostered_resident_requirement.deactivate()
    # The extracted-schedule validator independently checks (1d), so bypass it
    # only for this counterfactual model with that equation intentionally removed.
    result = HighsSolver(HighsConfig(validate_solution=False)).solve(built)
    assert result.status is SolveStatus.OPTIMAL
    assert result.schedule[0].resident_id == "R2"


def test_two_qualified_roster_assignments_conflict_with_unchanged_equation_1f() -> None:
    built = build_paper_model(_roster_input(assigned=frozenset({"R1", "R2"})))
    result = HighsSolver().solve(built)

    assert result.status is SolveStatus.INFEASIBLE
    assert not result.has_solution
    assert result.schedule == ()
    assert result.objective is None
    assert all(variable.value is None for variable in built.model.x.values())


@pytest.mark.parametrize(
    ("assigned", "qualified"),
    [(frozenset(), True), (frozenset({"R1"}), False), (frozenset(), False)],
)
def test_equation_1d_does_not_forbid_y_when_a_or_h_is_zero(
    assigned: frozenset[str],
    qualified: bool,
) -> None:
    data = _roster_input(assigned=assigned, qualified=qualified)
    data = replace(data, residents=(data.residents[0],))
    result = HighsSolver().solve(build_paper_model(data))

    assert result.status is SolveStatus.OPTIMAL
    assert result.schedule[0].resident_id == "R1"
    assert result.objective is not None
    assert result.objective.unassigned_count == 0
    assert result.objective.weighted_total == pytest.approx(1.0)


@pytest.mark.parametrize("resident_id", [None, "R2"])
def test_solution_validator_rejects_a_missing_required_roster_assignment(
    resident_id: str | None,
) -> None:
    built = build_paper_model(_roster_input())
    unassigned = int(resident_id is None)
    schedule = (ScheduledSurgery("P1", "OR-1", date(2026, 8, 10), resident_id),)
    objective = ObjectiveBreakdown(0.0, 0, unassigned, -float(unassigned))

    with pytest.raises(
        SolutionValidationError,
        match=r"richiede lo specializzando di turno.*secondo il vincolo \(1d\)",
    ):
        _validate_solution(built, schedule, objective)


def test_highs_finds_hand_checkable_optimum() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "MANDATORY",
                PatientCategory.MANDATORY,
                60,
                "high",
            ),
            Patient(
                "OPTION-A",
                PatientCategory.WAITING_LIST,
                60,
                "low",
                waiting_time_days=9,
                max_wait_days=10,
            ),
            Patient(
                "OPTION-B",
                PatientCategory.WAITING_LIST,
                60,
                "high",
                waiting_time_days=8,
                max_wait_days=10,
            ),
        ),
        residents=(
            Resident("R1", frozenset({"low"})),
            Resident("R2", frozenset({"high"})),
        ),
        sessions=(
            Session("OR-1", date(2026, 8, 10), 120, assigned_resident_ids=frozenset({"R1", "R2"})),
        ),
    )

    result = HighsSolver().solve(build_paper_model(data))

    assert result.status is SolveStatus.OPTIMAL
    assert {record.patient_id for record in result.schedule} == {"MANDATORY", "OPTION-A"}
    assert {record.resident_id for record in result.schedule} == {"R1", "R2"}
    assert result.objective is not None
    assert result.objective.treatment_efficiency == pytest.approx(0.9)
    assert result.objective.fairness_floor == 1
    assert result.objective.unassigned_count == 0
    assert result.objective.weighted_total == pytest.approx(10.0)


def test_highs_uses_unassigned_indicator_when_no_resident_is_available() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "MANDATORY",
                PatientCategory.MANDATORY,
                60,
                "low",
            ),
        ),
        residents=(Resident("R1", frozenset({"high"})),),
        sessions=(Session("OR-1", date(2026, 8, 10), 60, available_resident_ids=frozenset()),),
    )

    result = HighsSolver().solve(build_platform_model(data))

    assert result.status is SolveStatus.OPTIMAL
    assert result.schedule[0].resident_id is None
    assert result.objective is not None
    assert result.objective.unassigned_count == 1
    assert result.objective.weighted_total == pytest.approx(-1.0)


def test_highs_reports_infeasible_without_loading_variables() -> None:
    data = SchedulingInput(
        patients=tuple(
            Patient(
                f"REQUIRED-{index}",
                PatientCategory.MANDATORY,
                60,
                "low",
            )
            for index in range(3)
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(
            Session("OR-1", date(2026, 8, 10), 100),
            Session("OR-1", date(2026, 8, 11), 100),
        ),
    )

    result = HighsSolver().solve(build_paper_model(data))

    assert result.status is SolveStatus.INFEASIBLE
    assert result.schedule == ()
    assert result.objective is None


def test_changeover_prevents_overfilling_a_session() -> None:
    patients = tuple(
        Patient(
            f"P{index}",
            PatientCategory.WAITING_LIST,
            60,
            "low",
            waiting_time_days=5,
            max_wait_days=10,
        )
        for index in range(2)
    )
    common = {
        "patients": patients,
        "residents": (Resident("R1", frozenset({"low"})),),
        "sessions": (Session("OR-1", date(2026, 8, 10), 120),),
    }

    without_changeover = HighsSolver().solve(
        build_paper_model(SchedulingInput(**common, changeover_minutes=0))
    )
    with_changeover = HighsSolver().solve(
        build_platform_model(SchedulingInput(**common, changeover_minutes=11))
    )

    assert len(without_changeover.schedule) == 2
    assert len(with_changeover.schedule) == 1


def test_no_fairness_configuration_reports_the_actual_workload_floor() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "MANDATORY",
                PatientCategory.MANDATORY,
                60,
                "high",
            ),
            Patient(
                "OPTIONAL",
                PatientCategory.WAITING_LIST,
                60,
                "low",
                waiting_time_days=5,
                max_wait_days=10,
            ),
        ),
        residents=(
            Resident("R1", frozenset({"low"})),
            Resident("R2", frozenset({"high"})),
        ),
        sessions=(
            Session("OR-1", date(2026, 8, 10), 120, assigned_resident_ids=frozenset({"R1", "R2"})),
        ),
        objective_weights=ObjectiveWeights(fairness=0),
    )

    result = HighsSolver().solve(build_platform_model(data))

    assert result.status is SolveStatus.OPTIMAL
    assert result.objective is not None
    assert result.objective.fairness_floor == 1
    assert result.objective.weighted_total == pytest.approx(5.0)


def test_pre_cancelled_solve_never_loads_a_solution() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "MANDATORY",
                PatientCategory.MANDATORY,
                60,
                "low",
            ),
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(Session("OR-1", date(2026, 8, 10), 60),),
    )

    result = HighsSolver().solve(
        build_paper_model(data),
        cancel_requested=lambda: True,
    )

    assert result.status is SolveStatus.INTERRUPTED
    assert result.schedule == ()
    assert result.objective is None
    assert result.termination_condition == "cancelled_before_solve"


def test_highs_callback_interrupts_only_after_cancellation() -> None:
    class CallbackEvent:
        interrupted = False

        def interrupt(self) -> None:
            self.interrupted = True

    callback_event = CallbackEvent()
    _interrupt_if_requested(callback_event, lambda: False)
    assert callback_event.interrupted is False

    _interrupt_if_requested(callback_event, lambda: True)
    assert callback_event.interrupted is True


@pytest.mark.parametrize(
    ("termination", "expected"),
    [
        (TerminationCondition.maxTimeLimit, SolveStatus.LIMIT_REACHED),
        (TerminationCondition.maxIterations, SolveStatus.LIMIT_REACHED),
        (TerminationCondition.objectiveLimit, SolveStatus.LIMIT_REACHED),
        (TerminationCondition.interrupted, SolveStatus.INTERRUPTED),
        (TerminationCondition.error, SolveStatus.ERROR),
    ],
)
def test_termination_without_incumbent_is_preserved(
    termination: TerminationCondition,
    expected: SolveStatus,
) -> None:
    assert _status_without_solution(termination) is expected
