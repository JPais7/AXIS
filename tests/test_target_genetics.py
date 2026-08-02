import csv
import json
from pathlib import Path

import httpx

from axis.targets import GeneticEvidenceBuilder, OpenTargetsClient


def write_target_table(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("gene_symbol", "ensembl_id", "resolved"))
        writer.writerow(("RISK", "ENSG1", "True"))
        writer.writerow(("PROTECT", "ENSG2", "True"))
        writer.writerow(("MISSING", "", "False"))


def genetic_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    ensembl = payload["variables"]["id"]
    direction_target = "GoF" if ensembl == "ENSG1" else "LoF"
    direction_trait = "risk" if ensembl == "ENSG1" else "protect"
    return httpx.Response(
        200,
        json={
            "data": {
                "target": {
                    "evidences": {
                        "count": 1,
                        "rows": [
                            {
                                "id": f"evidence-{ensembl}",
                                "datasourceId": "gwas_credible_sets",
                                "datatypeId": "genetic_association",
                                "score": 0.8,
                                "directionOnTarget": direction_target,
                                "directionOnTrait": direction_trait,
                                "beta": None,
                                "oddsRatio": None,
                                "variantRsId": None,
                                "studyId": None,
                                "targetFromSourceId": ensembl,
                                "diseaseFromSourceMappedId": "MONDO_0005306",
                            }
                        ],
                    }
                }
            }
        },
    )


def test_genetic_evidence_preserves_and_maps_causal_direction(
    tmp_path: Path,
) -> None:
    target_table = tmp_path / "targets.tsv"
    write_target_table(target_table)
    http = httpx.Client(transport=httpx.MockTransport(genetic_handler))
    client = OpenTargetsClient(
        client=http,
        endpoint="https://example.test/graphql",
    )

    result = GeneticEvidenceBuilder().build(
        target_table,
        output_root=tmp_path / "genetics",
        client=client,
    )

    assert result.targets == 2
    assert result.genetically_supported == 2
    assert result.direction_resolved == 2
    with result.output_path.open(encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source, delimiter="\t"))
    assert rows[0]["therapeutic_direction"] == "inhibit"
    assert rows[1]["therapeutic_direction"] == "inhibit"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["disease_id"] == "MONDO_0005306"


def test_missing_direction_stays_unknown() -> None:
    assert GeneticEvidenceBuilder._direction(None, "risk") == "unknown"
    assert GeneticEvidenceBuilder._direction("GoF", None) == "unknown"
