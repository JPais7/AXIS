from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from axis.analysis.reproducibility import StudyReproducer

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _copy_frozen_study(tmp_path: Path) -> Path:
    manifest = json.loads(
        (
            PROJECT_ROOT
            / "reproducibility/ddx24-study/manifest.json"
        ).read_text(encoding="utf-8")
    )
    missing_inputs = [
        item["path"]
        for item in manifest["inputs"].values()
        if not (PROJECT_ROOT / item["path"]).is_file()
    ]
    if missing_inputs:
        pytest.skip(
            "DDX24 frozen participant-level inputs are not distributed in "
            "the public repository: " + ", ".join(missing_inputs)
        )
    for item in manifest["inputs"].values():
        source = PROJECT_ROOT / item["path"]
        target = tmp_path / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    shutil.copyfile(PROJECT_ROOT / "poetry.lock", tmp_path / "poetry.lock")
    manifest_path = tmp_path / "reproducibility/ddx24-study/manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def test_ddx24_study_reproduces_all_frozen_checks(tmp_path: Path) -> None:
    _copy_frozen_study(tmp_path)
    result = StudyReproducer().reproduce(
        "ddx24-study",
        workspace=tmp_path,
    )
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert result.checks == result.passed
    assert report["status"] == "reproduced"
    assert report["offline"] is True
    assert report["checks"]["failed"] == 0


def test_ddx24_study_rejects_changed_frozen_input(tmp_path: Path) -> None:
    _copy_frozen_study(tmp_path)
    changed = (
        tmp_path
        / "data/analysis/single-cell-validation/GSE163314/"
        "donor-pseudobulk.tsv"
    )
    changed.write_text(
        changed.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="input integrity"):
        StudyReproducer().reproduce(
            "ddx24-study",
            workspace=tmp_path,
        )
