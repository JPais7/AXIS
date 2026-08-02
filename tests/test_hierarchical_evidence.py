from axis.analysis import HierarchicalEvidenceAnalyzer


def test_hierarchical_synthesis_reports_direction_without_global_effect() -> None:
    cohorts = [
        {
            "gene_symbol": "DDX24",
            "direction": "lower_in_case",
            "case_samples": 2,
            "control_samples": 2,
        }
        for _ in range(5)
    ]
    contexts = [
        {"gene_symbol": "DDX24", "context_direction": "lower_in_case"},
        {"gene_symbol": "DDX24", "context_direction": "lower_in_case"},
        {"gene_symbol": "DDX24", "context_direction": "mixed"},
    ]

    result = HierarchicalEvidenceAnalyzer._synthesis(
        "DDX24", cohorts, contexts
    )

    assert result["cross_context_conclusion"] == (
        "directionally_supported_across_contexts"
    )
    assert result["global_effect"] == "not_estimated_incompatible_contexts"
