from axis.analysis.karow import KarowSupplementAuditor


def test_karow_extracts_both_directional_blocks() -> None:
    rows = [
        ["title"],
        ["Upregulated genes", "", "", "", "Downregulated genes"],
        ["Ensembl-ID", "Gene symbol", "", "", "Ensembl-ID", "Gene symbol"],
        ["ENSG1", "GENE1", "", "", "ENSG2", "GENE2"],
    ]

    result = KarowSupplementAuditor._extract(rows, "cohort_2", "rna_seq")

    assert {(row["gene_symbol"], row["direction"]) for row in result} == {
        ("GENE1", "higher_in_case"),
        ("GENE2", "lower_in_case"),
    }


def test_karow_candidate_validation_preserves_conflicts() -> None:
    signature = [
        {
            "cohort": "cohort_1",
            "modality": "microarray",
            "direction": "higher_in_case",
            "feature_id": "probe1",
            "gene_symbol": "GENE1",
        }
    ]

    result = KarowSupplementAuditor._validate_candidate(
        "GENE1", "lower_in_case", signature
    )

    assert result["status"] == "published_directional_conflict"
