import csv
from pathlib import Path

from axis.analysis import GeneEvidenceBuilder


def _write(path: Path, header: str, row: str) -> None:
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")


def test_gene_evidence_requires_multiple_layers_for_priority(
    tmp_path: Path,
) -> None:
    shortlist = tmp_path / "shortlist.tsv"
    single = tmp_path / "single.tsv"
    causal = tmp_path / "causal.tsv"
    karow = tmp_path / "karow.tsv"
    genetics = tmp_path / "genetics.tsv"
    intelligence = tmp_path / "intelligence.tsv"
    _write(
        shortlist,
        "gene_symbol\tselection_status\tavailable_studies\tdirection\t"
        "direction_concordant\tcombined_adjusted_p_value",
        "GENE1\texploratory_candidate\t2\thigher_in_case\tTrue\t0.01",
    )
    _write(
        single,
        "gene_symbol\tbest_single_cell_adjusted_p_value\t"
        "single_cell_bulk_direction_agrees",
        "GENE1\t0.01\tTrue",
    )
    _write(
        causal,
        "gene_symbol\tdecision\tbulk_direction",
        "GENE1\tgenerate_causal_evidence\thigher_in_case",
    )
    _write(
        karow,
        "cohort\tmodality\tdirection\tfeature_id\tgene_symbol",
        "cohort_2\trna_seq\thigher_in_case\tENSG1\tGENE1",
    )
    _write(
        genetics,
        "gene_symbol\tgenetic_evidence_count\tmaximum_evidence_score",
        "GENE1\t0\t0",
    )
    _write(
        intelligence,
        "gene_symbol\ttractability_modalities\tclinical_candidates\t"
        "safety_liabilities\tis_essential",
        "GENE1\tSM\t0\t0\t0",
    )

    result = GeneEvidenceBuilder().build(
        shortlist_path=shortlist,
        single_cell_path=single,
        causal_review_path=causal,
        karow_signature_path=karow,
        genetics_path=genetics,
        intelligence_path=intelligence,
        output_root=tmp_path / "out",
    )

    with result.master_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert row["priority_group"] == "experimental_priority"
    assert result.pharmacological_priorities == 0
    assert row["karow_supporting_cohorts"] == "cohort_2"
