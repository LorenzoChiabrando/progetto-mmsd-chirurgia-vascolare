from __future__ import annotations

import json
from pathlib import Path

from src.models.data_manager_libretto import DataManagerLibretto
from src.models.data_manager_pazienti import DataManagerPazienti
from src.models.id_generator import next_available_id
from src.planning_schema import OPTIMIZATION_KEY


def _write_json(path: Path, payload: dict[str, str]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_next_available_id_uses_highest_numeric_suffix(tmp_path: Path) -> None:
    _write_json(tmp_path / "PZ0002.json", {"id": "PZ0002"})
    _write_json(tmp_path / "PZ0055.json", {"id": "PZ0055"})
    _write_json(tmp_path / "PZ-not-an-id.json", {"id": "ignored"})

    assert next_available_id(tmp_path, "PZ", 4) == "PZ0056"


def test_patient_creation_never_overwrites_ids_when_sequence_has_gaps(tmp_path: Path) -> None:
    existing_path = tmp_path / "PZ0055.json"
    existing_payload = {"id": "PZ0055", "nome": "esistente"}
    _write_json(existing_path, existing_payload)
    _write_json(tmp_path / "PZ0002.json", {"id": "PZ0002"})
    manager = DataManagerPazienti(str(tmp_path))
    form = {
        "nome": "Paziente",
        "cognome": "Sintetico",
        "urgenza": "Media",
        "interventi": [{"codice": "SYN", "descrizione": "Test", "durata": 30}],
    }

    first = manager.crea_nuovo_paziente(form)
    second = manager.crea_nuovo_paziente(form)

    assert first["id"] == "PZ0056"
    assert second["id"] == "PZ0057"
    assert first[OPTIMIZATION_KEY] == {
        "versione_schema": 1,
        "categoria_paper": "I'",
        "attesa_massima_giorni": 60,
    }
    assert json.loads(existing_path.read_text(encoding="utf-8")) == existing_payload


def test_resident_creation_never_overwrites_ids_when_sequence_has_gaps(tmp_path: Path) -> None:
    existing_path = tmp_path / "SP008.json"
    existing_payload = {"id": "SP008", "nome": "esistente"}
    _write_json(existing_path, existing_payload)
    _write_json(tmp_path / "SP001.json", {"id": "SP001"})
    manager = DataManagerLibretto(str(tmp_path))

    created = manager.crea_nuovo_specializzando(
        {
            "matricola": "SYN-009",
            "nome": "Medico",
            "cognome": "Sintetico",
            "livello": "Junior",
            "stato": "Molinette",
        }
    )

    assert created["id"] == "SP009"
    assert OPTIMIZATION_KEY not in created
    assert json.loads(existing_path.read_text(encoding="utf-8")) == existing_payload
