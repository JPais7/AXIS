import csv
from pathlib import Path

from axis.targets import CandidateReviewBuilder


def write(path: Path, header: str, rows: tuple[str, ...]) -> None:
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def test_candidate_review_requires_causal_and_safety_gates(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.tsv"
    intelligence = tmp_path / "intelligence.tsv"
    genetics = tmp_path / "genetics.tsv"
    context = tmp_path / "context.tsv"
    write(
        candidates,
        "gene_symbol\tstructural_triage\texploratory_score"
        "\tbest_single_cell_adjusted_p_value\tbest_single_cell_direction"
        "\tbulk_direction\tsingle_cell_bulk_direction_agrees",
        (
            "SAFE\teligible_after_causal_review\t9\t0.01\tlower_in_case"
            "\tlower_in_case\tTrue",
            "RISK\teligible_after_causal_review\t8\t0.01\tlower_in_case"
            "\tlower_in_case\tTrue",
        ),
    )
    write(
        intelligence,
        "gene_symbol\tresolved\ttractability_modalities\tclinical_candidates"
        "\tsafety_liabilities\tis_essential",
        ("SAFE\tTrue\tSMALLMOLECULE\t0\t0\tFalse", "RISK\tTrue\t\t0\t1\tFalse"),
    )
    write(
        genetics,
        "gene_symbol\tgenetic_evidence_count\ttherapeutic_direction",
        ("SAFE\t1\tinhibit", "RISK\t1\tunknown"),
    )
    write(
        context,
        "gene_symbol\tmaximum_locus_to_gene_score\tstrong_molecular_colocalisations",
        ("SAFE\t0.8\t1", "RISK\t0.7\t0"),
    )

    result = CandidateReviewBuilder().build(
        candidates,
        intelligence_path=intelligence,
        genetics_path=genetics,
        context_path=context,
        output_root=tmp_path / "out",
    )

    with result.output_path.open(encoding="utf-8", newline="") as source:
        rows = {
            row["gene_symbol"]: row for row in csv.DictReader(source, delimiter="\t")
        }
    assert rows["SAFE"]["decision"] == "advance_to_perturbation"
    assert rows["SAFE"]["structural_assessment"] == (
        "review_PDB_then_AlphaFold_if_needed"
    )
    assert rows["RISK"]["decision"] == "deprioritise_safety_or_essentiality"
