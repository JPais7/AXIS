import csv
import gzip
from pathlib import Path

import httpx

from axis.targets import AtlasDownloadClient, NucleomeContactBuilder


def compressed(text: str) -> bytes:
    return gzip.compress(text.encode())


def test_contact_scan_is_selective_and_preserves_absence_uncertainty(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.tsv"
    plan.write_text(
        "gene_symbol\tlead_variant\tvariant_chromosome"
        "\tvariant_position_1based\ttranscription_start_1based\tquery_status\n"
        "CD2\t1_100000_A_G\tchr1\t100000\t120000"
        "\tready_for_processed_contact_query\n",
        encoding="utf-8",
    )
    metadata = (
        "cell,subtype,CisLongContact,Donor,Tissue\n"
        "PBMC_11714_CELL1,c1-b8,200,11714,PBMC\n"
        "PBMC_11714_CELL2,c1-b8,100,11714,PBMC\n"
    )
    contact = "0\tchr1\t100100\t0\t0\tchr1\t120100\t1\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if "metadata" in str(request.url):
            return httpx.Response(200, content=compressed(metadata))
        assert "CELL1" in str(request.url)
        return httpx.Response(200, content=compressed(contact))

    http = httpx.Client(transport=httpx.MockTransport(handler))
    result = NucleomeContactBuilder().build(
        plan,
        output_root=tmp_path / "out",
        cells_per_subtype_donor=1,
        subtypes=("c1-b8",),
        client=AtlasDownloadClient(client=http),
    )

    assert result.downloaded_cells == 1
    assert result.targets_with_observed_contacts == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert row["observed_contacts"] == "1"
    assert row["contact_status"] == "observed_in_sample"
    manifest = result.cell_manifest_path.read_text(encoding="utf-8")
    assert "CELL1" in manifest
    assert "CELL2" not in manifest
