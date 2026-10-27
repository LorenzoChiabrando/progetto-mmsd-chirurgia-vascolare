from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from src.calendar_versions import CalendarVersion
from src.controllers.controller_sale_operatorie import ControllerSaleOperatorie
from src.models import patient_plan_state
from src.models.data_manager_pazienti import DataManagerPazienti
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.views.view_nuovo_paziente import DialogNuovoPaziente

MONDAY = date(2026, 9, 28)


@pytest.fixture
def catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[DataManagerSaleOperatorie, DataManagerPazienti, str]:
    monkeypatch.setattr(
        "src.models.data_manager_pazienti.datetime",
        SimpleNamespace(now=lambda: MONDAY),
    )
    patients = DataManagerPazienti(str(tmp_path / "pazienti"))
    patient = patients.crea_nuovo_paziente(
        {"nome": "Synthetic", "cognome": "Case", "urgenza": "Alta", "note": "Keep this"}
    )
    plans = DataManagerSaleOperatorie(str(tmp_path / "sale_operatorie"))
    return plans, patients, patient["id"]


def _operation(patient_id: str) -> dict:
    return {"id_paziente": patient_id, "nome_paziente": "Synthetic Case", "durata": 60}


def _controller(plans, patients):
    controller = ControllerSaleOperatorie.__new__(ControllerSaleOperatorie)
    QObject.__init__(controller)
    controller.model = plans
    controller.model_paz = patients
    controller.model_lib = None
    controller.settimana_display = MONDAY
    controller.aggiorna_tabella = lambda: None
    controller._conferma = lambda *_args, **_kwargs: True
    controller._avviso = lambda *_args, **_kwargs: None
    return controller


def test_assigning_and_removing_updates_json_without_changing_other_fields(catalog) -> None:
    plans, patients, identifier = catalog
    before = patients.get_paziente_by_id(identifier)

    plans.set_operazioni("2026-09-28", [_operation(identifier)])
    assert patients.get_paziente_by_id(identifier) == {**before, "stato": "Pianificato"}
    plans.set_operazioni("2026-09-28", [])
    assert patients.get_paziente_by_id(identifier) == before


def test_removing_one_of_two_reservations_keeps_the_patient_planned(catalog) -> None:
    plans, patients, identifier = catalog
    plans.set_operazioni("2026-09-28", [_operation(identifier)])
    plans.set_operazioni("2026-10-05", [_operation(identifier)])
    plans.set_operazioni("2026-09-28", [])
    assert patients.get_paziente_by_id(identifier)["stato"] == "Pianificato"
    plans.set_operazioni("2026-10-05", [])
    assert patients.get_paziente_by_id(identifier)["stato"] == "In Attesa"


def test_completed_patients_are_never_reopened_by_draft_edits(catalog) -> None:
    plans, patients, identifier = catalog
    patients.aggiorna_stato_paziente(identifier, "Completato")
    plans.set_operazioni("2026-09-28", [_operation(identifier)])
    plans.set_operazioni("2026-09-28", [])
    assert patients.get_paziente_by_id(identifier)["stato"] == "Completato"


def test_clearing_a_cross_month_week_restores_waiting_states(catalog) -> None:
    plans, patients, identifier = catalog
    plans.set_operazioni("2026-10-02", [_operation(identifier)])
    assert patients.get_paziente_by_id(identifier)["stato"] == "Pianificato"

    _controller(plans, patients).pulisci_settimana()

    assert patients.get_paziente_by_id(identifier)["stato"] == "In Attesa"
    assert plans.get_operazioni("2026-10-02") == []


def test_planned_confirmation_keeps_patient_reserved_until_actual_confirmation(catalog) -> None:
    plans, patients, identifier = catalog
    plans.set_operazioni("2026-10-02", [_operation(identifier)])

    _controller(plans, patients).convalida_settimana()

    assert plans.get_stato_settimana(MONDAY) == "CONVALIDATO"
    assert patients.get_paziente_by_id(identifier)["stato"] == "Pianificato"
    actual = plans.for_version(CalendarVersion.EFFETTIVO)
    assert actual.has_settimana(MONDAY)
    assert actual.get_stato_settimana(MONDAY) == "BOZZA"
    actual.convalida_settimana(MONDAY)
    assert patients.get_paziente_by_id(identifier)["stato"] == "Completato"


def test_popup_removal_restores_waiting_state(catalog) -> None:
    plans, patients, identifier = catalog
    plans.set_operazioni("2026-09-28", [_operation(identifier)])
    accepted: list[bool] = []
    dialog = SimpleNamespace(accept=lambda: accepted.append(True))

    _controller(plans, patients)._rimuovi_paziente_da_slot(dialog, "2026-09-28", 0)

    assert accepted == [True]
    assert patients.get_paziente_by_id(identifier)["stato"] == "In Attesa"


def test_cross_day_move_keeps_planned_state(catalog) -> None:
    plans, patients, identifier = catalog
    plans.set_operazioni("2026-09-28", [_operation(identifier)])
    controller = _controller(plans, patients)
    controller.modalita_corrente = "PIANIFICAZIONE"
    controller._stato_corrente = "BOZZA"
    controller.view = SimpleNamespace(MAX_OPS=12)
    controller._sposta_operazione(0, 0, 4)

    assert patients.get_paziente_by_id(identifier)["stato"] == "Pianificato"
    assert plans.get_operazioni("2026-09-28") == []
    assert plans.get_operazioni("2026-10-02")[0]["id_paziente"] == identifier


def test_manual_insertion_persists_planned_state(catalog) -> None:
    plans, patients, identifier = catalog
    dialog = SimpleNamespace(accept=lambda: None)
    _controller(plans, patients)._inserisci_paziente_manuale(
        dialog,
        patients.get_paziente_by_id(identifier),
        "2026-09-28",
        8 * 60,
        "OR-1",
    )
    assert patients.get_paziente_by_id(identifier)["stato"] == "Pianificato"


def test_plan_and_patient_roll_back_together_when_patient_write_fails(
    catalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans, patients, identifier = catalog
    plans.set_operazioni("2026-09-28", [])
    plan_path = Path(plans.dir_sale_operatorie) / "2026-09.json"
    patient_path = Path(patients.dir_pazienti) / f"{identifier}.json"
    originals = {path: path.read_bytes() for path in (plan_path, patient_path)}
    real_replace = patient_plan_state.os.replace
    failed = False

    def fail_patient_once(source, destination) -> None:
        nonlocal failed
        if Path(destination) == patient_path and not failed:
            failed = True
            raise OSError("synthetic patient write failure")
        real_replace(source, destination)

    monkeypatch.setattr(patient_plan_state.os, "replace", fail_patient_once)
    with pytest.raises(OSError, match="synthetic patient write failure"):
        plans.set_operazioni("2026-09-28", [_operation(identifier)])
    assert {path: path.read_bytes() for path in originals} == originals
    assert plans.get_operazioni("2026-09-28") == []
    assert not list(plan_path.parent.glob("*.tmp"))
    assert not list(patient_path.parent.glob("*.tmp"))


def test_legacy_slot_assignment_also_updates_patient_state(catalog) -> None:
    plans, patients, identifier = catalog
    plans.set_slot_data("2026-09-28", "8.00-10.00", _operation(identifier))
    assert patients.get_paziente_by_id(identifier)["stato"] == "Pianificato"
    plans.set_operazioni("2026-09-28", [])
    assert patients.get_paziente_by_id(identifier)["stato"] == "In Attesa"


def test_unrelated_planned_patient_is_not_reset_without_an_assignment(catalog) -> None:
    plans, patients, identifier = catalog
    patients.aggiorna_stato_paziente(identifier, "Pianificato")
    plans.set_operazioni("2026-09-28", [])
    assert patients.get_paziente_by_id(identifier)["stato"] == "Pianificato"


def test_edit_dialog_preserves_planned_status(catalog) -> None:
    app = QApplication.instance() or QApplication([])
    plans, patients, identifier = catalog
    plans.set_operazioni("2026-09-28", [_operation(identifier)])
    dialog = DialogNuovoPaziente(paziente_dati=patients.get_paziente_by_id(identifier))
    assert dialog.combo_stato.currentText() == "Pianificato"
    dialog.input_note.setPlainText("Updated synthetic note")
    saved = patients.aggiorna_paziente(identifier, dialog.get_dati())
    assert saved["stato"] == "Pianificato"
    assert saved["note"] == "Updated synthetic note"
    dialog.deleteLater()
    app.processEvents()


def test_confirmed_cross_month_reference_does_not_return_patient_to_waiting(catalog) -> None:
    plans, patients, identifier = catalog
    plans.set_operazioni("2026-10-02", [_operation(identifier)])
    plans.set_stato_settimana(MONDAY, "CONVALIDATO")
    assert patients.get_paziente_by_id(identifier)["stato"] == "Pianificato"
    months = patient_plan_state.read_plan_months(Path(plans.dir_sale_operatorie))
    assert patient_plan_state.draft_patient_ids_by_week(months).get(MONDAY, set()) == set()
    assert (
        json.loads((Path(patients.dir_pazienti) / f"{identifier}.json").read_text())["stato"]
        == "Pianificato"
    )
