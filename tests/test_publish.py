import csv
import json
from pathlib import Path

from axis.analysis import RankingPublisher
from axis.domain import KnowledgeKind
from axis.storage import EvidenceStore


def write_ranking(root: Path) -> Path:
    path = root / "recurrence-ranking.tsv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=(
                "gene_symbol",
                "combined_adjusted_p_value",
                "recurrent",
            ),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "gene_symbol": "IL17A",
                "combined_adjusted_p_value": "0.01",
                "recurrent": "True",
            }
        )
        writer.writerow(
            {
                "gene_symbol": "PITX2",
                "combined_adjusted_p_value": "0.02",
                "recurrent": "False",
            }
        )
    (root / "recurrence-analysis.json").write_text(
        json.dumps(
            {
                "studies": ["GSE1", "GSE2"],
                "minimum_recurrent_studies": 2,
                "alpha": 0.05,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_publisher_creates_only_recurrent_immutable_claims(
    tmp_path: Path,
) -> None:
    ranking = write_ranking(tmp_path)

    with EvidenceStore() as store:
        result = RankingPublisher().publish(ranking, store=store)
        repeated = RankingPublisher().publish(ranking, store=store)
        claim = store.claims.get(result.claim_ids[0])

        assert result.recurrent_rows == 1
        assert result.claims_added == 1
        assert repeated.claim_ids == result.claim_ids
        assert store.statistics().claims == 1
        assert claim.subject.identifier == "IL17A"
        assert claim.knowledge_kind is KnowledgeKind.AXIS_INFERENCE
        assert claim.confidence == 0.99
        assert claim.provenance.transformations[0].parameters[0] == (
            "studies",
            "GSE1|GSE2",
        )


def test_publisher_creates_no_claims_without_recurrence(tmp_path: Path) -> None:
    ranking = write_ranking(tmp_path)
    content = ranking.read_text(encoding="utf-8").replace("True", "False")
    ranking.write_text(content, encoding="utf-8")

    with EvidenceStore() as store:
        result = RankingPublisher().publish(ranking, store=store)

        assert result.claims_added == 0
        assert store.statistics().claims == 0
