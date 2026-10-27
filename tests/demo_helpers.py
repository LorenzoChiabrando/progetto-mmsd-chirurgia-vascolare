"""Read and materialize the synthetic September–December acceptance scenario."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import date, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.reset_demo_data import build_demo_snapshot

REFERENCE = date(2026, 10, 27)
FIRST_MONTH = date(2026, 9, 1)
LAST_MONTH = date(2026, 12, 1)
MONTH_KEYS = tuple(f"2026-{month:02d}" for month in range(9, 13))
JsonRecord = dict[str, Any]


def scenario_files() -> dict[str, str]:
    """Generate the agreed 120-patient scenario without writing files."""
    return build_demo_snapshot(
        REFERENCE, start_month=FIRST_MONTH, end_month=LAST_MONTH, patient_count=120
    )


def decode_files(files: Mapping[str, str]) -> dict[str, JsonRecord]:
    """Decode only the JSON entries of a generated snapshot."""
    return {name: json.loads(text) for name, text in files.items() if name.endswith(".json")}


def catalog(records: Mapping[str, JsonRecord], directory: str) -> dict[str, JsonRecord]:
    """Index one flat catalog by its stable identifier."""
    return {
        record["id"]: record
        for name, record in records.items()
        if PurePosixPath(name).parent == PurePosixPath(directory)
    }


def months(
    records: Mapping[str, JsonRecord], directory: str, *, actual: bool = False
) -> dict[str, JsonRecord]:
    """Index planned or actual monthly JSON objects by YYYY-MM."""
    parent = PurePosixPath(directory) / "effettivo" if actual else PurePosixPath(directory)
    return {
        PurePosixPath(name).stem: record
        for name, record in records.items()
        if PurePosixPath(name).parent == parent
    }


def operations(
    monthly_records: Mapping[str, JsonRecord],
) -> Iterator[tuple[date, JsonRecord, JsonRecord]]:
    """Yield day, operation and daily record in stable date order."""
    for month_key in sorted(monthly_records):
        for day_text, daily in sorted(monthly_records[month_key].get("turni", {}).items()):
            for operation in daily.get("operazioni", []):
                yield date.fromisoformat(day_text), operation, daily


def monday(day: date) -> date:
    """Return the ISO week's Monday for a date."""
    return day - timedelta(days=day.weekday())


def minute(value: str) -> int:
    """Convert an HH:MM value to integer minutes after midnight."""
    hours, minutes = map(int, value.split(":"))
    assert 0 <= hours < 24 and 0 <= minutes < 60
    return 60 * hours + minutes


def materialize(root: Path) -> Path:
    """Write only generated synthetic files below a pytest temporary directory."""
    for name, text in scenario_files().items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def read_json(path: Path) -> JsonRecord:
    """Read one synthetic JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def json_bytes(root: Path) -> dict[str, bytes]:
    """Capture all synthetic JSON bytes for mutation and rollback assertions."""
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*.json")}
