from axis.analysis import TargetDeepDiveBuilder


def test_ddx24_remains_experimental_until_direction_is_resolved() -> None:
    decision = TargetDeepDiveBuilder()._decision(
        "DDX24",
        {"total_score": "47"},
        {
            "direction": "lower_in_case",
            "direction_concordant": "True",
            "combined_adjusted_p_value": "0.009",
        },
        {},
        {},
        {},
        {"genetic_evidence_count": "0", "therapeutic_direction": "unknown"},
        {"tractability_modalities": "PR", "clinical_candidates": "0"},
        {"target": {"drugAndClinicalCandidates": {"rows": []}}},
    )

    assert decision["decision"] == "experimental_only_not_drug_ready"
    assert "partial restoration" in str(decision["therapeutic_direction"])
    assert decision["known_drugs"] == ""


def test_ada_druggability_does_not_imply_safe_disease_direction() -> None:
    decision = TargetDeepDiveBuilder()._decision(
        "ADA",
        {"total_score": "35"},
        {
            "direction": "lower_in_case",
            "direction_concordant": "True",
            "combined_adjusted_p_value": "0.0002",
        },
        {},
        {},
        {"status": "published_directional_support"},
        {"genetic_evidence_count": "0", "therapeutic_direction": "unknown"},
        {"tractability_modalities": "SM", "clinical_candidates": "2"},
        {
            "target": {
                "drugAndClinicalCandidates": {
                    "rows": [{"drug": {"name": "PENTOSTATIN"}}]
                }
            }
        },
    )

    assert decision["decision"] == "deprioritise_systemic_ada_inhibition"
    assert decision["known_drugs"] == "PENTOSTATIN"
    assert "measure ADA activity" in str(decision["therapeutic_direction"])


def test_ddx24_robustness_gate_suspends_perturbation() -> None:
    decision = {
        "gene_symbol": "DDX24",
        "decision": "experimental_only_not_drug_ready",
        "therapeutic_direction": "test partial restoration",
        "principal_risk": "unknown",
        "stop_rule": "old",
    }
    updated = TargetDeepDiveBuilder._apply_robustness(
        decision,
        {"p_value": "0.109", "i_squared_percent": "86.7"},
        [
            {"effect_retained_percent": "19"},
            {"effect_retained_percent": "41"},
            {"effect_retained_percent": "1842"},
        ],
    )

    assert (
        updated["decision"]
        == "deprioritise_pending_reference_deconvolution"
    )
    assert updated["composition_attenuated_studies"] == 2


def test_single_cell_reference_restores_experimental_ddx24_status() -> None:
    decision = {
        "gene_symbol": "DDX24",
        "decision": "deprioritise_pending_reference_deconvolution",
    }
    reference = [
        {
            "gene_symbol": "DDX24",
            "cell_type": f"type_{index}",
            "adjusted_p_value": "0.01",
            "direction": "lower_in_case",
        }
        for index in range(5)
    ]

    updated = TargetDeepDiveBuilder._apply_single_cell_reference(
        decision, reference
    )

    assert updated["decision"] == "experimental_only_not_drug_ready"
    assert updated["reference_significant_cell_types"] == 5
