"""Keep persisted patient states aligned with operating-room drafts."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

JsonObject = dict[str, Any]


def read_plan_months(directory: Path) -> dict[str, JsonObject]:
    """Read monthly operating-room records without changing them.

    Raises:
        CorruptedDataError: a monthly file is not a valid JSON object; it is never
            treated as an empty month.
    """
    # Import locale: json_files importa write_json_batch da questo modulo.
    from src.models.json_files import read_json_object

    return {path.stem: read_json_object(path) for path in sorted(directory.glob("????-??.json"))}


def read_operational_plan_months(
    sale_directory: str | Path,
    replacements: Mapping[Path, JsonObject] | None = None,
) -> dict[str, JsonObject]:
    """Overlay initialized actual weeks on planned months without any writes.

    ``sale_directory`` is the original base directory. Replacement keys are
    monthly paths in that directory or its ``effettivo`` child. A week is
    initialized only by its entry in the Monday month's ``metadata.settimane``.
    Empty actual days therefore hide the original planned assignments as well.
    """
    base = Path(sale_directory).resolve()
    planned = read_plan_months(base)
    actual = read_plan_months(base / "effettivo")
    for path, replacement in (replacements or {}).items():
        path = Path(path).resolve()
        target = actual if path.parent == base / "effettivo" else planned
        if path.parent not in {base, base / "effettivo"}:
            continue
        target[path.stem] = deepcopy(replacement)
    result = deepcopy(planned)
    for month_key, month in sorted(actual.items()):
        for monday_text, state in month.get("metadata", {}).get("settimane", {}).items():
            monday = date.fromisoformat(monday_text)
            if monday.weekday() != 0 or monday.strftime("%Y-%m") != month_key:
                continue
            canonical = result.setdefault(month_key, {"metadata": {}, "turni": {}})
            canonical.setdefault("metadata", {}).setdefault("settimane", {})[monday_text] = state
            for offset in range(5):
                day = monday + timedelta(days=offset)
                key = day.strftime("%Y-%m")
                day_text = day.isoformat()
                target = result.setdefault(key, {"metadata": {}, "turni": {}})
                daily = actual.get(key, {}).get("turni", {}).get(day_text)
                if daily is None:
                    target.setdefault("turni", {}).pop(day_text, None)
                else:
                    target.setdefault("turni", {})[day_text] = deepcopy(daily)
    return result


def _daily_patient_ids(daily: JsonObject) -> set[str]:
    operations = list(daily.get("operazioni", []))
    operations.extend(
        value
        for key, value in daily.items()
        if key not in {"operazioni", "specializzandi"} and isinstance(value, dict)
    )
    return {
        operation["id_paziente"]
        for operation in operations
        if isinstance(operation.get("id_paziente"), str) and operation["id_paziente"]
    }


def _monthly_patient_ids(month: JsonObject) -> set[str]:
    return {
        patient_id
        for daily in month.get("turni", {}).values()
        for patient_id in _daily_patient_ids(daily)
    }


def draft_patient_ids_by_week(months: Mapping[str, JsonObject]) -> dict[date, set[str]]:
    """Collect draft reservations, using the Monday's month for week state."""
    reservations: dict[date, set[str]] = {}
    for month in months.values():
        for day_text, daily in month.get("turni", {}).items():
            try:
                day = date.fromisoformat(day_text)
            except ValueError:
                continue
            monday = day - timedelta(days=day.weekday())
            canonical = months.get(monday.strftime("%Y-%m"), {})
            week_state = (
                canonical.get("metadata", {}).get("settimane", {}).get(monday.isoformat(), "BOZZA")
            )
            if week_state != "CONVALIDATO":
                reservations.setdefault(monday, set()).update(_daily_patient_ids(daily))
    return reservations


def patient_status_updates(
    patient_directory: Path,
    sale_directory: Path,
    replacements: Mapping[Path, JsonObject],
) -> dict[Path, JsonObject]:
    """Prepare patient-state changes for a pending plan write, without writing.

    Only patients referenced by the replaced months are considered. Completed
    patients and unrelated fields are preserved. Removing the last reservation
    returns a planned patient to the waiting list; retained confirmed operations
    are left to the existing week-confirmation flow.
    """
    previous = read_operational_plan_months(sale_directory)
    months = read_operational_plan_months(sale_directory, replacements)
    affected: set[str] = set()
    for key in previous.keys() | months.keys():
        if previous.get(key) != months.get(key):
            affected.update(_monthly_patient_ids(previous.get(key, {})))
            affected.update(_monthly_patient_ids(months.get(key, {})))
    if not affected:
        return {}
    drafts = draft_patient_ids_by_week(months)
    planned = {patient_id for identifiers in drafts.values() for patient_id in identifiers}
    retained = {
        patient_id for month in months.values() for patient_id in _monthly_patient_ids(month)
    }
    updates: dict[Path, JsonObject] = {}
    for path in sorted(patient_directory.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        patient_id = record.get("id")
        current = record.get("stato")
        if patient_id not in affected or current not in {"In Attesa", "Pianificato"}:
            continue
        if patient_id in planned:
            desired = "Pianificato"
        elif patient_id not in retained:
            desired = "In Attesa"
        else:
            continue
        if desired != current:
            updates[path] = {**record, "stato": desired}
    return updates


def write_json_batch(updates: Mapping[Path, JsonObject]) -> None:
    """Save a plan and its patient states together; roll back write failures.

    This supports the application's single-instance workflow. It does not
    provide isolation from other processes or recovery after a process crash.
    """
    originals = {path: path.read_bytes() if path.exists() else None for path in updates}
    temporary_paths: dict[Path, Path] = {}
    committed: list[Path] = []
    try:
        for path, payload in updates.items():
            serialized = json.dumps(payload, indent=4).encode("utf-8")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary_paths[path] = _stage_bytes(path, serialized)
        for path, temporary in temporary_paths.items():
            os.replace(temporary, path)
            committed.append(path)
    except (OSError, TypeError, ValueError):
        for path in reversed(committed):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                temporary = _stage_bytes(path, original)
                try:
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
        raise
    finally:
        for temporary in temporary_paths.values():
            temporary.unlink(missing_ok=True)


def _stage_bytes(destination: Path, payload: bytes) -> Path:
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            mode = destination.stat().st_mode & 0o777 if destination.exists() else 0o600
            os.chmod(temporary, mode)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return temporary
