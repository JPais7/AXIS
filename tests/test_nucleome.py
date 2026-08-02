import csv
import json
from pathlib import Path

import httpx

from axis.targets import EnsemblClient, NucleomePlanBuilder


def test_nucleome_plan_creates_targeted_grch38_regions(tmp_path: Path) -> None:
    context = tmp_path / "context.tsv"
    context.write_text(
        "gene_symbol\tensembl_id\tlead_variants"
        "\tmaximum_locus_to_gene_score\n"
        "CD2\tENSG1\t1_117000_A_G\t0.64\n",
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/lookup/id/ENSG1"
        return httpx.Response(
            200,
            json={
                "seq_region_name": "1",
                "start": 120001,
                "end": 125000,
                "strand": 1,
                "assembly_name": "GRCh38",
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    result = NucleomePlanBuilder().build(
        context,
        output_root=tmp_path / "nucleome",
        variant_flank=1_000,
        promoter_flank=500,
        client=EnsemblClient(client=http, endpoint="https://example.test"),
    )

    assert result.targets == 1
    assert result.loci == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert row["variant_window_start_0based"] == "115999"
    assert row["promoter_start_0based"] == "119500"
    assert row["same_chromosome"] == "True"
    assert "PBMC_11714" in row["atlas_donors"]
    assert result.regions_path.read_text(encoding="utf-8").count("\n") == 2
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["genome_assembly"] == "GRCh38"
    assert "not disease-specific" in summary["interpretation"]
