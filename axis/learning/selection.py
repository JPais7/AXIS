"""Next-compound selection by explicit rules, never by a global acquisition score.

Each candidate may carry several explicit rationales. Dimensions stay separate and a
conflict between objectives is reported, not averaged.
"""

from typing import Any

from axis.learning.dataset import digest

RULES_VERSION = "axis-next-compound-1"
RULES: dict[str, str] = {
    "NEXT-001": "exploitation: the model predicts a value in the desired direction and the compound is inside the applicability domain.",
    "NEXT-002": "exploration: the compound lies outside the dominant scaffold group of the dataset.",
    "NEXT-003": "hypothesis_discrimination: the compound carries a transformation whose observed direction is contradicted or unreplicated, so its result separates competing SAR hypotheses.",
    "NEXT-004": "model_boundary: the compound is near the applicability boundary, so its result tests where the model stops applying.",
    "NEXT-005": "negative_control: the compound is a close analogue of a measured compound predicted weak, to confirm the lower end.",
    "NEXT-006": "replication: the compound already has contradictory measurements and needs a repeat.",
    "NEXT-007": "ties are broken by the stable compound reference, which is a display order only.",
}
CATEGORIES = (
    "exploitation",
    "exploration",
    "hypothesis_discrimination",
    "model_boundary",
    "negative_control",
    "replication",
)


def fingerprint() -> str:
    return digest({"v": RULES_VERSION, "rules": RULES})


def select(
    *,
    candidates: list[dict[str, Any]],
    dominant_scaffold: str | None,
    hypotheses: list[dict[str, Any]],
    contradictory_refs: list[str],
    capacity: int = 5,
    desired: str = "lower_value",
) -> dict[str, Any]:
    """``candidates``: {compound_ref, scaffold, prediction (or None), transformation (or None)}."""
    unresolved = {
        h["id"]
        for h in hypotheses
        if h["contradictory_observations"] or len(h["supporting_observations"]) < 2
    }
    rows = []
    for c in sorted(candidates, key=lambda x: x["compound_ref"]):
        pred = c.get("prediction")
        rationales = []
        if pred:
            status = pred["applicability"]["status"]
            better = (
                pred["predicted_value"] <= c.get("reference_value", float("inf"))
                if desired == "lower_value"
                else True
            )
            if status == "inside_domain" and better:
                rationales.append("exploitation")
            if status == "near_boundary":
                rationales.append("model_boundary")
            if c.get("analogue_of_weak"):
                rationales.append("negative_control")
        if dominant_scaffold is not None and c["scaffold"] != dominant_scaffold:
            rationales.append("exploration")
        if c.get("tests_hypotheses") and set(c["tests_hypotheses"]) & unresolved:
            rationales.append("hypothesis_discrimination")
        if c["compound_ref"] in contradictory_refs:
            rationales.append("replication")
        if rationales:
            rows.append(
                {
                    "compound_ref": c["compound_ref"],
                    "rationales": sorted(set(rationales)),
                    "prediction": pred,
                    "scaffold": c["scaffold"],
                    "hypotheses_addressed": sorted(
                        set(c.get("tests_hypotheses", [])) & unresolved
                    ),
                    "conflicts": _conflicts(rationales, pred),
                }
            )
    rows.sort(key=lambda r: (-len(r["rationales"]), r["compound_ref"]))
    chosen: list[dict[str, Any]] = []
    covered: set[str] = set()
    for r in rows:
        new = set(r["rationales"]) - covered
        if new or len(chosen) < 1:
            chosen.append(r)
            covered |= set(r["rationales"])
        if len(chosen) >= capacity:
            break
    return {
        "rules_version": RULES_VERSION,
        "rules_fingerprint": fingerprint(),
        "rules": RULES,
        "selected": chosen,
        "considered": len(candidates),
        "acquisition_score": None,
        "statement": (
            "No compound met an explicit selection rule; nothing is proposed."
            if not chosen
            else "Compounds are proposed because they reduce a stated chemical uncertainty, not because they have the highest predicted potency."
        ),
    }


def _conflicts(rationales: list[str], pred: dict[str, Any] | None) -> list[str]:
    out = []
    if "exploitation" in rationales and "model_boundary" in rationales:
        out.append(
            "exploitation and model_boundary cannot both hold; reported as stated"
        )
    if (
        pred
        and pred["applicability"]["status"] == "outside_domain"
        and "exploitation" in rationales
    ):
        out.append("predicted favourable but outside the applicability domain")
    return out
