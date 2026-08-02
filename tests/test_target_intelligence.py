import csv
import json
from pathlib import Path

import httpx

from axis.targets import OpenTargetsClient, TargetIntelligenceBuilder


def handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    if "ResolveTarget" in payload["query"]:
        return httpx.Response(
            200,
            json={
                "data": {
                    "search": {
                        "hits": [
                            {
                                "id": "ENSG1",
                                "entity": "target",
                                "name": "GENE1",
                                "description": "test target",
                            }
                        ]
                    }
                }
            },
        )
    return httpx.Response(
        200,
        json={
            "data": {
                "target": {
                    "id": "ENSG1",
                    "approvedSymbol": "GENE1",
                    "approvedName": "test target",
                    "biotype": "protein_coding",
                    "tractability": [
                        {
                            "label": "High-Quality Ligand",
                            "modality": "SM",
                            "value": True,
                        }
                    ],
                    "prioritisation": {
                        "items": [{"key": "geneEssentiality", "value": "0"}]
                    },
                    "safetyLiabilities": [],
                    "drugAndClinicalCandidates": {
                        "count": 1,
                        "rows": [
                            {
                                "id": "x",
                                "maxClinicalStage": "Phase 2",
                                "drug": {
                                    "id": "CHEMBL1",
                                    "name": "Drug",
                                    "drugType": "Small molecule",
                                    "maximumClinicalStage": "Phase 2",
                                },
                                "diseases": [],
                            }
                        ],
                    },
                    "associatedDiseases": {
                        "rows": [
                            {
                                "disease": {
                                    "id": "MONDO1",
                                    "name": "ankylosing spondylitis",
                                },
                                "score": 0.5,
                                "datatypeScores": [],
                            }
                        ]
                    },
                }
            }
        },
    )


def test_target_intelligence_caches_and_keeps_dimensions_separate(
    tmp_path: Path,
) -> None:
    calls = 0

    def counting_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(counting_handler))
    client = OpenTargetsClient(
        client=http,
        endpoint="https://example.test/graphql",
    )
    builder = TargetIntelligenceBuilder()

    result = builder.build(["GENE1"], output_root=tmp_path, client=client)
    cached = builder.build(["GENE1"], output_root=tmp_path, client=client)

    assert calls == 2
    assert result.resolved_targets == 1
    assert cached.resolved_targets == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert row["ensembl_id"] == "ENSG1"
    assert row["axspa_associations"] == "1"
    assert row["tractability_modalities"] == "SM"
    assert row["clinical_candidates"] == "1"
    assert row["maximum_clinical_stage"] == "PHASE_2"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "no aggregate target score" in summary["scoring_policy"]


def test_shortlist_gene_reader_preserves_rank_order(tmp_path: Path) -> None:
    path = tmp_path / "shortlist.tsv"
    path.write_text(
        "shortlist_rank\tgene_symbol\n1\tA\n2\tB\n3\tC\n",
        encoding="utf-8",
    )

    genes = TargetIntelligenceBuilder.genes_from_shortlist(path, limit=2)

    assert genes == ("A", "B")


def test_clinical_stage_order_places_approval_above_unknown() -> None:
    assert (
        TargetIntelligenceBuilder._maximum_stage(["UNKNOWN", "PHASE_3", "APPROVAL"])
        == "APPROVAL"
    )
