"""Build the frozen ERAP1 x axSpA retrospective benchmark package.

Reads the *current* curated evidence once, attributes every record to its source,
and partitions it by the real first-public-accessibility dates in
``temporal-availability.json``. Nothing is invented: a record whose source has no
date is never placed in a window.

    poetry run python scripts/build_retrospective_erap1.py
"""

import json
import sys
import tempfile
from pathlib import Path

from axis.cellular.service import CellularPharmacologyService
from axis.decision import rules
from axis.decision.evidence import load_records
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService
from axis.validation.package import build_set

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
OUT = Path(__file__).resolve().parents[1] / (
    "axis/resources/benchmarks/retrospective/erap1-axspa/v1"
)
MABEN = "PMID:31841350"
DIMENSIONS = [
    "temporal_integrity",
    "decision_validity_at_cutoff",
    "uncertainty_calibration",
    "recommendation_relevance",
    "future_evidence_relevance",
    "evidence_update_behavior",
    "overstated_claims",
    "baseline_comparison",
]
EXPECTATION = (
    "No outcome is predicted. The decision at the cutoff is recorded first; the case "
    "is then assessed on each dimension separately. A case in which the future "
    "evidence did not test the decision is a valid, non-failing outcome."
)
BIAS = (
    "These cases were chosen by the developers, who had read the later literature; "
    "ERAP1 x axSpA is also the dataset the decision rules were developed on, so every "
    "case here is a DEVELOPMENT benchmark, not an independent validation. The three "
    "cutoffs were fixed by publication chronology (before the first cellular study, "
    "after it, after the second wave) rather than chosen to produce an outcome, but "
    "the set is small and not a sample of any population of decisions."
)
CASES = [
    {
        "case_id": "erap1-axspa-t2011",
        "cutoff_id": "T-2011-12-31",
        "cutoff": "2011-12-31",
        "cutoff_rationale": (
            "After the open-state ERAP1 structure (PDB 3QNF, released 2011-02-23) and "
            "before the first cellular perturbation study (PMID 24504800, first listed "
            "2014-02-08): structure only, no cellular or chemical evidence."
        ),
        "case_type": "sparse_evidence_edge_case",
        "question": (
            "With only structural evidence accessible, does AXIS refrain from "
            "asserting cellular or chemical conclusions, and is what later arrives "
            "relevant?"
        ),
        "selection_rationale": (
            "Boundary case: tests behaviour on an almost empty evidence window."
        ),
    },
    {
        "case_id": "erap1-axspa-t2014",
        "cutoff_id": "T-2014-12-31",
        "cutoff": "2014-12-31",
        "cutoff_rationale": (
            "After the first ERAP1 peptidome/variant study (PMID 24504800) and before "
            "the knockdown/inhibitor co-culture study (PMID 26130142, first listed "
            "2015-07-02, nominal year 2016) and the dimer study (PMID 27107845, "
            "2016-04-25)."
        ),
        "case_type": "early_mechanistic_evidence",
        "question": (
            "Given the first mechanistic study only, what does AXIS state as the "
            "critical uncertainty and next experiment, and did later cellular "
            "evidence test it?"
        ),
        "selection_rationale": "First step of the real chronology.",
    },
    {
        "case_id": "erap1-axspa-t2016",
        "cutoff_id": "T-2016-12-31",
        "cutoff": "2016-12-31",
        "cutoff_rationale": (
            "After all cellular studies in the benchmark and before the first "
            "chemical-series paper (PMID 31841350, first listed 2019-12-17). The "
            "window is identical for any cutoff up to 2019-12-16."
        ),
        "case_type": "cellular_evidence_then_chemistry",
        "question": (
            "Given the cellular evidence only, does the later biochemical/selectivity "
            "evidence test AXIS's critical uncertainty?"
        ),
        "selection_rationale": (
            "Second step of the real chronology; the largest window."
        ),
    },
]
for case in CASES:
    case["dimensions"] = DIMENSIONS
    case["expectation"] = EXPECTATION


def source_map(records: dict, claim_sources: dict[str, str]) -> dict[str, str]:
    exp_source = {e["id"]: e["source_id"] for e in records["experiments"]}
    mapping: dict[str, str] = {}
    for e in records["experiments"]:
        mapping[f"experiments:{e['id']}"] = e["source_id"]
    for a in records["assessments"]:
        mapping[f"assessments:{a['id']}"] = exp_source[a["experiment_id"]]
    for r in records["readouts"]:
        mapping[f"readouts:{r['id']}"] = exp_source[r["experiment_id"]]
    for g in records["gaps"]:
        mapping[f"gaps:{g['id']}"] = exp_source[g["id"].removesuffix(":gap")]
    for kind in ("biochemical_measurements", "selectivity"):
        for r in records[kind]:
            mapping[f"{kind}:{r['id']}"] = MABEN
    for c in records["compounds"]:
        mapping[f"compounds:{c}"] = MABEN
    return mapping


def main() -> None:
    db = Path(tempfile.mkdtemp()) / "build.duckdb"
    with EvidenceStore(db) as store:
        import_curated_erap1(store)
        protein = TargetIdentityService(store).import_package(PROJECT)
        StructureIdentityService(store).import_package(PROJECT, protein)
        PharmacologyService(store).import_package(PROJECT, protein)
        CellularPharmacologyService(store).import_package(PROJECT, protein)
        decision = DecisionService(store)
        decision.import_package(PROJECT, protein)
        records = load_records(store, PROJECT, protein)
        inputs = decision.inputs(PROJECT, protein)
    records = json.loads(json.dumps(records, default=str))
    mapping = source_map(records, {})
    mapping.update({f"structure_ids:{s}": "PDB:3QNF" for s in records["structure_ids"]})
    # Project scaffolding (strategy ids) is design-time context, not literature
    # evidence; it is kept in every window and disclosed in the audit document.
    availability = json.loads((OUT / "temporal-availability.json").read_text())
    template = {k: inputs[k] for k in ("explanations", "candidates", "hypothesis")}
    template["candidates"] = [
        {**c, "status": "proposed", "result_claim_id": None}
        for c in template["candidates"]
    ]
    build_set(
        OUT,
        set_id="erap1-axspa",
        title="ERAP1 x axial spondyloarthritis — temporal backtest (development)",
        kind="development",
        synthetic=False,
        records=records,
        record_sources=mapping,
        availability_doc=availability,
        template=template,
        redactions=[
            {
                "token": "the DG013A label",
                "replacement": "the perturbagen label",
                "reason": (
                    "DG013A is first reported in the benchmark by a later study; the "
                    "name must not appear in a window that predates it."
                ),
            }
        ],
        cases=CASES,
        rules_version=rules.RULES_VERSION,
        rules_fingerprint=rules.fingerprint(),
        selection_bias_note=BIAS,
        forbidden_tokens={
            "PMID:31841350": [
                "Maben",
                "maben",
                "compound:maben",
                "10.1021/acs.jmedchem.9b00293",
            ],
            "PMID:26130142": [
                "DG013A",
                "chen-dg013a",
                "chen-knockdown",
                "chen-coculture",
            ],
            "PMID:27107845": ["tran-dimer", "tran-fhc"],
            "PMID:24504800": ["chen2014"],
            "PDB:3QNF": ["3QNF"],
        },
    )
    print(f"built {OUT}")


if __name__ == "__main__":
    sys.exit(main())
