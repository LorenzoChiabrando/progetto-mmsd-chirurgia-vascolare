from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import pyomo.core as pyo

from .domain import ObjectiveWeights, PatientCategory, SchedulingInput
from .exceptions import InputValidationError
from .validation import validate_scheduling_input


@dataclass(frozen=True, slots=True)
class BuiltSchedulingModel:
    """Pyomo model and its source data."""

    model: pyo.ConcreteModel
    source: SchedulingInput


@dataclass(frozen=True, slots=True)
class _BuildOptions:
    use_configured_objective: bool = False
    include_changeover: bool = False
    include_session_availability: bool = False
    include_patient_dates: bool = False
    max_operations_per_session: int | None = None


def build_paper_model(data: SchedulingInput) -> BuiltSchedulingModel:
    """Build (1a)-(1g) and (6) with the roster-based replacement of (1d)."""

    validate_scheduling_input(data)
    errors: list[str] = []
    if data.changeover_minutes != 0:
        errors.append(
            "build_paper_model richiede changeover_minutes=0; "
            "usare build_platform_model per la regola empirica dei tempi di cambio."
        )
    if any(session.available_resident_ids is not None for session in data.sessions):
        errors.append(
            "build_paper_model non gestisce la disponibilità giornaliera degli specializzandi; "
            "usare build_platform_model per i vincoli di disponibilità."
        )
    if any(patient.earliest_surgery_date is not None for patient in data.patients):
        errors.append(
            "build_paper_model non gestisce le date di inserimento dei pazienti; "
            "usare build_platform_model per i vincoli sulle date."
        )
    if data.objective_weights != ObjectiveWeights():
        errors.append(
            "build_paper_model richiede i coefficienti dell'obiettivo del paper C, +1, -1; "
            "usare build_platform_model per pesi sperimentali."
        )
    if errors:
        raise InputValidationError(errors)
    return _build_model(data, _BuildOptions())


def build_platform_model(
    data: SchedulingInput,
    *,
    max_operations_per_session: int | None = None,
) -> BuiltSchedulingModel:
    """Build the paper core with platform date, availability, changeover and row limits."""

    validate_scheduling_input(data)
    if max_operations_per_session is not None and (
        not isinstance(max_operations_per_session, int)
        or isinstance(max_operations_per_session, bool)
        or max_operations_per_session <= 0
    ):
        raise InputValidationError(["max_operations_per_session deve essere un intero positivo."])
    return _build_model(
        data,
        _BuildOptions(
            use_configured_objective=True,
            include_changeover=True,
            include_session_availability=True,
            include_patient_dates=True,
            max_operations_per_session=max_operations_per_session,
        ),
    )


def _build_model(data: SchedulingInput, options: _BuildOptions) -> BuiltSchedulingModel:
    patient_by_id = {patient.patient_id: patient for patient in data.patients}
    resident_by_id = {specialist.resident_id: specialist for specialist in data.residents}
    session_by_key = {session.key: session for session in data.sessions}

    patient_ids = tuple(patient_by_id)
    resident_ids = tuple(resident_by_id)
    room_ids = tuple(dict.fromkeys(session.room_id for session in data.sessions))
    day_ids = tuple(dict.fromkeys(session.day.isoformat() for session in data.sessions))
    session_keys = tuple(product(room_ids, day_ids))
    missing_sessions = sorted(set(session_keys) - set(session_by_key))
    if missing_sessions:
        raise InputValidationError(
            [
                "La formulazione del paper richiede una sessione v[k,t] per ogni "
                f"combinazione sala/giorno; mancano {missing_sessions}."
            ]
        )

    waiting_ids = tuple(
        patient.patient_id
        for patient in data.patients
        if patient.category is PatientCategory.WAITING_LIST
    )
    mandatory_ids = tuple(
        patient.patient_id
        for patient in data.patients
        if patient.category is PatientCategory.MANDATORY
    )
    rescheduled_ids = tuple(
        patient.patient_id
        for patient in data.patients
        if patient.category is PatientCategory.RESCHEDULED
    )
    required_ids = (*mandatory_ids, *rescheduled_ids)
    fairness_ids = (*waiting_ids, *mandatory_ids)
    level_ids = tuple(
        sorted(
            {patient.procedure_level for patient in data.patients}
            | {level for specialist in data.residents for level in specialist.qualified_levels}
        )
    )

    model = pyo.ConcreteModel(name="elective_surgery_and_specialist_training")
    model.PATIENTS = pyo.Set(initialize=patient_ids, ordered=True)
    model.WAITING_PATIENTS = pyo.Set(initialize=waiting_ids, within=model.PATIENTS, ordered=True)
    model.MANDATORY_PATIENTS = pyo.Set(
        initialize=mandatory_ids,
        within=model.PATIENTS,
        ordered=True,
    )
    model.RESCHEDULED_PATIENTS = pyo.Set(
        initialize=rescheduled_ids,
        within=model.PATIENTS,
        ordered=True,
    )
    model.REQUIRED_PATIENTS = pyo.Set(
        initialize=required_ids,
        within=model.PATIENTS,
        ordered=True,
    )
    model.FAIRNESS_PATIENTS = pyo.Set(
        initialize=fairness_ids,
        within=model.PATIENTS,
        ordered=True,
    )
    model.RESIDENTS = pyo.Set(initialize=resident_ids, ordered=True)
    model.ROOMS = pyo.Set(initialize=room_ids, ordered=True)
    model.DAYS = pyo.Set(initialize=day_ids, ordered=True)
    model.LEVELS = pyo.Set(initialize=level_ids, ordered=True)
    model.SESSIONS = pyo.Set(initialize=session_keys, dimen=2, ordered=True)

    model.duration_minutes = pyo.Param(
        model.PATIENTS,
        initialize={
            patient_id: patient.duration_minutes for patient_id, patient in patient_by_id.items()
        },
        within=pyo.PositiveIntegers,
    )
    model.procedure_level = pyo.Param(
        model.PATIENTS,
        initialize={
            patient_id: patient.procedure_level for patient_id, patient in patient_by_id.items()
        },
        within=model.LEVELS,
    )
    # In (2), u_i exists only for I'; use zero for I'' and I'''.
    model.urgency = pyo.Param(
        model.PATIENTS,
        initialize={
            patient_id: (
                patient_by_id[patient_id].urgency
                if patient_by_id[patient_id].category is PatientCategory.WAITING_LIST
                else 0.0
            )
            for patient_id in patient_ids
        },
        within=pyo.Reals,
    )
    model.capacity_minutes = pyo.Param(
        model.SESSIONS,
        initialize={key: session_by_key[key].capacity_minutes for key in session_keys},
        within=pyo.PositiveIntegers,
    )
    model.resident_level_qualification = pyo.Param(
        model.RESIDENTS,
        model.LEVELS,
        initialize={
            (resident_id, level): int(level in resident_by_id[resident_id].qualified_levels)
            for resident_id in resident_ids
            for level in level_ids
        },
        within=pyo.Binary,
    )
    model.resident_roster_assignment = pyo.Param(
        model.RESIDENTS,
        model.ROOMS,
        model.DAYS,
        initialize={
            (resident_id, room_id, day): 1
            for resident_id in resident_ids
            for room_id, day in session_keys
            if resident_id in session_by_key[room_id, day].assigned_resident_ids
        },
        default=0,
        within=pyo.Binary,
    )

    objective_weights = (
        data.objective_weights if options.use_configured_objective else ObjectiveWeights()
    )
    efficiency_scale = (
        data.efficiency_scale if options.use_configured_objective else data.paper_efficiency_scale
    )
    model.efficiency_scale = pyo.Param(initialize=efficiency_scale, within=pyo.PositiveReals)
    model.fairness_weight = pyo.Param(
        initialize=objective_weights.fairness,
        within=pyo.NonNegativeReals,
    )
    model.unassigned_weight = pyo.Param(
        initialize=objective_weights.unassigned_penalty,
        within=pyo.PositiveReals,
    )

    # X_ikt, Y_ijkt, epsilon_ikt and Z_f.
    model.x = pyo.Var(model.PATIENTS, model.ROOMS, model.DAYS, domain=pyo.Binary)
    model.y = pyo.Var(
        model.PATIENTS,
        model.RESIDENTS,
        model.ROOMS,
        model.DAYS,
        domain=pyo.Binary,
    )
    model.unassigned = pyo.Var(
        model.PATIENTS,
        model.ROOMS,
        model.DAYS,
        domain=pyo.NonNegativeIntegers,
    )
    model.fairness_floor = pyo.Var(domain=pyo.NonNegativeIntegers)

    def waiting_patient_once_rule(m: pyo.ConcreteModel, patient_id: str) -> pyo.Expression:
        """Equation (1a)."""

        return sum(m.x[patient_id, room_id, day] for room_id in m.ROOMS for day in m.DAYS) <= 1

    model.waiting_patient_once = pyo.Constraint(
        model.WAITING_PATIENTS,
        rule=waiting_patient_once_rule,
    )

    def required_patient_once_rule(m: pyo.ConcreteModel, patient_id: str) -> pyo.Expression:
        """Equation (1b)."""

        return sum(m.x[patient_id, room_id, day] for room_id in m.ROOMS for day in m.DAYS) == 1

    model.required_patient_once = pyo.Constraint(
        model.REQUIRED_PATIENTS,
        rule=required_patient_once_rule,
    )

    def capacity_rule(m: pyo.ConcreteModel, room_id: str, day: str) -> pyo.Expression:
        """Equation (1c), containing only p_i and v_kt as printed."""

        return (
            sum(
                m.duration_minutes[patient_id] * m.x[patient_id, room_id, day]
                for patient_id in m.PATIENTS
            )
            <= m.capacity_minutes[room_id, day]
        )

    model.session_capacity = pyo.Constraint(model.ROOMS, model.DAYS, rule=capacity_rule)

    def rostered_resident_requirement_rule(
        m: pyo.ConcreteModel,
        patient_id: str,
        resident_id: str,
        room_id: str,
        day: str,
    ) -> pyo.Expression:
        """Modified (1d): A_jkt h_j,f_i X_ikt <= Y_ijkt."""

        level = patient_by_id[patient_id].procedure_level
        return (
            m.resident_roster_assignment[resident_id, room_id, day]
            * m.resident_level_qualification[resident_id, level]
            * m.x[patient_id, room_id, day]
            <= m.y[patient_id, resident_id, room_id, day]
        )

    model.rostered_resident_requirement = pyo.Constraint(
        model.PATIENTS,
        model.RESIDENTS,
        model.ROOMS,
        model.DAYS,
        rule=rostered_resident_requirement_rule,
    )

    def resident_coverage_rule(
        m: pyo.ConcreteModel,
        patient_id: str,
        room_id: str,
        day: str,
    ) -> pyo.Expression:
        """Equation (1e): sum_j Y_ijkt + epsilon_ikt >= X_ikt."""

        body = (
            sum(m.y[patient_id, resident_id, room_id, day] for resident_id in m.RESIDENTS)
            + m.unassigned[patient_id, room_id, day]
            - m.x[patient_id, room_id, day]
        )
        return 0, body, None

    model.resident_coverage = pyo.Constraint(
        model.PATIENTS,
        model.ROOMS,
        model.DAYS,
        rule=resident_coverage_rule,
    )

    def at_most_one_resident_rule(
        m: pyo.ConcreteModel,
        patient_id: str,
        room_id: str,
        day: str,
    ) -> pyo.Expression:
        """Equation (1f): sum_j Y_ijkt <= X_ikt."""

        return (
            sum(m.y[patient_id, resident_id, room_id, day] for resident_id in m.RESIDENTS)
            <= m.x[patient_id, room_id, day]
        )

    model.at_most_one_resident = pyo.Constraint(
        model.PATIENTS,
        model.ROOMS,
        model.DAYS,
        rule=at_most_one_resident_rule,
    )

    def fairness_floor_rule(m: pyo.ConcreteModel, resident_id: str) -> pyo.Expression:
        """Equation (1g), excluding the rescheduled set I'''."""

        workload = sum(
            m.y[patient_id, resident_id, room_id, day]
            for patient_id in m.FAIRNESS_PATIENTS
            for room_id in m.ROOMS
            for day in m.DAYS
        )
        return m.fairness_floor <= workload

    model.fairness_floor_definition = pyo.Constraint(
        model.RESIDENTS,
        rule=fairness_floor_rule,
    )

    if options.include_changeover and data.changeover_minutes:
        changeover = data.changeover_minutes

        def changeover_capacity_rule(
            m: pyo.ConcreteModel,
            room_id: str,
            day: str,
        ) -> pyo.Expression:
            occupied = sum(
                (m.duration_minutes[patient_id] + changeover) * m.x[patient_id, room_id, day]
                for patient_id in m.PATIENTS
            )
            return occupied <= m.capacity_minutes[room_id, day] + changeover

        model.platform_changeover_capacity = pyo.Constraint(
            model.ROOMS,
            model.DAYS,
            rule=changeover_capacity_rule,
        )

    if options.include_session_availability and any(
        session.available_resident_ids is not None for session in data.sessions
    ):

        def session_availability_rule(
            m: pyo.ConcreteModel,
            patient_id: str,
            resident_id: str,
            room_id: str,
            day: str,
        ) -> pyo.Expression:
            available_ids = session_by_key[room_id, day].available_resident_ids
            available = int(available_ids is None or resident_id in available_ids)
            return m.y[patient_id, resident_id, room_id, day] <= available

        model.platform_resident_availability = pyo.Constraint(
            model.PATIENTS,
            model.RESIDENTS,
            model.ROOMS,
            model.DAYS,
            rule=session_availability_rule,
        )

    if options.include_patient_dates and any(
        patient.earliest_surgery_date is not None for patient in data.patients
    ):
        blocked_sessions = tuple(
            (patient.patient_id, room_id, day)
            for patient in data.patients
            if patient.earliest_surgery_date is not None
            for room_id, day in session_keys
            if session_by_key[room_id, day].day < patient.earliest_surgery_date
        )
        model.PRE_INSERTION_SESSIONS = pyo.Set(
            initialize=blocked_sessions, dimen=3, ordered=True,
        )

        def patient_date_rule(
            m: pyo.ConcreteModel, patient_id: str, room_id: str, day: str,
        ) -> pyo.Expression:
            """Platform rule: X_ikt = 0 on dates before patient insertion."""

            return m.x[patient_id, room_id, day] == 0

        model.platform_patient_date = pyo.Constraint(
            model.PRE_INSERTION_SESSIONS, rule=patient_date_rule,
        )

    if options.max_operations_per_session is not None:
        limit = options.max_operations_per_session

        def operation_row_limit_rule(
            m: pyo.ConcreteModel,
            room_id: str,
            day: str,
        ) -> pyo.Expression:
            return sum(m.x[patient_id, room_id, day] for patient_id in m.PATIENTS) <= limit

        model.platform_operation_row_limit = pyo.Constraint(
            model.ROOMS,
            model.DAYS,
            rule=operation_row_limit_rule,
        )

    # (2), (4), (5), (6); (3) follows from (1g) and maximising Z_f.
    model.treatment_efficiency = pyo.Expression(
        expr=sum(
            model.urgency[patient_id] * model.x[patient_id, room_id, day]
            for patient_id in model.PATIENTS
            for room_id in model.ROOMS
            for day in model.DAYS
        )
    )
    model.unassigned_count = pyo.Expression(
        expr=sum(
            model.unassigned[patient_id, room_id, day]
            for patient_id in model.PATIENTS
            for room_id in model.ROOMS
            for day in model.DAYS
        )
    )
    model.objective = pyo.Objective(
        expr=(
            model.efficiency_scale * model.treatment_efficiency
            + model.fairness_weight * model.fairness_floor
            - model.unassigned_weight * model.unassigned_count
        ),
        sense=pyo.maximize,
    )

    return BuiltSchedulingModel(model=model, source=data)
