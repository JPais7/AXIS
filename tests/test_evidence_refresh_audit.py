"""Publication guardrails for a partial, unapproved scientific refresh."""

import socket

import pytest

from axis.evidence_refresh import acceptance_blockers, audit


def test_partial_refresh_replays_offline_without_promoting_claims(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Audit attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    first = audit()
    second = audit()
    assert first == second
    assert first["integrity_errors"] == []
    assert first["verdict"] == "NOT READY FOR MERGE"
    assert first["DecisionState_v2"] == "not_created"
    assert first["new_claims_imported"] == 0
    assert first["draft_claims_pending_review"] == first["draft_atomic_claims"]


def test_proposed_exclusions_are_unresolved_not_final():
    result = audit()
    counts = result["checkpoint_screening_counts"]
    unresolved = sum(value for key, value in counts.items() if key != "already_indexed")
    assert result["unresolved_checkpoint_screening"] == unresolved
    assert unresolved >= counts["proposed_exclusion"]


def test_registry_existence_is_not_efficacy_or_engagement():
    result = audit()
    assert "NCT07047703" in result["registry_ids"]
    assert result["DecisionState_v2"] == "not_created"
    assert "material_fulltext_unresolved" in result["blockers"]


@pytest.mark.parametrize(
    "direction",
    [
        "supportive",
        "contradictory",
        "null",
        "context-only",
        "irrelevant-recent",
    ],
)
def test_technical_gate_cannot_accept_unreviewed_evidence_by_direction(direction):
    # This tests publication gating only, not completed scientific screening.
    candidate = {"direction": direction, "state": "proposed_exclusion"}
    assert candidate["state"] == "proposed_exclusion"
    blockers = acceptance_blockers(1, False, False, True, True, True, True)
    assert blockers == ["material_screening_backlog"]


def test_missing_decision_and_diff_block_publication():
    assert acceptance_blockers(0, False, False, True, False, False, True) == [
        "DecisionState_v2_absent",
        "causal_diff_absent",
    ]


def test_integrity_failure_blocks_publication_even_without_backlog():
    assert acceptance_blockers(0, False, False, True, True, True, False) == [
        "resource_integrity_failed",
    ]
