import csv
import json
from pathlib import Path

from axis.ingestion import (
    GeoSample,
    GeoSampleMetadataClient,
    PrioritySampleAuditor,
)


class FakeSampleClient:
    def samples(self, accession: str) -> tuple[GeoSample, ...]:
        samples = [
            GeoSample(
                f"GSM{index}",
                f"untreated ankylosing spondylitis patient {index}",
                "PBMC",
                (f"subject id: AS{index}",),
                f"{accession}_series_matrix.txt.gz",
            )
            for index in range(1, 4)
        ]
        samples.extend(
            GeoSample(
                f"GSM{index}",
                f"healthy control {index}",
                "PBMC",
                (f"subject id: HC{index}",),
                f"{accession}_series_matrix.txt.gz",
            )
            for index in range(4, 7)
        )
        return tuple(samples)


def test_sample_audit_finds_reviewable_case_control_design(tmp_path: Path) -> None:
    queue = tmp_path / "queue.tsv"
    queue.write_text(
        "accession\tpriority_tier\tpriority_score\nGSE1\thigh\t10\n",
        encoding="utf-8",
    )

    result = PrioritySampleAuditor().build(
        FakeSampleClient(),  # type: ignore[arg-type]
        queue,
        output_root=tmp_path,
    )

    assert result.audited_studies == 1
    assert result.design_review_candidates == 1
    with result.study_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert row["suggested_cases"] == "3"
    assert row["suggested_controls"] == "3"
    assert row["automatic_eligibility"] == "False"
    assert row["audit_status"] == "design_review_candidate"
    assert row["treated_cases"] == "0"
    assert row["unknown_treatment_cases"] == "0"
    assert result.design_queue_path.exists()
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["automatic_eligibility"] is False


def test_matrix_header_parser_extracts_sample_characteristics() -> None:
    lines = (
        '!Sample_title\t"AS patient"\t"healthy control"\n',
        '!Sample_geo_accession\t"GSM1"\t"GSM2"\n',
        '!Sample_source_name_ch1\t"blood"\t"blood"\n',
        '!Sample_characteristics_ch1\t"disease: AS"\t"disease: healthy"\n',
    )

    samples = GeoSampleMetadataClient._parse_header(lines, "matrix.txt.gz")

    assert len(samples) == 2
    assert samples[0].accession == "GSM1"
    assert samples[0].characteristics == ("disease: AS",)
