"""The terminal disposition must not masquerade as scientific completion."""

import json
from importlib.resources import files

from axis.evidence_refresh import PREFIX, audit


def test_terminal_disposition_preserves_incomplete_evidence_and_baseline():
    root = files("axis").joinpath(PREFIX)
    disposition = json.loads(root.joinpath("terminal-disposition.json").read_text())
    result = audit(root)
    assert disposition["status"] == result["overall_decision_impact"]
    assert disposition["terminal_for_this_refresh_attempt"] is True
    assert disposition["access_attempts_closed"] is True
    assert disposition["review_status"] == "pending_independent_review"
    assert not disposition["screening"]["completed"]
    assert disposition["screening"]["unresolved_original_checkpoint_records"] == (
        result["unresolved_checkpoint_screening"]
    )
    assert not disposition["freeze"]["final_scientific_evidence_set_frozen"]
    assert not disposition["freeze"]["protocol_changed"]
    assert not disposition["freeze"]["baseline_changed"]
    assert not disposition["outputs"]["baseline_reaffirmed"]
    assert not disposition["outputs"]["ready_for_merge"]
    for key in ("DecisionState_v2", "causal_diff", "commercial_brief_v1_1"):
        assert disposition["outputs"][key] == "not_created"
    assert disposition["cases"][0]["materiality"] == "decision_blocking"
    for path in disposition["access_evidence"]:
        assert root.joinpath(path).is_file()
    assert not result["integrity_errors"]
