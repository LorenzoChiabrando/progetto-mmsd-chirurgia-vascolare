from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from src.data_paths import PROJECT_ROOT

from .exceptions import OptimizationError
from .platform_service import plan_platform_week


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Solve a platform week with Pyomo/HiGHS and optionally persist it.",
    )
    parser.add_argument("--week", required=True, help="Monday in ISO format (YYYY-MM-DD)")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--data-dir", type=Path, help="Data directory shared with the GUI")
    parser.add_argument("--write", action="store_true", help="Commit the validated plan")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacement of an existing unconvalidated draft",
    )
    parser.add_argument("--backup-directory", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run weekly planning and print aggregate diagnostics."""
    args = _parser().parse_args(argv)
    try:
        monday = date.fromisoformat(args.week)
        run = plan_platform_week(
            args.project_root,
            monday,
            overwrite=args.overwrite,
            persist=args.write,
            backup_directory=args.backup_directory,
            data_directory=args.data_dir,
        )
    except (OptimizationError, ValueError) as exc:
        print(f"Pianificazione non riuscita: {exc}", file=sys.stderr)
        return 2

    objective = asdict(run.result.objective) if run.result.objective is not None else None
    payload = {
        "week": monday.isoformat(),
        "status": run.result.status.value,
        "termination_condition": run.result.termination_condition,
        "solver": f"{run.result.solver_name} {run.result.solver_version}",
        "objective": objective,
        "best_objective_bound": run.result.best_objective_bound,
        "relative_gap": run.result.relative_gap,
        "candidate_count": len(run.context.scheduling_input.patients),
        "excluded_other_draft_count": run.context.excluded_other_draft_count,
        "scheduled_count": len(run.result.schedule),
        "operations_per_day": {
            day_plan.day.isoformat(): len(day_plan.operations) for day_plan in run.plan.days
        },
        "written": run.write_receipt is not None,
        "updated_files": (
            [str(path) for path in run.write_receipt.updated_paths]
            if run.write_receipt is not None
            else []
        ),
        "backup_files": (
            [str(path) for path in run.write_receipt.backup_paths]
            if run.write_receipt is not None
            else []
        ),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
