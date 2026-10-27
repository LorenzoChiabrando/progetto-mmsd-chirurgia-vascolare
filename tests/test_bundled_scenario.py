"""Keep the committed demo reproducible from its documented generation command."""

from __future__ import annotations

from pathlib import Path

from demo_helpers import scenario_files


def test_bundled_demo_matches_the_documented_scenario() -> None:
    root = Path(__file__).resolve().parents[1] / "mock_data" / "scenario_2026_09_12"
    actual = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file()
    }
    assert actual == scenario_files()
