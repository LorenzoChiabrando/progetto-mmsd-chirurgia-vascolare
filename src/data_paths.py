"""Shared data-directory configuration for the GUI and planning service."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]

APP_DIRECTORY_NAME = "ScadenzarioCV"
# The previous executable kept data in an older format directly in ScadenzarioCV.
USER_DATA_VERSION = "v2"


def is_frozen() -> bool:
    """True when running as a bundled executable (PyInstaller sets ``sys.frozen``)."""
    return bool(getattr(sys, "frozen", False))


def user_app_directory(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Per-user folder of the executable, for its data and logs.

    ``%APPDATA%`` on Windows, ``~/Library/Application Support`` on macOS and
    ``$XDG_DATA_HOME`` (default ``~/.local/share``) elsewhere. Nothing is created.
    """
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else home
    if platform == "win32":
        base = Path(environ.get("APPDATA") or home / "AppData" / "Roaming")
    elif platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return base / APP_DIRECTORY_NAME / USER_DATA_VERSION


def user_data_directory() -> Path:
    """Default data folder of the executable, inside :func:`user_app_directory`."""
    return user_app_directory() / "dati"


def prepare_user_data(target: Path, bundled: Path) -> bool:
    """Copy the bundled demo data to ``target`` if it does not exist yet.

    The copy goes to a hidden sibling folder renamed at the end, so an interrupted
    first start never leaves half the data. Returns True when data was copied.
    """
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}-{uuid4().hex}")
    shutil.copytree(bundled, staging)
    staging.rename(target)
    return True


def resolve_data_directory(
    data_directory: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
) -> Path:
    """Resolve explicit path, MMSD_DATA_DIR, then the default data folder.

    The default is project/mock_data from source and :func:`user_data_directory`
    in the executable, whose bundle is extracted to a temporary folder. Relative
    configured paths are anchored to the project, never the working directory.
    Resolution does not create, migrate or classify any data.
    """
    root = Path(project_root).expanduser().resolve() if project_root is not None else PROJECT_ROOT
    configured = data_directory if data_directory is not None else os.environ.get("MMSD_DATA_DIR")
    if configured is None:
        if is_frozen():
            return user_data_directory()
        return (root / "mock_data").resolve()
    if not str(configured).strip():
        raise ValueError("La cartella dei dati non può essere vuota.")
    path = Path(configured).expanduser()
    return (path if path.is_absolute() else root / path).resolve()
