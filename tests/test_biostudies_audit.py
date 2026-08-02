import csv  # noqa: I001
from pathlib import Path
from typing import Any

from axis.ingestion import BioStudiesCandidateAuditor, parse_sdrf


SDRF = "\n".join(
    (
        "Source Name\tCharacteristics[individual]\tCharacteristics[disease]\t"
        "Comment[ENA_SAMPLE]\tFactor Value[stimulation]",
        "AS1_PB\tAS1\tankylosing spondylitis\tERS1\tnone",
        "AS1_PB\tAS1\tankylosing spondylitis\tERS1\tnone",
        "AS1_STIM\tAS1\tankylosing spondylitis\tERS2\tlipopolysaccharide",
        "AS2_PB\tAS2\tankylosing spondylitis\tERS3\tnone",
    )
)


class FakeClient:
    def fetch_study(self, accession: str) -> dict[str, Any]:
        return {
            "attributes": [{"name": "Title", "value": "Perturbation study"}],
            "section": {"files": [[{"path": f"{accession}.sdrf.txt"}]]},
        }

    def fetch_study_info(self, accession: str) -> dict[str, Any]:
        return {"httpLink": f"https://example.test/{accession}"}

    def fetch_text(self, url: str) -> str:
        assert url.endswith(".sdrf.txt")
        return SDRF


def test_parse_sdrf_collapses_sequencing_lanes() -> None:
    samples = parse_sdrf(SDRF)

    assert len(samples) == 3
    assert {sample.participant_id for sample in samples} == {"AS1", "AS2"}
    assert {sample.treatment for sample in samples} == {
        "",
        "stimulation=lipopolysaccharide",
    }


def test_audit_classifies_perturbation_as_mechanistic(tmp_path: Path) -> None:
    result = BioStudiesCandidateAuditor().audit(
        FakeClient(),
        ("E-MTAB-TEST",),
        output_root=tmp_path,
    )

    with result.output_path.open(encoding="utf-8", newline="") as source:
        audit = next(csv.DictReader(source, delimiter="\t"))
    assert audit["participants"] == "2"
    assert audit["case_participants"] == "2"
    assert audit["control_participants"] == "0"
    assert audit["recommended_role"] == "mechanistic_perturbation_context"
    assert audit["eligibility_status"] == "not_primary_replication"
