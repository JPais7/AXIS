import hashlib
import json
from pathlib import Path

import pytest

from axis.analysis import StudyAssessor, verify_study_eligibility
from axis.ingestion import GeoApiError


def make_study(root: Path) -> Path:
    directory = root / "GSE1" / "prepared" / "matrix"
    qc_directory = directory / "qc"
    qc_directory.mkdir(parents=True)
    gene_path = directory / "gene-level-results.tsv"
    gene_path.write_text("gene_symbol\nIL17A\n", encoding="utf-8")
    (directory / "differential-analysis.json").write_text(
        json.dumps({"method": {"declared_but_unmodeled_covariates": ["batch"]}}),
        encoding="utf-8",
    )
    (qc_directory / "qc-report.json").write_text(
        json.dumps(
            {
                "case_samples": 8,
                "control_samples": 9,
                "outlier_samples": [],
                "minimum_sample_correlation": 0.9,
            }
        ),
        encoding="utf-8",
    )
    return gene_path


def test_assessment_records_qc_and_checksum_bound_approval(
    tmp_path: Path,
) -> None:
    gene_path = make_study(tmp_path)

    path = StudyAssessor().assess(
        "GSE1",
        decision="approved",
        rationale="Independent human case-control study with acceptable QC.",
        species="Homo sapiens",
        tissue="blood-derived macrophages",
        phenotype="ankylosing spondylitis",
        allowed_roles=("discovery",),
        data_root=tmp_path,
    )[0]

    payload = verify_study_eligibility(gene_path)
    assert path.name == "study-eligibility.json"
    assert payload["decision"] == "approved"
    assert payload["case_samples"] == 8
    assert payload["unmodeled_covariates"] == ["batch"]
    assert payload["phenotype"] == "ankylosing spondylitis"
    assert payload["allowed_roles"] == ["discovery"]
    assert payload["gene_results_checksum"] == (
        "sha256:" + hashlib.sha256(gene_path.read_bytes()).hexdigest()
    )


def test_eligibility_becomes_stale_when_results_change(tmp_path: Path) -> None:
    gene_path = make_study(tmp_path)
    StudyAssessor().assess(
        "GSE1",
        decision="approved",
        rationale="Reviewed.",
        species="Homo sapiens",
        tissue="blood",
        phenotype="ankylosing spondylitis",
        allowed_roles=("discovery",),
        data_root=tmp_path,
    )
    gene_path.write_text("gene_symbol\nCHANGED\n", encoding="utf-8")

    with pytest.raises(GeoApiError, match="stale"):
        verify_study_eligibility(gene_path)


def test_review_decision_is_not_eligible_for_ranking(tmp_path: Path) -> None:
    gene_path = make_study(tmp_path)
    StudyAssessor().assess(
        "GSE1",
        decision="review",
        rationale="Covariate values still missing.",
        species="Homo sapiens",
        tissue="blood",
        phenotype="ankylosing spondylitis",
        allowed_roles=(),
        data_root=tmp_path,
    )

    with pytest.raises(GeoApiError, match="not approved"):
        verify_study_eligibility(gene_path)


def test_eligibility_rejects_unapproved_use_role(tmp_path: Path) -> None:
    gene_path = make_study(tmp_path)
    StudyAssessor().assess(
        "GSE1",
        decision="approved",
        rationale="Independent validation only.",
        species="Homo sapiens",
        tissue="blood",
        phenotype="ankylosing spondylitis",
        allowed_roles=("external_validation",),
        data_root=tmp_path,
    )

    with pytest.raises(GeoApiError, match="role 'discovery'"):
        verify_study_eligibility(gene_path, required_role="discovery")
