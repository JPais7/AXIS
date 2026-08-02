import json
from pathlib import Path

import pytest

from axis.analysis import DesignInspector


def write_analysis(root: Path, study: str, payload: dict[str, object]) -> Path:
    directory = root / study / "prepared" / "matrix"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "differential-analysis.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return directory


def test_design_recommends_limma_and_records_declared_covariates(
    tmp_path: Path,
) -> None:
    directory = write_analysis(
        tmp_path,
        "GSE1",
        {
            "case_samples": 8,
            "control_samples": 9,
            "platform": "GPL570",
        },
    )

    path = DesignInspector().create(
        "GSE1",
        independence="independent",
        covariates=("sex", "batch"),
        data_root=tmp_path,
    )[0]

    assert path == directory / "experimental-design.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["assay"] == "microarray"
    assert payload["recommended_method"] == ("limma empirical Bayes linear model")
    assert payload["covariates"] == ["sex", "batch"]
    assert payload["warnings"] == [
        "the executable analysis does not model declared covariates: sex, batch"
    ]


def test_design_reports_executed_adjusted_model(tmp_path: Path) -> None:
    write_analysis(
        tmp_path,
        "GSE1",
        {
            "case_samples": 18,
            "control_samples": 25,
            "platform": "GPL570",
            "method": {
                "selected": "linear-model",
                "name": "moderated general linear model",
                "modeled_covariates": ["sex", "age", "batch"],
            },
        },
    )

    path = DesignInspector().create(
        "GSE1",
        independence="independent",
        covariates=("sex", "age", "batch"),
        data_root=tmp_path,
    )[0]
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["executable_method"] == "moderated general linear model"
    assert payload["warnings"] == []


def test_design_flags_low_power_and_unknown_independence(tmp_path: Path) -> None:
    write_analysis(
        tmp_path,
        "GSE1",
        {
            "case_samples": 3,
            "control_samples": 3,
            "data_type": "normalized RNA-seq abundance",
        },
    )

    path = DesignInspector().create(
        "GSE1",
        independence="unknown",
        data_root=tmp_path,
    )[0]
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert "fewer than four samples" in payload["warnings"][0]
    assert "sample independence" in payload["warnings"][1]
    assert payload["assay"] == "rna-seq"


def test_design_rejects_pairing_for_independent_samples(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="incompatible"):
        DesignInspector().create(
            "GSE1",
            independence="independent",
            paired_by="subject",
            data_root=tmp_path,
        )
