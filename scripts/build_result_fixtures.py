"""Regenerate the frozen Phase 3.6 resource packages and their checksums.

Both packages are clearly labelled:
* scenario signatures: AI-suggested categorical facets, review pending;
* synthetic loop: SYNTHETIC / TEST-ONLY, never real experimental evidence.
"""

# ruff: noqa: E501
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "axis/resources/experimental-results"

SIGNATURES = {
    "decision:exp:chemical-genetic-engagement:s1": {
        "engagement_signal": "detected",
        "phenotype_in_target_null": "attenuated",
        "rescue": "restored",
    },
    "decision:exp:chemical-genetic-engagement:s2": {
        "engagement_signal": "detected",
        "phenotype_in_target_null": "unchanged",
    },
    "decision:exp:chemical-genetic-engagement:s3": {
        "engagement_signal": "not_detected",
        "phenotype_in_target_null": "attenuated",
    },
    "decision:exp:chemical-genetic-engagement:s4": {"background_dependence": "varies"},
    "decision:exp:chemical-genetic-engagement:s5": {"model_validity": "invalid"},
    "decision:exp:engagement-assay:s1": {
        "engagement_signal": "detected",
        "signal_in_target_depleted": "absent",
    },
    "decision:exp:engagement-assay:s2": {"engagement_signal": "not_detected"},
    "decision:exp:engagement-assay:s3": {
        "engagement_signal": "detected_only_above_active_exposure"
    },
    "decision:exp:engagement-assay:s4": {"assay_validity": "failed"},
    "decision:exp:engagement-phenotype-alignment:s1": {
        "engagement_phenotype_alignment": "aligned"
    },
    "decision:exp:engagement-phenotype-alignment:s2": {
        "phenotype_without_engagement": "true"
    },
    "decision:exp:engagement-phenotype-alignment:s3": {
        "assay_sensitivity": "inadequate"
    },
    "decision:exp:phenotype-replication:s1": {"phenotype_reproduced": "true"},
    "decision:exp:phenotype-replication:s2": {"phenotype_reproduced": "false"},
    "decision:exp:phenotype-replication:s3": {"assay_validity": "failed"},
    "decision:exp:allotype-matched-panel:s1": {"effect_by_background": "varies"},
    "decision:exp:allotype-matched-panel:s2": {"effect_by_background": "consistent"},
    "decision:exp:allotype-matched-panel:s3": {"panel_validity": "invalid"},
    "decision:exp:orthogonal-chemical-probe:s1": {
        "probe_engagement": "detected",
        "probe_phenotype": "reproduced",
    },
    "decision:exp:orthogonal-chemical-probe:s2": {
        "probe_engagement": "detected",
        "probe_phenotype": "not_reproduced",
    },
    "decision:exp:orthogonal-chemical-probe:s3": {"probe_qualified": "false"},
}


def write_package(directory: Path, manifest: dict) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    (directory / "manifest.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    (directory / "manifest.sha256").write_text(digest + "\n")
    return digest


def main() -> None:
    write_package(
        ROOT / "scenario-signatures/erap1-axspa/v1",
        {
            "importer_version": "axis-scenario-signatures-1",
            "package_version": "1.0.0",
            "knowledge_kind": "ai_suggestion",
            "review_status": "pending_expert_review",
            "boundary": "Categorical observation facets that would correspond to each anticipated outcome scenario. AI-suggested, not reviewed; a real result is never forced into a scenario.",
            "signatures": SIGNATURES,
        },
    )
    synth = ROOT / "synthetic/erap1-decision-loop/v1"
    raw_dir = synth / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw = (
        "# SYNTHETIC TEST DATA - NOT REAL EXPERIMENTAL EVIDENCE\n"
        "well\tcondition\tarm\tsignal_au\n"
        "A1\tvehicle\twild_type\t1000\nA2\tvehicle\twild_type\t1010\nA3\tvehicle\twild_type\t990\n"
        "B1\tcompound_active_exposure\twild_type\t580\nB2\tcompound_active_exposure\twild_type\t600\nB3\tcompound_active_exposure\twild_type\t560\n"
        "C1\tcompound_active_exposure\ttarget_depleted\t1005\nC2\tcompound_active_exposure\ttarget_depleted\t995\nC3\tcompound_active_exposure\ttarget_depleted\t1010\n"
    )
    processed = (
        "# SYNTHETIC TEST DATA - NOT REAL EXPERIMENTAL EVIDENCE\n"
        "arm\tcondition\tnormalized_signal\n"
        "wild_type\tvehicle\t1.00\nwild_type\tcompound_active_exposure\t0.58\ntarget_depleted\tcompound_active_exposure\t1.00\n"
    )
    (raw_dir / "engagement-plate-reader.tsv").write_text(raw)
    (raw_dir / "engagement-normalized.tsv").write_text(processed)

    def sha(name: str) -> str:
        return hashlib.sha256((raw_dir / name).read_bytes()).hexdigest()

    manifest = {
        "importer_version": "axis-results-1",
        "package_id": "synthetic-erap1-decision-loop",
        "package_version": "1.0.0",
        "scientific_status": "synthetic_test_fixture",
        "not_real_experimental_evidence": True,
        "label": "SYNTHETIC / TEST-ONLY - not real experimental evidence",
        "project_id": "AXIS-DD-ERAP1-CURATED-001",
        "recorded_by": "Synthetic fixture loader",
        "recorded_at": "2026-10-05T09:00:00+00:00",
        "artifacts": [
            {
                "id": "synthetic:art:raw",
                "path": "raw/engagement-plate-reader.tsv",
                "media_type": "text/tab-separated-values",
                "role": "raw",
                "sha256": sha("engagement-plate-reader.tsv"),
                "description": "Synthetic plate-reader export",
            },
            {
                "id": "synthetic:art:processed",
                "path": "raw/engagement-normalized.tsv",
                "media_type": "text/tab-separated-values",
                "role": "processed",
                "sha256": sha("engagement-normalized.tsv"),
                "description": "Synthetic normalized signal",
            },
        ],
        "experiments": [
            {
                "id": "synthetic:exp:engagement-maben3",
                "proposal_id": "decision:exp:engagement-assay",
                "executed_at": "2026-10-05T08:00:00+00:00",
                "performed_by": "Synthetic fixture",
                "scope": {"scope_type": "compound", "scope_id": "compound:maben-3"},
                "compound_id": "compound:maben-3",
                "context": {
                    "cell_line": "SYNTHETIC line",
                    "hla_allele": "unspecified (synthetic)",
                    "disease_status": "none (synthetic)",
                },
                "target_label": "ERAP1",
                "construct": "not reported",
                "assay": "synthetic cellular engagement readout",
                "controls": ["vehicle", "target-depleted cells"],
                "exposure": "phenotype-active exposure (synthetic)",
                "measures_edges": ["engagement"],
                "endpoints": ["cellular_engagement_signal"],
                "protocol_reference": "synthetic-protocol-1",
                "qc": {
                    "control_status": "passed",
                    "technical_validity": "valid",
                    "replicate_quality": "adequate",
                    "assessment": "interpretable",
                    "rationale": "Synthetic: vehicle and target-depleted controls behaved as expected.",
                },
            }
        ],
        "results": [
            {
                "id": "synthetic:res:engagement-maben3",
                "version": 1,
                "experiment_id": "synthetic:exp:engagement-maben3",
                "endpoint": "cellular_engagement_signal",
                "result_type": "binary_detection",
                "qualitative_result": "Signal reduced to 0.58 of vehicle at the active exposure in wild-type cells; no reduction in target-depleted cells.",
                "replicates": {"n": 3, "type": "biological"},
                "statistics": {"mean_wild_type": 0.58, "mean_target_depleted": 1.0},
                "raw_artifact_ids": ["synthetic:art:raw"],
                "processed_artifact_ids": ["synthetic:art:processed"],
                "transformations": [
                    {
                        "input": "synthetic:art:raw",
                        "output": "synthetic:art:processed",
                        "method": "vehicle normalization",
                        "version": "synthetic-1",
                    }
                ],
                "analysis": {
                    "method": "vehicle normalization",
                    "version": "synthetic-1",
                },
                "observed_at": "2026-10-05T08:30:00+00:00",
                "facets": {
                    "engagement_signal": "detected",
                    "signal_in_target_depleted": "absent",
                },
            }
        ],
        "interpretations": [
            {
                "id": "synthetic:int:engagement-maben3",
                "result_id": "synthetic:res:engagement-maben3",
                "edge": "engagement",
                "scope_type": "compound",
                "scope_id": "compound:maben-3",
                "proposed_state": "supported",
                "statement": "Consistent with direct cellular engagement of the target by compound:maben-3 at the tested exposure in the synthetic system.",
                "rationale": "Signal depends on the target and is absent in target-depleted cells (synthetic).",
                "knowledge_kind": "ai_suggestion",
                "caveats": ["single synthetic system"],
            }
        ],
    }
    write_package(synth, manifest)


if __name__ == "__main__":
    main()
