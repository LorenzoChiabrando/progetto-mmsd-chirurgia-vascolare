"""Explicit calendar versions and shared period validation."""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from pathlib import Path


class CalendarVersion(str, Enum):
    """Persisted calendar branches; legacy files belong to PREVISTO."""

    PREVISTO = "previsto"
    EFFETTIVO = "effettivo"


class CalendarVersionError(ValueError):
    """A calendar write violates period existence or confirmation rules."""


def version_directory(directory: str | Path, version: CalendarVersion) -> Path:
    """Return a version's directory without creating it."""
    base = Path(directory)
    return base / "effettivo" if version == CalendarVersion.EFFETTIVO else base


def month_filename(year: int, month: int) -> str:
    """Validate a calendar month and return its legacy-compatible filename."""
    date(year, month, 1)
    return f"{year:04d}-{month:02d}.json"


def week_days(monday: date) -> tuple[date, ...]:
    """Validate a Monday and return the five working days, including boundaries."""
    if not isinstance(monday, date) or monday.weekday() != 0:
        raise CalendarVersionError("La settimana deve iniziare di lunedì.")
    return tuple(monday + timedelta(days=offset) for offset in range(5))
