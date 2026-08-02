from axis.analysis import SingleCellRobustnessAnalyzer


def test_lineage_summary_keeps_targets_separate() -> None:
    rows = [
        {
            "gene_symbol": gene,
            "cell_type": "CD4 TCM",
            "direction": direction,
            "adjusted_p_value": adjusted,
            "log2_cpm_difference": effect,
        }
        for gene, direction, adjusted, effect in (
            ("DDX24", "lower_in_case", "0.01", "-0.4"),
            ("ADA", "higher_in_case", "0.5", "0.1"),
        )
    ]

    result = SingleCellRobustnessAnalyzer._lineages(rows)

    ddx_t = next(
        row
        for row in result
        if row["gene_symbol"] == "DDX24" and row["lineage"] == "T_cell"
    )
    assert ddx_t["significant_lower_in_case"] == 1
