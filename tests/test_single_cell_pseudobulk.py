import csv
import gzip
import io
import tarfile
from pathlib import Path

from axis.analysis import SingleCellPseudobulkAnalyzer


def add_gzip_member(archive: tarfile.TarFile, name: str, text: str) -> None:
    payload = gzip.compress(text.encode())
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    archive.addfile(info, io.BytesIO(payload))


def test_streaming_pseudobulk_uses_subject_level_values(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.tsv.gz"
    with gzip.open(metadata, "wt", encoding="utf-8") as output:
        output.write(
            "CellName\tSubject\tStatus\tIncludedInStudy\tCellType\n"
            "RUN_AAAA\tA1\tAXI\tTRUE\tCD4 TCM\n"
            "RUN_BBBB\tH1\tHealthy\tTRUE\tCD4 TCM\n"
        )
    archive_path = tmp_path / "matrix.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        add_gzip_member(archive, "RUN.barcodes.tsv.gz", "AAAA-1\nBBBB-1\n")
        add_gzip_member(
            archive,
            "RUN.features.tsv.gz",
            "ENSG1\tCD2\tGene Expression\nENSG2\tOTHER\tGene Expression\n",
        )
        add_gzip_member(
            archive,
            "RUN.matrix.mtx.gz",
            "%%MatrixMarket matrix coordinate integer general\n"
            "2 2 4\n"
            "1 1 10\n"
            "2 1 90\n"
            "1 2 2\n"
            "2 2 98\n",
        )

    result = SingleCellPseudobulkAnalyzer().analyze(
        archive_path,
        metadata,
        target_genes=("CD2",),
        cell_types=("CD4 TCM",),
        minimum_cells=1,
        output_root=tmp_path / "out",
    )

    assert result.runs == 1
    assert result.subjects == 2
    with result.pseudobulk_path.open(encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source, delimiter="\t"))
    assert len(rows) == 2
    assert {row["library_count"] for row in rows} == {"100"}
    assert {row["raw_pseudobulk_count"] for row in rows} == {"10", "2"}
