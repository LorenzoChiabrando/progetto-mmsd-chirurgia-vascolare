"""Exercise the adapter with valid non-optimal incumbents at the time limit."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pyomo.core as pyo
import pytest
from pyomo.contrib.appsi.base import TerminationCondition

from src.optimization import (
    HighsSolver,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
    SolveStatus,
    build_paper_model,
    solver,
)
from src.optimization.model import BuiltSchedulingModel


def _limited_incumbent(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fairness: int,
    unassigned: int,
) -> BuiltSchedulingModel:
    built = build_paper_model(
        SchedulingInput(
            patients=(Patient("P", PatientCategory.MANDATORY, 60, "L"),),
            residents=(Resident("R", frozenset({"L"})),),
            sessions=(
                Session("OR", date(2026, 9, 21), 60, assigned_resident_ids=frozenset({"R"})),
            ),
        )
    )
    key = ("P", "OR", "2026-09-21")
    built.model.x[key].value = 1
    built.model.y["P", "R", "OR", "2026-09-21"].value = 1
    built.model.unassigned[key].value = unassigned
    built.model.fairness_floor.value = fairness
    for constraint in built.model.component_data_objects(pyo.Constraint, active=True):
        value = pyo.value(constraint.body)
        if constraint.lower is not None:
            assert value >= pyo.value(constraint.lower) - 1e-8
        if constraint.upper is not None:
            assert value <= pyo.value(constraint.upper) + 1e-8

    class LimitedHighs:
        def __init__(self) -> None:
            self.config = SimpleNamespace()
            self.highs_options = {}
            self._solver_model = SimpleNamespace(
                getModelStatus=lambda: SimpleNamespace(name="kTimeLimit")
            )

        def available(self) -> bool:
            return True

        def version(self) -> tuple[int, int, int]:
            return (1, 0, 0)

        def solve(self, model: pyo.ConcreteModel) -> SimpleNamespace:
            return SimpleNamespace(
                termination_condition=TerminationCondition.maxTimeLimit,
                best_feasible_objective=pyo.value(model.objective),
                best_objective_bound=1.0,
                solution_loader=SimpleNamespace(load_vars=lambda: None),
            )

    monkeypatch.setattr(solver, "Highs", LimitedHighs)
    return built


def test_time_limit_with_a_tight_feasible_incumbent_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _limited_incumbent(monkeypatch, fairness=1, unassigned=0)
    result = HighsSolver().solve(built)
    assert result.status is SolveStatus.FEASIBLE
    assert len(result.schedule) == 1
    assert result.objective is not None
    assert result.objective.weighted_total == pytest.approx(1.0)


def test_time_limit_should_accept_a_feasible_incumbent_with_slack_epsilon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _limited_incumbent(monkeypatch, fairness=1, unassigned=2)
    result = HighsSolver().solve(built)
    assert result.status is SolveStatus.FEASIBLE


def test_time_limit_objective_breakdown_should_reconcile_with_its_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _limited_incumbent(monkeypatch, fairness=0, unassigned=0)
    result = HighsSolver().solve(built)
    assert result.status is SolveStatus.FEASIBLE
    objective = result.objective
    assert objective is not None
    reconstructed = (
        built.source.paper_efficiency_scale * objective.treatment_efficiency
        + objective.fairness_floor
        - objective.unassigned_count
    )
    assert reconstructed == pytest.approx(objective.weighted_total)
