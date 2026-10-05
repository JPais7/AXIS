"""Close the bounded audit with traceable claims or an explicit refusal.

Offline by default. Does not alter v1, historical decisions, rules or review states.
Generic Claim storage is not a substitute for admitted cellular decision inputs.
"""

import argparse
import json
import subprocess
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from axis.domain.models import (
    Claim,
    ClaimContext,
    EntityKind,
    EntityRef,
    KnowledgeKind,
    Provenance,
    SourceKind,
)
from axis.domain.pharmacology import Assay, BioactivityMeasurement
from axis.evidence_integration import (
    CUTOFF,
    digest,
    eligible_date,
    replay,
    verify_package,
)
from axis.pharmacology.selectivity import compare
from axis.storage import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "axis/resources/evidence-integration/erap1-data-rich/2026/v1"
OUTPUT = BASE.parent / "closure-v1"
START = "c901d3061a7f0d3d4f3169da99b7ad528834d9b9"
MAIN = "d491ebe47ee0c40dfaa3823a44a9decd1afae29d"
ALGORITHM = "erap1-scientific-closure-1"


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def domain_claim(envelope: dict[str, Any]) -> Claim:
    """Existing immutable Claim; review/source-class remain in the envelope."""
    row = envelope["domain_claim"]
    return Claim(
        identifier=row["identifier"],
        subject=EntityRef(
            **(row["subject"] | {"kind": EntityKind(row["subject"]["kind"])})
        ),
        predicate=row["predicate"],
        object=EntityRef(
            **(row["object"] | {"kind": EntityKind(row["object"]["kind"])})
        ),
        knowledge_kind=KnowledgeKind(row["knowledge_kind"]),
        provenance=Provenance(
            source_kind=SourceKind(row["provenance"]["source_kind"]),
            source_identifier=row["provenance"]["source_identifier"],
            retrieved_at=datetime.fromisoformat(row["provenance"]["retrieved_at"]),
            source_uri=row["provenance"]["source_uri"],
            checksum=row["provenance"]["checksum"],
        ),
        context=ClaimContext(**row["context"]),
    )


def envelope(spec: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    source_kind = (
        SourceKind.AXIS_PIPELINE
        if spec["kind"] in {"axis_observation", "axis_inference"}
        else SourceKind.PUBLICATION
    )
    claim = Claim(
        identifier=spec["id"],
        subject=EntityRef(EntityKind.PROTEIN, "Q9NZ08", "ERAP1", "UniProt"),
        predicate=spec["text"],
        object=EntityRef(EntityKind.STUDY, spec["source"], spec["source"], "source"),
        knowledge_kind=KnowledgeKind(spec["kind"]),
        provenance=Provenance(
            source_kind=source_kind,
            source_identifier=spec["source"],
            retrieved_at=datetime.fromisoformat(artifact["retrieved_at"]),
            source_uri=artifact["url"],
            checksum=artifact["sha256"],
        ),
        context=ClaimContext(**spec["context"]),
    )
    return {
        "domain_claim": json.loads(json.dumps(asdict(claim), default=str)),
        "source_class": spec["source_class"],
        "source_locator": spec["locator"],
        "source_artifact": artifact["cache_path"],
        "polarity": spec["polarity"],
        "scope": spec["scope"],
        "supporting_evidence": [
            {"sha256": artifact["sha256"], "locator": spec["locator"]}
        ],
        "contradicting_evidence": spec.get("contradicting_evidence", []),
        "limitations": spec["limitations"],
        "review_state": "pending_review",
        "decision_input_admission": (
            "NO FINAL INTEGRATED INPUTS: source-context stop condition"
        ),
    }


def selectivity_replay() -> dict[str, Any]:
    """Run actual existing rules on the source-specific compound-7 counterscreens."""
    result = {}
    for target, substrate in (("ERAP2", "Arg-AMC"), ("LNPEP", "Leu-AMC")):
        common = {
            "assay_type": "biochemical_activity",
            "source_snapshot_id": "closure:hry-2024",
            "locator": "Figure 1 / selectivity paragraph",
            "taxon_id": 9606,
            "biological_system": "isolated enzyme",
        }
        primary_assay = Assay(
            id="closure:hry:ERAP1",
            name="YTAFTIPSI cleavage",
            target_gene="ERAP1",
            source_assay_identifier="ERAP1",
            substrate="YTAFTIPSI",
            **common,
        )
        counter_assay = Assay(
            id="closure:hry:" + target,
            name=substrate,
            target_gene=target,
            source_assay_identifier=target,
            substrate=substrate,
            **common,
        )
        measurement = {
            "compound_id": "10.1021/acsmedchemlett.4c00401:compound:7",
            "endpoint": "IC50",
            "original_unit": "nM",
            "source_snapshot_id": "closure:hry-2024",
            "locator": "SI Table S1 row 7 / main selectivity paragraph",
        }
        primary_value = 10 ** (9 - 7.7)
        primary = BioactivityMeasurement(
            id="closure:hry:7:ERAP1",
            assay_id=primary_assay.id,
            relation_operator="=",
            original_value=str(primary_value),
            value=primary_value,
            source_record_id="7:ERAP1",
            **measurement,
        )
        counter = BioactivityMeasurement(
            id="closure:hry:7:" + target,
            assay_id=counter_assay.id,
            relation_operator=">",
            original_value="100000",
            value=100000,
            source_record_id="7:" + target,
            replicate_count=1,
            **measurement,
        )
        result[target] = {
            "source_endpoint": "ERAP2/IRAP pIC50 <4, n=1; ERAP1 pIC50 7.7",
            "normalization": "IC50[nM]=10**(9-pIC50); reversed inequality",
            "inputs": {
                "primary_assay": asdict(primary_assay),
                "counter_assay": asdict(counter_assay),
                "primary_measurement": asdict(primary),
                "counter_measurement": asdict(counter),
            },
            "axis_observation": compare(primary, counter, primary_assay, counter_assay),
            "source_assertion_scope": (
                "Qualitative counterscreen result; authors' ratio not independently "
                "adopted"
            ),
        }
    return result


def roundtrip(claims: list[dict[str, Any]]) -> int:
    with (
        tempfile.TemporaryDirectory(prefix="axis-closure-") as temp,
        EvidenceStore(Path(temp) / "claims.duckdb") as store,
    ):
        for item in claims:
            claim = domain_claim(item)
            store.claims.add(claim)
            store.claims.add(claim)  # Idempotence, not independent review.
            if store.claims.get(claim.identifier) != claim:
                raise ValueError("stored claim differs from curation")
    return len(claims)


def verify_closure(root: Path = OUTPUT) -> dict[str, Any]:
    manifest = read(root / "manifest.json")
    if (
        digest((root / "manifest.json").read_bytes())
        != (root / "manifest.sha256").read_text().strip()
    ):
        raise ValueError("closure manifest checksum mismatch")
    if manifest["algorithm"] != ALGORITHM or manifest["cutoff"] != CUTOFF:
        raise ValueError("unsupported closure version/cutoff")
    if digest(Path(__file__).read_bytes()) != manifest["code_sha256"]:
        raise ValueError("closure replay code differs from frozen version")
    verify_package(BASE)
    if digest((BASE / "manifest.json").read_bytes()) != manifest["v1_manifest_sha256"]:
        raise ValueError("frozen v1 changed")
    for name, expected in manifest["checksums"].items():
        path = root / name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(
            root.resolve()
        ):
            raise ValueError("unsafe closure resource path")
        if digest(path.read_bytes()) != expected:
            raise ValueError("closure resource checksum mismatch: " + name)
    return manifest


def replay_closure(root: Path = OUTPUT) -> dict[str, Any]:
    verify_closure(root)
    sources = {
        s["cache_path"]: s for s in read(root / "source-adjudication.json")["artifacts"]
    }
    claims = read(root / "integrated-claims.json")["claims"]
    for c in claims:
        if c["review_state"] != "pending_review":
            raise ValueError("AI curation cannot approve itself")
        if (
            c["domain_claim"]["provenance"]["checksum"]
            != sources[c["source_artifact"]]["sha256"]
        ):
            raise ValueError("claim has no matching source checksum")
    if (
        json.loads(json.dumps(selectivity_replay()))
        != read(root / "assay-comparability.json")["selectivity"]
    ):
        raise ValueError("selectivity replay differs")
    audit = replay(BASE)
    refusal = read(root / "decision-refusal.json")
    if refusal["candidate_created"] or refusal["after"] is not None:
        raise ValueError("blocked closure cannot contain an AFTER decision")
    return {
        "status": "OFFLINE CLOSURE REFUSAL AND ADMITTED CLAIM REPLAY PASSED",
        "existing_claim_roundtrips": roundtrip(claims),
        "partial_audit_replay": audit["status"],
        "scientific_outcome": "SCIENTIFIC REASSESSMENT BLOCKED",
        "integrated_decision_replayed": False,
    }


def build(cache: Path | None = None) -> None:
    verify_package(BASE)
    adjudication = read(OUTPUT / "adjudication.json")
    curated = read(OUTPUT / "claim-curation.json")
    if not adjudication["blockers"]:
        raise ValueError(
            "This bounded closure implements refusal, not a reassessment bypass"
        )
    if adjudication["cutoff"] != CUTOFF:
        raise ValueError("wrong cutoff")
    original_artifacts = {
        s["cache_path"]: s for s in read(BASE / "source-artifacts.json")
    }
    artifact_names = {c["artifact"] for c in curated["claims"]}
    artifact_names |= {a["artifact"] for a in adjudication["assays"]}
    structures = read(BASE / "structure-index.json")
    artifact_names |= {s["pdb_id"] + ".cif" for s in structures}
    artifacts = []
    for name in sorted(artifact_names):
        a = original_artifacts[name]
        if a["status"] != 200 or not a.get("sha256"):
            raise ValueError("unverified source artifact")
        if cache is not None and digest((cache / name).read_bytes()) != a["sha256"]:
            raise ValueError("source cache checksum mismatch: " + name)
        artifacts.append(
            {k: a[k] for k in ("cache_path", "url", "sha256", "bytes", "retrieved_at")}
        )
    source_by_name = {a["cache_path"]: a for a in artifacts}
    claims = [envelope(c, source_by_name[c["artifact"]]) for c in curated["claims"]]
    for s in structures:
        if not eligible_date(s["release_date"]):
            raise ValueError("post-cutoff structure")
        pdb = s["pdb_id"]
        spec = {
            "id": "closure:claim:structure:" + pdb,
            "text": (
                f"PDB {pdb} contains mapped human ERAP1 crystallographic "
                "constructs and deposited organic components, with experimental "
                f"X-ray resolution {s['metadata']['resolution']} A; "
                "this is not a computational pose or cellular occupancy measurement."
            ),
            "kind": "axis_observation",
            "source_class": "structural database",
            "source": "PDB:" + pdb,
            "artifact": pdb + ".cif",
            "locator": (
                "mmCIF _struct_ref/_struct_ref_seq_dif/_atom_site; v1 "
                "structure-index.json:"
            )
            + pdb,
            "context": {
                "species": "human",
                "experimental_system": "crystallographic constructs",
                "assay": "X-ray diffraction",
                "endpoint": "source-anchored sequence mapping and coordinates",
            },
            "polarity": "supports",
            "scope": "experimental construct geometry only",
            "limitations": [
                (
                    "Preserve all construct changes, missing residues and author "
                    "versus canonical numbering in v1 structure-index"
                ),
                (
                    "Do not classify every buffer/additive as a pharmacological "
                    "ligand or assign regulatory-site activity from contact distance"
                ),
                (
                    "9TFN SI 2.00 A differs from current deposited 1.739 A; both "
                    "contexts retained"
                ),
            ],
        }
        claims.append(envelope(spec, source_by_name[pdb + ".cif"]))
    observations = read(BASE / "computational-replications.json")["peptides"]
    # Source classifications and actual recomputations are separate objects.
    computational = {
        "PXD066752": {
            "source_assertion": read(BASE / "computational-replications.json")[
                "source_conclusion_reproduced"
            ]["PXD066752"]["source_assertion"],
            "axis_observation": observations["PXD066752"],
            "locator": "10.1111/imm.70056 Figure 3A / inputs/report.pr_matrix.tsv",
        },
        "PXD054491_PXD054494": {
            "source_assertion": {
                "inhibitor_up": 321,
                "inhibitor_down": 146,
                "KO_up": 263,
                "KO_down": 238,
            },
            "axis_observation": observations["2025_supplement"],
            "locator": (
                "10.1016/j.mcpro.2025.100964 Results / Supplement Table A source rows "
                "frozen in inputs/2025-supplement-peptides.json"
            ),
        },
    }
    studies = read(BASE / "study-index.json")
    if any(not eligible_date(s.get("first_publication_date")) for s in studies):
        raise ValueError("post-cutoff study in frozen candidate index")
    write(
        OUTPUT / "source-adjudication.json",
        {
            "cutoff": CUTOFF,
            "artifacts": artifacts,
            "assays": adjudication["assays"],
            "publication_identity": studies,
            "review_state": "pending_review",
            "publisher_attempts": [
                a
                for a in original_artifacts.values()
                if a["cache_path"]
                in {"bradshaw-publisher.html", "tinworth-publisher.html"}
            ],
            "refused_promotions": [
                "2026 assay protocol borrowed from 2024 reference or crystal construct",
                (
                    "Tinworth CIA/cancer efficacy, dependency or occupancy without "
                    "sufficient main methods"
                ),
                (
                    "Sponsor/conference evidence promoted into independently "
                    "adjudicated human results"
                ),
                "New-compound engagement transferred to historical Maben chemistry",
            ],
        },
    )
    write(
        OUTPUT / "integrated-claims.json",
        {
            "claims": claims,
            "existing_domain": "axis.domain.models.Claim",
            "existing_store_roundtrip_count": roundtrip(claims),
            "computational_evidence": computational,
            "researcher_hypothesis": curated["researcher_hypothesis"],
            "engine_input_boundary": (
                "Stored admitted claims are not themselves cellular assessments; no "
                "fabricated assembler inputs or final AFTER state"
            ),
        },
    )
    write(
        OUTPUT / "assay-comparability.json",
        {
            "assays": adjudication["assays"],
            "selectivity": selectivity_replay(),
            "cross_programme_pooling": "REFUSED",
            "review_state": "pending_review",
        },
    )
    write(
        OUTPUT / "learning-eligibility.json",
        {
            "historical_status": "MODEL NOT BUILT",
            "closure_status": "MODEL NOT BUILT",
            "candidate_version": "candidate-v2, unadmitted",
            "reason": (
                "2026 biochemical/cellular assay context remains insufficiently "
                "adjudicated; numerical thresholds alone cannot admit records"
            ),
            "prior_numerical_diagnostics": read(BASE / "chemical-datasets.json")[
                "learning"
            ],
            "prior_diagnostics_not_new_admission": True,
            "eligibility_rerun_on_unadjudicated_records": False,
            "thresholds_changed": False,
            "model_built": False,
            "hryczanek_scope": (
                "Source-reported observed SAR and cellular protocol; not a newly "
                "admitted predictive learning dataset"
            ),
        },
    )
    before = read(BASE / "before.json")
    write(
        OUTPUT / "decision-refusal.json",
        {
            "outcome": "C — REASSESSMENT BLOCKED",
            "status": "SCIENTIFIC REASSESSMENT BLOCKED",
            "candidate_created": False,
            "before": before["canonical_decision"],
            "before_summary": before["decision_summary"],
            "after": None,
            "blocker_ids": [b["id"] for b in adjudication["blockers"]],
            "existing_rules_fingerprint": before["rules_fingerprint"],
            "historical_state_modified": False,
            "reason": (
                "Exact assay context could not be recovered sufficiently for priority "
                "2026 chemistry; apply user stop condition rather than infer "
                "protocols or treat structural-only analysis as full reassessment"
            ),
        },
    )
    write(
        OUTPUT / "causal-decision-diff.json",
        {
            "status": "NOT ASSESSABLE: no defensible integrated AFTER",
            "decision_changes": {
                k: {
                    "changed": None,
                    "reason": "Final integrated DecisionState creation refused",
                }
                for k in (
                    "critical_uncertainty",
                    "next_experiment",
                    "therapeutic_strategy",
                    "structural_tractability",
                    "programme_pharmacological_tractability",
                )
            },
            "learning_admission": {
                "changed": False,
                "before": "MODEL NOT BUILT",
                "after": "MODEL NOT BUILT",
                "reason": (
                    "Unadjudicated contexts, not failure of every numerical threshold"
                ),
            },
            "historical_maben_engagement": {
                "changed": False,
                "status": "UNRESOLVED",
                "reason": (
                    "No admitted new source directly tests historical compounds at "
                    "phenotype-active exposures"
                ),
            },
            "nondecision_observations": {
                "new_structures": {
                    "added": 12,
                    "claim_ids": [
                        c["domain_claim"]["identifier"]
                        for c in claims
                        if c["source_class"] == "structural database"
                    ],
                    "rule_boundary": (
                        "DECISION-STRUCT-001: structure cannot resolve "
                        "engagement/dependency"
                    ),
                },
                "processed_peptide_replay": (
                    "Reproduces sequence counts/source classifications, not "
                    "independent statistical or raw-MS results"
                ),
            },
            "advanced_question": {
                "status": "QUESTION PARTIALLY ADVANCED",
                "epistemic_kind": "axis_inference",
                "supporting_claims": curated["researcher_hypothesis"][
                    "supporting_claims"
                ],
                "scope": (
                    "Mechanistic framing only; not an engine-selected uncertainty or "
                    "validated protective processing state"
                ),
            },
            "commercial_update": "NO UPDATE JUSTIFIED",
            "commercial_scope": (
                "No final scientific decision update available; a future evidence "
                "addendum remains conditional on scientific closure/review"
            ),
        },
    )
    write(
        OUTPUT / "unresolved-blockers.json",
        {
            "status": "SCIENTIFIC REASSESSMENT BLOCKED",
            "blockers": adjudication["blockers"],
            "nonblocking_limitations": adjudication["nonblocking_limitations"],
        },
    )
    gates = {
        "Data acquisition": "PASS WITH CONDITIONS",
        "Data provenance": "PASS WITH CONDITIONS",
        "Chemical identity": "PASS WITH CONDITIONS",
        "Assay normalization": "FAIL",
        "Structural integration": "PASS WITH CONDITIONS",
        "Immunopeptidome reproducibility": "PASS WITH CONDITIONS",
        "Claim-level evidence integration": "PASS WITH CONDITIONS",
        "Chemical Learning eligibility": "PASS WITH CONDITIONS",
        "Epistemic integrity": "PASS WITH CONDITIONS",
        "Decision causality": "FAIL",
        "Offline reproducibility": "PASS WITH CONDITIONS",
        "External-review readiness": "FAIL",
    }
    write(
        OUTPUT / "acceptance-matrix.json",
        {
            "gates": gates,
            "verdict": "NOT READY FOR INDEPENDENT SCIENTIFIC REVIEW",
            "conditions": {
                "Claim-level evidence integration": (
                    "Defensible subset roundtripped in existing Claim store; rejected "
                    "assays and final integrated engine inputs excluded"
                ),
                "Offline reproducibility": (
                    "Refusal, admitted claims, selectivity and partial-audit "
                    "computations replay; no completed integrated decision claimed"
                ),
                "Chemical Learning eligibility": (
                    "Explicit scientific refusal despite some prior numeric passes; "
                    "no threshold changes or model"
                ),
            },
        },
    )
    write(
        OUTPUT / "repository-state.json",
        {
            "branch": "codex/erap1-data-rich-evidence-integration-2026",
            "starting_sha": START,
            "baseline_sha": MAIN,
            "remote_branch_verified_sha": START,
            "remote_main_verified_sha": MAIN,
            "final_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "closure_changes": (
                "uncommitted; no commit/push/merge authorized in this request"
            ),
            "frozen_v1_manifest_sha256": digest((BASE / "manifest.json").read_bytes()),
            "canonical_before_sha256": digest((BASE / "before.json").read_bytes()),
            "canonical_commercial_snapshot_sha256": digest(
                (
                    ROOT / "reports/commercial/erap1-axspa/v1/state-snapshot.json"
                ).read_bytes()
            ),
        },
    )
    checksums = {
        str(p.relative_to(OUTPUT)): digest(p.read_bytes())
        for p in sorted(OUTPUT.iterdir())
        if p.is_file() and p.name not in {"manifest.json", "manifest.sha256"}
    }
    write(
        OUTPUT / "manifest.json",
        {
            "algorithm": ALGORITHM,
            "cutoff": CUTOFF,
            "review_state": "pending_review",
            "status": "NOT READY FOR INDEPENDENT SCIENTIFIC REVIEW",
            "checksums": checksums,
            "v1_manifest_sha256": digest((BASE / "manifest.json").read_bytes()),
            "code_sha256": digest(Path(__file__).read_bytes()),
            "environment": before["dependencies"],
            "random_seed": None,
            "boundary": (
                "Completed bounded refusal audit, not an integrated DecisionState"
            ),
        },
    )
    (OUTPUT / "manifest.sha256").write_text(
        digest((OUTPUT / "manifest.json").read_bytes()) + "\n"
    )
    print(json.dumps(replay_closure(), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.replay:
        print(json.dumps(replay_closure(), indent=2))
    else:
        build(args.cache)
