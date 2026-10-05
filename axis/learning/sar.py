"""Observed SAR, matched molecular pairs and SAR hypotheses (pure).

* ObservedSAR traces directly to measurements in one assay context and says only what
  those measurements show ("had the lower reported value"), never why.
* SARHypothesis is an inference (`axis_inference`) with supporting and contradicting
  observations; it is not a source assertion and is born pending review.
"""

from typing import Any

from rdkit import Chem
from rdkit.Chem import rdMMPA

from axis.computational import chem
from axis.learning.dataset import digest

MMP_RULES = {
    "version": "axis-mmp-1",
    "fragmentation": "RDKit rdMMPA single cut; the larger fragment is the shared core",
    "max_changed_heavy_atoms": 13,
    "causality": "a matched pair is a local observation, never a mechanism",
}


def _fragments(smiles: str) -> list[tuple[str, str]]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []
    out = []
    for core, chains in rdMMPA.FragmentMol(mol, maxCuts=1, resultsAsMols=False):
        parts = sorted((core + "." + chains).strip(".").split("."))
        if len(parts) != 2:
            continue
        mols = [Chem.MolFromSmiles(p) for p in parts]
        if any(m is None for m in mols):
            continue
        heavy = [int(m.GetNumHeavyAtoms()) - 1 for m in mols if m is not None]
        big, small = (0, 1) if heavy[0] >= heavy[1] else (1, 0)
        limit = int(MMP_RULES["max_changed_heavy_atoms"])  # type: ignore[call-overload]
        if heavy[small] <= limit:
            out.append((parts[big], parts[small]))
    return sorted(set(out))


def matched_pairs(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    smiles = {c["compound_ref"]: c["smiles"] for c in dataset["compounds"]}
    values = {v["compound_ref"]: v for v in dataset["compound_values"]}
    by_core: dict[str, list[tuple[str, str]]] = {}
    for ref in sorted(smiles):
        if ref not in values:
            continue
        for core, changed in _fragments(smiles[ref]):
            by_core.setdefault(core, []).append((ref, changed))
    seen: set[tuple[str, str]] = set()
    pairs = []
    for core, members in sorted(by_core.items()):
        for i, (a, fa) in enumerate(members):
            for b, fb in members[i + 1 :]:
                if a == b or fa == fb or (a, b) in seen:
                    continue
                seen.add((a, b))
                va, vb = values[a], values[b]
                exact = (
                    va["operator"] == "="
                    and vb["operator"] == "="
                    and va["value"]
                    and vb["value"]
                )
                change = (
                    {
                        "direction": _direction(va["value"], vb["value"]),
                        "log10_ratio_b_over_a": _log_ratio(va["value"], vb["value"]),
                    }
                    if exact
                    else {
                        "direction": "not_quantifiable",
                        "reason": "at least one value is censored, contradictory or missing",
                    }
                )
                pairs.append(
                    {
                        "id": f"pair:{dataset['id']}:{a}:{b}",
                        "kind": "matched_molecular_pair",
                        "epistemic_class": "axis_observation",
                        "compound_a": a,
                        "compound_b": b,
                        "shared_core": core,
                        "transformation": f"{fa} >> {fb}",
                        "assay_context": dataset["assay_context"],
                        "measurement_a": _ref(va),
                        "measurement_b": _ref(vb),
                        "activity_change": change,
                        "statement": _statement(a, b, fa, fb, change, dataset),
                        "comparability": "directly_comparable (same dataset context)",
                        "rules": MMP_RULES,
                        "limitations": [
                            "local observation; no causal claim",
                            "values are as reported, including their assay-specific context",
                        ],
                    }
                )
    return pairs


def _ref(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": v["value"],
        "operator": v["operator"],
        "n_measurements": v["n_measurements"],
        "sources": v["sources"],
        "contradictory": v["contradictory"],
    }


def _direction(a: float, b: float) -> str:
    return "lower_in_b" if b < a else "higher_in_b" if b > a else "equal"


def _log_ratio(a: float, b: float) -> float:
    import math

    return round(math.log10(b / a), 3)


def _statement(
    a: str, b: str, fa: str, fb: str, change: dict[str, Any], ds: dict[str, Any]
) -> str:
    ctx = ds["assay_context"]
    where = f"{ctx['endpoint']} ({ctx['target']}, {ctx.get('substrate') or 'substrate unspecified'})"
    if change["direction"] == "not_quantifiable":
        return f"{a} and {b} differ by {fa} versus {fb}; a difference in {where} cannot be quantified from the reported values."
    word = {"lower_in_b": "lower", "higher_in_b": "higher", "equal": "equal"}[
        change["direction"]
    ]
    return (
        f"Within the compounds measured in {where}, {b} (…{fb}) had a {word} reported "
        f"value than {a} (…{fa}). This is an observation about these two compounds, not a mechanism."
    )


def scaffold_groups(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """Algorithmic scaffold groups; not curated medicinal-chemistry series."""
    smiles = {c["compound_ref"]: c["smiles"] for c in dataset["compounds"]}
    groups: dict[str, list[str]] = {}
    for ref in sorted(smiles):
        groups.setdefault(chem.scaffold(smiles[ref]), []).append(ref)
    values = {v["compound_ref"]: v for v in dataset["compound_values"]}
    out = []
    for scaffold, members in sorted(groups.items()):
        out.append(
            {
                "id": f"scaffold:{dataset['id']}:{digest(scaffold)[:10]}",
                "kind": "algorithmic_scaffold_group",
                "epistemic_class": "axis_observation",
                "scaffold": scaffold,
                "definition": "Bemis-Murcko (RDKit); not a curated chemical series",
                "members": members,
                "measured_members": [m for m in members if m in values],
                "assay_context": dataset["assay_context"],
            }
        )
    return out


def hypotheses(
    dataset: dict[str, Any], pairs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """SAR hypotheses from repeated transformations: inference, pending review."""
    by_transformation: dict[str, list[dict[str, Any]]] = {}
    for p in pairs:
        if p["activity_change"]["direction"] in ("lower_in_b", "higher_in_b"):
            by_transformation.setdefault(p["transformation"], []).append(p)
    out = []
    for transformation, items in sorted(by_transformation.items()):
        directions = [i["activity_change"]["direction"] for i in items]
        support = [
            i["id"] for i in items if i["activity_change"]["direction"] == directions[0]
        ]
        against = [
            i["id"] for i in items if i["activity_change"]["direction"] != directions[0]
        ]
        if len(items) < 2:
            scope = "single matched pair: too little to propose a SAR hypothesis"
            continue
        word = "lower" if directions[0] == "lower_in_b" else "higher"
        out.append(
            {
                "id": f"sar-hypothesis:{dataset['id']}:{digest(transformation)[:10]}",
                "epistemic_class": "axis_inference",
                "epistemic_status": "axis_inference",
                "statement": (
                    f"The transformation {transformation} may be associated with a {word} "
                    f"{dataset['endpoint']} in this series and assay context."
                ),
                "scope": f"{dataset['target']}; {dataset['assay_context'].get('substrate')}; compounds sharing the observed cores",
                "supporting_observations": support,
                "contradictory_observations": against,
                "missing_evidence": [
                    "measurements in a second assay context",
                    "an independent series carrying the same change",
                ],
                "falsification": "a matched pair of this transformation with the opposite direction in the same assay",
                "review_state": "pending_review",
                "causality": "association within matched pairs; not a mechanism",
                "scope_note": scope if len(items) < 2 else "",
            }
        )
    return out
