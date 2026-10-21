"""Qt worker that runs weekly optimization without blocking the GUI thread."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal

from src.data_paths import resolve_data_directory
from src.optimization.exceptions import OptimizationError, PlanningCancelledError
from src.optimization.platform_service import PlatformPlanningRun, plan_platform_week

PlanningService = Callable[..., PlatformPlanningRun]

_LOGGER = logging.getLogger(__name__)


class PlatformPlanningWorker(QThread):
    """Run one planning service call in an owned Qt thread."""

    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        project_root: str | Path,
        monday: date,
        *,
        overwrite: bool,
        cancel_event: Event,
        data_directory: str | Path | None = None,
        planning_service: PlanningService = plan_platform_week,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_root = Path(project_root).resolve()
        self._data_directory = resolve_data_directory(
            data_directory, project_root=self._project_root,
        )
        self._monday = monday
        self._overwrite = overwrite
        self._cancel_event = cancel_event
        self._planning_service = planning_service

    def run(self) -> None:
        """Execute the application service entirely outside the GUI thread."""

        try:
            result = self._planning_service(
                self._project_root,
                self._monday,
                overwrite=self._overwrite,
                persist=True,
                data_directory=self._data_directory,
                cancel_requested=self._cancel_event.is_set,
            )
        except PlanningCancelledError:
            self.cancelled.emit()
        except OptimizationError as exc:
            self.failed.emit(str(exc))
        except Exception:
            _LOGGER.exception("Unexpected failure in the platform planning worker")
            self.failed.emit("Errore imprevisto durante la generazione del piano settimanale.")
        else:
            self.succeeded.emit(result)
