"""Fail fast when total procedure minutes disagree with the procedure details."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any

import pytest

from src.optimization import PlatformDataError
from src.optimization.platform_mapping import RosterAssignment, build_platform_context
from src.planning_schema import OPTIMIZATION_KEY, default_patient_optimization

MONDAY = date(2026, 11, 2)


def _patient(interventions: Any = None, *, total: int = 90) -> dict:
    return {
        "id": "SYN-P1",
        "nome": "Sintetico",
        "cognome": "Demo",
        "stato": "In Attesa",
        "data_inserimento": "01/10/2026",
        "durata_intervento": total,
        "complessita": "Bassa",
        "urgenza": "Alta",
        "interventi": interventions,
        OPTIMIZATION_KEY: default_patient_optimization("Alta"),
    }


def _context(patient: dict):
    return build_platform_context(
        monday=MONDAY,
        patient_records=(patient,),
        resident_records=(
            {"id": "R1", "livello": "Junior", "stato": "Molinette"},
            {"id": "R2", "livello": "Junior", "stato": "Molinette"},
        ),
        roster_by_day={
            MONDAY + timedelta(days=offset): (
                RosterAssignment("OR-1", "OR I", "R1", "Uno D.", 600),
                RosterAssignment("OR-2", "OR II", "R2", "Due D.", 600),
            )
            for offset in range(5)
        },
    )


@pytest.mark.parametrize(
    "interventions", [None, [], [{"durata": 90}], [{"durata": 30}, {"durata": 60}]]
)
def test_coherent_details_and_legacy_totals_are_accepted_without_mutation(
    interventions: Any,
) -> None:
    patient = _patient(interventions)
    original = deepcopy(patient)
    result = _context(patient)
    assert result.scheduling_input.patients[0].duration_minutes == 90
    assert patient == original


def test_legacy_record_without_interventions_uses_its_total() -> None:
    patient = _patient()
    del patient["interventi"]
    assert _context(patient).scheduling_input.patients[0].duration_minutes == 90


@pytest.mark.parametrize(
    "interventions",
    [
        [{"durata": 120}],
        [{"durata": 30}, {"durata": 30}],
    ],
)
def test_mismatched_total_is_rejected(interventions: Any) -> None:
    with pytest.raises(PlatformDataError, match="durate incoerenti"):
        _context(_patient(interventions))


@pytest.mark.parametrize("invalid", [0, -1, 90.0, "90", True, None])
def test_detail_minutes_must_be_positive_integers(invalid: object) -> None:
    with pytest.raises(PlatformDataError, match="minuti interi positivi"):
        _context(_patient([{"durata": invalid}]))


@pytest.mark.parametrize("interventions", [{}, "", "invalid", 1, [{"codice": "TEST"}], [None]])
def test_malformed_details_fail_with_an_operational_error(interventions: Any) -> None:
    with pytest.raises(PlatformDataError):
        _context(_patient(interventions))
