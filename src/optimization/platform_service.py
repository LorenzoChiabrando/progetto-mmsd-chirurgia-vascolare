from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.data_paths import resolve_data_directory

from .exceptions import PlanningCancelledError
from .model import build_platform_model
from .platform_io import PlatformWriteReceipt, load_platform_context, persist_platform_week_plan
from .platform_mapping import (
    PlatformPlanningContext,
    PlatformPlanningPolicy,
    PlatformWeekPlan,
    map_result_to_platform_plan,
)
from .results import SolveResult
from .solver import HighsConfig, HighsSolver


@dataclass(frozen=True, slots=True)
class PlatformPlanningRun:
    """Result, mapped plan and optional write receipt."""

    context: PlatformPlanningContext
    result: SolveResult
    plan: PlatformWeekPlan
    write_receipt: PlatformWriteReceipt | None = None


def plan_platform_week(
    project_root: str | Path,
    monday: date,
    *,
    overwrite: bool = False,
    persist: bool = False,
    backup_directory: str | Path | None = None,
    policy: PlatformPlanningPolicy | None = None,
    solver_config: HighsConfig | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    data_directory: str | Path | None = None,
) -> PlatformPlanningRun:
    """Load, solve and optionally persist one platform week."""
    _raise_if_cancelled(cancel_requested)
    active_policy = policy or PlatformPlanningPolicy()
    directory = resolve_data_directory(data_directory, project_root=project_root)
    context = load_platform_context(
        project_root, monday, active_policy, data_directory=directory,
    )
    _raise_if_cancelled(cancel_requested)
    built = build_platform_model(
        context.scheduling_input,
        max_operations_per_session=active_policy.max_operations_per_session,
    )
    _raise_if_cancelled(cancel_requested)
    result = HighsSolver(solver_config).solve(built, cancel_requested=cancel_requested)
    _raise_if_cancelled(cancel_requested)
    plan = map_result_to_platform_plan(context, result, active_policy)
    _raise_if_cancelled(cancel_requested)
    receipt = None
    if persist:
        receipt = persist_platform_week_plan(
            project_root,
            plan,
            overwrite=overwrite,
            backup_directory=backup_directory,
            data_directory=directory,
        )
    return PlatformPlanningRun(
        context=context,
        result=result,
        plan=plan,
        write_receipt=receipt,
    )


def _raise_if_cancelled(cancel_requested: Callable[[], bool] | None) -> None:
    if cancel_requested is not None and cancel_requested():
        raise PlanningCancelledError("Pianificazione annullata prima del salvataggio.")
