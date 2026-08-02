import csv
import json
from pathlib import Path

from axis.targets import TherapeuticReadinessBuilder


def write_table(path: Path, header: str, row: str) -> None:
    path.write_text(header + "\n" + row + "\n", encoding="utf-8")


def test_readiness_preserves_direction_uncertainty(tmp_path: Path) -> None:
    genetics = tmp_path / "genetics.tsv"
    context = tmp_path / "context.tsv"
    discovery = tmp_path / "discovery.tsv"
    validation = tmp_path / "validation.tsv"
    intelligence = tmp_path / "intelligence.tsv"
    nucleome = tmp_path / "nucleome.tsv"
    dossier = tmp_path / "GENE1.json"
    dossier.write_text(
        json.dumps(
            {
                "target": {
                    "drugAndClinicalCandidates": {
                        "rows": [{"drug": {"name": "DRUG A"}}]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    write_table(
        genetics,
        "gene_symbol\tgenetic_evidence_count\tmaximum_evidence_score"
        "\ttherapeutic_direction",
        "GENE1\t2\t0.8\tunknown",
    )
    write_table(
        context,
        "gene_symbol\tmaximum_locus_to_gene_score"
        "\tstrong_molecular_colocalisations\ttop_normal_expression_contexts",
        "GENE1\t0.7\t0\tT cell|blood",
    )
    write_table(
        discovery,
        "gene_symbol\tdirection",
        "GENE1\tlower_in_case",
    )
    write_table(
        validation,
        "gene_symbol\tvalidation_direction\tdirection_agrees\tvalidation_p_value",
        "GENE1\tlower_in_case\tTrue\t0.04",
    )
    write_table(
        intelligence,
        "gene_symbol\tclinical_candidates\tmaximum_clinical_stage\tdossier_path",
        f"GENE1\t1\tPHASE_2\t{dossier}",
    )
    write_table(
        nucleome,
        "gene_symbol\tcell_subtype\tdonor\tcontact_status",
        "GENE1\tMemory T\t11714\tobserved_in_sample",
    )

    result = TherapeuticReadinessBuilder().build(
        genetics_path=genetics,
        context_path=context,
        discovery_path=discovery,
        validation_path=validation,
        intelligence_path=intelligence,
        nucleome_path=nucleome,
        output_root=tmp_path / "out",
    )

    with result.output_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert row["follow_up_priority"] == "mechanistic_priority"
    assert row["known_target_drugs"] == "DRUG A"
    assert row["drug_actionability"] == "blocked_by_unknown_therapeutic_direction"
    assert row["normal_immune_contexts"] == "T cell|blood"
    assert row["reference_4d_contact_observed"] == "True"
    assert row["reference_4d_contact_donors"] == "11714"
    assert "resolve_causal_modulation_direction" in row["next_evidence_needed"]
    assert result.direction_resolved == 0
