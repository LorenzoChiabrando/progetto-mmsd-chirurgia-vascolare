from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class PatientCategory(str, Enum):
    """Patient sets I', I'' and I''' from the paper."""

    WAITING_LIST = "waiting_list"
    MANDATORY = "mandatory"
    RESCHEDULED = "rescheduled"


@dataclass(frozen=True, slots=True)
class Patient:
    """Surgical case with signed waiting days and an optional first permitted date.

    Durations are minutes. ``earliest_surgery_date`` is inclusive and is enforced
    by the platform model; ``None`` leaves the patient dates unrestricted.
    """

    patient_id: str
    category: PatientCategory
    duration_minutes: int
    procedure_level: str
    waiting_time_days: int | None = None
    max_wait_days: int | None = None
    earliest_surgery_date: date | None = None

    @property
    def urgency(self) -> float:
        """Return u_i = waiting_time_days / max_wait_days."""

        if self.waiting_time_days is None or self.max_wait_days is None:
            return 0.0
        return self.waiting_time_days / self.max_wait_days


@dataclass(frozen=True, slots=True)
class Resident:
    """Resident and procedure-level qualifications h_jl used by (1d)."""

    resident_id: str
    qualified_levels: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "qualified_levels", frozenset(self.qualified_levels))


@dataclass(frozen=True, slots=True)
class Session:
    """Room/day capacity in minutes, roster A_jkt and optional platform availability.

    ``assigned_resident_ids`` contains exactly the residents with A_jkt=1.
    An empty set means no roster assignment; it does not mean everyone is assigned.
    ``available_resident_ids=None`` leaves the platform availability unrestricted.
    """

    room_id: str
    day: date
    capacity_minutes: int
    available_resident_ids: frozenset[str] | None = None
    assigned_resident_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "assigned_resident_ids", frozenset(self.assigned_resident_ids))
        if self.available_resident_ids is not None:
            object.__setattr__(
                self,
                "available_resident_ids",
                frozenset(self.available_resident_ids),
            )

    @property
    def key(self) -> tuple[str, str]:
        """Return ``(room_id, ISO date)``."""

        return self.room_id, self.day.isoformat()


@dataclass(frozen=True, slots=True)
class ObjectiveWeights:
    """Coefficients for (6); ``efficiency_scale=None`` uses C from (5)."""

    efficiency_scale: float | None = None
    fairness: float = 1.0
    unassigned_penalty: float = 1.0


@dataclass(frozen=True, slots=True)
class SchedulingInput:
    """Input data for one weekly MILP instance."""

    patients: tuple[Patient, ...]
    residents: tuple[Resident, ...]
    sessions: tuple[Session, ...]
    objective_weights: ObjectiveWeights = field(default_factory=ObjectiveWeights)
    changeover_minutes: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "patients", tuple(self.patients))
        object.__setattr__(self, "residents", tuple(self.residents))
        object.__setattr__(self, "sessions", tuple(self.sessions))

    @property
    def paper_efficiency_scale(self) -> float:
        """Compute C from (5), using 1 when I' is empty."""

        limits = [
            patient.max_wait_days
            for patient in self.patients
            if patient.category is PatientCategory.WAITING_LIST
            and patient.max_wait_days is not None
        ]
        return float(max(limits, default=1))

    @property
    def efficiency_scale(self) -> float:
        """Return the configured scale or C from (5)."""

        configured = self.objective_weights.efficiency_scale
        return float(configured if configured is not None else self.paper_efficiency_scale)
