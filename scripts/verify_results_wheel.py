"""Run from outside the checkout with the installed wheel on PYTHONPATH.

Verifies the frozen Phase 3.6 resources, migration 010, import, review, explicit
rebuild, DecisionState v2 and the causal diff, with the network and model libraries
disabled and two independent stores producing identical results.
"""

import hashlib
import json
import socket
from datetime import UTC, datetime
from importlib import resources
from unittest.mock import patch

import httpx

import axis
from axis.api.server import ReadAPI
from axis.cellular.service import CellularPharmacologyService
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.experiments.results import ResultsService
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
FIXED = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def deny(*args: object, **kwargs: object) -> None:
    raise AssertionError("network disabled")


def main() -> None:
    base = resources.files("axis").joinpath("resources/experimental-results")
    for rel in (
        "synthetic/erap1-decision-loop/v1",
        "scenario-signatures/erap1-axspa/v1",
    ):
        root = base.joinpath(rel)
        digest = hashlib.sha256(root.joinpath("manifest.json").read_bytes()).hexdigest()
        assert digest == root.joinpath("manifest.sha256").read_text().strip(), rel
    assert (
        resources.files("axis.storage.migrations")
        .joinpath("010_experimental_results.sql")
        .is_file()
    )
    manifest = json.loads(
        base.joinpath("synthetic/erap1-decision-loop/v1/manifest.json").read_bytes()
    )
    assert manifest["scientific_status"] == "synthetic_test_fixture"
    assert manifest["not_real_experimental_evidence"] is True
    states = []
    with (
        patch.object(socket.socket, "connect", deny),
        patch.object(socket, "create_connection", deny),
        patch.object(httpx.Client, "request", deny),
        patch.dict("sys.modules", {"anthropic": None, "openai": None}),
    ):
        for _ in range(2):
            with EvidenceStore() as store:
                import_curated_erap1(store)
                protein = TargetIdentityService(store).import_package(PROJECT)
                PharmacologyService(store).import_package(PROJECT, protein)
                CellularPharmacologyService(store).import_package(PROJECT, protein)
                decision = DecisionService(store)
                decision.import_package(PROJECT, protein)
                results = ResultsService(store)
                results.import_signatures(PROJECT)
                v1 = decision.build(PROJECT, protein, created_at=FIXED)
                assert store.statistics().schema_version == 10
                summary = results.import_package(PROJECT, allow_synthetic=True)
                assert summary["decision_state_changed"] is False
                assert decision.current(PROJECT, protein)["id"] == v1["id"]
                results.record_review(
                    PROJECT,
                    "experimental_result",
                    "synthetic:res:engagement-maben3@v1",
                    "Dr Example",
                    "accepted",
                    "frozen test review",
                )
                results.record_review(
                    PROJECT,
                    "result_interpretation",
                    "synthetic:int:engagement-maben3",
                    "Dr Example",
                    "accepted",
                    "frozen test review",
                )
                v2 = decision.rebuild(PROJECT, protein, created_at=FIXED)
                assert v2["supersedes_id"] == v1["id"] and v2["synthetic"] is True
                assert (
                    v2["effective_evidence"]["engagement_rollup"]["status"] == "partial"
                )
                api = ReadAPI(store)
                for route in (
                    "performed-experiments",
                    "results",
                    "review-queue",
                    "decision/timeline",
                    "decision/diff",
                ):
                    assert api.get(f"/api/projects/{PROJECT}/{route}", {})
                states.append(json.dumps(v2, sort_keys=True, default=str))
    assert states[0] == states[1]
    print(
        json.dumps(
            {
                "loaded_axis": axis.__file__,
                "schema": 10,
                "two_store_offline_replay": True,
                "llm_off": True,
                "decision_state_v2": json.loads(states[0])["id"],
                "causes": [
                    c["category"] for c in json.loads(states[0])["diff"]["causes"]
                ],
                "decision_changed": json.loads(states[0])["diff"]["decision_changed"][
                    "answer"
                ],
                "rules_version": json.loads(states[0])["rules_version"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
