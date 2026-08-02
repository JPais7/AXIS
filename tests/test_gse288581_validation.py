import csv
import gzip
from pathlib import Path

from axis.analysis import Gse288581Validator


def test_gse288581_selects_only_blood_gex_donors(tmp_path: Path) -> None:
    matrix = tmp_path / "series.txt.gz"
    with gzip.open(matrix, "wt", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(["!Sample_geo_accession", "GSM1", "GSM2", "GSM3"])
        writer.writerow(
            [
                "!Sample_title",
                "PB73-4_PBMC_GEX, CD45RO+ CD8+",
                "HC1564_PBMC_GEX, CD45RO+ CD8+",
                "PB73-4_PBMC_TCR, CD45RO+ CD8+",
            ]
        )
        writer.writerow(
            [
                "!Sample_source_name_ch1",
                "Peripheral Blood",
                "Peripheral Blood",
                "Peripheral Blood",
            ]
        )
        writer.writerow(
            [
                "!Sample_supplementary_file_2",
                "ftp://example/a_features.tsv.gz",
                "ftp://example/b_features.tsv.gz",
                "",
            ]
        )
        writer.writerow(
            [
                "!Sample_supplementary_file_3",
                "ftp://example/a_matrix.mtx.gz",
                "ftp://example/b_matrix.mtx.gz",
                "",
            ]
        )

    selected = Gse288581Validator._selected_samples(matrix)

    assert len(selected) == 2
    assert selected[0]["donor_id"] == "AS73-4"
    assert selected[1]["group"] == "Healthy"
