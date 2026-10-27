from __future__ import annotations

from datetime import date
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtWidgets import QApplication

from src.optimization.exceptions import OptimizationError, PlanningCancelledError
from src.workers.platform_planning_worker import PlatformPlanningWorker


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _record_signals(worker: PlatformPlanningWorker) -> dict[str, list[object]]:
    emitted: dict[str, list[object]] = {
        "succeeded": [],
        "failed": [],
        "cancelled": [],
        "finished": [],
    }
    worker.succeeded.connect(emitted["succeeded"].append)
    worker.failed.connect(emitted["failed"].append)
    worker.cancelled.connect(lambda: emitted["cancelled"].append(True))
    worker.finished.connect(lambda: emitted["finished"].append(True))
    return emitted


def test_worker_forwards_persistence_overwrite_and_live_cancel_callback(
    tmp_path: Path,
    qt_app: QApplication,
) -> None:
    monday = date(2026, 5, 4)
    cancel_event = Event()
    expected_result = object()
    received: dict[str, object] = {}

    def planning_service(project_root, service_monday, **kwargs):
        received.update(
            project_root=project_root,
            monday=service_monday,
            **kwargs,
        )
        return expected_result

    worker = PlatformPlanningWorker(
        tmp_path,
        monday,
        overwrite=True,
        cancel_event=cancel_event,
        planning_service=planning_service,
    )
    emitted = _record_signals(worker)

    worker.start()
    assert worker.wait(2_000)
    qt_app.processEvents()

    assert received["project_root"] == tmp_path.resolve()
    assert received["data_directory"] == tmp_path.resolve() / "mock_data"
    assert received["monday"] == monday
    assert received["overwrite"] is True
    assert received["persist"] is True
    cancel_requested = received["cancel_requested"]
    assert callable(cancel_requested)
    assert cancel_requested() is False
    cancel_event.set()
    assert cancel_requested() is True
    assert emitted == {
        "succeeded": [expected_result],
        "failed": [],
        "cancelled": [],
        "finished": [True],
    }


@pytest.mark.parametrize(
    ("exception", "expected_failure", "is_cancelled"),
    [
        (OptimizationError("safe diagnostic"), "safe diagnostic", False),
        (PlanningCancelledError("cancelled"), None, True),
        (
            RuntimeError("private detail"),
            "Errore imprevisto durante la generazione del piano settimanale.",
            False,
        ),
    ],
)
def test_worker_reports_failure_or_cancellation_and_always_finishes(
    tmp_path: Path,
    exception: Exception,
    expected_failure: str | None,
    is_cancelled: bool,
    qt_app: QApplication,
) -> None:
    def failing_service(*_args, **_kwargs):
        raise exception

    worker = PlatformPlanningWorker(
        tmp_path,
        date(2026, 5, 4),
        overwrite=False,
        cancel_event=Event(),
        planning_service=failing_service,
    )
    emitted = _record_signals(worker)

    worker.start()
    assert worker.wait(2_000)
    qt_app.processEvents()

    assert emitted["succeeded"] == []
    assert emitted["failed"] == ([] if expected_failure is None else [expected_failure])
    assert emitted["cancelled"] == ([True] if is_cancelled else [])
    assert emitted["finished"] == [True]
