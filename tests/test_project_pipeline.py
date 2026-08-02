import json
from pathlib import Path

import pytest

from axis.analysis import AxisProjectPipeline


def test_project_pipeline_blocks_when_upstream_artifact_is_missing(
    tmp_path: Path,
) -> None:
    result = AxisProjectPipeline().status(
        workspace=tmp_path,
        output_root=Path("project"),
    )

    payload = json.loads(result.status_path.read_text(encoding="utf-8"))
    assert result.completed == 0
    assert result.blocked == 33
    assert payload["status"] == "attention_required"
    assert payload["stages"][0]["name"] == "study_search"


def test_project_pipeline_refuses_changed_frozen_inputs(tmp_path: Path) -> None:
    output = tmp_path / "project"
    output.mkdir()
    lock = output / "discovery-input-lock.json"
    lock.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="frozen discovery inputs changed"):
        AxisProjectPipeline().run(
            workspace=tmp_path,
            output_root=Path("project"),
        )
