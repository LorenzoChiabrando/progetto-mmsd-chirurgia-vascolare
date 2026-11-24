from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

_DATABASE = ".id-sequences.sqlite3"
_CATALOGS = ("pazienti", "libretti", "sale_operatorie", "scadenzario")


def _historical_maximum(directory: Path, prefix: str) -> int:
    """Seed a legacy catalogue from records, calendar references and local demo backups."""
    folders = [directory]
    highest = 0
    if directory.name in ("pazienti", "libretti"):
        dataset = directory.parent
        backups = dataset.parent / ".demo_backups"
        snapshots = [dataset]
        if backups.is_dir():
            snapshots.extend(path for path in backups.iterdir() if path.is_dir())
        folders = [snapshot / name for snapshot in snapshots for name in _CATALOGS]
        for snapshot in snapshots[1:]:
            sequence = snapshot / directory.name / _DATABASE
            if sequence.is_file():
                with closing(sqlite3.connect(sequence.as_uri() + "?mode=ro", uri=True)) as db:
                    row = db.execute(
                        "SELECT last_id FROM sequences WHERE prefix = ?", (prefix,)
                    ).fetchone()
                    if row:
                        highest = max(highest, row[0])

    # Old records also use IDs as dictionary keys, e.g. in compatibility settings.
    pattern = re.compile(rb'"' + re.escape(prefix.encode()) + rb'([0-9]+)"')
    for folder in folders:
        for path in folder.rglob("*.json"):
            suffix = path.stem.removeprefix(prefix)
            if path.stem.startswith(prefix) and suffix.isascii() and suffix.isdigit():
                highest = max(highest, int(suffix))
            for match in pattern.finditer(path.read_bytes()):
                highest = max(highest, int(match[1]))
    return highest


def _update_sequence(directory: str | Path, prefix: str, *, issued: int | None) -> int:
    root = Path(directory).resolve()
    with closing(sqlite3.connect(root / _DATABASE, timeout=30)) as db, db:
        # Take the writer lock before reading or initializing the counter. Commit the
        # reservation before exposing the ID, even if creating the JSON subsequently fails.
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "CREATE TABLE IF NOT EXISTS sequences (prefix TEXT PRIMARY KEY, last_id INTEGER NOT NULL)"
        )
        row = db.execute("SELECT last_id FROM sequences WHERE prefix = ?", (prefix,)).fetchone()
        last = row[0] if row else _historical_maximum(root, prefix)
        high = last + 1 if issued is None else max(last, issued)
        db.execute("INSERT OR REPLACE INTO sequences VALUES (?, ?)", (prefix, high))
        return high


def next_available_id(directory: str | Path, prefix: str, width: int) -> str:
    """Reserve a unique number. Deletion, restart and failed creates cannot release it."""
    if not prefix:
        raise ValueError("Il prefisso dell'identificativo non può essere vuoto.")
    if width < 1:
        raise ValueError("La lunghezza dell'identificativo deve essere almeno 1.")
    number = _update_sequence(directory, prefix, issued=None)
    return f"{prefix}{number:0{width}d}"


def remember_existing_id(directory: str | Path, prefix: str, identifier: str) -> None:
    """Retain a legacy ID even if deletion is the first action after upgrading."""
    suffix = identifier.removeprefix(prefix)
    if identifier.startswith(prefix) and suffix.isascii() and suffix.isdigit():
        _update_sequence(directory, prefix, issued=int(suffix))
