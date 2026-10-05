"""Behavioral cross-target contracts and frozen scientific equivalence."""

import json
import socket
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from axis.assay_context import CuratedComparison, ScopedLimitation
from axis.case_config import reference_case
from axis.cellular.service import CellularPharmacologyService
from axis.computational.service import canonical as campaign_canonical
from axis.decision.service import canonical as decision_canonical
from axis.learning.dataset import canonical as learning_canonical
from axis.serialization import canonical_json
from axis.storage import EvidenceStore
from scripts import audit_axis_consolidation as audit
from scripts.audit_axis_consolidation import compare


@pytest.mark.parametrize(
    "value", [{"z": "é", "a": [None, 3.5]}, datetime(2026, 10, 5, tzinfo=UTC), {}]
)
def test_existing_digest_serialization_is_identical(value: object) -> None:
    expected = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    assert canonical_json(value) == expected
    assert decision_canonical(value) == expected
    assert campaign_canonical(value) == expected
    assert learning_canonical(value) == expected


def test_reference_configuration_preserves_old_strings() -> None:
    profile = reference_case("erap1-axspa")
    assert profile["primary_target"] == "ERAP1"
    assert profile["comparison_targets"] == ["ERAP2", "LNPEP"]
    assert profile["proposal_context"] == (
        "Matched HLA and ERAP1 genetic context; controls required"
    )
    assert profile["proposal_design"] == (
        "Chemical perturbation, ERAP1 genetic depletion/rescue and "
        "orthogonal controls; measure toxicity separately"
    )


@pytest.mark.parametrize("name", ["../erap1-axspa", "/etc/passwd", "", "X"])
def test_configuration_cannot_escape_resource_directory(name: str) -> None:
    with pytest.raises(ValueError, match="invalid case"):
        reference_case(name)


@pytest.mark.parametrize(
    "field", ["temperature", "allotype", "salt/form", "replicates"]
)
def test_missing_field_is_not_automatically_a_global_blocker(field: str) -> None:
    limitation = ScopedLimitation(
        (field,),
        "cross-programme quantitative transfer",
        False,
        "No transfer is asserted by the current decision",
    )
    assert limitation.classification == "LOCAL_LIMITATION"


def test_material_missing_prerequisite_requires_explicit_rule() -> None:
    with pytest.raises(ValueError, match="explicit decision dependency"):
        ScopedLimitation(("substrate",), "source activity", True, "unresolved identity")
    limitation = ScopedLimitation(
        ("substrate",),
        "source activity",
        True,
        "unresolved identity",
        "case-admission:source-assay-identity",
    )
    assert limitation.classification == "DECISION_BLOCKER"


def test_generic_comparability_does_not_assume_erap1_or_numeric_equivalence() -> None:
    comparison = CuratedComparison(
        "fictional-target biochemical vs reporter",
        "NOT_COMPARABLE",
        "distinct endpoints; no pooling",
        "synthetic:test-only",
    )
    assert comparison.status == "NOT_COMPARABLE"
    assert not hasattr(comparison, "ratio")


def test_golden_reference_replays_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("scientific replay attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result = compare()
    assert result["scientific_equivalence"] == "PASS"
    assert result["changed_dimensions"] == []


@pytest.mark.parametrize("target", ["ERAP1", "SYNTHETIC-OTHER-TARGET"])
def test_cellular_projection_queries_the_registered_target(target: str) -> None:
    filters: list[dict[str, object]] = []

    def collection(*args: object) -> dict[str, object]:
        filters.append(cast(dict[str, object], args[-1]))
        return {"items": [], "has_more": False}

    store = SimpleNamespace(
        cellular=SimpleNamespace(
            collection=lambda *args: {"items": [], "has_more": False}
        ),
        pharmacology=SimpleNamespace(collection=collection),
        projects=SimpleNamespace(
            get=lambda _: SimpleNamespace(target_disease_pair="p")
        ),
        target_disease_pairs=SimpleNamespace(
            get=lambda _: SimpleNamespace(target=SimpleNamespace(identifier=target))
        ),
    )
    result = CellularPharmacologyService(cast(EvidenceStore, store)).chain(
        "p", "protein"
    )
    assert filters == [{"target": target, "assay_type": "biochemical_activity"}]
    assert result["boundary"].startswith("Independent evidence classes")


@pytest.mark.parametrize(
    "dimension",
    [
        "classification",
        "critical_uncertainty",
        "recommended_experiment",
        "learning",
        "sources",
        "claims",
        "causal_diff",
        "protected_hashes",
    ],
)
def test_golden_verifier_refuses_material_change(
    dimension: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = json.loads((audit.AUDIT / "golden-reference.json").read_text())
    actual = deepcopy(baseline)
    if dimension == "protected_hashes":
        path = next(iter(actual[dimension]))
        actual[dimension][path] = "tampered"
    else:
        actual[dimension] = "tampered"
    monkeypatch.setattr(audit, "material", lambda: actual)
    with pytest.raises(ValueError, match="SCIENTIFIC_CHANGE"):
        compare()
