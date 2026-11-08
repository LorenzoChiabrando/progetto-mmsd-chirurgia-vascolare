from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class SolveStatus(str, Enum):
    """Solver-independent status."""

    OPTIMAL = "optimal"
    FEASIBLE = "feasible_not_proven_optimal"
    INFEASIBLE = "infeasible"
    INFEASIBLE_OR_UNBOUNDED = "infeasible_or_unbounded"
    UNBOUNDED = "unbounded"
    LIMIT_REACHED = "limit_reached_no_solution"
    INTERRUPTED = "interrupted"
    ERROR = "error"

    @property
    def label(self) -> str:
        """Etichetta italiana per l'interfaccia; ``value`` resta il codice stabile."""

        return _SOLVE_STATUS_LABELS[self]


_SOLVE_STATUS_LABELS = {
    SolveStatus.OPTIMAL: "ottimo",
    SolveStatus.FEASIBLE: "ammissibile (ottimalità non dimostrata)",
    SolveStatus.INFEASIBLE: "nessuna soluzione ammissibile",
    SolveStatus.INFEASIBLE_OR_UNBOUNDED: "inammissibile o illimitato",
    SolveStatus.UNBOUNDED: "illimitato",
    SolveStatus.LIMIT_REACHED: "limite raggiunto senza soluzione",
    SolveStatus.INTERRUPTED: "interrotto",
    SolveStatus.ERROR: "errore del solver",
}


@dataclass(frozen=True, slots=True)
class ScheduledSurgery:
    """Patient assigned to an operating-room session."""

    patient_id: str
    room_id: str
    day: date
    resident_id: str | None


@dataclass(frozen=True, slots=True)
class ObjectiveBreakdown:
    """Objective components and weighted total."""

    treatment_efficiency: float
    fairness_floor: int
    unassigned_count: int
    weighted_total: float


@dataclass(frozen=True, slots=True)
class SolveResult:
    """Solver result independent of Pyomo."""

    status: SolveStatus
    termination_condition: str
    solver_name: str
    solver_version: str
    elapsed_seconds: float
    schedule: tuple[ScheduledSurgery, ...] = ()
    objective: ObjectiveBreakdown | None = None
    best_objective_bound: float | None = None
    relative_gap: float | None = None

    @property
    def has_solution(self) -> bool:
        """Return whether the result contains a feasible solution."""

        return self.status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}
