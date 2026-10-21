from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pyomo.core as pyo
from pyomo.contrib.appsi.base import TerminationCondition
from pyomo.contrib.appsi.solvers import Highs

from .domain import PatientCategory
from .exceptions import SolutionValidationError, SolverUnavailableError
from .model import BuiltSchedulingModel
from .results import ObjectiveBreakdown, ScheduledSurgery, SolveResult, SolveStatus


@dataclass(frozen=True, slots=True)
class HighsConfig:
    """HiGHS options used by the solver."""

    time_limit_seconds: float = 300.0
    mip_relative_gap: float = 1e-4
    threads: int = 1
    random_seed: int = 0
    stream_solver: bool = False
    validate_solution: bool = True

    def __post_init__(self) -> None:
        if not math.isfinite(self.time_limit_seconds) or self.time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds deve essere finito e positivo.")
        if not math.isfinite(self.mip_relative_gap) or not 0 <= self.mip_relative_gap < 1:
            raise ValueError("mip_relative_gap deve essere finito e compreso in [0, 1).")
        if self.threads <= 0:
            raise ValueError("threads deve essere positivo.")
        if self.random_seed < 0:
            raise ValueError("random_seed non può essere negativo.")


class HighsSolver:
    """Pyomo APPSI wrapper for HiGHS."""

    def __init__(self, config: HighsConfig | None = None) -> None:
        self.config = config or HighsConfig()

    @staticmethod
    def is_available() -> bool:
        """Return whether the ``highspy`` bindings are available."""

        return bool(Highs().available())

    def solve(
        self,
        built: BuiltSchedulingModel,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> SolveResult:
        """Solve a model and return no assignments after an interruption."""

        solver = Highs()
        availability = solver.available()
        if not bool(availability):
            raise SolverUnavailableError(
                "Il solver HiGHS non è disponibile. Installare le dipendenze del progetto con "
                "`python -m pip install -r requirements.txt`. "
                f"Stato riportato da Pyomo: {availability}"
            )

        solver.config.load_solution = False
        solver.config.time_limit = self.config.time_limit_seconds
        solver.config.mip_gap = self.config.mip_relative_gap
        solver.config.stream_solver = self.config.stream_solver
        solver.highs_options.update(
            threads=self.config.threads,
            random_seed=self.config.random_seed,
            presolve="choose",
        )

        started = time.perf_counter()
        detach_cancellation: Callable[[], None] | None = None
        if cancel_requested is not None:
            solver.set_instance(built.model)
            if cancel_requested():
                return _interrupted_result(solver, time.perf_counter() - started)
            detach_cancellation = _attach_highs_cancellation(solver, cancel_requested)
        try:
            raw_results = solver.solve(built.model)
        finally:
            if detach_cancellation is not None:
                detach_cancellation()
        elapsed = time.perf_counter() - started

        termination = raw_results.termination_condition
        raw_status = _raw_highs_status(solver)
        was_interrupted = raw_status in {"kInterrupt", "kHighsInterrupt"}
        has_incumbent = _finite_or_none(raw_results.best_feasible_objective) is not None
        should_load = not was_interrupted and (
            termination is TerminationCondition.optimal or has_incumbent
        )

        if was_interrupted:
            status = SolveStatus.INTERRUPTED
            schedule = ()
            objective = None
        elif should_load:
            raw_results.solution_loader.load_vars()
            status = (
                SolveStatus.OPTIMAL
                if termination is TerminationCondition.optimal
                else SolveStatus.FEASIBLE
            )
            schedule = _extract_schedule(built)
            # With zero fairness weight, Z_f may be below the actual minimum workload.
            objective = _extract_objective(
                built.model,
                fairness_floor=_actual_fairness_floor(built, schedule),
            )
            if self.config.validate_solution:
                _validate_solution(built, schedule, objective)
        else:
            status = _status_without_solution(termination)
            schedule = ()
            objective = None

        best_bound = _finite_or_none(raw_results.best_objective_bound)
        relative_gap = (
            _relative_gap(objective.weighted_total, best_bound)
            if objective is not None and best_bound is not None
            else None
        )

        return SolveResult(
            status=status,
            termination_condition=(
                f"HighsModelStatus.{raw_status}" if was_interrupted else str(termination)
            ),
            solver_name="HiGHS",
            solver_version=".".join(str(part) for part in solver.version()),
            elapsed_seconds=elapsed,
            schedule=schedule,
            objective=objective,
            best_objective_bound=best_bound,
            relative_gap=relative_gap,
        )


def _attach_highs_cancellation(
    solver: Highs,
    cancel_requested: Callable[[], bool],
) -> Callable[[], None]:
    backend = getattr(solver, "_solver_model", None)
    if backend is None:
        raise SolverUnavailableError(
            "Pyomo APPSI HiGHS non ha esposto un modello highspy inizializzato."
        )

    channels: list[Any] = []
    for name in ("cbMipInterrupt", "cbSimplexInterrupt", "cbIpmInterrupt"):
        channel = getattr(backend, name, None)
        if not callable(getattr(channel, "subscribe", None)) or not callable(
            getattr(channel, "unsubscribe", None)
        ):
            raise SolverUnavailableError(
                f"La versione installata di highspy non offre la callback di annullamento {name}."
            )
        channels.append(channel)

    def interrupt_if_requested(callback_event: Any) -> None:
        _interrupt_if_requested(callback_event, cancel_requested)

    subscribed: list[Any] = []
    try:
        for channel in channels:
            channel.subscribe(interrupt_if_requested)
            subscribed.append(channel)
    except Exception as exc:
        for channel in reversed(subscribed):
            channel.unsubscribe(interrupt_if_requested)
        raise SolverUnavailableError(
            "Impossibile installare le callback di annullamento di HiGHS."
        ) from exc

    def detach() -> None:
        for channel in reversed(subscribed):
            channel.unsubscribe(interrupt_if_requested)

    return detach


def _interrupt_if_requested(
    callback_event: Any,
    cancel_requested: Callable[[], bool],
) -> None:
    if cancel_requested():
        callback_event.interrupt()


def _raw_highs_status(solver: Highs) -> str:
    backend = getattr(solver, "_solver_model", None)
    get_status = getattr(backend, "getModelStatus", None)
    if not callable(get_status):
        return ""
    return str(getattr(get_status(), "name", ""))


def _interrupted_result(solver: Highs, elapsed_seconds: float) -> SolveResult:
    return SolveResult(
        status=SolveStatus.INTERRUPTED,
        termination_condition="cancelled_before_solve",
        solver_name="HiGHS",
        solver_version=".".join(str(part) for part in solver.version()),
        elapsed_seconds=elapsed_seconds,
    )


def _status_without_solution(termination: TerminationCondition) -> SolveStatus:
    if termination is TerminationCondition.infeasible:
        return SolveStatus.INFEASIBLE
    if termination is TerminationCondition.infeasibleOrUnbounded:
        return SolveStatus.INFEASIBLE_OR_UNBOUNDED
    if termination is TerminationCondition.unbounded:
        return SolveStatus.UNBOUNDED
    if termination in {
        TerminationCondition.maxTimeLimit,
        TerminationCondition.maxIterations,
        TerminationCondition.objectiveLimit,
    }:
        return SolveStatus.LIMIT_REACHED
    if termination is TerminationCondition.interrupted:
        return SolveStatus.INTERRUPTED
    return SolveStatus.ERROR


def _extract_schedule(built: BuiltSchedulingModel) -> tuple[ScheduledSurgery, ...]:
    model = built.model
    session_by_key = {session.key: session for session in built.source.sessions}
    records: list[ScheduledSurgery] = []

    for patient in built.source.patients:
        for room_id, day_key in model.SESSIONS:
            if pyo.value(model.x[patient.patient_id, room_id, day_key]) < 0.5:
                continue
            assigned = [
                resident.resident_id
                for resident in built.source.residents
                if pyo.value(model.y[patient.patient_id, resident.resident_id, room_id, day_key])
                > 0.5
            ]
            records.append(
                ScheduledSurgery(
                    patient_id=patient.patient_id,
                    room_id=room_id,
                    day=session_by_key[room_id, day_key].day,
                    resident_id=assigned[0] if assigned else None,
                )
            )

    return tuple(sorted(records, key=lambda item: (item.day, item.room_id, item.patient_id)))


def _extract_objective(
    model: pyo.ConcreteModel,
    *,
    fairness_floor: int,
) -> ObjectiveBreakdown:
    return ObjectiveBreakdown(
        treatment_efficiency=float(pyo.value(model.treatment_efficiency)),
        fairness_floor=fairness_floor,
        unassigned_count=int(round(pyo.value(model.unassigned_count))),
        weighted_total=float(pyo.value(model.objective)),
    )


def _validate_solution(
    built: BuiltSchedulingModel,
    schedule: tuple[ScheduledSurgery, ...],
    objective: ObjectiveBreakdown,
    tolerance: float = 1e-6,
) -> None:
    source = built.source
    patient_by_id = {patient.patient_id: patient for patient in source.patients}
    resident_by_id = {resident.resident_id: resident for resident in source.residents}
    session_by_key = {session.key: session for session in source.sessions}
    scheduled_by_patient: dict[str, list[ScheduledSurgery]] = {}
    for record in schedule:
        scheduled_by_patient.setdefault(record.patient_id, []).append(record)

    errors: list[str] = []
    for patient in source.patients:
        count = len(scheduled_by_patient.get(patient.patient_id, []))
        if patient.category is PatientCategory.WAITING_LIST and count > 1:
            errors.append(
                f"Paziente in lista d'attesa {patient.patient_id!r} pianificato {count} volte."
            )
        if patient.category is not PatientCategory.WAITING_LIST and count != 1:
            errors.append(
                f"Paziente obbligatorio {patient.patient_id!r} pianificato {count} volte."
            )

    session_load: dict[tuple[str, object], list[int]] = {}
    for record in schedule:
        patient = patient_by_id[record.patient_id]
        if patient.earliest_surgery_date is not None and record.day < patient.earliest_surgery_date:
            errors.append(
                f"Paziente {record.patient_id!r} pianificato prima della data di inserimento."
            )
        key = (record.room_id, record.day)
        session_load.setdefault(key, []).append(patient.duration_minutes)
        session = session_by_key[record.room_id, record.day.isoformat()]
        for resident_id in sorted(session.assigned_resident_ids):
            resident = resident_by_id[resident_id]
            if (
                patient.procedure_level in resident.qualified_levels
                and record.resident_id != resident_id
            ):
                errors.append(
                    f"Il paziente {record.patient_id!r} richiede lo specializzando di turno "
                    f"{resident_id!r} nella sessione {session.key!r} secondo il vincolo (1d)."
                )
        if (
            record.resident_id is not None
            and session.available_resident_ids is not None
            and record.resident_id not in session.available_resident_ids
        ):
            errors.append(
                f"Lo specializzando {record.resident_id!r} non è disponibile per la sessione "
                f"{session.key!r}."
            )

    for session in source.sessions:
        durations = session_load.get((session.room_id, session.day), [])
        occupied = sum(durations)
        if durations:
            occupied += source.changeover_minutes * (len(durations) - 1)
        if occupied > session.capacity_minutes + tolerance:
            errors.append(
                f"La sessione {session.key!r} occupa {occupied} minuti su "
                f"{session.capacity_minutes}."
            )

    unassigned = sum(record.resident_id is None for record in schedule)
    if unassigned != objective.unassigned_count:
        errors.append(
            f"unassigned_count dichiarato {objective.unassigned_count}, ricalcolato {unassigned}."
        )

    actual_floor = _actual_fairness_floor(built, schedule)
    if objective.fairness_floor != actual_floor:
        errors.append(
            f"fairness_floor dichiarato {objective.fairness_floor}, ricalcolato {actual_floor}."
        )

    if errors:
        raise SolutionValidationError(
            "Soluzione del solver non valida:\n- " + "\n- ".join(errors)
        )


def _actual_fairness_floor(
    built: BuiltSchedulingModel,
    schedule: tuple[ScheduledSurgery, ...],
) -> int:
    patient_by_id = {patient.patient_id: patient for patient in built.source.patients}
    workloads = {resident.resident_id: 0 for resident in built.source.residents}
    for record in schedule:
        patient = patient_by_id[record.patient_id]
        if record.resident_id is not None and patient.category is not PatientCategory.RESCHEDULED:
            workloads[record.resident_id] += 1
    return min(workloads.values(), default=0)


def _finite_or_none(value: object) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _relative_gap(objective: float, bound: float) -> float:
    return abs(objective - bound) / max(1.0, abs(objective))
