from pathlib import Path

from axis.analysis import ImprovementAuditor


def test_improvement_audit_flags_heterogeneity_and_composition(
    tmp_path: Path,
) -> None:
    meta = tmp_path / "meta.tsv"
    composition = tmp_path / "composition.tsv"
    quarantine = tmp_path / "quarantine.tsv"
    meta.write_text(
        "gene_symbol\ti_squared_percent\tp_value\n"
        "DDX24\t86\t0.1\nADA\t62\t0.001\n",
        encoding="utf-8",
    )
    composition.write_text(
        "gene_symbol\teffect_retained_percent\n"
        "DDX24\t20\nDDX24\t40\nADA\t10\nADA\t20\n",
        encoding="utf-8",
    )
    quarantine.write_text("accession\nS1\nS2\n", encoding="utf-8")

    result = ImprovementAuditor().audit(
        meta_analysis_path=meta,
        composition_path=composition,
        quarantine_path=quarantine,
        output_root=tmp_path / "out",
    )

    assert result.critical == 3
    assert result.findings >= 5
