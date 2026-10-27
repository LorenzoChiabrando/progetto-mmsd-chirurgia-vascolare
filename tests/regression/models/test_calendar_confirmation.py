from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.calendar_versions import CalendarVersion, CalendarVersionError
from src.models import patient_plan_state
from src.models.data_manager import DataManager
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie

MONDAY = date(2026, 9, 28)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def catalog(tmp_path: Path) -> tuple[DataManagerSaleOperatorie, Path, Path]:
    patient = tmp_path / "pazienti" / "PZ0001.json"
    _write(
        patient,
        {
            "id": "PZ0001",
            "stato": "In Attesa",
            "complessita": "Media",
            "tipo_chirurgia": "Aperta",
            "note": "Synthetic",
        },
    )
    libretti = tmp_path / "custom_libretti"
    for identifier, surname in (("SP001", "Alpha"), ("SP002", "Beta")):
        _write(
            libretti / f"{identifier}.json", {"id": identifier, "nome": "Test", "cognome": surname}
        )
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    rooms.set_specializzandi("2026-10-02", "Alpha T.", "Beta T.")
    rooms.set_operazioni(
        "2026-10-02",
        [
            {
                "id_paziente": "PZ0001",
                "nome_paziente": "Synthetic Case",
                "ora_inizio": "09:00",
                "intervento": "Synthetic operation",
            }
        ],
    )
    return rooms, patient, libretti


def test_planned_confirmation_copies_without_completions_or_activities(catalog) -> None:
    rooms, patient, libretti = catalog
    originals = {path: path.read_bytes() for path in libretti.glob("*.json")}
    rooms.convalida_settimana(MONDAY)
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    assert rooms.get_stato_settimana(MONDAY) == "CONVALIDATO"
    assert actual.get_stato_settimana(MONDAY) == "BOZZA"
    assert actual.get_operazioni("2026-10-02") == rooms.get_operazioni("2026-10-02")
    assert _read(patient)["stato"] == "Pianificato"
    assert {path: path.read_bytes() for path in originals} == originals
    assert rooms.get_pianificazioni_pazienti() == {"PZ0001": (date(2026, 10, 2),)}


def test_actual_confirmation_records_legacy_assignments_and_completes(catalog) -> None:
    rooms, patient, libretti = catalog
    rooms.convalida_settimana(MONDAY)
    planned = {path: path.read_bytes() for path in Path(rooms.dir_sale_operatorie).glob("*.json")}
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    actual.convalida_settimana(MONDAY, dir_libretti=libretti)
    assert actual.get_stato_settimana(MONDAY) == "CONVALIDATO"
    assert _read(patient) == {
        "id": "PZ0001",
        "stato": "Completato",
        "complessita": "Media",
        "tipo_chirurgia": "Aperta",
        "note": "Synthetic",
    }
    activity = _read(libretti / "SP001.json")["attivita"][0]
    assert activity == {
        "data": "2026-10-02",
        "slot": "09:00",
        "nome_paziente": "Synthetic Case",
        "id_paziente": "PZ0001",
        "diagnosi": "",
        "intervento": "Synthetic operation",
        "codice_intervento": "",
        "interventi": [],
        "chirurgo": "",
        "complessita": "Media",
        "tipo_chirurgia": "Aperta",
        "ora_inizio": "09:00",
        "ora_fine": "18:00",
        "durata": 90,
        "ruolo": "OR I",
    }
    assert _read(libretti / "SP002.json")["attivita"][0] == {**activity, "ruolo": "OR II"}
    assert {path: path.read_bytes() for path in planned} == planned
    assert rooms.get_pianificazioni_pazienti() == {}
    for action in (
        lambda: actual.convalida_settimana(MONDAY, dir_libretti=libretti),
        lambda: actual.set_operazioni("2026-10-02", []),
        lambda: actual.set_stato_settimana(MONDAY, "BOZZA"),
    ):
        with pytest.raises(CalendarVersionError):
            action()


@pytest.mark.parametrize(
    "assignment,counts",
    [
        ({"specializzando": "Alpha T.", "ruolo_specializzando": "OR II"}, (1, 0)),
        ({"id_specializzando": ""}, (0, 0)),
    ],
)
def test_individual_assignment_presence_disables_daily_fallback(
    catalog, assignment: dict, counts: tuple[int, int]
) -> None:
    rooms, _, libretti = catalog
    operations = rooms.get_operazioni("2026-10-02")
    operations[0].update(assignment)
    rooms.set_operazioni("2026-10-02", operations)
    rooms.convalida_settimana(MONDAY)
    rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(MONDAY, dir_libretti=libretti)
    assert (
        tuple(
            len(_read(libretti / f"{identifier}.json").get("attivita", []))
            for identifier in ("SP001", "SP002")
        )
        == counts
    )


def test_activity_deduplication_preserves_existing_entry(catalog) -> None:
    rooms, _, libretti = catalog
    path = libretti / "SP001.json"
    existing = {"data": "2026-10-02", "slot": "09:00", "ruolo": "Legacy preserved"}
    _write(path, {**_read(path), "attivita": [existing]})
    rooms.convalida_settimana(MONDAY)
    rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(MONDAY, dir_libretti=libretti)
    assert _read(path)["attivita"] == [existing]


def test_actual_confirmation_rolls_back_all_files_on_last_activity_failure(
    catalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rooms, _, libretti = catalog
    rooms.convalida_settimana(MONDAY)
    original = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    failed = False
    real_replace = patient_plan_state.os.replace

    def fail_once(source, destination):
        nonlocal failed
        if Path(destination) == libretti / "SP002.json" and not failed:
            failed = True
            raise OSError("synthetic activity write failure")
        real_replace(source, destination)

    monkeypatch.setattr(patient_plan_state.os, "replace", fail_once)
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    with pytest.raises(OSError, match="synthetic activity"):
        actual.convalida_settimana(MONDAY, dir_libretti=libretti)
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == original
    assert actual.get_stato_settimana(MONDAY) == "BOZZA"
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("kind", ["schedule", "rooms"])
def test_planned_confirmation_rolls_back_copy_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    if kind == "schedule":
        manager = DataManager(tmp_path / "scadenzario")
        manager.set_valore_cella("2026-09-28", "OR I", "Alpha T.")

        def confirm():
            manager.convalida_mese(2026, 9)

        target = Path(manager._get_filepath(2026, 9))
    else:
        manager = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
        manager.set_operazioni("2026-09-28", [])

        def confirm():
            manager.convalida_settimana(MONDAY)

        target = Path(manager._get_filepath(2026, 9))
    original = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    real_replace = patient_plan_state.os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(destination) == target and not failed:
            failed = True
            raise OSError("synthetic confirmation failure")
        real_replace(source, destination)

    monkeypatch.setattr(patient_plan_state.os, "replace", fail_once)
    with pytest.raises(OSError, match="synthetic confirmation"):
        confirm()
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == original
    assert not list(tmp_path.rglob("*.tmp"))


def test_schedule_confirmation_and_immutability(tmp_path: Path) -> None:
    schedule = DataManager(tmp_path / "scadenzario")
    schedule.set_valore_cella("2026-09-28", "OR I", "Alpha T.")
    schedule.convalida_mese(2026, 9)
    actual = schedule.for_version(CalendarVersion.EFFETTIVO)
    actual.set_valore_cella("2026-09-28", "OR I", "Beta T.")
    assert schedule.get_valore_cella("2026-09-28", "OR I") == "Alpha T."
    actual.convalida_mese(2026, 9)
    for manager in (schedule, actual):
        with pytest.raises(CalendarVersionError):
            manager.set_valore_cella("2026-09-28", "OR I", "New T.")
        with pytest.raises(CalendarVersionError):
            manager.set_stato_mese(2026, 9, "BOZZA")


def test_duplicate_actual_week_creation_never_overwrites(catalog) -> None:
    rooms, _, _ = catalog
    rooms.convalida_settimana(MONDAY)
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    actual.set_operazioni("2026-10-02", [])
    with pytest.raises(CalendarVersionError, match="esiste già"):
        rooms.crea_effettivo_settimana(MONDAY)
    assert actual.get_operazioni("2026-10-02") == []


def test_legacy_explicit_creation_preserves_existing_activity_history(catalog) -> None:
    rooms, patient, libretti = catalog
    path = Path(rooms._get_filepath(2026, 9))
    _write(path, {"metadata": {"settimane": {MONDAY.isoformat(): "CONVALIDATO"}}, "turni": {}})
    _write(patient, {**_read(patient), "stato": "Completato"})
    history = libretti / "SP001.json"
    _write(history, {**_read(history), "attivita": [{"data": "2026-10-02", "slot": "09:00"}]})
    before = history.read_bytes()
    assert not rooms.for_version(CalendarVersion.EFFETTIVO).has_settimana(MONDAY)
    rooms.crea_effettivo_settimana(MONDAY)
    assert _read(patient)["stato"] == "Completato"
    assert history.read_bytes() == before


def test_missing_required_libretti_prevents_any_confirmation_write(catalog, tmp_path: Path) -> None:
    rooms, _, _ = catalog
    rooms.convalida_settimana(MONDAY)
    original = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    with pytest.raises(CalendarVersionError, match="libretti"):
        actual.convalida_settimana(MONDAY, dir_libretti=tmp_path / "absent")
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == original
    assert not (tmp_path / "absent").exists()


def test_missing_periods_cannot_be_confirmed(tmp_path: Path) -> None:
    with pytest.raises(CalendarVersionError):
        DataManager(tmp_path / "scadenzario").convalida_mese(2026, 9)
    with pytest.raises(CalendarVersionError):
        DataManagerSaleOperatorie(tmp_path / "sale_operatorie").convalida_settimana(MONDAY)
    assert list(tmp_path.iterdir()) == []


def test_missing_required_patients_prevents_any_confirmation_write(tmp_path: Path) -> None:
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    rooms.set_operazioni("2026-09-28", [{"id_paziente": "PZ0001"}])
    rooms.convalida_settimana(MONDAY)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    with pytest.raises(CalendarVersionError, match="pazienti"):
        rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(MONDAY)
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


def test_empty_actual_week_can_be_confirmed_without_unneeded_catalogs(tmp_path: Path) -> None:
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    rooms.set_operazioni("2026-09-28", [])
    rooms.convalida_settimana(MONDAY)
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    actual.convalida_settimana(MONDAY)
    assert actual.get_stato_settimana(MONDAY) == "CONVALIDATO"
    assert not (tmp_path / "pazienti").exists()
    assert not (tmp_path / "libretti").exists()


def test_individual_unknown_recipient_prevents_partial_confirmation(
    catalog, tmp_path: Path
) -> None:
    rooms, patient, libretti = catalog
    operations = rooms.get_operazioni("2026-10-02")
    operations[0]["specializzando"] = "Unknown T."
    rooms.set_operazioni("2026-10-02", operations)
    rooms.convalida_settimana(MONDAY)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    with pytest.raises(CalendarVersionError, match="assegnatario"):
        rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
            MONDAY,
            dir_libretti=libretti,
        )
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before
    assert _read(patient)["stato"] == "Pianificato"


def test_missing_referenced_patient_prevents_partial_confirmation(catalog, tmp_path: Path) -> None:
    rooms, _, libretti = catalog
    operations = rooms.get_operazioni("2026-10-02")
    operations.append({"id_paziente": "PZ9999", "nome_paziente": "Synthetic missing"})
    rooms.set_operazioni("2026-10-02", operations)
    rooms.convalida_settimana(MONDAY)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    with pytest.raises(CalendarVersionError, match="scheda paziente"):
        rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
            MONDAY,
            dir_libretti=libretti,
        )
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


def test_legacy_operation_without_patient_id_can_still_register(catalog) -> None:
    rooms, patient, libretti = catalog
    operations = rooms.get_operazioni("2026-10-02")
    operations[0].pop("id_paziente")
    rooms.set_operazioni("2026-10-02", operations)
    rooms.convalida_settimana(MONDAY)
    rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
        MONDAY,
        dir_libretti=libretti,
    )
    assert _read(libretti / "SP001.json")["attivita"][0]["id_paziente"] == ""
    assert _read(patient)["stato"] == "In Attesa"


@pytest.mark.parametrize("label", ["De Synthetic T.", "  DE   Synthetic t  "])
def test_compound_surname_legacy_assignment_uses_complete_normalized_label(
    catalog,
    label: str,
) -> None:
    rooms, _, libretti = catalog
    resident = libretti / "SP001.json"
    _write(resident, {**_read(resident), "cognome": "De Synthetic"})
    rooms.set_specializzandi("2026-10-02", label, "")
    rooms.convalida_settimana(MONDAY)
    rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
        MONDAY,
        dir_libretti=libretti,
    )
    assert len(_read(resident)["attivita"]) == 1
    assert "attivita" not in _read(libretti / "SP002.json")


def test_ambiguous_legacy_recipient_blocks_confirmation_without_writes(
    catalog,
    tmp_path: Path,
) -> None:
    rooms, _, libretti = catalog
    resident = libretti / "SP002.json"
    _write(resident, {**_read(resident), "cognome": "Alpha", "nome": "Thomas"})
    rooms.set_specializzandi("2026-10-02", "Alpha T.", "")
    rooms.convalida_settimana(MONDAY)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    with pytest.raises(CalendarVersionError, match="ambiguo"):
        rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
            MONDAY,
            dir_libretti=libretti,
        )
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


@pytest.mark.parametrize("display_name", ["Alpha T.", "Outdated T.", ""])
def test_stable_resident_id_resolves_ambiguous_or_outdated_display_name(
    catalog,
    display_name: str,
) -> None:
    rooms, _, libretti = catalog
    duplicate = libretti / "SP002.json"
    _write(duplicate, {**_read(duplicate), "cognome": "Alpha", "nome": "Thomas"})
    operations = rooms.get_operazioni("2026-10-02")
    operations[0].update(
        {
            "id_specializzando": "SP001",
            "specializzando": display_name,
            "ruolo_specializzando": "OR II",
        }
    )
    rooms.set_operazioni("2026-10-02", operations)
    rooms.convalida_settimana(MONDAY)
    rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
        MONDAY,
        dir_libretti=libretti,
    )
    activities = _read(libretti / "SP001.json")["attivita"]
    assert len(activities) == 1
    assert activities[0]["ruolo"] == "OR II"
    assert "id_specializzando" not in activities[0]
    assert "attivita" not in _read(duplicate)


def test_unknown_stable_resident_id_never_falls_back_to_display_name(
    catalog,
    tmp_path: Path,
) -> None:
    rooms, _, libretti = catalog
    operations = rooms.get_operazioni("2026-10-02")
    operations[0].update({"id_specializzando": "SP999", "specializzando": "Alpha T."})
    rooms.set_operazioni("2026-10-02", operations)
    rooms.convalida_settimana(MONDAY)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    with pytest.raises(CalendarVersionError, match="assegnatario"):
        rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
            MONDAY,
            dir_libretti=libretti,
        )
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


@pytest.mark.parametrize("first_has_id", [True, False])
def test_mixed_id_and_legacy_activities_keep_first_duplicate_in_operation_order(
    catalog,
    first_has_id: bool,
) -> None:
    rooms, _, libretti = catalog
    rooms.set_specializzandi("2026-10-02", "Alpha T.", "")
    base = rooms.get_operazioni("2026-10-02")[0]
    operations = [{**base, "intervento": "First"}, {**base, "intervento": "Second"}]
    operations[0 if first_has_id else 1].update(
        {
            "id_specializzando": "SP001",
            "specializzando": "Alpha T.",
        }
    )
    rooms.set_operazioni("2026-10-02", operations)
    rooms.convalida_settimana(MONDAY)
    rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
        MONDAY,
        dir_libretti=libretti,
    )
    activities = _read(libretti / "SP001.json")["attivita"]
    assert len(activities) == 1
    assert activities[0]["intervento"] == "First"


def test_duplicate_stable_resident_id_blocks_confirmation(catalog, tmp_path: Path) -> None:
    rooms, _, libretti = catalog
    duplicate = libretti / "SP002.json"
    _write(duplicate, {**_read(duplicate), "id": "SP001"})
    operations = rooms.get_operazioni("2026-10-02")
    operations[0].update({"id_specializzando": "SP001", "specializzando": "Alpha T."})
    rooms.set_operazioni("2026-10-02", operations)
    rooms.convalida_settimana(MONDAY)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    with pytest.raises(CalendarVersionError, match="ambiguo"):
        rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
            MONDAY,
            dir_libretti=libretti,
        )
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


def test_historical_start_time_is_used_for_deduplication_and_ordering(catalog) -> None:
    rooms, patient, libretti = catalog
    path = libretti / "SP001.json"
    historical = {
        "data": "2026-10-02",
        "ora_inizio": "09:00",
        "ora_fine": "09:30",
        "intervento": "Historical record preserved",
    }
    explicit_slot = {
        "data": "2026-10-02",
        "slot": "08:00",
        "ora_inizio": "11:00",
        "intervento": "Explicit slot remains authoritative",
    }
    _write(path, {**_read(path), "attivita": [historical, explicit_slot]})
    operations = rooms.get_operazioni("2026-10-02")
    operations.append({**operations[0], "ora_inizio": "10:00", "intervento": "New activity"})
    rooms.set_operazioni("2026-10-02", operations)
    rooms.convalida_settimana(MONDAY)
    rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(
        MONDAY,
        dir_libretti=libretti,
    )
    activities = _read(path)["attivita"]
    assert len(activities) == 3
    assert activities[:2] == [explicit_slot, historical]
    assert activities[2]["slot"] == "10:00"
    assert activities[2]["intervento"] == "New activity"
    assert "slot" not in activities[1]
    assert _read(patient)["stato"] == "Completato"
