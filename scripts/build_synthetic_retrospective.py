"""Build the SYNTHETIC / TEST ONLY generic retrospective benchmark.

Every source, date, compound and result here is invented to exercise the
validation machinery on a target that is not ERAP1. Nothing is scientific
evidence. The decision template is derived from the ERAP1 template by mapping its
names to synthetic ones; that mapping is the only place real names appear.

    poetry run python scripts/build_synthetic_retrospective.py
"""

import json
from pathlib import Path
from typing import Any

from axis.decision import rules
from axis.validation.package import build_set

OUT = Path(__file__).resolve().parents[1] / (
    "axis/resources/benchmarks/retrospective/synthetic-generic/v1"
)
ERAP1 = Path(__file__).resolve().parents[1] / (
    "axis/resources/benchmarks/retrospective/erap1-axspa/v1"
)
NAMES = {
    "ERAP1": "SYN-TARGET-A",
    "HLA-B27": "SYN-CONTEXT-B",
    "axial spondyloarthritis": "synthetic disease C",
    "axSpA": "SYN-DISEASE-C",
    "the perturbagen label": "the perturbagen label",
}
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
LABEL = "SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE"


def experiment(
    eid: str,
    source: str,
    modality: str,
    *,
    compound: str | None = None,
    perturbagen: str | None = None,
    allele: str | None = "SYN-ALLELE-1",
) -> dict[str, Any]:
    return {
        "id": eid,
        "source_id": source,
        "label": f"{LABEL}: {eid}",
        "modality": modality,
        "compound_id": compound,
        "reported_perturbagen": perturbagen,
        "context": {
            "cell_line": "SYN-CELLS",
            "hla_allele": allele,
            "erap1_allotype": None,
            "disease_status": LABEL,
            "scientific_context": {
                "allotype": None,
                "assay": "SYN-ASSAY",
                "cell_type": "SYN-CELLS",
                "comparison": None,
                "endpoint": "SYN-ENDPOINT",
                "experimental_system": "SYN-CELLS",
                "genotype": None,
                "hla_status": "SYN-CONTEXT expressed",
                "population": None,
                "species": "synthetic",
                "tissue": None,
                "treatment": None,
            },
        },
        "controls": [],
        "perturbation_id": f"syn:pert:{eid}",
        "concentration": None,
        "dosing_schedule": None,
        "duration": None,
        "vehicle": None,
        "locator": LABEL,
        "limitation": LABEL,
    }


def assess(
    eid: str, edge: str, state: str, dependency: str = "not_assessed"
) -> dict[str, Any]:
    return {
        "id": f"{eid}:{edge}",
        "experiment_id": eid,
        "edge": edge,
        "state": state,
        "dependency": dependency,
        "directness": "not_assessed",
        "disease_relevance": "unknown",
        "rationale": LABEL,
        "review_status": "pending_expert_review",
        "rule_version": "synthetic",
        "created_by": LABEL,
        "supporting_readout_ids": [],
        "contradicting_readout_ids": [],
    }


def readout(eid: str, direction: str) -> dict[str, Any]:
    return {
        "id": f"{eid}:readout",
        "experiment_id": eid,
        "endpoint": "SYN-ENDPOINT",
        "direction": direction,
        "claim_id": f"syn:claim:{eid}",
        "locator": LABEL,
        "measurement_id": None,
        "original_unit": None,
        "original_value": None,
        "proximity": "HLA_molecular",
        "qualitative_result": LABEL,
        "replicate_information": LABEL,
        "statistical_result": LABEL,
    }


def gap(eid: str, compound: str | None) -> dict[str, Any]:
    return {
        "id": f"{eid}:gap",
        "edge": "engagement",
        "compound_id": compound,
        "claim_ids": [],
        "perturbation_id": f"syn:pert:{eid}",
        "proposal_title": LABEL,
        "question": LABEL,
    }


SOURCES: dict[str, tuple[str, str]] = {
    "SYN:S1": ("2018-03-01", "bounded"),
    "SYN:S2": ("2019-09-01", "bounded"),
    "SYN:S3": ("2020-06-01", "bounded"),
    "SYN:S4": ("2021-01-15", "bounded"),
    "SYN:S5": ("2021-09-01", "bounded"),
    "SYN:S6": ("", "unknown"),
    "SYN:S7": ("2019-03-01", "bounded"),
}


def availability() -> dict[str, Any]:
    sources = {}
    for key, (day, kind) in SOURCES.items():
        sources[key] = {
            "title": f"{LABEL} — invented source {key}",
            "nominal_publication_date": day or "unknown",
            "first_publicly_accessible_date": day or None,
            "availability_kind": kind,
            "availability_basis": LABEL,
        }
    return {"resource": "temporal-availability", "note": LABEL, "sources": sources}


def records() -> tuple[dict[str, Any], dict[str, str]]:
    exps = [
        experiment("syn:e1-genetic", "SYN:S1", "knockdown"),
        experiment(
            "syn:e2-compound", "SYN:S1", "small_molecule", compound="syn:cmpd-1"
        ),
        # S2: positive engagement for the compound
        experiment(
            "syn:e3-engagement", "SYN:S2", "small_molecule", compound="syn:cmpd-1"
        ),
        # S3: engagement negative for a second compound (weakening)
        experiment(
            "syn:e4-negative", "SYN:S3", "small_molecule", compound="syn:cmpd-2"
        ),
        # S4: irrelevant to the decision (different edge, no new information)
        experiment("syn:e5-irrelevant", "SYN:S4", "other"),
        # S5: non-interpretable
        experiment("syn:e6-noninterp", "SYN:S5", "other"),
        # S7: a negative engagement result for the same compound as S2
        experiment(
            "syn:e8-conflict", "SYN:S7", "small_molecule", compound="syn:cmpd-1"
        ),
        # S6: availability unknown: must never enter any window
        experiment("syn:e7-unknown", "SYN:S6", "knockdown"),
    ]
    assessments = [
        assess("syn:e1-genetic", "hla", "supported", "supported"),
        assess("syn:e1-genetic", "immune", "supported", "supported"),
        assess("syn:e2-compound", "exposure", "supported"),
        assess("syn:e2-compound", "hla", "supported", "uncertain"),
        assess("syn:e2-compound", "engagement", "not_assessed"),
        assess("syn:e3-engagement", "engagement", "supported"),
        assess("syn:e4-negative", "engagement", "contradicted"),
        assess("syn:e5-irrelevant", "clinical", "not_assessed"),
        assess("syn:e8-conflict", "engagement", "contradicted"),
        assess("syn:e7-unknown", "hla", "contradicted", "contradicted"),
    ]
    mapping: dict[str, str] = {}
    exp_source = {e["id"]: e["source_id"] for e in exps}
    for e in exps:
        mapping[f"experiments:{e['id']}"] = e["source_id"]
    for a in assessments:
        mapping[f"assessments:{a['id']}"] = exp_source[a["experiment_id"]]
    readouts = [
        readout("syn:e1-genetic", "decrease"),
        readout("syn:e2-compound", "decrease"),
    ]
    for r in readouts:
        mapping[f"readouts:{r['id']}"] = exp_source[r["experiment_id"]]
    measurements = [
        {
            "id": "measurement:syn:1",
            "compound_id": "syn:cmpd-1",
            "endpoint": "SYN-IC50",
            "source_snapshot_id": "syn:snapshot",
        }
    ]
    mapping["biochemical_measurements:measurement:syn:1"] = "SYN:S1"
    mapping["compounds:syn:cmpd-1"] = "SYN:S1"
    gaps = [gap("syn:e2-compound", "syn:cmpd-1")]
    for g in gaps:
        mapping[f"gaps:{g['id']}"] = "SYN:S1"
    return (
        {
            "target_label": "SYN-TARGET-A",
            "experiments": exps,
            "assessments": assessments,
            "readouts": readouts,
            "biochemical_measurements": measurements,
            "selectivity": [],
            "compounds": ["syn:cmpd-1"],
            "gaps": gaps,
            "structure_ids": [],
            "strategy_ids": [],
        },
        mapping,
    )


def case(
    cid: str,
    cutoff: str,
    case_type: str,
    question: str,
    why: str,
    horizon: str,
    exclude: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "horizon": horizon,
        "excluded_sources": exclude or [],
        "case_id": cid,
        "cutoff_id": f"T-{cutoff}",
        "cutoff": cutoff,
        "cutoff_rationale": f"{LABEL}: invented cutoff",
        "case_type": case_type,
        "question": question,
        "selection_rationale": why,
        "dimensions": DIMENSIONS,
        "expectation": "No outcome predicted; each dimension is assessed separately.",
        "label": LABEL,
    }


def main() -> None:
    recs, mapping = records()
    template = json.loads(
        json.dumps(
            json.loads((ERAP1 / "decision-template.json").read_text())["template"]
        )
    )
    text = json.dumps(template)
    for old, new in NAMES.items():
        text = text.replace(old, new)
    template = json.loads(text)
    cases = [
        case(
            "syn-generic-positive",
            "2019-01-01",
            "synthetic_generic_positive_path",
            "Does later engagement evidence for the compound test the stated question?",
            "Synthetic: compound active biochemically and in cells, engagement open.",
            horizon="2019-12-31",
            exclude=["SYN:S7", "SYN:S3"],
        ),
        case(
            "syn-generic-negative",
            "2019-01-01",
            "synthetic_generic_negative_future",
            "Does a later negative engagement result weaken the decision?",
            "Synthetic: same window; the only later source is a negative result.",
            horizon="2019-04-30",
            exclude=["SYN:S2", "SYN:S3"],
        ),
        case(
            "syn-generic-ambiguous",
            "2019-01-01",
            "synthetic_generic_mixed_future",
            "Do mixed later results settle the question?",
            "Synthetic: the same window as the positive case with a longer horizon.",
            horizon="2020-12-31",
        ),
        case(
            "syn-generic-irrelevant",
            "2020-12-31",
            "synthetic_generic_irrelevant_and_noninterpretable",
            "Do irrelevant and non-interpretable later sources change the conclusion?",
            "Synthetic: later evidence is irrelevant or non-interpretable.",
            horizon="2021-12-31",
        ),
        case(
            "syn-generic-undated",
            "2019-12-31",
            "synthetic_generic_unknown_availability",
            "Is evidence of unknown availability kept out of window and future?",
            "Synthetic: an undated source must never enter either set.",
            horizon="2099-12-31",
        ),
    ]
    build_set(
        OUT,
        set_id="synthetic-generic",
        title=f"{LABEL} — generic non-ERAP1 acceptance fixtures",
        kind="synthetic_test",
        synthetic=True,
        records=recs,
        record_sources=mapping,
        availability_doc=availability(),
        template=template,
        redactions=[],
        cases=cases,
        rules_version=rules.RULES_VERSION,
        rules_fingerprint=rules.fingerprint(),
        selection_bias_note=f"{LABEL}. Fixtures were constructed to exercise the "
        "machinery; they are not a sample of anything.",
        forbidden_tokens={
            "SYN:S2": ["syn:e3"],
            "SYN:S3": ["syn:e4", "syn:cmpd-2"],
            "SYN:S4": ["syn:e5"],
            "SYN:S5": ["syn:e6"],
            "SYN:S7": ["syn:e8"],
            "SYN:S6": ["syn:e7"],
        },
    )
    print(f"built {OUT}")


if __name__ == "__main__":
    main()
