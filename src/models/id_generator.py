from __future__ import annotations

from pathlib import Path


def next_available_id(directory: str | Path, prefix: str, width: int) -> str:
    """Return an ID greater than every valid JSON ID already in ``directory``.

    Filenames that do not match ``<prefix><numeric suffix>.json`` are ignored.
    The caller should still create the destination file in exclusive mode to
    prevent overwrites if two writers run concurrently.
    """
    if not prefix:
        raise ValueError("Il prefisso dell'identificativo non può essere vuoto.")
    if width < 1:
        raise ValueError("La lunghezza dell'identificativo deve essere almeno 1.")

    root = Path(directory)
    highest_suffix = 0
    for path in root.glob(f"{prefix}*.json"):
        suffix = path.stem.removeprefix(prefix)
        if suffix.isdigit():
            highest_suffix = max(highest_suffix, int(suffix))

    return f"{prefix}{highest_suffix + 1:0{width}d}"
