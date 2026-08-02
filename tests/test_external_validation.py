import csv
import hashlib
import json
from pathlib import Path

from axis.analysis import ExternalValidator


def write_inputs(root: Path) -> tuple[Path, Path]:
    concordance = root / "direction-concordance.tsv"
    with concordance.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("gene_symbol", "direction_concordant", "direction"))
        writer.writerow(("KEEP", "True", "higher_in_case"))
        writer.writerow(("BACKGROUND", "True", "higher_in_case"))
    shortlist = root / "exploratory-shortlist.tsv"
    with shortlist.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("shortlist_rank", "gene_symbol", "direction"))
        writer.writerow(("1", "KEEP", "higher_in_case"))
    checksum = hashlib.sha256(concordance.read_bytes()).hexdigest()
    (root / "exploratory-shortlist.json").write_text(
        json.dumps(
            {
                "analysis_role": "exploratory_shortlist",
                "studies": ["GSE1", "GSE2"],
                "source_path": str(concordance),
                "source_checksum": f"sha256:{checksum}",
            }
        ),
        encoding="utf-8",
    )
    return shortlist, concordance


def write_validation(root: Path) -> None:
    path = root / "GSE3" / "prepared" / "rnaseq-normalized" / "gene-level-results.tsv"
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "gene_symbol",
                "median_mean_difference",
                "simes_p_value",
                "adjusted_p_value",
            )
        )
        writer.writerow(("KEEP", "1.0", "0.01", "0.02"))
        writer.writerow(("BACKGROUND", "-1.0", "0.5", "0.8"))
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    (path.parent / "study-eligibility.json").write_text(
        json.dumps(
            {
                "accession": "GSE3",
                "decision": "approved",
                "species": "Homo sapiens",
                "tissue": "blood",
                "phenotype": "ankylosing spondylitis",
                "allowed_roles": ["external_validation"],
                "gene_results_checksum": f"sha256:{checksum}",
            }
        ),
        encoding="utf-8",
    )


def test_external_validation_uses_frozen_independent_shortlist(
    tmp_path: Path,
) -> None:
    shortlist, _ = write_inputs(tmp_path)
    data_root = tmp_path / "geo"
    write_validation(data_root)

    result = ExternalValidator().validate(
        shortlist,
        "GSE3",
        data_root=data_root,
        output_root=tmp_path / "validation",
    )

    assert result.matched_candidates == 1
    assert result.direction_validated == 1
    assert result.nominally_validated == 1
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["discovery_studies"] == ["GSE1", "GSE2"]
    assert summary["publication_eligible"] is False
    assert summary["nominal_directional_enrichment"]["candidate_supported"] == 1
