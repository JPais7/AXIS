import csv
import hashlib
import json
from pathlib import Path

from axis.analysis import ShortlistBuilder


def write_concordance(root: Path) -> Path:
    path = root / "direction-concordance.tsv"
    fields = (
        "gene_symbol",
        "available_studies",
        "direction",
        "direction_concordant",
        "nominal_supporting_studies",
        "study_directions",
        "study_effects",
        "mean_absolute_effect_percentile",
        "combined_p_value",
        "combined_adjusted_p_value",
    )
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for gene, concordant, support, percentile, adjusted in (
            ("KEEP", True, 2, 0.95, 0.01),
            ("WEAK", True, 2, 0.70, 0.01),
            ("MIXED", False, 2, 0.99, 0.01),
        ):
            writer.writerow(
                {
                    "gene_symbol": gene,
                    "available_studies": 2,
                    "direction": "higher_in_case",
                    "direction_concordant": concordant,
                    "nominal_supporting_studies": support,
                    "study_directions": "",
                    "study_effects": "",
                    "mean_absolute_effect_percentile": percentile,
                    "combined_p_value": adjusted / 2,
                    "combined_adjusted_p_value": adjusted,
                }
            )
    (root / "direction-concordance-analysis.json").write_text(
        json.dumps(
            {
                "analysis_role": "exploratory_direction_concordance",
                "studies": ["GSE1", "GSE2"],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_shortlist_applies_all_criteria_and_records_checksum(
    tmp_path: Path,
) -> None:
    source = write_concordance(tmp_path)

    result = ShortlistBuilder().build(source)

    assert result.candidates == 1
    with result.output_path.open(encoding="utf-8", newline="") as output:
        row = next(csv.DictReader(output, delimiter="\t"))
    assert row["shortlist_rank"] == "1"
    assert row["selection_status"] == "exploratory_candidate"
    assert row["gene_symbol"] == "KEEP"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    assert summary["source_checksum"] == f"sha256:{expected}"
    assert summary["publication_eligible"] is False
