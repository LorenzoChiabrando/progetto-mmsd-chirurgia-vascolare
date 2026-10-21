"""Shared data-directory configuration for the GUI and planning service."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_data_directory(
    data_directory: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
) -> Path:
    """Resolve explicit path, MMSD_DATA_DIR, then the legacy project/mock_data path.

    Relative configured paths are anchored to the project, never the working
    directory. Resolution does not create, migrate or classify any data.
    """
    root = Path(project_root).expanduser().resolve() if project_root is not None else PROJECT_ROOT
    configured = data_directory if data_directory is not None else os.environ.get("MMSD_DATA_DIR")
    if configured is None:
        return (root / "mock_data").resolve()
    if not str(configured).strip():
        raise ValueError("La cartella dei dati non può essere vuota.")
    path = Path(configured).expanduser()
    return (path if path.is_absolute() else root / path).resolve()
