import csv
import json
from pathlib import Path

from axis.analysis import Cd8EvidenceReviewer


def test_cd8_evidence_review_does_not_overclaim_third_cohort(
    tmp_path: Path,
) -> None:
    result = Cd8EvidenceReviewer().review(output_root=tmp_path)
    rows = list(
        csv.DictReader(result.registry_path.open(encoding="utf-8"), delimiter="\t")
    )
    readiness = json.loads(result.readiness_path.read_text(encoding="utf-8"))

    assert result.eligible == 2
    assert sum(row["meta_analysis_eligible"] == "True" for row in rows) == 2
    assert readiness["third_public_cohort_found"] is True
    assert readiness["third_cohort_accession"] == "PRJNA1168183"
    assert readiness["publication_ready_systematic_review"] is False
