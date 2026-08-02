import csv
import hashlib
import json
from pathlib import Path

import pytest

from axis.analysis import RankingPublisher, SensitivityAnalyzer
from axis.storage import EvidenceStore


def write_study(
    root: Path,
    study: str,
    effects: tuple[tuple[str, float, float], ...],
) -> None:
    path = root / study / "prepared" / "matrix" / "gene-level-results.tsv"
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "gene_symbol",
                "median_mean_difference",
                "simes_p_value",
                "adjusted_p_value",
            )
        )
        for gene, effect, adjusted in effects:
            writer.writerow((gene, effect, adjusted / 2, adjusted))
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    (path.parent / "study-eligibility.json").write_text(
        json.dumps(
            {
                "accession": study,
                "decision": "approved",
                "species": "Homo sapiens",
                "tissue": "blood",
                "phenotype": "ankylosing spondylitis",
                "allowed_roles": ["discovery"],
                "gene_results_checksum": f"sha256:{checksum}",
            }
        ),
        encoding="utf-8",
    )


def test_sensitivity_reports_gene_stability_and_marks_scenarios(
    tmp_path: Path,
) -> None:
    for study in ("GSE1", "GSE2"):
        write_study(
            tmp_path,
            study,
            (
                ("STABLE", 1.0, 0.01),
                ("RELAXED", 0.2, 0.08),
            ),
        )

    result = SensitivityAnalyzer().run(
        ["GSE1", "GSE2"],
        data_root=tmp_path,
        output_root=tmp_path / "sensitivity",
        alphas=(0.05, 0.1),
        min_differences=(0.0, 0.5),
    )

    assert result.scenarios == 4
    assert result.stable_genes == 1
    with result.gene_path.open(encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source, delimiter="\t"))
    assert rows[0]["gene_symbol"] == "STABLE"
    assert rows[0]["recurrent_scenarios"] == "4"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["analysis_role"] == "sensitivity"
    assert summary["publication_eligible"] is False

    scenario_ranking = next(
        (tmp_path / "sensitivity" / "scenarios").glob("*/recurrence-ranking.tsv")
    )
    with (
        EvidenceStore() as store,
        pytest.raises(ValueError, match="cannot be published"),
    ):
        RankingPublisher().publish(scenario_ranking, store=store)
