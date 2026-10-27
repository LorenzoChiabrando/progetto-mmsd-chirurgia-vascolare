"""Refuse stale results and conflicting bookings before touching any stored data."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from demo_helpers import json_bytes, materialize, read_json

from src.models.data_manager import DataManager
from src.optimization import HighsConfig, HighsSolver, plan_platform_week, platform_io
from src.optimization.exceptions import PlatformDataError, PlatformPersistenceError
from src.optimization.platform_io import load_platform_context, persist_platform_week_plan
from src.planning_schema import OPTIMIZATION_KEY

pytestmark = pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")
WEEK = date(2026, 11, 2)
CONFIG = HighsConfig(time_limit_seconds=20, mip_relative_gap=0)


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    root = materialize(tmp_path / "data")
    manager = DataManager(root / "scadenzario", root / "libretti")
    manager.convalida_mese(2026, 11)
    return root


def _solve(directory: Path, week: date = WEEK):
    return plan_platform_week(
        directory.parent, week, data_directory=directory, solver_config=CONFIG
    )


def _write(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record), encoding="utf-8")


@pytest.mark.parametrize(
    "changed", ["roster", "capacity", "status", "duration", "resident", "added", "removed"]
)
def test_changed_input_invalidates_result_without_overwriting_data(directory: Path, changed: str):
    run = _solve(directory)
    assert run.plan.source_fingerprint
    selected = run.result.schedule[0].patient_id
    if changed in {"roster", "capacity"}:
        path = directory / "scadenzario/2026-11.json"
        record = read_json(path)
        if changed == "roster":
            daily = record["turni"][WEEK.isoformat()]
            daily["Sala Op. I"], daily["Sala Op. II"] = daily["Sala Op. II"], daily["Sala Op. I"]
        else:
            record[OPTIMIZATION_KEY]["sale_operatorie"]["OR-1"]["capacita_minuti"] = 1
    elif changed == "resident":
        path = directory / "libretti/SP001.json"
        record = read_json(path)
        record["livello"] = "Senior"
        record["note"] = "Synthetic concurrent edit"
    else:
        path = directory / "pazienti" / f"{selected}.json"
        record = read_json(path)
        if changed == "status":
            record["stato"] = "Completato"
        elif changed == "duration":
            record["durata_intervento"] = 1_000
        elif changed == "added":
            path = directory / "pazienti/PZ9999.json"
            record["id"] = "PZ9999"
        elif changed == "removed":
            path.unlink()
    if changed != "removed":
        _write(path, record)
    before = json_bytes(directory)
    with pytest.raises(PlatformPersistenceError, match="cambiati"):
        persist_platform_week_plan(
            directory.parent, run.plan, overwrite=True, data_directory=directory
        )
    assert json_bytes(directory) == before


def test_an_unchanged_snapshot_can_be_written(directory: Path) -> None:
    run = _solve(directory)
    receipt = persist_platform_week_plan(
        directory.parent, run.plan, overwrite=True, data_directory=directory
    )
    assert receipt.updated_paths


def test_service_returns_the_committed_revision_for_subsequent_edits(directory: Path) -> None:
    run = plan_platform_week(
        directory.parent,
        WEEK,
        data_directory=directory,
        solver_config=CONFIG,
        overwrite=True,
        persist=True,
    )
    assert run.plan.source_fingerprint == run.write_receipt.committed_fingerprint
    assert run.plan.source_fingerprint != run.context.source_fingerprint
    first_day = run.plan.days[0]
    reduced = replace(
        run.plan,
        days=(replace(first_day, operations=()), *run.plan.days[1:]),
    )
    receipt = persist_platform_week_plan(
        directory.parent, reduced, overwrite=True, data_directory=directory
    )
    assert receipt.updated_paths


@pytest.mark.parametrize("remove_fingerprint", [False, True])
def test_two_week_snapshots_cannot_book_the_same_patients(
    directory: Path, remove_fingerprint: bool
) -> None:
    first = _solve(directory)
    second = _solve(directory, date(2026, 11, 9))
    assert {item.patient_id for item in first.result.schedule} & {
        item.patient_id for item in second.result.schedule
    }
    persist_platform_week_plan(
        directory.parent, first.plan, overwrite=True, data_directory=directory
    )
    second_plan = (
        replace(second.plan, source_fingerprint=None) if remove_fingerprint else second.plan
    )
    before = json_bytes(directory)
    with pytest.raises(PlatformPersistenceError, match="cambiati|altra settimana"):
        persist_platform_week_plan(
            directory.parent, second_plan, overwrite=True, data_directory=directory
        )
    assert json_bytes(directory) == before


def test_changed_data_during_read_never_produces_a_mixed_snapshot(
    directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = platform_io._read_catalog
    changed = False

    def read_then_change(path: Path):
        nonlocal changed
        records = original(path)
        if path.name == "pazienti" and not changed:
            changed = True
            target = directory / "pazienti/PZ0120.json"
            record = read_json(target)
            record["note"] = "Synthetic concurrent update"
            _write(target, record)
        return records

    monkeypatch.setattr(platform_io, "_read_catalog", read_then_change)
    with pytest.raises(PlatformDataError, match="durante la lettura"):
        load_platform_context(directory.parent, WEEK, data_directory=directory)


def test_legacy_slot_reservations_are_checked_even_without_fingerprint(directory: Path) -> None:
    run = _solve(directory)
    path = directory / "sale_operatorie/2026-11.json"
    record = read_json(path)
    record["turni"]["2026-11-09"]["8.00-10.00"] = {
        "id_paziente": run.result.schedule[0].patient_id,
    }
    _write(path, record)
    before = json_bytes(directory)
    with pytest.raises(PlatformPersistenceError, match="altra settimana"):
        persist_platform_week_plan(
            directory.parent,
            replace(run.plan, source_fingerprint=None),
            overwrite=True,
            data_directory=directory,
        )
    assert json_bytes(directory) == before


@pytest.mark.parametrize("state", ["Completato", "Annullato"])
def test_manual_plan_cannot_assign_unavailable_patient(directory: Path, state: str) -> None:
    run = _solve(directory)
    path = directory / "pazienti" / f"{run.result.schedule[0].patient_id}.json"
    record = read_json(path)
    record["stato"] = state
    _write(path, record)
    before = json_bytes(directory)
    with pytest.raises(PlatformPersistenceError, match="non più disponibile"):
        persist_platform_week_plan(
            directory.parent,
            replace(run.plan, source_fingerprint=None),
            overwrite=True,
            data_directory=directory,
        )
    assert json_bytes(directory) == before
