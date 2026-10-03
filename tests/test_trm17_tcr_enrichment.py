import csv
import gzip
import json
from pathlib import Path

from axis.analysis.trm17_tcr_enrichment import Trm17TcrEnrichmentAnalyzer


def test_audit_refuses_to_infer_tcr_from_expression_metadata(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.tsv.gz"
    with gzip.open(metadata, "wt", encoding="utf-8") as output:
        output.write("cell_barcode\tcart_patient_id\tactive_ident\nA\tP1\tT cells\n")
    result = Trm17TcrEnrichmentAnalyzer().analyze(
        metadata, output_root=tmp_path / "out"
    )
    assert result.status == "not_identifiable"
    status = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "paired single-cell TCR repertoire table" in status["missing_requirements"]
    assert "validated per-cell TRM17 annotation" in status["missing_requirements"]


def test_reports_trbv9_and_other_segments_with_participant_effects(
    tmp_path: Path,
) -> None:
    metadata = tmp_path / "metadata.tsv"
    repertoire = tmp_path / "tcr.tsv"
    metadata.write_text(
        "cell_barcode\tparticipant\tis_trm17\n"
        "A1\tP1\ttrue\nA2\tP1\ttrue\nA3\tP1\tfalse\nA4\tP1\tfalse\n"
        "B1\tP2\ttrue\nB2\tP2\ttrue\nB3\tP2\tfalse\nB4\tP2\tfalse\n"
        "C1\tP3\ttrue\nC2\tP3\ttrue\nC3\tP3\tfalse\nC4\tP3\tfalse\n",
        encoding="utf-8",
    )
    repertoire.write_text(
        "cell_barcode\tv_gene\n"
        "A1\tTRBV9*01\nA2\tTRBV9*01\nA3\tTRBV5-1*01\nA4\tTRBV5-1*01\n"
        "B1\tTRBV9*01\nB2\tTRBV9*01\nB3\tTRBV5-1*01\nB4\tTRBV5-1*01\n"
        "C1\tTRBV9*01\nC2\tTRBV9*01\nC3\tTRBV5-1*01\nC4\tTRBV5-1*01\n",
        encoding="utf-8",
    )
    result = Trm17TcrEnrichmentAnalyzer().analyze(
        metadata, repertoire_path=repertoire, output_root=tmp_path / "out"
    )
    assert result.status == "complete"
    assert result.participants == 3
    with result.segment_path.open(encoding="utf-8", newline="") as source:
        rows = {row["trbv"]: row for row in csv.DictReader(source, delimiter="\t")}
    assert rows["TRBV9"]["trm17_cells"] == "6"
    assert rows["TRBV9"]["participants_with_both_states"] == "3"
