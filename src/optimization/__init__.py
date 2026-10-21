from __future__ import annotations

from .domain import (
    ObjectiveWeights,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
)
from .exceptions import (
    InputValidationError,
    OptimizationError,
    PlanningCancelledError,
    PlatformDataError,
    PlatformPersistenceError,
    SolutionValidationError,
    SolverUnavailableError,
)
from .model import BuiltSchedulingModel, build_paper_model, build_platform_model
from .platform_mapping import PlatformPlanningPolicy
from .platform_service import PlatformPlanningRun, plan_platform_week
from .results import ObjectiveBreakdown, ScheduledSurgery, SolveResult, SolveStatus
from .solver import HighsConfig, HighsSolver

__all__ = [
    "BuiltSchedulingModel",
    "HighsConfig",
    "HighsSolver",
    "InputValidationError",
    "ObjectiveBreakdown",
    "ObjectiveWeights",
    "OptimizationError",
    "PlanningCancelledError",
    "Patient",
    "PatientCategory",
    "PlatformDataError",
    "PlatformPersistenceError",
    "PlatformPlanningPolicy",
    "PlatformPlanningRun",
    "Resident",
    "ScheduledSurgery",
    "SchedulingInput",
    "Session",
    "SolutionValidationError",
    "SolveResult",
    "SolveStatus",
    "SolverUnavailableError",
    "build_paper_model",
    "build_platform_model",
    "plan_platform_week",
]
