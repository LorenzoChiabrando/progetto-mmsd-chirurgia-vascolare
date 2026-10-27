"""Generate a synthetic demo interval, backing up previous data on explicit writes."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.demo_scenario import (  # noqa: E402
    DEMO_RESIDENT_NAMES,
    ROTATION_ROLES,
    _monday,
    _weekly_roles,
    build_demo_snapshot,
)

__all__ = [
    "DEMO_RESIDENT_NAMES",
    "ROTATION_ROLES",
    "_monday",
    "_weekly_roles",
    "build_demo_snapshot",
    "reset_demo_data",
    "main",
]


def reset_demo_data(
    project_root: Path,
    reference: date,
    *,
    start_month: date | None = None,
    end_month: date | None = None,
    patient_count: int = 120,
    data_directory: str | Path | None = None,
) -> Path | None:
    """Replace one demo directory and return its backup path, or None initially.

    The caller must close the application and authorize replacement before calling.
    ``data_directory`` defaults to ``project_root / 'mock_data'``; relative paths
    are anchored at ``project_root``. Staging and backups stay beside the target.
    Generation arguments follow ``build_demo_snapshot``. Invalid inputs fail before
    staging or moving files; replacement failures restore the previous directory.
    """
    target, backup_root = _data_paths(project_root, data_directory)
    snapshot = build_demo_snapshot(
        reference, start_month=start_month, end_month=end_month, patient_count=patient_count
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".demo-stage-{uuid4().hex}"
    staging.mkdir(mode=0o700)
    try:
        for name, text in snapshot.items():
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text, encoding="utf-8")
        backup = None
        if target.exists():
            backup_root.mkdir(mode=0o700, exist_ok=True)
            backup = backup_root / f"{reference.isoformat()}-{uuid4().hex}"
            target.rename(backup)
        try:
            staging.rename(target)
        except OSError:
            if backup is not None:
                backup.rename(target)
            raise
        return backup
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _data_paths(project_root: Path, data_directory: str | Path | None) -> tuple[Path, Path]:
    """Resolve a target without writes and reject unsafe directory replacements."""
    root = project_root.resolve()
    selected = Path("mock_data") if data_directory is None else Path(data_directory)
    target = selected if selected.is_absolute() else root / selected
    if target.is_symlink():
        raise ValueError("Demo data and backup directories must not be symbolic links.")
    target = target.resolve()
    backup_root = target.parent / ".demo_backups"
    if backup_root.is_symlink():
        raise ValueError("Demo data and backup directories must not be symbolic links.")
    if target == root or target in root.parents:
        raise ValueError("The data directory must not replace the project or its ancestors.")
    if target == backup_root or target.name.startswith(".demo-stage-"):
        raise ValueError("The data directory must not use a reserved staging or backup name.")
    if any(path.exists() and not path.is_dir() for path in (target, backup_root)):
        raise ValueError("Demo data and backup paths must be directories.")
    return target, backup_root


def _parse_month(value: str) -> date:
    try:
        return date.fromisoformat(f"{value}-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use a month in YYYY-MM format.") from exc


def main() -> None:
    """Preview counts; replace the demo only with --write and retain a backup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--reference-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--start-month", type=_parse_month)
    parser.add_argument("--end-month", type=_parse_month)
    parser.add_argument("--patient-count", type=int, default=120)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Target directory; relative paths use --project-root (default: mock_data).",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    options = {
        "start_month": args.start_month,
        "end_month": args.end_month,
        "patient_count": args.patient_count,
    }
    try:
        target, _ = _data_paths(args.project_root, args.data_dir)
        files = build_demo_snapshot(args.reference_date, **options)
    except ValueError as exc:
        parser.error(str(exc))
    months = sorted(Path(name).stem for name in files if Path(name).parent == Path("scadenzario"))
    print(
        f"Demo sintetica al {args.reference_date}: {len(files)} file, "
        f"{args.patient_count} pazienti, {len(DEMO_RESIDENT_NAMES)} specializzandi."
    )
    print(f"Intervallo: {months[0]} – {months[-1]}; interventi soltanto nelle settimane complete.")
    print(f"Destinazione: {target}")
    if args.write:
        backup = reset_demo_data(
            args.project_root, args.reference_date, data_directory=args.data_dir, **options
        )
        print(f"Dati aggiornati. Backup precedente: {backup or 'nessuno'}")
    else:
        print("Anteprima: usare --write ad applicazione chiusa per sostituire i dati.")


if __name__ == "__main__":
    main()
