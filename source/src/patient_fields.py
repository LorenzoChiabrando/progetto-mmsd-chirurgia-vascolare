"""Normalization shared by patient forms, CSV imports and persistence."""

from __future__ import annotations

import re
from datetime import date, datetime

DEFAULT_INTERVENTION_MINUTES = 90
UNCLASSIFIED = "Da classificare"


def parse_patient_insertion_date(value: object) -> date:
    """Parse the platform's DD/MM/YYYY insertion date; reject missing/invalid values."""

    if not isinstance(value, str):
        raise ValueError("Manca la data di inserimento del paziente.")
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(
            "La data di inserimento del paziente deve essere nel formato GG/MM/AAAA."
        ) from exc


def normalize_diagnosis(code: str, description: str) -> tuple[str, str, str]:
    """Return code, description and legacy summary without inventing missing data.

    Accept separate fields, a terminal parenthesized code, a code alone, or the
    legacy ``[code] description`` representation. An explicit code takes precedence.
    """
    code, description = code.strip(), description.strip()
    leading = re.match(r"^\[([^\[\]]+)\]\s*(.*)$", description, flags=re.DOTALL)
    trailing = re.search(r"\(([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*)\)\s*$", description)
    if leading and (not code or code == leading.group(1)):
        code, description = code or leading.group(1), leading.group(2).strip()
    elif trailing and (not code or code == trailing.group(1)):
        code, description = code or trailing.group(1), description[: trailing.start()].strip()
    elif re.fullmatch(r"[A-Za-z]?[0-9]+(?:\.[0-9]+)?", description) and (
        not code or code == description
    ):
        code, description = code or description, ""
    summary = f"[{code}] {description}".strip() if code else description
    return code, description, summary
