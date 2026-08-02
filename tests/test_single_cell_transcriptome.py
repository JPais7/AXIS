import csv
import gzip
import io
import tarfile
from pathlib import Path

from axis.analysis import SingleCellTranscriptomeAnalyzer


def add_gzip_member(archive: tarfile.TarFile, name: str, text: str) -> None:
    payload = gzip.compress(text.encode())
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    archive.addfile(info, io.BytesIO(payload))


def test_transcriptome_analysis_filters_and_integrates(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.tsv.gz"
    cells = (
        ("A1", "AXI", "AAAA"),
        ("A2", "AXI", "BBBB"),
        ("H1", "Healthy", "CCCC"),
        ("H2", "Healthy", "DDDD"),
    )
    with gzip.open(metadata, "wt", encoding="utf-8") as output:
        output.write("CellName\tSubject\tStatus\tIncludedInStudy\tCellType\n")
        for subject, status, barcode in cells:
            output.write(f"RUN_{barcode}\t{subject}\t{status}\tTRUE\tCD4 TCM\n")
    archive_path = tmp_path / "matrix.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        add_gzip_member(
            archive,
            "RUN.barcodes.tsv.gz",
            "\n".join(f"{barcode}-1" for _, _, barcode in cells) + "\n",
        )
        add_gzip_member(
            archive,
            "RUN.features.tsv.gz",
            "E1\tCD2\tGene Expression\n"
            "E2\tCD3D\tGene Expression\n"
            "E3\tCD3E\tGene Expression\n"
            "E4\tOTHER\tGene Expression\n",
        )
        entries = []
        for cell_index, count in enumerate((80, 70, 10, 15), start=1):
            entries.extend(
                (
                    f"1 {cell_index} {count}",
                    f"2 {cell_index} {count}",
                    f"3 {cell_index} {count}",
                    f"4 {cell_index} {300 - 3 * count}",
                )
            )
        add_gzip_member(
            archive,
            "RUN.matrix.mtx.gz",
            "%%MatrixMarket matrix coordinate integer general\n"
            f"4 4 {len(entries)}\n" + "\n".join(entries) + "\n",
        )
    bulk = tmp_path / "bulk.tsv"
    bulk.write_text(
        "gene_symbol\tdirection\tdirection_concordant\nCD2\thigher_in_case\tTrue\n",
        encoding="utf-8",
    )

    result = SingleCellTranscriptomeAnalyzer().analyze(
        archive_path,
        metadata,
        cell_types=("CD4 TCM",),
        minimum_cells=1,
        minimum_cpm=0,
        minimum_group_fraction=0.01,
        bulk_path=bulk,
        output_root=tmp_path / "out",
    )

    assert result.genes_tested == 4
    with result.candidate_path.open(encoding="utf-8", newline="") as source:
        candidates = {
            row["gene_symbol"]: row for row in csv.DictReader(source, delimiter="\t")
        }
    assert candidates["CD2"]["single_cell_bulk_direction_agrees"] == "True"
    assert candidates["CD2"]["best_single_cell_direction"] == "higher_in_case"
    with result.pathway_path.open(encoding="utf-8", newline="") as source:
        pathways = tuple(csv.DictReader(source, delimiter="\t"))
    assert any(row["pathway"] == "T_cell_receptor_signalling" for row in pathways)
