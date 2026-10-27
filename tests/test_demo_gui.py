"""Offscreen acceptance checks using the actual application's views and worker."""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from threading import get_ident
from types import SimpleNamespace
from typing import Any

import pytest
from demo_helpers import REFERENCE, json_bytes, materialize, read_json
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QTableWidget

import main
from src.calendar_versions import CalendarVersion
from src.controllers import controller_sale_operatorie, controller_scadenzario
from src.optimization.platform_service import PlatformPlanningRun, plan_platform_week
from src.optimization.solver import HighsConfig, HighsSolver
from src.views.components import messages


class ScenarioDate(date):
    """Keep the GUI's navigation clock at the documented demo date."""

    @classmethod
    def today(cls) -> ScenarioDate:
        return cls(REFERENCE.year, REFERENCE.month, REFERENCE.day)


@dataclass(slots=True)
class GuiDemo:
    """One window and isolated synthetic data, with nonblocking messages."""

    application: QApplication
    window: main.MainWindow
    root: Path
    alerts: list[tuple[str, str]]
    confirmations: list[str]


@pytest.fixture(scope="module")
def qt_application() -> QApplication:
    application = QApplication.instance() or QApplication([])
    assert application.platformName() == "offscreen"
    return application


@pytest.fixture
def gui_demo(
    qt_application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[GuiDemo]:
    assert Path(main.__file__).resolve() == Path(__file__).resolve().parents[1] / "main.py"
    clock = SimpleNamespace(date=ScenarioDate, timedelta=timedelta)
    monkeypatch.setattr(controller_scadenzario, "datetime", clock)
    monkeypatch.setattr(controller_sale_operatorie, "datetime", clock)
    alerts: list[tuple[str, str]] = []
    confirmations: list[str] = []
    unexpected_dialogs: list[str] = []

    def show_message(_parent: object, title: str, _message: str, **kwargs: Any) -> None:
        alerts.append((title, kwargs.get("kind", "info")))

    def ask_confirmation(_parent: object, title: str, _message: str, **_kwargs: Any) -> bool:
        confirmations.append(title)
        return True

    def reject_unexpected_dialog(dialog: QDialog) -> int:
        unexpected_dialogs.append(type(dialog).__name__)
        return int(QDialog.DialogCode.Rejected)

    monkeypatch.setattr(messages, "show_message", show_message)
    monkeypatch.setattr(messages, "ask_confirmation", ask_confirmation)
    monkeypatch.setattr(QDialog, "exec", reject_unexpected_dialog)
    root = materialize(tmp_path / "mock_data")
    window = main.MainWindow(data_directory=root)
    window.show()
    qt_application.processEvents()
    try:
        yield GuiDemo(qt_application, window, root, alerts, confirmations)
    finally:
        stopped = window.controller_sale_operatorie.shutdown_planning(timeout_ms=5000)
        window.close()
        window.deleteLater()
        qt_application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert stopped, "The real planning worker did not stop within the cleanup deadline."
        assert not unexpected_dialogs, f"Unexpected modal dialogs: {unexpected_dialogs}"


def _visible_operation_count(table: QTableWidget) -> int:
    return sum(
        table.cellWidget(row, column) is not None
        and table.cellWidget(row, column).objectName() in {"CellaOperazione", "CellaOperazioneOggi"}
        for column in range(table.columnCount())
        for row in range(2, table.rowCount())
    )


def _assert_roster_month(gui: GuiDemo, month: int, *, empty: bool = False) -> None:
    controller = gui.window.controller_scad
    view = gui.window.view_scad
    days = calendar.monthrange(2026, month)[1]
    assert (controller.anno_corrente, controller.mese_corrente) == (2026, month)
    assert view.modello_attivita.columnCount() == days
    assert view.modello_specializzandi.rowCount() == 8
    assert view.modello_specializzandi.columnCount() == days + 1
    assigned = sum(
        bool(view.modello_attivita.value_at(row, column))
        for row in range(view.modello_attivita.rowCount())
        for column in range(days)
    )
    weekdays = sum(date(2026, month, day).weekday() < 5 for day in range(1, days + 1))
    assert assigned == (0 if empty else weekdays * 8)
    assert sum(
        int(view.modello_specializzandi.data(view.modello_specializzandi.index(row, 0)))
        for row in range(8)
    ) == (0 if empty else weekdays * 7)


def test_main_window_loads_all_sections_and_filters_120_patients(gui_demo: GuiDemo) -> None:
    gui = gui_demo
    before = json_bytes(gui.root)
    window = gui.window
    assert window.data_directory == gui.root
    expected_views = (
        window.view_scad,
        window.view_libretto,
        window.view_sale_operatorie,
        window.view_pazienti,
    )
    assert window.body_stack.count() == 4
    for index, view in enumerate(expected_views):
        window.sidebar.setCurrentRow(index)
        gui.application.processEvents()
        assert window.body_stack.currentWidget() is view
    view = window.view_pazienti
    assert view.lbl_count_total.text() == "120 pazienti totali"
    assert view.lbl_count_attesa.text() == "20 in attesa  ·  62 pianificati"
    assert view.lista_risultati.count() == 82
    view.chk_completato.setChecked(True)
    assert view.lista_risultati.count() == 120
    state_buttons = (
        (view.chk_in_attesa, "In Attesa", 20),
        (view.chk_pianificato, "Pianificato", 62),
        (view.chk_completato, "Completato", 38),
    )
    for selected, state, count in state_buttons:
        for button, _, _ in state_buttons:
            button.setChecked(button is selected)
        assert view.lista_risultati.count() == count
        view.lista_risultati.setCurrentRow(0)
        identifier = view.lista_risultati.currentItem().data(Qt.ItemDataRole.UserRole)
        view.btn_apri.click()
        assert view.stacked_widget.currentIndex() == 1
        patient = read_json(gui.root / "pazienti" / f"{identifier}.json")
        assert view.val_stato.text() == state
        assert view.val_data.text() == patient["data_inserimento"]
        assert patient["codice_intervento"] in view.val_intervento.text()
        view.btn_indietro.click()
    assert json_bytes(gui.root) == before
    assert not gui.alerts


def test_roster_navigation_renders_four_months_and_both_versions(gui_demo: GuiDemo) -> None:
    gui = gui_demo
    before = json_bytes(gui.root)
    view = gui.window.view_scad
    controller = gui.window.controller_scad
    view.btn_storico.click()
    view.btn_prev.click()
    _assert_roster_month(gui, 9)
    for version in (CalendarVersion.EFFETTIVO, CalendarVersion.PREVISTO):
        view.combo_versione.setCurrentIndex(view.combo_versione.findData(version.value))
        assert controller.versione_corrente == version
        _assert_roster_month(gui, 9)
    view.btn_indietro.click()
    view.btn_corrente.click()
    _assert_roster_month(gui, 10)
    view.combo_versione.setCurrentIndex(view.combo_versione.findData("effettivo"))
    _assert_roster_month(gui, 10)
    assert controller._puo_modificare()
    view.combo_versione.setCurrentIndex(view.combo_versione.findData("previsto"))
    assert not controller._puo_modificare()
    view.btn_indietro.click()
    view.btn_pianificazione.click()
    for month in (11, 12):
        _assert_roster_month(gui, month)
        view.btn_per_specializzando.click()
        view.btn_per_attivita.click()
        view.combo_versione.setCurrentIndex(view.combo_versione.findData("effettivo"))
        _assert_roster_month(gui, month, empty=True)
        assert "non ancora creato" in view.lbl_versione_info.text()
        view.combo_versione.setCurrentIndex(view.combo_versione.findData("previsto"))
        if month == 11:
            view.btn_next.click()
    assert json_bytes(gui.root) == before
    assert not gui.alerts


@pytest.mark.parametrize("version", [CalendarVersion.PREVISTO, CalendarVersion.EFFETTIVO])
def test_operating_room_month_views_render_correct_numbers(
    gui_demo: GuiDemo, version: CalendarVersion
) -> None:
    gui = gui_demo
    window = gui.window
    before = json_bytes(gui.root)
    window.sidebar.setCurrentRow(2)
    controller = window.controller_sale_operatorie
    view = window.view_sale_operatorie
    controller.apri_vista("CONSULTAZIONE")
    view.combo_versione.setCurrentIndex(view.combo_versione.findData(version))
    assert controller.versione == version
    for month, expected in ((9, 20), (10, 24), (11, 28), (12, 28)):
        controller.settimana_display = date(2026, month, 7)
        controller.imposta_visualizzazione("MESE")
        assert view.tabella.columnCount() == calendar.monthrange(2026, month)[1]
        assert _visible_operation_count(view.tabella) == (
            0 if version == CalendarVersion.EFFETTIVO and month > 10 else expected
        )
        if version == CalendarVersion.EFFETTIVO and month > 10:
            assert "manca" in view.lbl_versione_status.text()
    assert json_bytes(gui.root) == before
    assert not gui.alerts


def test_all_eight_logbooks_open_completed_and_planned_tabs(gui_demo: GuiDemo) -> None:
    gui = gui_demo
    window = gui.window
    before = json_bytes(gui.root)
    window.sidebar.setCurrentRow(1)
    view = window.view_libretto
    controller = window.controller_libretto
    assert view.lista_risultati.count() == 8
    total_completed = 0
    for row in range(8):
        view.lista_risultati.setCurrentRow(row)
        identifier = view.lista_risultati.currentItem().data(Qt.ItemDataRole.UserRole)
        view.btn_apri.click()
        assert view.stacked_widget.currentIndex() == 1
        record = read_json(gui.root / "libretti" / f"{identifier}.json")
        completed = controller._cache_completate
        assert len(completed) == len(record["attivita"]) + len(record["attivita_extra"])
        total_completed += len(record["attivita"])
        view.btn_tab_pianificate.click()
        assert controller._categoria_corrente == "pianificate"
        assert controller._cache_pianificate
        assert view.lista_attivita.count() > 1
        view.btn_tab_completate.click()
        assert controller._categoria_corrente == "completate"
        view.btn_indietro.click()
    assert total_completed == 38
    assert json_bytes(gui.root) == before
    assert not gui.alerts


def test_real_planning_worker_saves_november_and_restores_gui_controls(
    gui_demo: GuiDemo, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not HighsSolver.is_available():
        pytest.skip("HiGHS Python bindings are unavailable")
    gui = gui_demo
    window = gui.window
    window.controller_scad.apri_calendario("PIANIFICAZIONE")
    window.view_scad.btn_convalida.click()
    assert window.data_manager.get_stato_mese(2026, 11) == "CONVALIDATO"
    before = json_bytes(gui.root)
    window.sidebar.setCurrentRow(2)
    controller = window.controller_sale_operatorie
    view = window.view_sale_operatorie
    controller.apri_vista("PIANIFICAZIONE")
    assert controller.settimana_display == date(2026, 11, 2)
    calling_thread = get_ident()
    service_threads: list[int] = []

    def bounded_real_service(*args: Any, **kwargs: Any) -> PlatformPlanningRun:
        service_threads.append(get_ident())
        return plan_platform_week(
            *args, **kwargs, solver_config=HighsConfig(time_limit_seconds=10.0)
        )

    monkeypatch.setattr(controller, "_planning_service", bounded_real_service)
    completed: list[PlatformPlanningRun] = []
    errors: list[str] = []
    busy_states: list[bool] = []
    ticks: list[bool] = []
    expired: list[bool] = []
    loop = QEventLoop()
    heartbeat = QTimer()
    heartbeat.setInterval(1)
    heartbeat.timeout.connect(lambda: ticks.append(True))
    deadline = QTimer()
    deadline.setSingleShot(True)

    def finish_if_idle(busy: bool) -> None:
        busy_states.append(busy)
        if not busy:
            loop.quit()

    def timeout() -> None:
        expired.append(True)
        controller._request_planning_cancellation()
        loop.quit()

    deadline.timeout.connect(timeout)
    controller.planning_busy_changed.connect(finish_if_idle)
    view.btn_pianifica.click()
    worker = controller._planning_worker
    assert worker is not None
    worker.succeeded.connect(completed.append)
    worker.failed.connect(errors.append)
    assert not window.sidebar.isEnabled()
    assert not view.combo_versione.isEnabled()
    heartbeat.start()
    deadline.start(20_000)
    try:
        loop.exec()
    finally:
        heartbeat.stop()
        deadline.stop()
        controller.planning_busy_changed.disconnect(finish_if_idle)
    assert not expired, "The real GUI planning cycle exceeded the 20-second deadline."
    assert not errors
    assert len(completed) == 1
    result = completed[0]
    assert result.result.has_solution
    assert result.write_receipt is not None
    assert result.result.schedule
    assert service_threads and all(thread != calling_thread for thread in service_threads)
    assert ticks, "Qt did not process timer events while the real planner ran."
    assert busy_states == [True, False]
    assert controller._planning_worker is None
    assert window.sidebar.isEnabled()
    assert view.combo_versione.isEnabled()
    assert _visible_operation_count(view.tabella) == len(result.result.schedule)
    assert any(title.startswith("Pianificazione completata") for title, _ in gui.alerts)
    after = json_bytes(gui.root)
    changed = {name for name in before if after[name] != before[name]}
    assert "sale_operatorie/2026-11.json" in changed
    assert all(
        name == "sale_operatorie/2026-11.json" or name.startswith("pazienti/") for name in changed
    )
    assert (
        sum(
            read_json(path)["stato"] == "Completato"
            for path in (gui.root / "pazienti").glob("*.json")
        )
        == 38
    )
    window.sidebar.setCurrentRow(3)
    assert window.view_pazienti.lbl_count_total.text() == "120 pazienti totali"
