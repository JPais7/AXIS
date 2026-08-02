from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from axis.analysis.demo import AxisDemoRunner

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _copy_demo(tmp_path: Path) -> None:
    target = tmp_path / "examples" / "demo"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PROJECT_ROOT / "examples" / "demo", target)


def test_synthetic_demo_passes_all_checks(tmp_path: Path) -> None:
    _copy_demo(tmp_path)
    result = AxisDemoRunner().run(workspace=tmp_path)
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert result.checks == 9
    assert result.passed == result.checks
    assert report["status"] == "passed"
    assert report["synthetic"] is True
    assert report["offline"] is True


def test_synthetic_demo_rejects_changed_input(tmp_path: Path) -> None:
    _copy_demo(tmp_path)
    source = tmp_path / "examples" / "demo" / "cohort-effects.tsv"
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        AxisDemoRunner().run(workspace=tmp_path)


def test_installed_demo_falls_back_to_packaged_resources(tmp_path: Path) -> None:
    result = AxisDemoRunner().run(workspace=tmp_path)
    assert result.passed == 9
    assert result.report_path.is_file()
