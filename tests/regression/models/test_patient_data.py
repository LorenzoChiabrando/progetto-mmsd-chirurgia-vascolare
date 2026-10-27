from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.controllers.controller_pazienti import ControllerPazienti
from src.models.data_manager_pazienti import DataManagerPazienti
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie


def test_new_patient_keeps_waiting_state_and_structured_diagnosis(tmp_path: Path) -> None:
    manager = DataManagerPazienti(
        dir_pazienti=str(tmp_path / "pazienti"),
        dir_libretti=str(tmp_path / "libretti"),
    )

    patient = manager.crea_nuovo_paziente(
        {
            "nome": "Ada",
            "cognome": "Test",
            "codice_diagnosi": "433.10",
            "descrizione_diagnosi": "Diagnosi sintetica",
            "interventi": [{"codice": "38.12", "descrizione": "Procedura sintetica", "durata": 47}],
            "tipo_chirurgia": "Aperta",
            "complessita": "Media",
            "urgenza": "Media",
            "stato": "In Attesa",
        }
    )

    stored = manager.get_paziente_by_id(patient["id"])
    assert stored is not None
    assert stored["stato"] == "In Attesa"
    assert stored["codice_diagnosi"] == "433.10"
    assert stored["descrizione_diagnosi"] == "Diagnosi sintetica"
    assert stored["diagnosi"] == "[433.10] Diagnosi sintetica"
    assert stored["durata_intervento"] == 47


def test_planned_status_uses_only_explicit_operation_links(tmp_path: Path) -> None:
    schedule_directory = tmp_path / "sale_operatorie"
    schedule_directory.mkdir()
    (schedule_directory / "2026-05.json").write_text(
        json.dumps(
            {
                "metadata": {"settimane": {"2026-05-04": "BOZZA"}},
                "turni": {
                    "2026-05-05": {
                        "operazioni": [{"id_paziente": "PZ0001"}],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    manager = DataManagerSaleOperatorie(
        dir_sale_operatorie=str(schedule_directory),
        filepath_anagrafica=str(tmp_path / "missing.json"),
    )

    planning = manager.get_pianificazioni_pazienti()

    assert planning == {"PZ0001": (date(2026, 5, 5),)}
    assert "PZ0002" not in manager.get_pazienti_pianificati_ids()


def test_waiting_patient_is_not_planned_without_its_own_operation_link() -> None:
    class _Schedule:
        def get_pianificazioni_pazienti(self) -> dict[str, tuple[date, ...]]:
            return {"PZ0001": (date(2026, 5, 5),)}

    controller = ControllerPazienti.__new__(ControllerPazienti)
    controller.model_sale_op = _Schedule()

    assert controller._stato_e_data_intervento({"id": "PZ0002", "stato": "In Attesa"}) == (
        "In Attesa",
        None,
    )
    assert controller._stato_e_data_intervento({"id": "PZ0001", "stato": "In Attesa"}) == (
        "Pianificato",
        "05/05/2026",
    )
