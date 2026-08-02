import json
from pathlib import Path

from axis.analysis import PublicationPackager


def test_publication_package_binds_claims_to_checksummed_artifacts(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact.tsv"
    meta = tmp_path / "meta.tsv"
    composition = tmp_path / "composition.tsv"
    artifact.write_text("result\nvalue\n", encoding="utf-8")
    meta.write_text(
        "gene_symbol\tpooled_effect\tci_low\tci_high\tp_value\t"
        "i_squared_percent\n"
        "DDX24\t-0.2\t-0.5\t0.1\t0.1\t80\n"
        "ADA\t-0.3\t-0.5\t-0.1\t0.01\t60\n",
        encoding="utf-8",
    )
    composition.write_text(
        "gene_symbol\teffect_retained_percent\nDDX24\t20\n",
        encoding="utf-8",
    )

    result = PublicationPackager().build(
        artifacts={
            "discovery_lock": artifact,
            "meta_analysis": meta,
            "leave_one_out": artifact,
            "composition": composition,
            "laboratory_plan": artifact,
        },
        meta_analysis_path=meta,
        composition_path=composition,
        output_root=tmp_path / "out",
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.artifacts == 5
    assert manifest["claim_policy"]["DDX24"].startswith("exploratory")
    assert manifest["artifacts"]["meta_analysis"]["sha256"]
