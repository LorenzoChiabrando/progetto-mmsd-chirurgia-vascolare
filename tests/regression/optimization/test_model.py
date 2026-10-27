from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from itertools import product

import pyomo.core as pyo
import pytest
from pyomo.repn.standard_repn import generate_standard_repn

from src.optimization import (
    InputValidationError,
    ObjectiveWeights,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
    build_paper_model,
    build_platform_model,
)


def _model_input(
    *,
    changeover_minutes: int = 0,
    with_availability: bool = False,
    objective_weights: ObjectiveWeights | None = None,
) -> SchedulingInput:
    monday = date(2026, 8, 10)
    available = frozenset({"R-LOW"}) if with_availability else None
    return SchedulingInput(
        patients=(
            Patient(
                "P-WAIT",
                PatientCategory.WAITING_LIST,
                60,
                "low",
                waiting_time_days=5,
                max_wait_days=20,
            ),
            Patient(
                "P-MANDATORY",
                PatientCategory.MANDATORY,
                90,
                "high",
                waiting_time_days=10,
                max_wait_days=20,
            ),
            Patient(
                "P-RESCHEDULED",
                PatientCategory.RESCHEDULED,
                30,
                "high",
            ),
        ),
        residents=(
            Resident("R-LOW", frozenset({"low"})),
            Resident("R-HIGH", frozenset({"high"})),
        ),
        sessions=tuple(
            Session(
                "OR-1",
                monday + timedelta(days=offset),
                180,
                available_resident_ids=available,
                assigned_resident_ids=frozenset({"R-LOW" if offset == 0 else "R-HIGH"}),
            )
            for offset in range(2)
        ),
        objective_weights=objective_weights or ObjectiveWeights(),
        changeover_minutes=changeover_minutes,
    )


def _coefficients(expression: pyo.Expression) -> dict[str, float]:
    representation = generate_standard_repn(expression)
    return {
        variable.name: float(coefficient)
        for variable, coefficient in zip(
            representation.linear_vars,
            representation.linear_coefs,
            strict=True,
        )
    }


def test_paper_model_uses_full_cartesian_variables_and_literal_domains() -> None:
    model = build_paper_model(_model_input()).model

    assert len(model.x) == 3 * 1 * 2
    assert len(model.y) == 3 * 2 * 1 * 2
    assert len(model.unassigned) == 3 * 1 * 2
    assert ("P-WAIT", "R-HIGH", "OR-1", "2026-08-10") in model.y

    assert model.x["P-WAIT", "OR-1", "2026-08-10"].is_binary()
    assert model.y["P-WAIT", "R-LOW", "OR-1", "2026-08-10"].is_binary()
    epsilon = model.unassigned["P-WAIT", "OR-1", "2026-08-10"]
    assert epsilon.is_integer()
    assert not epsilon.is_binary()
    assert epsilon.lb == 0
    assert epsilon.ub is None
    assert model.fairness_floor.is_integer()
    assert not model.fairness_floor.is_binary()
    assert model.fairness_floor.lb == 0
    assert model.fairness_floor.ub is None


def test_paper_model_has_all_seven_constraint_families() -> None:
    model = build_paper_model(_model_input()).model

    assert len(model.waiting_patient_once) == 1  # (1a)
    assert len(model.required_patient_once) == 2  # (1b)
    assert len(model.session_capacity) == 2  # (1c)
    assert len(model.rostered_resident_requirement) == 12  # (1d)
    assert len(model.resident_coverage) == 6  # (1e)
    assert len(model.at_most_one_resident) == 6  # (1f)
    assert len(model.fairness_floor_definition) == 2  # (1g)

    assert not hasattr(model, "resident_assignment_state")
    assert not hasattr(model, "platform_changeover_capacity")
    assert not hasattr(model, "platform_resident_availability")
    assert not hasattr(model, "platform_operation_row_limit")
    assert not hasattr(model, "session_used")


def test_equations_1a_to_1c_keep_the_printed_coefficients() -> None:
    model = build_paper_model(_model_input()).model

    waiting = model.waiting_patient_once["P-WAIT"]
    assert waiting.lower is None
    assert pyo.value(waiting.upper) == 1
    assert set(_coefficients(waiting.body).values()) == {1.0}

    required = model.required_patient_once["P-MANDATORY"]
    assert pyo.value(required.lower) == 1
    assert pyo.value(required.upper) == 1
    assert set(_coefficients(required.body).values()) == {1.0}

    capacity = model.session_capacity["OR-1", "2026-08-10"]
    assert capacity.lower is None
    assert pyo.value(capacity.upper) == 180
    assert _coefficients(capacity.body) == {
        "x[P-WAIT,OR-1,2026-08-10]": 60.0,
        "x[P-MANDATORY,OR-1,2026-08-10]": 90.0,
        "x[P-RESCHEDULED,OR-1,2026-08-10]": 30.0,
    }


def test_roster_parameter_is_binary_indexed_by_resident_room_day_and_replaces_s() -> None:
    data = _model_input()
    model = build_paper_model(data).model

    assert model.resident_roster_assignment.domain is pyo.Binary
    assert not model.resident_roster_assignment.mutable
    assert set(model.resident_roster_assignment) == set(
        product(model.RESIDENTS, model.ROOMS, model.DAYS)
    )
    assert pyo.value(model.resident_roster_assignment["R-LOW", "OR-1", "2026-08-10"]) == 1
    assert pyo.value(model.resident_roster_assignment["R-LOW", "OR-1", "2026-08-11"]) == 0
    assert pyo.value(model.resident_roster_assignment["R-HIGH", "OR-1", "2026-08-10"]) == 0
    assert pyo.value(model.resident_roster_assignment["R-HIGH", "OR-1", "2026-08-11"]) == 1
    assert not hasattr(model, "patient_resident_qualification")
    assert not hasattr(model, "resident_compatibility")
    assert not hasattr(data.patients[0], "qualified_resident_ids")


@pytest.mark.parametrize("builder", [build_paper_model, build_platform_model])
@pytest.mark.parametrize(("assigned", "qualified"), tuple(product((0, 1), repeat=2)))
def test_equation_1d_has_exact_roster_coefficients_and_truth_table(
    builder,
    assigned: int,
    qualified: int,
) -> None:
    source = _model_input()
    resident = Resident("R-LOW", frozenset({"low"}) if qualified else frozenset({"high"}))
    session = replace(
        source.sessions[0],
        assigned_resident_ids=frozenset({"R-LOW"}) if assigned else frozenset(),
    )
    model = builder(
        replace(source, patients=(source.patients[0],), residents=(resident,), sessions=(session,))
    ).model
    key = ("P-WAIT", "R-LOW", "OR-1", "2026-08-10")
    constraint = model.rostered_resident_requirement[key]
    expected = {"y[P-WAIT,R-LOW,OR-1,2026-08-10]": -1.0}
    if assigned * qualified:
        expected["x[P-WAIT,OR-1,2026-08-10]"] = 1.0
    assert constraint.lower is None
    assert pyo.value(constraint.upper) == 0
    assert _coefficients(constraint.body) == expected

    for x_value, y_value in product((0, 1), repeat=2):
        model.x["P-WAIT", "OR-1", "2026-08-10"].set_value(x_value)
        model.y[key].set_value(y_value)
        is_feasible = pyo.value(constraint.body) <= 1e-9
        assert is_feasible == (assigned * qualified * x_value <= y_value)


def test_missing_roster_assignments_mean_a_zero_not_all_residents_assigned() -> None:
    source = _model_input()
    sessions = tuple(
        replace(session, assigned_resident_ids=frozenset()) for session in source.sessions
    )
    model = build_paper_model(replace(source, sessions=sessions)).model

    assert all(pyo.value(value) == 0 for value in model.resident_roster_assignment.values())


def test_equations_1e_and_1f_remain_separate_inequalities() -> None:
    model = build_paper_model(_model_input()).model
    key = ("P-WAIT", "OR-1", "2026-08-10")

    coverage = model.resident_coverage[key]
    assert pyo.value(coverage.lower) == 0
    assert coverage.upper is None
    assert _coefficients(coverage.body) == {
        "y[P-WAIT,R-LOW,OR-1,2026-08-10]": 1.0,
        "y[P-WAIT,R-HIGH,OR-1,2026-08-10]": 1.0,
        "unassigned[P-WAIT,OR-1,2026-08-10]": 1.0,
        "x[P-WAIT,OR-1,2026-08-10]": -1.0,
    }

    at_most_one = model.at_most_one_resident[key]
    assert at_most_one.lower is None
    assert pyo.value(at_most_one.upper) == 0
    assert _coefficients(at_most_one.body) == {
        "y[P-WAIT,R-LOW,OR-1,2026-08-10]": 1.0,
        "y[P-WAIT,R-HIGH,OR-1,2026-08-10]": 1.0,
        "x[P-WAIT,OR-1,2026-08-10]": -1.0,
    }

    # This point is feasible for the printed (1e)-(1f), although epsilon=2 is
    # suboptimal. It would be rejected by the former compact equality.
    model.x[key].set_value(1)
    model.y["P-WAIT", "R-LOW", "OR-1", "2026-08-10"].set_value(1)
    model.y["P-WAIT", "R-HIGH", "OR-1", "2026-08-10"].set_value(0)
    model.unassigned[key].set_value(2)
    assert pyo.value(coverage.body) >= pyo.value(coverage.lower)
    assert pyo.value(at_most_one.body) <= pyo.value(at_most_one.upper)


def test_equation_1g_excludes_only_rescheduled_patients() -> None:
    model = build_paper_model(_model_input()).model
    fairness = model.fairness_floor_definition["R-HIGH"]
    coefficients = _coefficients(fairness.body)

    assert coefficients["fairness_floor"] == 1.0
    assert coefficients["y[P-WAIT,R-HIGH,OR-1,2026-08-10]"] == -1.0
    assert coefficients["y[P-MANDATORY,R-HIGH,OR-1,2026-08-10]"] == -1.0
    assert "y[P-RESCHEDULED,R-HIGH,OR-1,2026-08-10]" not in coefficients
    assert fairness.lower is None
    assert pyo.value(fairness.upper) == 0


def test_objective_matches_equations_2_to_6() -> None:
    model = build_paper_model(_model_input()).model
    coefficients = _coefficients(model.objective.expr)

    assert model.objective.sense is pyo.maximize
    assert pyo.value(model.efficiency_scale) == 20
    assert set(model.urgency) == {"P-WAIT", "P-MANDATORY", "P-RESCHEDULED"}
    assert pyo.value(model.urgency["P-MANDATORY"]) == 0
    assert coefficients["x[P-WAIT,OR-1,2026-08-10]"] == pytest.approx(5.0)
    assert coefficients["x[P-WAIT,OR-1,2026-08-11]"] == pytest.approx(5.0)
    assert "x[P-MANDATORY,OR-1,2026-08-10]" not in coefficients
    assert coefficients["fairness_floor"] == 1.0
    assert coefficients["unassigned[P-WAIT,OR-1,2026-08-10]"] == -1.0


@pytest.mark.parametrize(
    "data",
    [
        _model_input(changeover_minutes=11),
        _model_input(with_availability=True),
        _model_input(objective_weights=ObjectiveWeights(fairness=0)),
    ],
)
def test_paper_builder_rejects_non_paper_settings(data: SchedulingInput) -> None:
    with pytest.raises(InputValidationError, match="build_platform_model"):
        build_paper_model(data)


def test_platform_extensions_are_named_and_do_not_replace_equation_1c() -> None:
    model = build_platform_model(
        _model_input(changeover_minutes=11, with_availability=True),
        max_operations_per_session=12,
    ).model

    base_capacity = model.session_capacity["OR-1", "2026-08-10"]
    assert pyo.value(base_capacity.upper) == 180
    assert _coefficients(base_capacity.body)["x[P-WAIT,OR-1,2026-08-10]"] == 60

    changeover = model.platform_changeover_capacity["OR-1", "2026-08-10"]
    assert pyo.value(changeover.upper) == 191
    assert _coefficients(changeover.body) == {
        "x[P-WAIT,OR-1,2026-08-10]": 71.0,
        "x[P-MANDATORY,OR-1,2026-08-10]": 101.0,
        "x[P-RESCHEDULED,OR-1,2026-08-10]": 41.0,
    }

    unavailable = model.platform_resident_availability["P-WAIT", "R-HIGH", "OR-1", "2026-08-10"]
    available = model.platform_resident_availability["P-WAIT", "R-LOW", "OR-1", "2026-08-10"]
    assert pyo.value(unavailable.upper) == 0
    assert pyo.value(available.upper) == 1
    assert pyo.value(model.platform_operation_row_limit["OR-1", "2026-08-10"].upper) == 12


def test_paper_builder_requires_a_complete_room_day_grid() -> None:
    source = _model_input()
    data = SchedulingInput(
        patients=source.patients,
        residents=source.residents,
        sessions=(
            source.sessions[0],
            Session("OR-2", date(2026, 8, 11), 180),
        ),
    )

    with pytest.raises(InputValidationError, match="ogni combinazione sala/giorno"):
        build_paper_model(data)
