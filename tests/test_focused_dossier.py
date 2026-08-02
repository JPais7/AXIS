import json
from pathlib import Path

from axis.targets import FocusedTargetDossierBuilder


def table(path: Path, header: str, row: str) -> None:
    path.write_text(header + "\n" + row + "\n", encoding="utf-8")


def test_focused_dossier_promotes_experiment_not_drug(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk.tsv"
    single = tmp_path / "single.tsv"
    published = tmp_path / "published.tsv"
    intelligence = tmp_path / "intelligence.tsv"
    genetics = tmp_path / "genetics.tsv"
    dossiers = tmp_path / "dossiers"
    dossiers.mkdir()
    table(
        bulk,
        "gene_symbol\tavailable_studies\tdirection\tdirection_concordant"
        "\tstudy_effects\tcombined_adjusted_p_value",
        "EWSR1\t3\tlower_in_case\tTrue\ta:-1|b:-1|c:-1\t0.01",
    )
    table(
        single,
        "gene_symbol\tcell_type\tdirection\tlog2_cpm_difference\tadjusted_p_value",
        "EWSR1\tCD4 TCM\tlower_in_case\t-0.4\t0.02",
    )
    table(
        published,
        "gene_symbol\tvalidation_status\tbest_published_cell_subtype"
        "\tbest_published_direction\tbest_published_adjusted_p_value",
        "EWSR1\tpublished_directional_support\tCD14 Mono\tlower_in_case\t0.001",
    )
    table(
        intelligence,
        "gene_symbol\ttractability_modalities\tclinical_candidates\tsafety_liabilities",
        "EWSR1\tPR|SM\t0\t0",
    )
    table(
        genetics,
        "gene_symbol\tgenetic_evidence_count\tmaximum_evidence_score"
        "\ttherapeutic_direction",
        "EWSR1\t0\t0\tunknown",
    )
    (dossiers / "EWSR1.json").write_text(
        json.dumps(
            {
                "target": {
                    "prioritisation": {
                        "items": [
                            {"key": "isInMembrane", "value": "0"},
                            {"key": "isSecreted", "value": "0"},
                        ]
                    },
                    "tractability": [{"label": "High-Quality Pocket", "value": False}],
                }
            }
        ),
        encoding="utf-8",
    )

    result = FocusedTargetDossierBuilder().build(
        "EWSR1",
        bulk_path=bulk,
        single_cell_path=single,
        published_path=published,
        intelligence_path=intelligence,
        genetics_path=genetics,
        dossier_directory=dossiers,
        output_root=tmp_path / "out",
    )

    payload = json.loads(result.dossier_path.read_text(encoding="utf-8"))
    assert result.decision == "mechanistic_perturbation_candidate"
    assert payload["therapeutic_status"] == "not_ready_no_causal_direction"
    assert "defer_alphafold" in payload["structural_status"]
