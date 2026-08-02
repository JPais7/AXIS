from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from axis.analysis.workflow_comparison import (
    WorkflowComparisonPreparer,
    WorkflowComparisonSummarizer,
)


def _write_assessment(
    template: Path,
    destination: Path,
    *,
    reviewer: str,
    disagree: bool = False,
) -> None:
    with template.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for index, row in enumerate(rows):
        row["reviewer"] = reviewer
        row["rating"] = "fail" if disagree and index == 0 else "pass"
        row["elapsed_seconds"] = "1.5"
        row["manual_decisions"] = "1"
        row["evidence"] = "synthetic-output.tsv"
        row["notes"] = "No deviation."
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=tuple(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def test_comparison_preparation_separates_reference_and_checksums(
    tmp_path: Path,
) -> None:
    result = WorkflowComparisonPreparer().prepare(output_root=tmp_path / "comparison")
    result = WorkflowComparisonPreparer().prepare(output_root=tmp_path / "comparison")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert manifest["synthetic"] is True
    assert manifest["no_weighted_overall_score"] is True
    assert result.assessment_template_path.is_file()
    assert (result.output_root / "evaluator-package/candidate-studies.tsv").is_file()
    procedure = (
        result.output_root / "evaluator-package/STANDARD-OPERATING-PROCEDURE.md"
    ).read_text(encoding="utf-8")
    rubric_path = result.output_root / "evaluator-package/rating-rubric.tsv"
    result_template = result.output_root / "evaluator-package/result-template.tsv"
    assert rubric_path.is_file()
    assert result_template.is_file()
    assert "start timing immediately before" in procedure
    assert "unsuccessful attempt is fail" in rubric_path.read_text(encoding="utf-8")
    with rubric_path.open(encoding="utf-8", newline="") as handle:
        rubric = list(csv.DictReader(handle, delimiter="\t"))
    with result.assessment_template_path.open(encoding="utf-8", newline="") as handle:
        assessment = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rubric) == 21
    assert {row["criterion"] for row in rubric} == {
        row["criterion"] for row in assessment
    }
    assert (
        result.output_root / "coordinator-reference/expected-study-decisions.tsv"
    ).is_file()
    for item in manifest["files"]:
        path = result.output_root / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_comparison_summary_preserves_disagreement_and_has_no_score(
    tmp_path: Path,
) -> None:
    preparation = WorkflowComparisonPreparer().prepare(
        output_root=tmp_path / "comparison"
    )
    first = tmp_path / "reviewer-a.tsv"
    second = tmp_path / "reviewer-b.tsv"
    _write_assessment(preparation.assessment_template_path, first, reviewer="A")
    _write_assessment(
        preparation.assessment_template_path,
        second,
        reviewer="B",
        disagree=True,
    )

    result = WorkflowComparisonSummarizer().summarize(
        [first, second],
        output_root=tmp_path / "summary",
    )
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    with result.article_table_path.open(encoding="utf-8", newline="") as handle:
        article_rows = list(csv.DictReader(handle, delimiter="\t"))

    assert result.disagreements == 1
    assert report["status"] == "consensus_required"
    assert report["no_weighted_overall_score"] is True
    assert {row["weighted_score"] for row in article_rows} == {"not_calculated"}
    assert sum(int(row["unresolved"]) for row in article_rows) == 1
    assert result.consensus_template_path.is_file()

    with result.consensus_template_path.open(encoding="utf-8", newline="") as handle:
        consensus_rows = list(csv.DictReader(handle, delimiter="\t"))
    consensus_rows[0]["consensus"] = "pass"
    consensus_rows[0]["rationale"] = "Resolved against the frozen reference."
    with result.consensus_template_path.open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=tuple(consensus_rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(consensus_rows)
    resolved = WorkflowComparisonSummarizer().summarize(
        [first, second],
        consensus_path=result.consensus_template_path,
        output_root=tmp_path / "resolved",
    )
    resolved_report = json.loads(resolved.report_path.read_text(encoding="utf-8"))
    assert resolved_report["status"] == "complete"
    assert resolved_report["unresolved_disagreements"] == 0


def test_comparison_summary_requires_two_reviewers(tmp_path: Path) -> None:
    preparation = WorkflowComparisonPreparer().prepare(
        output_root=tmp_path / "comparison"
    )
    assessment = tmp_path / "reviewer-a.tsv"
    _write_assessment(preparation.assessment_template_path, assessment, reviewer="A")

    with pytest.raises(ValueError, match="exactly two"):
        WorkflowComparisonSummarizer().summarize([assessment])
