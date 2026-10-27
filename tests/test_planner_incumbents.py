"""Validate and normalize feasible time-limited incumbents without changing the MILP."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pyomo.core as pyo
import pytest
from pyomo.contrib.appsi.base import TerminationCondition

from src.optimization import (
    HighsSolver,
    ObjectiveWeights,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
    SolutionValidationError,
    SolveStatus,
    build_platform_model,
)
from src.optimization import solver as solver_module
from src.optimization.model import BuiltSchedulingModel

DAY = date(2026, 11, 2)
KEY = ("P", "OR", DAY.isoformat())


def _limited_incumbent(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fairness: int = 0,
    epsilon: int = 2,
    bound: float | None = 3.0,
    weights: ObjectiveWeights | None = None,
    waiting_days: int | None = None,
) -> BuiltSchedulingModel:
    patients = [Patient("P", PatientCategory.MANDATORY, 30, "low")]
    if waiting_days is not None:
        patients.append(Patient("W", PatientCategory.WAITING_LIST, 30, "low", waiting_days, 10))
    built = build_platform_model(
        SchedulingInput(
            tuple(patients),
            (Resident("R", frozenset({"low"})),),
            (Session("OR", DAY, 120, frozenset({"R"}), frozenset({"R"})),),
            objective_weights=weights or ObjectiveWeights(),
        ),
    )
    for variable in built.model.component_data_objects(pyo.Var):
        variable.set_value(0)
    for patient in patients:
        built.model.x[patient.patient_id, "OR", DAY.isoformat()].set_value(1)
        built.model.y[patient.patient_id, "R", "OR", DAY.isoformat()].set_value(1)
        built.model.unassigned[patient.patient_id, "OR", DAY.isoformat()].set_value(epsilon)
    built.model.fairness_floor.set_value(fairness)
    fake = SimpleNamespace(
        config=SimpleNamespace(),
        highs_options={},
        available=lambda: True,
        version=lambda: (1, 15, 1),
        _solver_model=SimpleNamespace(getModelStatus=lambda: SimpleNamespace(name="kTimeLimit")),
        solve=lambda model: SimpleNamespace(
            termination_condition=TerminationCondition.maxTimeLimit,
            best_feasible_objective=float(pyo.value(model.objective)),
            best_objective_bound=bound,
            solution_loader=SimpleNamespace(load_vars=lambda: None),
        ),
    )
    monkeypatch.setattr(solver_module, "Highs", lambda: fake)
    return built


@pytest.mark.parametrize(("fairness", "epsilon"), [(0, 0), (0, 2), (1, 0), (1, 3)])
def test_valid_slack_incumbent_has_consistent_canonical_objective(
    monkeypatch: pytest.MonkeyPatch,
    fairness: int,
    epsilon: int,
) -> None:
    built = _limited_incumbent(monkeypatch, fairness=fairness, epsilon=epsilon)
    raw_objective = pyo.value(built.model.objective)
    result = HighsSolver().solve(built)
    assert result.status is SolveStatus.FEASIBLE
    assert len(result.schedule) == 1
    assert result.objective is not None
    assert result.objective.fairness_floor == 1
    assert result.objective.unassigned_count == 0
    assert result.objective.treatment_efficiency == 0
    assert result.objective.weighted_total == pytest.approx(1)
    assert result.best_objective_bound == 3
    assert result.relative_gap == pytest.approx(2)
    assert pyo.value(built.model.objective) == raw_objective
    assert built.model.unassigned[KEY].value == epsilon
    assert built.model.fairness_floor.value == fairness


def test_zero_fairness_weight_and_signed_urgency_remain_consistent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _limited_incumbent(
        monkeypatch,
        weights=ObjectiveWeights(5.0, 0.0, 3.0),
        waiting_days=-2,
        bound=0,
    )
    result = HighsSolver().solve(built)
    assert result.status is SolveStatus.FEASIBLE
    assert result.objective is not None
    assert result.objective.treatment_efficiency == pytest.approx(-0.2)
    assert result.objective.fairness_floor == 2
    assert result.objective.unassigned_count == 0
    assert result.objective.weighted_total == pytest.approx(-1)
    assert result.relative_gap == pytest.approx(1)


@pytest.mark.parametrize(("bound", "expected"), [(1, 1), (1 - 1e-10, 1), (0, None)])
def test_bound_is_reconciled_with_the_tightened_incumbent(
    monkeypatch: pytest.MonkeyPatch,
    bound: float,
    expected: float | None,
) -> None:
    result = HighsSolver().solve(_limited_incumbent(monkeypatch, bound=bound))
    assert result.status is SolveStatus.FEASIBLE
    assert result.best_objective_bound == expected
    if expected is None:
        assert result.relative_gap is None
    else:
        assert result.relative_gap == pytest.approx(0)


def test_raw_constraint_violation_is_not_hidden_by_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _limited_incumbent(monkeypatch)
    built.model.y["P", "R", "OR", DAY.isoformat()].set_value(0)
    with pytest.raises(SolutionValidationError, match="rostered_resident_requirement"):
        HighsSolver().solve(built)


def test_raw_nonintegral_auxiliary_is_not_rounded_into_validity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _limited_incumbent(monkeypatch)
    built.model.unassigned[KEY].set_value(0.5, skip_validation=True)
    with pytest.raises(SolutionValidationError, match="non intero"):
        HighsSolver().solve(built)


def test_missing_raw_value_is_rejected_before_extracting_assignments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _limited_incumbent(monkeypatch)
    # The incumbent value normally comes independently from the solver, not the variables.
    original_factory = solver_module.Highs
    fake = original_factory()
    fake.solve = lambda _: SimpleNamespace(
        termination_condition=TerminationCondition.maxTimeLimit,
        best_feasible_objective=0,
        best_objective_bound=3,
        solution_loader=SimpleNamespace(load_vars=lambda: None),
    )
    built.model.x[KEY].set_value(None)
    with pytest.raises(SolutionValidationError, match="mancante o non finito"):
        HighsSolver().solve(built)


@pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")
def test_real_optimum_and_bound_still_agree_after_normalization() -> None:
    data = SchedulingInput(
        (Patient("P", PatientCategory.MANDATORY, 30, "low"),),
        (Resident("R", frozenset({"low"})),),
        (Session("OR", DAY, 60, frozenset({"R"}), frozenset({"R"})),),
    )
    result = HighsSolver().solve(build_platform_model(data))
    assert result.status is SolveStatus.OPTIMAL
    assert result.objective is not None
    assert result.objective.weighted_total == pytest.approx(1)
    assert result.best_objective_bound == pytest.approx(1)
    assert result.relative_gap == pytest.approx(0)


@pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")
def test_actual_unassigned_operation_retains_its_penalty() -> None:
    data = SchedulingInput(
        (Patient("P", PatientCategory.MANDATORY, 30, "low"),),
        (Resident("R", frozenset({"low"})),),
        (Session("OR", DAY, 60, frozenset()),),
    )
    result = HighsSolver().solve(build_platform_model(data))
    assert result.status is SolveStatus.OPTIMAL
    assert result.schedule[0].resident_id is None
    assert result.objective is not None
    assert result.objective.unassigned_count == 1
    assert result.objective.weighted_total == pytest.approx(-1)
