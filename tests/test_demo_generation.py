"""Directory isolation and failure recovery for explicit demo generation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from demo_helpers import FIRST_MONTH, LAST_MONTH, REFERENCE, scenario_files

from scripts.reset_demo_data import reset_demo_data

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reset_demo_data.py"
RELATIVE_TARGET = Path("mock_data") / "scenario_2026_09_12"


def _existing_project(root: Path) -> dict[str, bytes]:
    original = root / "mock_data" / "scadenzario" / "2026-10.json"
    original.parent.mkdir(parents=True)
    original.write_bytes(b'{"metadata":{"stato":"CONVALIDATO"},"turni":{}}\n')
    older_backup = root / ".demo_backups" / "existing" / "sentinel.txt"
    older_backup.parent.mkdir(parents=True)
    older_backup.write_bytes(b"existing synthetic backup")
    return _file_bytes(root)


def _file_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def _assert_original_preserved(root: Path, original: dict[str, bytes]) -> None:
    assert {name: (root / name).read_bytes() for name in original} == original


def _run_cli(root: Path, cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(root),
            "--reference-date",
            REFERENCE.isoformat(),
            "--start-month",
            "2026-09",
            "--end-month",
            "2026-12",
            "--patient-count",
            "120",
            *arguments,
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("selection_type", ["relative_string", "relative_path", "absolute"])
def test_selected_directory_receives_exact_snapshot_without_changing_original_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selection_type: str
) -> None:
    root = tmp_path / "project"
    original = _existing_project(root)
    monkeypatch.chdir(tmp_path)
    selected: str | Path
    if selection_type == "absolute":
        selected = tmp_path / "external" / "scenario"
        target = selected
    else:
        selected = str(RELATIVE_TARGET) if selection_type == "relative_string" else RELATIVE_TARGET
        target = root / RELATIVE_TARGET
    backup = reset_demo_data(
        root,
        REFERENCE,
        start_month=FIRST_MONTH,
        end_month=LAST_MONTH,
        data_directory=selected,
    )
    assert backup is None
    assert _file_bytes(target) == {
        name: text.encode("utf-8") for name, text in scenario_files().items()
    }
    _assert_original_preserved(root, original)
    assert not (tmp_path / RELATIVE_TARGET).exists()
    assert not list(target.parent.glob(".demo-stage-*"))


def test_default_directory_retains_legacy_backup_location(tmp_path: Path) -> None:
    root = tmp_path / "project"
    original = _existing_project(root)
    backup = reset_demo_data(root, REFERENCE)
    assert backup is not None and backup.parent == root / ".demo_backups"
    assert (backup / "scadenzario" / "2026-10.json").read_bytes() == original[
        "mock_data/scadenzario/2026-10.json"
    ]
    assert (root / ".demo_backups" / "existing" / "sentinel.txt").read_bytes() == original[
        ".demo_backups/existing/sentinel.txt"
    ]
    assert len(list((root / "mock_data" / "pazienti").glob("*.json"))) == 120


def test_selected_directory_backup_contains_only_its_previous_contents(tmp_path: Path) -> None:
    root = tmp_path / "project"
    original = _existing_project(root)
    target = root / RELATIVE_TARGET
    target.mkdir()
    (target / "sentinel.txt").write_bytes(b"previous standalone scenario")
    before = _file_bytes(target)
    backup = reset_demo_data(root, REFERENCE, data_directory=RELATIVE_TARGET)
    assert backup is not None and backup.parent == target.parent / ".demo_backups"
    assert _file_bytes(backup) == before
    assert not (target / "sentinel.txt").exists()
    _assert_original_preserved(root, original)


@pytest.mark.parametrize("failure", ["stage_write", "replace"])
def test_failed_selected_directory_update_restores_all_existing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    root = tmp_path / "project"
    _existing_project(root)
    target = root / RELATIVE_TARGET
    target.mkdir()
    (target / "sentinel.txt").write_bytes(b"previous standalone scenario")
    before = _file_bytes(root)
    original_rename = Path.rename
    original_write = Path.write_text

    def fail_rename(path: Path, destination: str | Path) -> Path:
        if path.name.startswith(".demo-stage-"):
            raise OSError("injected replace failure")
        return original_rename(path, destination)

    def fail_write(path: Path, data: str, *args: Any, **kwargs: Any) -> int:
        if path.name == "PZ0005.json":
            raise OSError("injected stage_write failure")
        return original_write(path, data, *args, **kwargs)

    if failure == "replace":
        monkeypatch.setattr(Path, "rename", fail_rename)
    else:
        monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(OSError, match=f"injected {failure} failure"):
        reset_demo_data(root, REFERENCE, data_directory=RELATIVE_TARGET)
    assert _file_bytes(root) == before
    assert not list(target.parent.glob(".demo-stage-*"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"patient_count": 0},
        {"start_month": LAST_MONTH, "end_month": FIRST_MONTH},
        {"start_month": FIRST_MONTH.replace(day=2)},
    ],
)
def test_invalid_generation_options_do_not_create_target_parent(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    root = tmp_path / "absent-project"
    with pytest.raises(ValueError):
        reset_demo_data(root, REFERENCE, data_directory=RELATIVE_TARGET, **overrides)
    assert not root.exists()


@pytest.mark.parametrize("link_kind", ["target", "backup"])
def test_selected_target_and_backup_symlinks_are_rejected(tmp_path: Path, link_kind: str) -> None:
    root = tmp_path / "project"
    original = _existing_project(root)
    external = tmp_path / "external"
    external.mkdir()
    (external / "sentinel.txt").write_bytes(b"must not change through a symlink")
    target = root / RELATIVE_TARGET
    linked = target if link_kind == "target" else target.parent / ".demo_backups"
    linked.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic links"):
        reset_demo_data(root, REFERENCE, data_directory=RELATIVE_TARGET)
    assert linked.is_symlink()
    assert _file_bytes(external) == {"sentinel.txt": b"must not change through a symlink"}
    _assert_original_preserved(root, original)


@pytest.mark.parametrize("selection", [".", "..", ".demo_backups", ".demo-stage-reserved"])
def test_directory_selection_cannot_replace_project_or_reserved_directories(
    tmp_path: Path, selection: str
) -> None:
    root = tmp_path / "project"
    original = _existing_project(root)
    with pytest.raises(ValueError):
        reset_demo_data(root, REFERENCE, data_directory=selection)
    assert _file_bytes(root) == original


def test_cli_preview_reports_exact_destination_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "project"
    before = _existing_project(root)
    result = _run_cli(root, tmp_path, "--data-dir", str(RELATIVE_TARGET))
    assert result.returncode == 0, result.stderr
    assert "120 pazienti" in result.stdout
    assert f"Destinazione: {root / RELATIVE_TARGET}" in result.stdout
    assert "Anteprima" in result.stdout
    assert _file_bytes(root) == before
    assert not (root / RELATIVE_TARGET).exists()
    assert not list((root / "mock_data").glob(".demo-stage-*"))


def test_cli_write_anchors_relative_destination_to_project_not_working_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    before = _existing_project(root)
    result = _run_cli(root, tmp_path, "--data-dir", str(RELATIVE_TARGET), "--write")
    assert result.returncode == 0, result.stderr
    assert _file_bytes(root / RELATIVE_TARGET) == {
        name: text.encode("utf-8") for name, text in scenario_files().items()
    }
    _assert_original_preserved(root, before)
    assert not (tmp_path / RELATIVE_TARGET).exists()


def test_cli_rejects_unsafe_destination_before_write(tmp_path: Path) -> None:
    root = tmp_path / "project"
    before = _existing_project(root)
    result = _run_cli(root, tmp_path, "--data-dir", ".", "--write")
    assert result.returncode == 2
    assert "must not replace the project" in result.stderr
    assert _file_bytes(root) == before
