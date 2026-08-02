import csv  # noqa: I001
from pathlib import Path

from axis.ingestion import SraCandidateAuditor


RUNINFO = "\n".join(
    (
        "Run,BioSample,SampleName,Subject_ID,ScientificName,Sex,Disease",
        "R1,SAM1,AF_1,,Homo sapiens,male,",
        "R2,SAM1,AF_1,,Homo sapiens,male,",
        "R3,SAM2,AF_2,,Homo sapiens,male,",
        "R4,SAM3,AF_3,,Homo sapiens,male,",
        "R5,SAM4,CF_1,,Homo sapiens,male,",
        "R6,SAM5,CF_2,,Homo sapiens,male,",
        "R7,SAM6,CF_3,,Homo sapiens,male,",
    )
)


class FakeSraClient:
    def fetch_runinfo(self, accession: str) -> str:
        assert accession == "SRP1"
        return RUNINFO


def test_sra_audit_requires_and_records_declared_group_patterns(
    tmp_path: Path,
) -> None:
    result = SraCandidateAuditor().audit(
        FakeSraClient(),
        ("SRP1",),
        output_root=tmp_path,
        case_pattern=r"^AF_",
        control_pattern=r"^CF_",
    )

    with result.output_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert row["runs"] == "7"
    assert row["biological_samples"] == "6"
    assert row["case_participants"] == "3"
    assert row["control_participants"] == "3"
    assert row["group_mapping_status"] == "declared_patterns"
    assert row["eligibility_status"] == "manual_review_required"
