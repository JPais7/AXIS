"""Bounded audit integrity; no claim of completed scientific reassessment."""

import json
from pathlib import Path

import pytest

from axis.evidence_integration import (
    eligible_date,
    learning_admission,
    normalize_chemical,
    normalize_pic50,
    replay,
    source_assigned_stereo,
    verify_package,
)
from axis.sources.pdb import reference_segments

PACKAGE = (
    Path(__file__).resolve().parents[1]
    / "axis/resources/evidence-integration/erap1-data-rich/2026/v1"
)


def test_cutoff() -> None:
    assert eligible_date("2026-10-05")
    assert not eligible_date("2026-10-06")
    assert not eligible_date(None)


@pytest.mark.parametrize("original,operator", [("<7", ">"), (">=7", "<=")])
def test_log_censoring(original: str, operator: str) -> None:
    result = normalize_pic50(original)
    assert result["derived_value"] == 100
    assert result["derived_operator"] == operator


def test_source_identity_retained() -> None:
    row = {"SMILES": "C[C@H](O)F |o1:1|", "Compound_ID": "1"}
    result = normalize_chemical(row, "source", "csv:2")
    assert result["source_row"] == row
    assert result["original_smiles"] == row["SMILES"]
    assert result["enhanced_stereo_groups"]
    assert result["review_state"] == "pending_review"
    assert source_assigned_stereo(row["SMILES"], {1: "R"}) != (
        source_assigned_stereo(row["SMILES"], {1: "S"})
    )


def test_no_assay_admission_from_numbers() -> None:
    assert not learning_admission({"target": "ERAP1"})["admitted"]


def test_explicit_indels_required() -> None:
    row = dict(
        align_id="1",
        seq_align_beg=1,
        seq_align_end=3,
        db_align_beg=1,
        db_align_end=4,
    )
    with pytest.raises(ValueError, match="unequal"):
        reference_segments(row, [])
    diffs = [
        dict(
            align_id="1",
            seq_num=None,
            pdbx_seq_db_seq_num=2,
            details="deletion",
        )
    ]
    assert reference_segments(row, diffs) == [(1, 1, 1, 1), (2, 3, 3, 4)]
    with pytest.raises(ValueError, match="contradicts"):
        reference_segments(
            row,
            diffs
            + [
                dict(
                    align_id="1",
                    seq_num=2,
                    pdbx_seq_db_seq_num=2,
                )
            ],
        )


def test_offline_audit_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket, "create_connection", refuse)
    result = replay(PACKAGE)
    assert "WITHHELD" in result["decision_reassessment"]
    assert result["observations"]["PXD066752"]["union"] == 2325
    decision = json.loads((PACKAGE / "decision-impact.json").read_text())
    assert not decision["final_decision_state_created"]
    assert not decision["historical_state_modified"]


def test_manifest_tampering(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "manifest.sha256").write_text("wrong")
    with pytest.raises(ValueError, match="checksum"):
        verify_package(tmp_path)
