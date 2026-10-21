from __future__ import annotations

from collections.abc import Iterable


class OptimizationError(RuntimeError):
    """Base optimization error."""


class InputValidationError(OptimizationError, ValueError):
    """Invalid scheduling input."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = tuple(errors)
        details = "\n".join(f"- {error}" for error in self.errors)
        super().__init__(f"Dati di pianificazione non validi:\n{details}")


class SolverUnavailableError(OptimizationError):
    """Solver not available."""


class SolutionValidationError(OptimizationError):
    """Invalid solver solution."""


class PlanningCancelledError(OptimizationError):
    """Planning cancelled before persistence."""


class PlatformDataError(OptimizationError, ValueError):
    """Invalid platform data."""


class PlatformPersistenceError(OptimizationError):
    """Platform plan not persisted."""
