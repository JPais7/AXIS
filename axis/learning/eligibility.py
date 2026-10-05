"""Model eligibility: a deterministic gate that may refuse to build a model (pure).

The thresholds are AXIS policy for a held-out, scaffold-aware evaluation, not
universal statistical laws. They are data, fingerprinted, and generic: nothing here
knows a target.
"""

import hashlib
import json
from typing import Any

from axis.computational import chem

POLICY: dict[str, Any] = {
    "version": "axis-model-eligibility-1",
    "min_exact_compounds": 20,
    "min_scaffolds": 5,
    "min_compounds_per_scaffold_for_scaffold_split": 1,
    "max_censored_fraction": 0.5,
    "min_activity_range_log10": 1.0,
    "min_per_class": 5,
    "max_contradictory_fraction": 0.2,
    "max_dominant_scaffold_fraction": 0.7,
    "rationale": (
        "A regression evaluated on held-out scaffolds needs enough exact, "
        "chemically varied, mutually comparable measurements for a test partition "
        "to contain more than a handful of compounds."
    ),
}


def policy_fingerprint() -> str:
    text = json.dumps(POLICY, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def assess(dataset: dict[str, Any], *, task: str = "regression") -> dict[str, Any]:
    values = dataset["compound_values"]
    smiles = {c["compound_ref"]: c["smiles"] for c in dataset["compounds"]}
    exact = [v for v in values if v["operator"] == "=" and v["value"] is not None]
    censored = [v for v in values if v["operator"] in (">", "<", ">=", "<=")]
    contradictory = [v for v in values if v["contradictory"]]
    scaffolds: dict[str, int] = {}
    for v in exact:
        scaffolds[chem.scaffold(smiles[v["compound_ref"]])] = (
            scaffolds.get(chem.scaffold(smiles[v["compound_ref"]]), 0) + 1
        )
    nums = [v["value"] for v in exact if v["value"] and v["value"] > 0]
    import math

    rng = math.log10(max(nums) / min(nums)) if len(nums) > 1 else 0.0
    n_all = len(values)
    inchi = {
        chem.prepare_compound(
            c, smiles[c], compound_identity=None, input_stereo=None
        ).get("inchi_key")
        for c in smiles
        if chem.parse(smiles[c]) is not None
    }
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str, blocking: bool = True) -> None:
        checks.append(
            {"check": name, "passed": ok, "detail": detail, "blocking": blocking}
        )

    check("single assay context", True, "dataset is one context by construction")
    unparsed = [c for c in smiles if chem.parse(smiles[c]) is None]
    check(
        "valid structures",
        not unparsed,
        f"{len(unparsed)} compounds have an unparseable structure",
    )
    check(
        "sample size",
        len(exact) >= POLICY["min_exact_compounds"],
        f"{len(exact)} compounds with an exact value; policy minimum {POLICY['min_exact_compounds']}",
    )
    check(
        "chemical diversity",
        len(scaffolds) >= POLICY["min_scaffolds"],
        f"{len(scaffolds)} Murcko scaffolds among exact-value compounds; minimum {POLICY['min_scaffolds']}",
    )
    dominant = max(scaffolds.values()) / len(exact) if exact else 1.0
    check(
        "series concentration",
        dominant <= POLICY["max_dominant_scaffold_fraction"],
        f"largest scaffold group holds {dominant:.0%} of exact-value compounds",
        blocking=False,
    )
    cf = len(censored) / n_all if n_all else 1.0
    check(
        "censoring",
        cf <= POLICY["max_censored_fraction"],
        f"{len(censored)} of {n_all} compounds have only censored values",
    )
    check(
        "activity range",
        rng >= POLICY["min_activity_range_log10"],
        f"exact values span {rng:.2f} log10 units; minimum {POLICY['min_activity_range_log10']}",
    )
    check(
        "contradictory measurements",
        (len(contradictory) / n_all if n_all else 0)
        <= POLICY["max_contradictory_fraction"],
        f"{len(contradictory)} compounds with contradictory exact values (kept, excluded from fitting)",
        blocking=False,
    )
    check(
        "duplicate structures",
        len(inchi) == len(smiles),
        f"{len(smiles)} compound references, {len(inchi)} distinct structures",
    )
    blocking = [c for c in checks if not c["passed"] and c["blocking"]]
    soft = [c for c in checks if not c["passed"] and not c["blocking"]]
    if blocking:
        conclusion = "not_eligible"
    elif soft:
        conclusion = "eligible_with_conditions"
    else:
        conclusion = "eligible"
    if conclusion == "not_eligible":
        readiness = "SAR_ONLY" if len(values) >= 2 else "INSUFFICIENT_DATA"
        if not values:
            readiness = "INSUFFICIENT_DATA"
    elif conclusion == "eligible_with_conditions":
        readiness = "MODEL_ELIGIBLE_WITH_CONDITIONS"
    else:
        readiness = "MODEL_ELIGIBLE"
    return {
        "dataset_id": dataset["id"],
        "task": task,
        "conclusion": conclusion,
        "readiness": readiness,
        "checks": checks,
        "reasons": [f"{c['check']}: {c['detail']}" for c in blocking + soft],
        "counts": {
            "compounds": n_all,
            "exact": len(exact),
            "censored_only": len(censored),
            "contradictory": len(contradictory),
            "scaffolds": len(scaffolds),
            "activity_range_log10": round(rng, 3),
        },
        "policy": POLICY,
        "policy_fingerprint": policy_fingerprint(),
        "model_built": False,
    }
