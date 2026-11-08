from __future__ import annotations

import math
from datetime import date, datetime
from numbers import Real

from .domain import ObjectiveWeights, PatientCategory, SchedulingInput
from .exceptions import InputValidationError


def validate_scheduling_input(data: SchedulingInput) -> None:
    """Validate input data before constructing Pyomo components."""

    errors: list[str] = []

    if not data.patients:
        errors.append("Serve almeno un paziente.")
    if not data.residents:
        errors.append("Serve almeno uno specializzando per il criterio di equità max-min.")
    if not data.sessions:
        errors.append("Serve almeno una sessione di sala operatoria.")

    patient_ids: list[str] = []
    resident_ids: list[str] = []
    session_keys: list[tuple[str, str]] = []

    for resident in data.residents:
        prefix = f"Specializzando {resident.resident_id!r}"
        if not isinstance(resident.resident_id, str):
            errors.append(f"{prefix}: resident_id deve essere un testo.")
        else:
            resident_ids.append(resident.resident_id)
            if not resident.resident_id.strip():
                errors.append("resident_id non può essere vuoto.")

        invalid_levels = [
            level for level in resident.qualified_levels if not isinstance(level, str)
        ]
        if invalid_levels:
            errors.append(
                f"{prefix}: i livelli abilitati devono essere testi: "
                f"{sorted(map(repr, invalid_levels))}"
            )
        if any(isinstance(level, str) and not level.strip() for level in resident.qualified_levels):
            errors.append(f"{prefix}: contiene un livello abilitato vuoto.")

    known_residents = set(resident_ids)
    required_durations: list[tuple[str, int]] = []
    for patient in data.patients:
        prefix = f"Paziente {patient.patient_id!r}"
        if not isinstance(patient.patient_id, str):
            errors.append(f"{prefix}: patient_id deve essere un testo.")
        else:
            patient_ids.append(patient.patient_id)
            if not patient.patient_id.strip():
                errors.append("patient_id non può essere vuoto.")

        category_is_valid = isinstance(patient.category, PatientCategory)
        if not category_is_valid:
            errors.append(f"{prefix}: categoria non valida: {patient.category!r}.")

        duration_is_valid = _is_plain_int(patient.duration_minutes)
        if not duration_is_valid:
            errors.append(f"{prefix}: duration_minutes deve essere un intero.")
        elif patient.duration_minutes <= 0:
            errors.append(f"{prefix}: duration_minutes deve essere positivo.")
        elif category_is_valid and patient.category in {
            PatientCategory.MANDATORY,
            PatientCategory.RESCHEDULED,
        }:
            required_durations.append((str(patient.patient_id), patient.duration_minutes))

        if not isinstance(patient.procedure_level, str):
            errors.append(f"{prefix}: procedure_level deve essere un testo.")
        elif not patient.procedure_level.strip():
            errors.append(f"{prefix}: procedure_level non può essere vuoto.")

        waiting_values = (patient.waiting_time_days, patient.max_wait_days)
        if patient.category is PatientCategory.WAITING_LIST and None in waiting_values:
            errors.append(f"{prefix}: richiede waiting_time_days e max_wait_days.")
        if (patient.waiting_time_days is None) != (patient.max_wait_days is None):
            errors.append(f"{prefix}: deve definire entrambi i campi di attesa o nessuno.")
        if patient.waiting_time_days is not None and not _is_plain_int(patient.waiting_time_days):
            errors.append(f"{prefix}: waiting_time_days deve essere un intero.")
        _validate_optional_integer(
            errors,
            prefix,
            "max_wait_days",
            patient.max_wait_days,
            allow_zero=False,
        )
        if patient.earliest_surgery_date is not None and (
            not isinstance(patient.earliest_surgery_date, date)
            or isinstance(patient.earliest_surgery_date, datetime)
        ):
            errors.append(f"{prefix}: earliest_surgery_date deve essere una datetime.date.")

    valid_capacities: list[int] = []
    for session in data.sessions:
        prefix = f"Sessione ({session.room_id!r}, {session.day!r})"
        room_is_valid = isinstance(session.room_id, str)
        day_is_valid = isinstance(session.day, date)
        if not room_is_valid:
            errors.append(f"{prefix}: room_id deve essere un testo.")
        elif not session.room_id.strip():
            errors.append("room_id della sessione non può essere vuoto.")
        if not day_is_valid:
            errors.append(f"{prefix}: day deve essere una datetime.date.")
        if room_is_valid and day_is_valid:
            session_keys.append((session.room_id, session.day.isoformat()))

        if not _is_plain_int(session.capacity_minutes):
            errors.append(f"{prefix}: capacity_minutes deve essere un intero.")
        elif session.capacity_minutes <= 0:
            errors.append(f"{prefix}: capacity_minutes deve essere positivo.")
        else:
            valid_capacities.append(session.capacity_minutes)

        invalid_assigned_ids = [
            resident_id
            for resident_id in session.assigned_resident_ids
            if not isinstance(resident_id, str)
        ]
        if invalid_assigned_ids:
            errors.append(
                f"{prefix}: gli identificativi degli specializzandi assegnati devono essere testi: "
                f"{sorted(map(repr, invalid_assigned_ids))}"
            )
        assigned_ids = {
            resident_id
            for resident_id in session.assigned_resident_ids
            if isinstance(resident_id, str)
        }
        unknown_assigned = assigned_ids - known_residents
        if unknown_assigned:
            errors.append(
                f"{prefix}: specializzandi assegnati sconosciuti: {sorted(unknown_assigned)}"
            )

        if session.available_resident_ids is not None:
            invalid_available_ids = [
                resident_id
                for resident_id in session.available_resident_ids
                if not isinstance(resident_id, str)
            ]
            if invalid_available_ids:
                errors.append(
                    f"{prefix}: gli identificativi degli specializzandi disponibili "
                    "devono essere testi: "
                    f"{sorted(map(repr, invalid_available_ids))}"
                )
            available_ids = {
                resident_id
                for resident_id in session.available_resident_ids
                if isinstance(resident_id, str)
            }
            unknown_available = available_ids - known_residents
            if unknown_available:
                errors.append(
                    f"{prefix}: specializzandi disponibili sconosciuti: {sorted(unknown_available)}"
                )

    _append_duplicate_errors(errors, "paziente", patient_ids)
    _append_duplicate_errors(errors, "specializzando", resident_ids)
    _append_duplicate_errors(errors, "sessione", session_keys)

    weights = data.objective_weights
    if not isinstance(weights, ObjectiveWeights):
        errors.append("objective_weights deve essere un'istanza di ObjectiveWeights.")
    else:
        if weights.efficiency_scale is not None and not _is_finite_positive_number(
            weights.efficiency_scale
        ):
            errors.append("efficiency_scale dell'obiettivo deve essere finito e positivo.")
        if not _is_finite_non_negative_number(weights.fairness):
            errors.append("Il peso di equità dell'obiettivo deve essere finito e non negativo.")
        if not _is_finite_positive_number(weights.unassigned_penalty):
            errors.append("unassigned_penalty dell'obiettivo deve essere finito e positivo.")

    changeover_is_valid = _is_plain_int(data.changeover_minutes)
    if not changeover_is_valid:
        errors.append("changeover_minutes deve essere un intero.")
    elif data.changeover_minutes < 0:
        errors.append("changeover_minutes non può essere negativo.")

    if len(valid_capacities) == len(data.sessions) and valid_capacities:
        _validate_obvious_required_capacity(
            errors,
            required_durations,
            valid_capacities,
            data.changeover_minutes if changeover_is_valid else 0,
        )

    if errors:
        raise InputValidationError(errors)


def _validate_optional_integer(
    errors: list[str],
    prefix: str,
    field_name: str,
    value: object,
    *,
    allow_zero: bool,
) -> None:
    if value is None:
        return
    if not _is_plain_int(value):
        errors.append(f"{prefix}: {field_name} deve essere un intero.")
        return
    if value < 0 or (value == 0 and not allow_zero):
        qualifier = "non negativo" if allow_zero else "positivo"
        errors.append(f"{prefix}: {field_name} deve essere {qualifier}.")


def _validate_obvious_required_capacity(
    errors: list[str],
    required_durations: list[tuple[str, int]],
    capacities: list[int],
    changeover_minutes: int,
) -> None:
    max_capacity = max(capacities)
    for patient_id, duration in required_durations:
        if duration > max_capacity:
            errors.append(
                f"Il paziente obbligatorio {patient_id!r} richiede {duration} minuti, ma la "
                f"sessione più lunga ne ha {max_capacity}."
            )

    minimum_changeovers = max(0, len(required_durations) - len(capacities))
    minimum_total_load = sum(duration for _, duration in required_durations)
    minimum_total_load += changeover_minutes * minimum_changeovers
    total_capacity = sum(capacities)
    if minimum_total_load > total_capacity:
        errors.append(
            f"I pazienti obbligatori richiedono almeno {minimum_total_load} minuti in totale, "
            f"ma ne sono disponibili solo {total_capacity}."
        )


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_positive_number(value: object) -> bool:
    return _is_finite_number(value) and float(value) > 0


def _is_finite_non_negative_number(value: object) -> bool:
    return _is_finite_number(value) and float(value) >= 0


def _is_finite_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))


def _append_duplicate_errors(errors: list[str], label: str, values: list[object]) -> None:
    seen: set[object] = set()
    duplicates: set[object] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        errors.append(f"Identificativi {label} duplicati: {sorted(duplicates)!r}.")
