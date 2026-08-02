import csv
import json
from pathlib import Path

import httpx

from axis.targets import CausalContextBuilder, OpenTargetsClient


def write_genetics(path: Path) -> None:
    path.write_text(
        "gene_symbol\tensembl_id\tgenetic_evidence_count\n"
        "GENE1\tENSG1\t2\n"
        "NO_SUPPORT\tENSG2\t0\n",
        encoding="utf-8",
    )


def context_handler(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {
                "target": {
                    "evidences": {
                        "count": 1,
                        "rows": [
                            {
                                "id": "e1",
                                "score": 0.8,
                                "credibleSet": {
                                    "studyLocusId": "locus1",
                                    "finemappingMethod": "PICS",
                                    "confidence": "fine-mapped",
                                    "purityMeanR2": 0.9,
                                    "beta": 0.2,
                                    "pValueMantissa": 1.0,
                                    "pValueExponent": -8,
                                    "variant": {
                                        "id": "1_100_A_G",
                                        "rsIds": ["rs1"],
                                    },
                                    "study": {
                                        "id": "study1",
                                        "traitFromSource": "AS",
                                        "nCases": 100,
                                        "nControls": 200,
                                        "nSamples": 300,
                                    },
                                    "l2GPredictions": {
                                        "count": 1,
                                        "rows": [
                                            {
                                                "score": 0.8,
                                                "target": {
                                                    "id": "ENSG1",
                                                    "approvedSymbol": "GENE1",
                                                },
                                            }
                                        ],
                                    },
                                    "colocalisation": {
                                        "count": 1,
                                        "rows": [
                                            {
                                                "h4": 0.9,
                                                "clpp": 0.1,
                                                "rightStudyType": "eqtl",
                                                "colocalisationMethod": "COLOC",
                                                "otherStudyLocus": {
                                                    "qtlGeneId": "ENSG1",
                                                    "study": {
                                                        "studyType": "eqtl",
                                                        "target": {
                                                            "id": "ENSG1",
                                                            "approvedSymbol": "GENE1",
                                                        },
                                                        "biosample": {
                                                            "biosampleId": "CL1",
                                                            "biosampleName": "T cell",
                                                        },
                                                    },
                                                },
                                            }
                                        ],
                                    },
                                },
                            }
                        ],
                    },
                    "baselineExpression": {
                        "count": 1,
                        "rows": [
                            {
                                "datasourceId": "baseline",
                                "datatypeId": "rna",
                                "tissueBiosampleFromSource": "blood",
                                "celltypeBiosampleFromSource": "T cell",
                                "median": 10.0,
                                "specificity_score": 0.5,
                                "distribution_score": 0.9,
                            }
                        ],
                    },
                }
            }
        },
    )


def test_context_reports_finemapping_colocalisation_and_expression(
    tmp_path: Path,
) -> None:
    genetics = tmp_path / "genetics.tsv"
    write_genetics(genetics)
    http = httpx.Client(transport=httpx.MockTransport(context_handler))
    client = OpenTargetsClient(
        client=http,
        endpoint="https://example.test/graphql",
    )

    result = CausalContextBuilder().build(
        genetics,
        output_root=tmp_path / "context",
        client=client,
    )

    assert result.targets == 1
    assert result.strong_locus_to_gene == 1
    assert result.molecular_colocalisation == 1
    with result.output_path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source, delimiter="\t"))
    assert row["maximum_locus_to_gene_score"] == "0.8"
    assert row["strong_colocalisation_contexts"] == "T cell"
    assert row["top_normal_expression_contexts"] == "T cell"
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "normal baseline expression" in summary["expression_scope"]
