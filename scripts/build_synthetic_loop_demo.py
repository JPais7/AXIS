"""Build a SEPARATE database that demonstrates the synthetic experimental-results loop.

Never run this against a production database: every result it imports is
SYNTHETIC / TEST-ONLY. Usage: python scripts/build_synthetic_loop_demo.py PATH.duckdb
"""

# ruff: noqa: E501
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.cellular.service import CellularPharmacologyService
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.experiments.results import ResultsService
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
SYN = Path(str(resources.files("axis").joinpath("resources/experimental-results/synthetic/erap1-decision-loop/v1")))
ENGAGE = "decision:exp:engagement-assay"
DETECTED = {"engagement_signal": "detected", "signal_in_target_depleted": "absent"}


def experiment(eid: str, compound: str | None, *, qc: str = "interpretable", perturbagen: str | None = None) -> dict[str, Any]:
    scope = {"scope_type": "perturbagen", "scope_id": perturbagen} if perturbagen else {"scope_type": "compound", "scope_id": compound}
    return {
        "id": eid, "proposal_id": ENGAGE, "executed_at": "2026-10-05T08:00:00+00:00",
        "performed_by": "Synthetic fixture", "scope": scope,
        ("reported_perturbagen" if perturbagen else "compound_id"): perturbagen or compound,
        "context": {"cell_line": "SYNTHETIC line", "hla_allele": "unspecified (synthetic)"},
        "target_label": "ERAP1", "construct": "not reported", "assay": "synthetic engagement readout",
        "controls": ["vehicle", "target-depleted cells"], "exposure": "phenotype-active exposure (synthetic)",
        "measures_edges": ["engagement"], "endpoints": ["cellular_engagement_signal"],
        "qc": {"control_status": "failed" if qc == "non_interpretable" else "passed",
               "technical_validity": "invalid" if qc == "non_interpretable" else "valid",
               "replicate_quality": "adequate", "assessment": qc, "rationale": "synthetic QC"},
    }


def result(rid: str, eid: str, facets: dict[str, str], text: str, rtype: str = "binary_detection") -> dict[str, Any]:
    return {"id": rid, "version": 1, "experiment_id": eid, "endpoint": "cellular_engagement_signal",
            "result_type": rtype, "qualitative_result": text, "replicates": {"n": 3, "type": "biological"},
            "raw_artifact_ids": ["synthetic:art:raw"], "processed_artifact_ids": ["synthetic:art:processed"],
            "analysis": {"method": "vehicle normalization", "version": "synthetic-1"},
            "observed_at": "2026-10-05T08:30:00+00:00", "facets": facets}


def interp(iid: str, rid: str, scope_id: str, state: str = "supported", scope_type: str = "compound") -> dict[str, Any]:
    return {"id": iid, "result_id": rid, "edge": "engagement", "scope_type": scope_type, "scope_id": scope_id,
            "proposed_state": state, "statement": f"Synthetic interpretation {iid}", "rationale": "synthetic",
            "knowledge_kind": "ai_suggestion", "caveats": ["single synthetic system"]}


def write(directory: Path, experiments: list[dict], results: list[dict], interpretations: list[dict]) -> Path:
    manifest = json.loads((SYN / "manifest.json").read_text())
    manifest.update(experiments=experiments, results=results, interpretations=interpretations)
    shutil.copytree(SYN / "raw", directory / "raw", dirs_exist_ok=True)
    raw = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    (directory / "manifest.json").write_bytes(raw)
    (directory / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    return directory


def main(path: str) -> None:
    stamp = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    with EvidenceStore(path) as store, tempfile.TemporaryDirectory() as tmp:
        import_curated_erap1(store)
        protein = TargetIdentityService(store).import_package(PROJECT)
        StructureIdentityService(store).import_package(PROJECT, protein)
        PharmacologyService(store).import_package(PROJECT, protein)
        CellularPharmacologyService(store).import_package(PROJECT, protein)
        decision = DecisionService(store)
        decision.import_package(PROJECT, protein)
        results = ResultsService(store)
        results.import_signatures(PROJECT)
        decision.build(PROJECT, protein, created_at=stamp)  # v1, before any result
        experiments = [
            experiment("synthetic:exp:engagement-maben3", "compound:maben-3"),
            experiment("synthetic:exp:failed-maben2", "compound:maben-2", qc="non_interpretable"),
            experiment("synthetic:exp:unexpected-maben1", "compound:maben-1"),
            experiment("synthetic:exp:disputed-maben1", "compound:maben-1"),
        ]
        rows = [
            result("synthetic:res:engagement-maben3", experiments[0]["id"], DETECTED, "Signal reduced to 0.58 of vehicle in wild-type cells; none in target-depleted cells."),
            result("synthetic:res:failed-maben2", experiments[1]["id"], {"assay_validity": "failed"}, "Positive control failed; no usable signal.", "technical_failure"),
            result("synthetic:res:unexpected-maben1", experiments[2]["id"], {"unanticipated_observation": "signal increased"}, "Signal increased above vehicle; not an anticipated outcome."),
            result("synthetic:res:disputed-maben1", experiments[3]["id"], DETECTED, "Signal reduced in wild-type cells."),
        ]
        ints = [
            interp("synthetic:int:engagement-maben3", rows[0]["id"], "compound:maben-3"),
            interp("synthetic:int:failed-maben2", rows[1]["id"], "compound:maben-2", "contradicted"),
            interp("synthetic:int:unexpected-maben1", rows[2]["id"], "compound:maben-1", "insufficient"),
            interp("synthetic:int:disputed-maben1", rows[3]["id"], "compound:maben-1"),
        ]
        results.import_package(PROJECT, write(Path(tmp) / "loop", experiments, rows, ints), allow_synthetic=True)
        decision.rebuild(PROJECT, protein, trigger="after synthetic import, exploratory", created_at=stamp)  # v2 (pending)
        results.record_review(PROJECT, "experimental_result", "synthetic:res:engagement-maben3@v1", "Dr Example", "accepted", "synthetic review")
        results.record_review(PROJECT, "result_interpretation", "synthetic:int:engagement-maben3", "Dr Example", "accepted_with_caveat", "synthetic review", caveat="synthetic system only")
        results.record_review(PROJECT, "experimental_result", "synthetic:res:disputed-maben1@v1", "Dr Example", "accepted", "synthetic")
        results.record_review(PROJECT, "result_interpretation", "synthetic:int:disputed-maben1", "Reviewer A", "accepted", "synthetic")
        results.record_review(PROJECT, "result_interpretation", "synthetic:int:disputed-maben1", "Reviewer B", "rejected", "synthetic disagreement")
        decision.rebuild(PROJECT, protein, trigger="after synthetic review", created_at=stamp)  # v3
        # a second, decision-sensitive batch: the remaining required scopes are resolved
        more = [
            experiment("synthetic:exp:engagement-maben2", "compound:maben-2"),
            experiment("synthetic:exp:engagement-dg013a", None, perturbagen="DG013A"),
        ]
        more_results = [
            result("synthetic:res:engagement-maben2", more[0]["id"], DETECTED, "Signal reduced in wild-type cells; none in target-depleted cells."),
            result("synthetic:res:engagement-dg013a", more[1]["id"], DETECTED, "Signal reduced in wild-type cells; none in target-depleted cells."),
        ]
        more_ints = [
            interp("synthetic:int:engagement-maben2", more_results[0]["id"], "compound:maben-2"),
            interp("synthetic:int:engagement-dg013a", more_results[1]["id"], "DG013A", scope_type="perturbagen"),
        ]
        results.import_package(PROJECT, write(Path(tmp) / "loop2", more, more_results, more_ints), allow_synthetic=True)
        for rid, iid in (("synthetic:res:engagement-maben2@v1", "synthetic:int:engagement-maben2"), ("synthetic:res:engagement-dg013a@v1", "synthetic:int:engagement-dg013a")):
            results.record_review(PROJECT, "experimental_result", rid, "Dr Example", "accepted", "synthetic review")
            results.record_review(PROJECT, "result_interpretation", iid, "Dr Example", "accepted", "synthetic review")
        decision.rebuild(PROJECT, protein, trigger="after second synthetic batch", created_at=stamp)  # v4


if __name__ == "__main__":
    main(sys.argv[1])
