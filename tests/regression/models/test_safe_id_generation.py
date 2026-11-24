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


def test_patient_and_resident_ids_survive_deletion_and_restart(tmp_path: Path) -> None:
    patients_dir = tmp_path / "pazienti"
    residents_dir = tmp_path / "libretti"
    patients = DataManagerPazienti(patients_dir)
    residents = DataManagerLibretto(residents_dir)
    patient = {"nome": "Eva", "cognome": "Test", "urgenza": "Media"}
    resident = {**patient, "matricola": "S1", "livello": "Junior", "stato": "Molinette"}

    # Deleting an existing record can be the first action after installing the update.
    _write_json(patients_dir / "PZ0120.json", {"id": "PZ0120"})
    _write_json(residents_dir / "SP008.json", {"id": "SP008"})
    assert patients.elimina_paziente("PZ0120")
    assert residents.elimina_specializzando("SP008")
    assert DataManagerPazienti(patients_dir).crea_nuovo_paziente(patient)["id"] == "PZ0121"
    assert DataManagerLibretto(residents_dir).crea_nuovo_specializzando(resident)["id"] == "SP009"
    assert patients.elimina_paziente("PZ0121")
    assert residents.elimina_specializzando("SP009")
    assert DataManagerPazienti(patients_dir).crea_nuovo_paziente(patient)["id"] == "PZ0122"
    assert DataManagerLibretto(residents_dir).crea_nuovo_specializzando(resident)["id"] == "SP010"


def test_seed_uses_historical_references_and_demo_backups(tmp_path: Path) -> None:
    root = tmp_path / "dati"
    patients = root / "pazienti"
    residents = root / "libretti"
    calendar = root / "sale_operatorie" / "effettivo"
    backup = tmp_path / ".demo_backups" / "snapshot" / "pazienti"
    for path in (patients, residents, calendar, backup):
        path.mkdir(parents=True)
    _write_json(calendar / "2026-11.json", {"id_specializzando": "SP019", "id_paziente": "PZ0100"})
    _write_json(backup / "PZ0200.json", {"id": "PZ0200"})
    assert next_available_id(backup, "PZ", 4) == "PZ0201"

    assert next_available_id(patients, "PZ", 4) == "PZ0202"
    assert next_available_id(residents, "SP", 3) == "SP020"


def test_concurrent_creations_reserve_distinct_ids(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    manager = DataManagerPazienti(tmp_path)
    forms = [{"nome": str(index), "cognome": "Test", "urgenza": "Media"} for index in range(24)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(manager.crea_nuovo_paziente, forms))
    assert sorted(record["id"] for record in records) == [
        f"PZ{number:04d}" for number in range(1, 25)
    ]
    for record in records:
        assert manager.get_paziente_by_id(record["id"]) == record
