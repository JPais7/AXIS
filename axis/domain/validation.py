"""Target-neutral vocabulary for retrospective validation (Phase 3.7).

No disease, target, allele or compound appears here; those live in case data.
"""

AVAILABILITY_KINDS = ("established", "bounded", "uncertain", "unknown")
# Only these kinds may enter a window; `uncertain` and `unknown` fail closed.
ELIGIBLE_KINDS = ("established", "bounded")
CASE_STATUSES = ("draft", "sealed", "executed", "revealed", "reviewed", "invalid")
BENCHMARK_KINDS = ("development", "validation", "synthetic_test")
SYNTHETIC_LABEL = "SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE"
INVALID_LABEL = "INVALID — TEMPORAL LEAKAGE"
CONCLUSIONS = (
    "supported_by_future_evidence",
    "weakened_by_future_evidence",
    "contradicted_by_future_evidence",
    "ambiguous",
    "future_evidence_did_not_test_the_decision",
    "invalid_due_to_leakage",
    "not_interpretable",
)
RELEVANCE = (
    "changes_critical_uncertainty",
    "changes_other_uncertainty",
    "adds_evidence_to_open_uncertainty",
    "addresses_unassessed_edge",
    "adds_to_assessed_edge",
    "does_not_test_decision_question",
    "non_interpretable",
)
DIMENSIONS = (
    "temporal_integrity",
    "decision_validity_at_cutoff",
    "uncertainty_calibration",
    "recommendation_relevance",
    "future_evidence_relevance",
    "evidence_update_behavior",
    "overstated_claims",
    "baseline_comparison",
)
LEAKAGE_CATEGORIES = (
    "record_after_cutoff",
    "availability_unknown_or_uncertain",
    "source_not_in_availability_table",
    "template_names_future_source",
    "future_file_opened_before_reveal",
    "protocol_checksum_mismatch",
    "window_checksum_mismatch",
    "output_names_future_source",
    "baseline_not_frozen_before_reveal",
    "future_record_in_window",
)
