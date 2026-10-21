from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, timedelta

from .domain import Patient, PatientCategory, Resident, SchedulingInput, Session
from .model import build_paper_model
from .solver import HighsSolver


def build_example_input() -> SchedulingInput:
    """Build a synthetic two-day instance."""

    residents = (
        Resident("R-JUNIOR", frozenset({"low", "medium", "high"})),
        Resident("R-SENIOR", frozenset({"high"})),
    )
    patients = (
        Patient(
            "P-URGENT",
            PatientCategory.WAITING_LIST,
            120,
            "high",
            waiting_time_days=25,
            max_wait_days=30,
        ),
        Patient(
            "P-STANDARD",
            PatientCategory.WAITING_LIST,
            90,
            "low",
            waiting_time_days=10,
            max_wait_days=30,
        ),
        Patient(
            "P-FOLLOWUP",
            PatientCategory.MANDATORY,
            60,
            "medium",
        ),
        Patient(
            "P-RESCHEDULED",
            PatientCategory.RESCHEDULED,
            60,
            "high",
        ),
    )
    monday = date(2026, 8, 10)
    sessions = tuple(
        Session(
            "OR-1",
            monday + timedelta(days=offset),
            300,
            assigned_resident_ids=frozenset({resident.resident_id}),
        )
        for offset, resident in enumerate(residents)
    )
    return SchedulingInput(
        patients=patients,
        residents=residents,
        sessions=sessions,
    )


def main() -> None:
    """Solve the example and print its JSON result."""

    result = HighsSolver().solve(build_paper_model(build_example_input()))
    payload = {
        "status": result.status.value,
        "termination_condition": result.termination_condition,
        "solver": f"{result.solver_name} {result.solver_version}",
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "objective": asdict(result.objective) if result.objective else None,
        "schedule": [
            {
                **asdict(record),
                "day": record.day.isoformat(),
            }
            for record in result.schedule
        ],
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
