"""Open-future adapter for the existing temporal validation machinery.

No network, clock, database writes or scientific approval. T0 is a checksummed
resource; reveals return append-only, review-gated proposals, never mutate it.
The ordinary compound-level DecisionState is referenced, not overwritten.
"""

import json
from copy import deepcopy
from datetime import date, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.decision import rules
from axis.domain.models import KnowledgeKind
from axis.validation import core, temporal
from axis.validation.package import PackageError, sha256_file

SCHEMA = "axis-prospective-freeze-1"
ADAPTER_VERSION = "open-future-adapter-1"


def fingerprint() -> str:
    return temporal.digest(
        {
            "version": ADAPTER_VERSION,
            "implementation": sha256_file(Path(__file__)),
            "decision_rules": rules.fingerprint(),
        }
    )


def registry_root() -> Path:
    return Path(str(resources.files("axis"))) / "resources/validation/prospective"


def load(path: Path) -> dict[str, Any]:
    """Fail closed on changed files, dates, intervention or epistemic provenance."""
    manifest_path = path / "manifest.json"
    if sha256_file(manifest_path) != (path / "manifest.sha256").read_text().strip():
        raise PackageError("prospective manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text())
    if manifest["schema"] != SCHEMA:
        raise PackageError("unsupported prospective schema")
    documents: dict[str, Any] = {}
    for name, checksum in manifest["files"].items():
        target = (path / name).resolve()
        if not target.is_relative_to(path.resolve()):
            raise PackageError("resource path escapes package")
        if sha256_file(target) != checksum:
            raise PackageError(f"prospective resource changed: {name}")
        if name.endswith(".json"):
            documents[name] = json.loads(target.read_text())
    bundle = {"manifest": manifest, **documents}
    validate(bundle)
    return bundle


def validate(bundle: dict[str, Any]) -> None:
    case = bundle["case.json"]
    if case["review_status"] != "pending_review":
        raise PackageError("T0 requires independent scientific review")
    cutoff = date.fromisoformat(case["cutoff"])
    frozen = datetime.fromisoformat(case["frozen_at"])
    if frozen.utcoffset() is None or frozen.date() != cutoff:
        raise PackageError("freeze must be timezone-aware and on cutoff day")
    sources = {s["id"]: s for s in bundle["source-index.json"]["sources"]}
    for source in sources.values():
        public = source.get("available_by")
        if not public or date.fromisoformat(public) > cutoff:
            raise PackageError("undated or post-cutoff T0 source")
        retrieved = datetime.fromisoformat(source["retrieved_at"])
        if retrieved.utcoffset() is None or retrieved > frozen:
            raise PackageError("source retrieved after freeze")
    claims = bundle["evidence-snapshot.json"]["claims"]
    claim_ids = {c["id"] for c in claims}
    for claim in claims:
        if claim["source_id"] not in sources:
            raise PackageError("claim has no frozen source")
        source = sources[claim["source_id"]]
        if claim["evidence_class"] != source["evidence_class"]:
            raise PackageError("evidence class upgraded or changed")
        if claim["knowledge_kind"] != KnowledgeKind.SOURCE_ASSERTION:
            raise PackageError("reported source claim promoted to result")
        if claim["review_status"] != "pending_review":
            raise PackageError("new curation cannot approve itself")
        if claim.get("intervention") not in (None, case["intervention"]):
            raise PackageError("evidence cannot transfer between interventions")
    for position in bundle["evidence-snapshot.json"]["positions"]:
        if not position["claim_ids"] or not set(position["claim_ids"]) <= claim_ids:
            raise PackageError("scientific position has no supporting claims")
        if position["knowledge_kind"] != KnowledgeKind.AXIS_INFERENCE:
            raise PackageError("scientific synthesis must remain inference")
        if position["review_status"] != "pending_review":
            raise PackageError("scientific synthesis cannot approve itself")
    uncertainties = {u["id"] for u in case["uncertainties"]}
    hypotheses = {h["id"] for h in case["hypotheses"]}
    scientific_rows = (
        case["hypotheses"]
        + case["uncertainties"]
        + bundle["prospective-discriminators.json"]["items"]
        + bundle["outcome-scenarios.json"]["items"]
    )
    if any(row["review_status"] != "pending_review" for row in scientific_rows):
        raise PackageError("new scientific content cannot self-approve")
    for row in bundle["prospective-discriminators.json"]["items"]:
        if not set(row["uncertainty_ids"]) <= uncertainties:
            raise PackageError("discriminator references unknown uncertainty")
        if not set(row["hypothesis_ids"]) <= hypotheses:
            raise PackageError("discriminator references unknown explanation")
        for key in (
            "measurement",
            "strengthens",
            "weakens",
            "ambiguous",
            "non_interpretable",
            "consequences",
        ):
            if not row.get(key):
                raise PackageError(f"discriminator missing {key}")
    for row in bundle["outcome-scenarios.json"]["items"]:
        if (
            not row["uncertainty_ids"]
            or not set(row["uncertainty_ids"]) <= uncertainties
        ):
            raise PackageError("scenario missing uncertainty mapping")
        if not row["consequence"]:
            raise PackageError("scenario missing consequence")
    if case["rules_fingerprint"] != rules.fingerprint():
        raise PackageError("decision rules changed: replay pinned software")
    if case["adapter_fingerprint"] != fingerprint():
        raise PackageError("adapter changed: replay pinned software")


def replay(bundle: dict[str, Any]) -> dict[str, Any]:
    validate(bundle)
    case = bundle["case.json"]
    state = {
        "case_id": case["case_id"],
        "cutoff": case["cutoff"],
        "review_status": "pending_review",
        "edges": {
            p["id"]: p["status"] for p in bundle["evidence-snapshot.json"]["positions"]
        },
        "explanations": {h["id"]: "unresolved" for h in case["hypotheses"]},
        "uncertainties": {
            u["id"]: {"category": u["category"], "status": "open"}
            for u in case["uncertainties"]
        },
        "critical_uncertainty_id": case["critical_uncertainty_id"],
        "recommended_experiment_id": None,
        "canonical_decision_reference": deepcopy(case["canonical_decision"]),
        "rules_fingerprint": case["rules_fingerprint"],
        "adapter_fingerprint": case["adapter_fingerprint"],
        "trace": {
            p["id"]: p["claim_ids"]
            for p in bundle["evidence-snapshot.json"]["positions"]
        },
    }
    state["fingerprint"] = temporal.digest(state)
    return state


def reveal(
    bundle: dict[str, Any],
    evidence: dict[str, Any],
    previous: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Record a partial reveal and causal proposal, not an approved DecisionState.

    Caller supplies verified source metadata and a review-gated interpretation.
    This function cannot verify public authenticity or adjudicate a paper. Its
    output must be retained as a new artifact through the existing results loop;
    it neither persists results nor marks scientific review accepted.
    """
    t0 = replay(bundle)
    chain = deepcopy(previous or [])
    parent = t0["fingerprint"]
    state = deepcopy(t0)
    for item in chain:
        body = {k: v for k, v in item.items() if k != "fingerprint"}
        if item["parent_fingerprint"] != parent or item[
            "fingerprint"
        ] != temporal.digest(body):
            raise PackageError("invalid reveal chain")
        if item["t0_fingerprint"] != t0["fingerprint"]:
            raise PackageError("reveal belongs to another freeze")
        state = deepcopy(item["proposed_case_state"])
        parent = item["fingerprint"]
    case = bundle["case.json"]
    public = date.fromisoformat(evidence["first_public_date"])
    if public <= date.fromisoformat(case["cutoff"]):
        raise PackageError("not future evidence; never backfill T0")
    if chain and public < date.fromisoformat(
        chain[-1]["evidence"]["first_public_date"]
    ):
        raise PackageError("reveal sequence must follow actual public release order")
    if evidence["intervention"] != case["intervention"]:
        raise PackageError("future evidence concerns another compound")
    if evidence["knowledge_kind"] not in (
        KnowledgeKind.SOURCE_ASSERTION,
        KnowledgeKind.EXPERIMENTAL_RESULT,
    ):
        raise PackageError("future observation must retain its epistemic kind")
    if evidence["review_status"] != "pending_review":
        raise PackageError("adapter cannot approve scientific curation")
    if evidence["evidence_class"] not in (
        "peer_reviewed_primary",
        "conference_evidence",
        "trial_registry",
        "sponsor_reported",
        "database_record",
        "experimental_result",
    ):
        raise PackageError("unknown source provenance class")
    if (
        evidence["knowledge_kind"] == KnowledgeKind.EXPERIMENTAL_RESULT
        and evidence["evidence_class"] != "experimental_result"
    ):
        raise PackageError("reported source is not an imported experimental result")
    if not all(
        evidence.get(k)
        for k in ("id", "url", "content_sha256", "observation", "rationale")
    ):
        raise PackageError("future evidence needs provenance and an observation")
    if any(evidence["id"] == x["evidence"]["id"] for x in chain):
        raise PackageError("duplicate reveal source")
    rows = {d["id"]: d for d in bundle["prospective-discriminators.json"]["items"]}
    if evidence["discriminator_id"] not in rows:
        raise PackageError("observation must test a frozen discriminator")
    discriminator = rows[evidence["discriminator_id"]]
    outcome = evidence["outcome"]
    if outcome not in ("strengthens", "weakens", "ambiguous", "non_interpretable"):
        raise PackageError("unknown outcome classification")
    before = deepcopy(state)
    admissible = evidence["evidence_class"] in (
        "peer_reviewed_primary",
        "experimental_result",
    )
    if (
        outcome in ("strengthens", "weakens")
        and evidence.get("methods_and_data_available")
        and admissible
    ):
        for uncertainty in discriminator["uncertainty_ids"]:
            state["uncertainties"][uncertainty]["status"] = "partially_resolved"
    else:
        outcome = (
            outcome if outcome in ("ambiguous", "non_interpretable") else "ambiguous"
        )
    state.pop("fingerprint", None)
    state["review_status"] = "pending_review"
    state["fingerprint"] = temporal.digest(state)
    result = {
        "t0_fingerprint": t0["fingerprint"],
        "parent_fingerprint": parent,
        "sequence": len(chain) + 1,
        "evidence": deepcopy(evidence),
        "uncertainty_ids": discriminator["uncertainty_ids"],
        "hypothesis_ids": discriminator["hypothesis_ids"],
        "interpretation": outcome,
        "review_status": "pending_review",
        "consequence": discriminator["consequences"][outcome],
        "proposed_case_state": state,
        "canonical_decision_state_update": None,
        "causal_diff": {
            **core.state_diff(before, state),
            "source_id": evidence["id"],
            "discriminator_id": discriminator["id"],
            "outcome": outcome,
            "rationale": evidence["rationale"],
            "proposal_only": True,
        },
    }
    result["fingerprint"] = temporal.digest(result)
    return result


def packages() -> list[dict[str, Any]]:
    return [load(p.parent) for p in sorted(registry_root().glob("*/v*/manifest.json"))]


def case_row(bundle: dict[str, Any]) -> dict[str, Any]:
    case = bundle["case.json"]
    return {
        "case_id": case["case_id"],
        "set_id": bundle["manifest"]["package_id"],
        "status": "frozen",
        "benchmark_kind": "prospective",
        "synthetic": False,
        "label": "LONG-HORIZON PROSPECTIVE CASE — pending independent review",
        "cutoff": case["cutoff"],
        "case_type": "prospective",
        "question": case["question"],
    }


def view(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        **case_row(bundle),
        "prospective": {
            "case": deepcopy(bundle["case.json"]),
            "state": replay(bundle),
            "evidence": deepcopy(bundle["evidence-snapshot.json"]),
            "sources": deepcopy(bundle["source-index.json"]),
            "discriminators": deepcopy(
                bundle["prospective-discriminators.json"]["items"]
            ),
            "scenarios": deepcopy(bundle["outcome-scenarios.json"]["items"]),
            "reveals": [],
            "future_results_known": False,
        },
    }
