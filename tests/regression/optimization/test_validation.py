from __future__ import annotations

from datetime import date

import pytest

from src.optimization import (
    InputValidationError,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
    build_paper_model,
)


def test_validation_reports_multiple_input_errors() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                patient_id="P1",
                category=PatientCategory.WAITING_LIST,
                duration_minutes=-1,
                procedure_level="low",
            ),
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(
            Session("OR-1", date(2026, 8, 10), 0, assigned_resident_ids=frozenset({"UNKNOWN"})),
        ),
    )

    with pytest.raises(InputValidationError) as caught:
        build_paper_model(data)

    message = str(caught.value)
    assert "duration_minutes deve essere positivo" in message
    assert "richiede waiting_time_days e max_wait_days" in message
    assert "specializzandi assegnati sconosciuti" in message
    assert "capacity_minutes deve essere positivo" in message


def test_validation_rejects_duplicate_identifiers() -> None:
    patient = Patient(
        patient_id="P1",
        category=PatientCategory.WAITING_LIST,
        duration_minutes=60,
        procedure_level="low",
        waiting_time_days=1,
        max_wait_days=10,
    )
    data = SchedulingInput(
        patients=(patient, patient),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(Session("OR-1", date(2026, 8, 10), 120),),
    )

    with pytest.raises(InputValidationError, match="Identificativi paziente duplicati"):
        build_paper_model(data)


def test_validation_converts_wrong_field_types_to_domain_errors() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                patient_id=7,  # type: ignore[arg-type]
                category="waiting_list",  # type: ignore[arg-type]
                duration_minutes=60.5,  # type: ignore[arg-type]
                procedure_level=3,  # type: ignore[arg-type]
                waiting_time_days=1.5,  # type: ignore[arg-type]
                max_wait_days="10",  # type: ignore[arg-type]
            ),
        ),
        residents=(
            Resident(
                resident_id=4,  # type: ignore[arg-type]
                qualified_levels=frozenset({1}),  # type: ignore[arg-type]
            ),
        ),
        sessions=(
            Session(
                room_id=5,  # type: ignore[arg-type]
                day="2026-08-10",  # type: ignore[arg-type]
                capacity_minutes=60.5,  # type: ignore[arg-type]
                assigned_resident_ids=frozenset({99}),  # type: ignore[arg-type]
            ),
        ),
        changeover_minutes=1.5,  # type: ignore[arg-type]
    )

    with pytest.raises(InputValidationError) as caught:
        build_paper_model(data)

    message = str(caught.value)
    assert "patient_id deve essere un testo" in message
    assert "duration_minutes deve essere un intero" in message
    assert "day deve essere una datetime.date" in message
    assert "capacity_minutes deve essere un intero" in message
    assert "changeover_minutes deve essere un intero" in message
    assert "gli identificativi degli specializzandi assegnati devono essere testi" in message


def test_validation_rejects_an_individually_impossible_required_patient() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "TOO-LONG",
                PatientCategory.MANDATORY,
                121,
                "low",
            ),
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(Session("OR-1", date(2026, 8, 10), 120),),
    )

    with pytest.raises(InputValidationError, match="sessione più lunga ne ha 120"):
        build_paper_model(data)


def test_validation_rejects_unknown_available_resident() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "P1",
                PatientCategory.WAITING_LIST,
                60,
                "low",
                waiting_time_days=1,
                max_wait_days=10,
            ),
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(
            Session(
                "OR-1",
                date(2026, 8, 10),
                120,
                available_resident_ids=frozenset({"UNKNOWN"}),
            ),
        ),
    )

    with pytest.raises(InputValidationError, match="specializzandi disponibili sconosciuti"):
        build_paper_model(data)
