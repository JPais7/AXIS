from axis.analysis import SecondarySingleCellReviewer


def test_secondary_sample_parser_collapses_assay_components() -> None:
    rows = SecondarySingleCellReviewer._sample_rows(
        [
            {
                "accession": "GSE277117",
                "library_id": "GSM1",
                "title": "PBMC, NR, TNFi, Pre, scRNA, KAS01_KAS02",
                "source": "PBMC",
            }
        ],
        [
            {
                "accession": "GSE288581",
                "library_id": "GSM2",
                "title": "HC1564_PBMC_GEX, CD45RO+ CD8+",
                "source": "Peripheral Blood",
            }
        ],
    )

    assert rows[0]["participant_count"] == 2
    assert rows[1]["group"] == "healthy_control"
    assert rows[1]["participant_ids"] == "1564"
