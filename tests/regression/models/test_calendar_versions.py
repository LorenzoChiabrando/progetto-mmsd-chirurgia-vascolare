from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.calendar_versions import CalendarVersion, CalendarVersionError
from src.models.data_manager import DataManager
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.models.patient_plan_state import read_operational_plan_months


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _patient(root: Path, identifier: str = "PZ0001", state: str = "In Attesa") -> Path:
    path = root / "pazienti" / f"{identifier}.json"
    _write(path, {"id": identifier, "stato": state, "note": "Synthetic"})
    return path


def _operation(identifier: str = "PZ0001") -> dict:
    return {"id_paziente": identifier, "nome_paziente": "Synthetic Case"}


def test_reading_missing_versions_never_creates_files(tmp_path: Path) -> None:
    schedule = DataManager(tmp_path / "scadenzario")
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    for version in CalendarVersion:
        accessor = schedule.for_version(version)
        assert not accessor.has_mese(2026, 9)
        assert accessor.load_mese(2026, 9)["turni"] == {}
        room_accessor = rooms.for_version(version)
        assert not room_accessor.has_settimana(date(2026, 9, 28))
        assert room_accessor.load_mese(2026, 9)["turni"] == {}
    assert list(tmp_path.iterdir()) == []


def test_accessors_preserve_original_related_directories(tmp_path: Path) -> None:
    schedule = DataManager(tmp_path / "scadenzario", tmp_path / "custom_lib")
    actual = schedule.for_version(CalendarVersion.EFFETTIVO)
    assert Path(actual.dir_scadenzario) == tmp_path / "scadenzario" / "effettivo"
    assert actual.dir_libretti == schedule.dir_libretti
    assert actual.for_version(CalendarVersion.PREVISTO).dir_scadenzario == schedule.dir_scadenzario
    rooms = DataManagerSaleOperatorie(
        tmp_path / "sale_operatorie",
        tmp_path / "people.json",
        tmp_path / "custom_patients",
    )
    actual_rooms = rooms.for_version(CalendarVersion.EFFETTIVO)
    assert actual_rooms.dir_pazienti == rooms.dir_pazienti
    assert actual_rooms.filepath_anagrafica == rooms.filepath_anagrafica
    assert (
        actual_rooms.for_version(CalendarVersion.PREVISTO).dir_sale_operatorie
        == rooms.dir_sale_operatorie
    )


def test_default_related_directories_are_not_under_actual(tmp_path: Path) -> None:
    schedule = DataManager(tmp_path / "scadenzario", version=CalendarVersion.EFFETTIVO)
    rooms = DataManagerSaleOperatorie(
        tmp_path / "sale_operatorie", version=CalendarVersion.EFFETTIVO
    )
    assert Path(schedule.dir_libretti) == tmp_path / "libretti"
    assert rooms.dir_pazienti == tmp_path / "pazienti"
    assert (
        Path(rooms.filepath_anagrafica)
        == tmp_path / "static_data" / "anagrafica_specializzandi.json"
    )


def test_legacy_confirmed_month_is_not_copied_on_read(tmp_path: Path) -> None:
    path = tmp_path / "scadenzario" / "2026-09.json"
    _write(
        path, {"metadata": {"stato": "CONVALIDATO"}, "turni": {"2026-09-01": {"OR I": "Test A."}}}
    )
    original = path.read_bytes()
    schedule = DataManager(path.parent)
    actual = schedule.for_version(CalendarVersion.EFFETTIVO)
    assert schedule.get_stato_mese(2026, 9) == "CONVALIDATO"
    assert not actual.has_mese(2026, 9)
    schedule.crea_effettivo_mese(2026, 9)
    assert actual.get_stato_mese(2026, 9) == "BOZZA"
    actual.set_valore_cella("2026-09-01", "OR I", "Test B.")
    assert path.read_bytes() == original
    with pytest.raises(CalendarVersionError, match="esiste già"):
        schedule.crea_effettivo_mese(2026, 9)
    assert actual.get_valore_cella("2026-09-01", "OR I") == "Test B."


def test_independent_accessors_read_fresh_data_and_detached_values(tmp_path: Path) -> None:
    for cls, directory in (
        (DataManager, "scadenzario"),
        (DataManagerSaleOperatorie, "sale_operatorie"),
    ):
        first = cls(tmp_path / directory)
        second = first.for_version(CalendarVersion.PREVISTO)
        assert second.load_mese(2026, 9)["turni"] == {}
        first.set_valore_cella("2026-09-28", "OR I", "Test A.")
        loaded = second.load_mese(2026, 9)
        assert loaded["turni"]["2026-09-28"]["OR I"] == "Test A."
        loaded["turni"].clear()
        assert first.load_mese(2026, 9)["turni"]
        assert second.load_mese(2026, 9)["turni"]


@pytest.mark.parametrize(
    "monday,friday", [(date(2026, 9, 28), "2026-10-02"), (date(2026, 12, 28), "2027-01-01")]
)
def test_actual_week_isolated_at_month_and_year_boundary(
    tmp_path: Path, monday: date, friday: str
) -> None:
    patient = _patient(tmp_path)
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    rooms.set_operazioni(friday, [_operation()])
    rooms.convalida_settimana(monday)
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    assert actual.has_settimana(monday)
    assert actual.get_stato_settimana(monday) == "BOZZA"
    actual.set_operazioni(friday, [])
    assert rooms.get_operazioni(friday) == [_operation()]
    assert actual.get_operazioni(friday) == []
    assert json.loads(patient.read_text())["stato"] == "In Attesa"
    assert rooms.get_pianificazioni_pazienti() == {}
    with pytest.raises(CalendarVersionError):
        rooms.set_operazioni(friday, [])


def test_actual_month_file_does_not_authorize_uninitialized_weeks(tmp_path: Path) -> None:
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    rooms.set_operazioni("2026-09-07", [])
    rooms.convalida_settimana(date(2026, 9, 7))
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    assert not actual.has_settimana(date(2026, 9, 14))
    with pytest.raises(CalendarVersionError):
        actual.set_operazioni("2026-09-14", [_operation()])
    assert not actual.has_settimana(date(2026, 9, 14))


def test_operational_replacements_hide_planned_week_without_writes(tmp_path: Path) -> None:
    base = tmp_path / "sale_operatorie"
    planned = {"metadata": {}, "turni": {"2026-09-28": {"operazioni": [_operation()]}}}
    _write(base / "2026-09.json", planned)
    replacements = {
        base / "effettivo" / "2026-09.json": {
            "metadata": {"settimane": {"2026-09-28": "BOZZA"}},
            "turni": {},
        }
    }
    assert read_operational_plan_months(base)["2026-09"]["turni"]
    assert read_operational_plan_months(base, replacements)["2026-09"]["turni"] == {}
    assert not (base / "effettivo").exists()


def test_other_operational_booking_and_completed_state_are_preserved(tmp_path: Path) -> None:
    patient = _patient(tmp_path)
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    rooms.set_operazioni("2026-09-28", [_operation()])
    rooms.set_operazioni("2026-10-05", [_operation()])
    rooms.convalida_settimana(date(2026, 9, 28))
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    actual.set_operazioni("2026-09-28", [])
    assert json.loads(patient.read_text())["stato"] == "Pianificato"
    assert rooms.get_pianificazioni_pazienti() == {"PZ0001": (date(2026, 10, 5),)}
    _write(patient, {"id": "PZ0001", "stato": "Completato"})
    rooms.set_operazioni("2026-10-05", [])
    assert json.loads(patient.read_text())["stato"] == "Completato"


def test_actual_schedule_requires_explicit_creation(tmp_path: Path) -> None:
    actual = DataManager(tmp_path / "scadenzario", version=CalendarVersion.EFFETTIVO)
    with pytest.raises(CalendarVersionError):
        actual.set_valore_cella("2026-09-28", "OR I", "Test A.")
    assert list(tmp_path.iterdir()) == []


def test_invalid_periods_are_rejected(tmp_path: Path) -> None:
    schedule = DataManager(tmp_path / "scadenzario")
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    with pytest.raises(ValueError):
        schedule.load_mese(2026, 13)
    with pytest.raises(CalendarVersionError):
        rooms.has_settimana(date(2026, 9, 29))
    assert list(tmp_path.iterdir()) == []


def test_copying_another_actual_week_preserves_previous_edits(tmp_path: Path) -> None:
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    rooms.set_operazioni("2026-09-07", [_operation("PZ0001")])
    rooms.set_operazioni("2026-09-14", [_operation("PZ0002")])
    rooms.convalida_settimana(date(2026, 9, 7))
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    actual.set_operazioni("2026-09-07", [])
    rooms.convalida_settimana(date(2026, 9, 14))
    assert actual.get_operazioni("2026-09-07") == []
    assert actual.get_operazioni("2026-09-14") == [_operation("PZ0002")]
    assert actual.get_stato_settimana(date(2026, 9, 7)) == "BOZZA"
    assert actual.get_stato_settimana(date(2026, 9, 14)) == "BOZZA"


def test_actual_accessors_observe_creation_and_subsequent_changes(tmp_path: Path) -> None:
    schedule = DataManager(tmp_path / "scadenzario")
    actual_one = schedule.for_version(CalendarVersion.EFFETTIVO)
    actual_two = schedule.for_version(CalendarVersion.EFFETTIVO)
    assert actual_two.load_mese(2026, 9)["turni"] == {}
    schedule.set_valore_cella("2026-09-28", "OR I", "Alpha T.")
    schedule.convalida_mese(2026, 9)
    assert actual_one.get_valore_cella("2026-09-28", "OR I") == "Alpha T."
    actual_one.set_valore_cella("2026-09-28", "OR I", "Beta T.")
    assert actual_two.get_valore_cella("2026-09-28", "OR I") == "Beta T."


def test_giro_visite_missing_actual_month_cannot_cause_partial_write(tmp_path: Path) -> None:
    schedule = DataManager(tmp_path / "scadenzario")
    schedule.set_giro_visite_settimana("2026-09-28", 2026, 9, "Alpha T.")
    schedule.convalida_mese(2026, 9)
    actual = schedule.for_version(CalendarVersion.EFFETTIVO)
    before = (tmp_path / "scadenzario" / "effettivo" / "2026-09.json").read_bytes()
    with pytest.raises(CalendarVersionError, match="tutti i mesi"):
        actual.set_giro_visite_settimana("2026-09-28", 2026, 9, "Beta T.")
    assert (tmp_path / "scadenzario" / "effettivo" / "2026-09.json").read_bytes() == before
    assert not actual.has_mese(2026, 10)
    schedule.convalida_mese(2026, 10)
    actual.set_giro_visite_settimana("2026-09-28", 2026, 9, "Beta T.")
    assert all(
        actual.load_mese(2026, month)["giro_visite"]["2026-09-28"] == "Beta T." for month in (9, 10)
    )


def test_bulk_writes_cannot_change_confirmed_week_or_authorize_missing_actual(
    tmp_path: Path,
) -> None:
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    rooms.set_operazioni("2026-10-02", [_operation()])
    rooms.convalida_settimana(date(2026, 9, 28))
    changed = rooms.load_mese(2026, 10)
    changed["turni"]["2026-10-02"]["operazioni"] = []
    with pytest.raises(CalendarVersionError):
        rooms.save_mese(2026, 10, changed)
    actual = rooms.for_version(CalendarVersion.EFFETTIVO)
    changed = actual.load_mese(2026, 10)
    changed.setdefault("metadata", {}).setdefault("settimane", {})["2026-10-05"] = "BOZZA"
    changed["turni"]["2026-10-05"] = {"operazioni": [_operation()]}
    with pytest.raises(CalendarVersionError):
        actual.save_mese(2026, 10, changed)


def test_schedule_preserves_configuration_and_copies_it_independently(tmp_path: Path) -> None:
    schedule = DataManager(tmp_path / "scadenzario")
    initial = schedule.load_mese(2026, 9)
    initial["custom"] = {"nested": [1, 2]}
    schedule.save_mese(2026, 9, initial)
    schedule.convalida_mese(2026, 9)
    actual = schedule.for_version(CalendarVersion.EFFETTIVO)
    changed = actual.load_mese(2026, 9)
    assert changed == {**initial, "metadata": {"stato": "BOZZA"}}
    changed["custom"]["nested"].append(3)
    actual.save_mese(2026, 9, changed)
    assert schedule.load_mese(2026, 9)["custom"] == {"nested": [1, 2]}


@pytest.mark.parametrize("present", [False, True])
def test_actual_week_presence_reads_only_fresh_monday_month(
    tmp_path: Path,
    present: bool,
) -> None:
    base = tmp_path / "sale_operatorie" / "effettivo"
    monday_path = base / "2026-09.json"
    _write(monday_path, {"metadata": {"settimane": {}}, "turni": {}})
    (base / "2026-10.json").write_text("unreadable unrelated month", encoding="utf-8")
    actual = DataManagerSaleOperatorie(base.parent, version=CalendarVersion.EFFETTIVO)
    assert not actual.has_settimana(date(2026, 9, 28))
    weeks = {"2026-09-28": "BOZZA"} if present else {}
    _write(monday_path, {"metadata": {"settimane": weeks}, "turni": {}})
    assert actual.has_settimana(date(2026, 9, 28)) is present


@pytest.mark.parametrize(
    "monday,friday,months",
    [
        (date(2026, 9, 7), "2026-09-11", [(2026, 9)]),
        (date(2026, 9, 28), "2026-10-02", [(2026, 9), (2026, 10)]),
        (date(2026, 12, 28), "2027-01-01", [(2026, 12), (2027, 1)]),
    ],
)
def test_planned_week_presence_reads_each_relevant_month_at_most_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    monday: date,
    friday: str,
    months: list[tuple[int, int]],
) -> None:
    base = tmp_path / "sale_operatorie"
    _write(base / f"{friday[:7]}.json", {"turni": {friday: {}}})
    (base / "2026-08.json").write_text("unreadable unrelated month", encoding="utf-8")
    rooms = DataManagerSaleOperatorie(base)
    loaded = []
    original_load = rooms.load_mese

    def load_month(year: int, month: int) -> dict:
        loaded.append((year, month))
        return original_load(year, month)

    monkeypatch.setattr(rooms, "load_mese", load_month)
    assert rooms.has_settimana(monday)
    assert loaded == months
