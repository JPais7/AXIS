"""Run from outside the checkout with installed wheel on PYTHONPATH."""

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
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
FIXED = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)


def deny(*args: object, **kwargs: object) -> None:
    raise AssertionError("network disabled")


def main() -> None:
    root = resources.files("axis").joinpath("resources/decision/erap1-axspa/v1")
    digest = hashlib.sha256(root.joinpath("manifest.json").read_bytes()).hexdigest()
    assert digest == root.joinpath("manifest.sha256").read_text().strip()
    assert (
        resources.files("axis.storage.migrations")
        .joinpath("009_experimental_decision.sql")
        .is_file()
    )
    results = []
    with (
        patch.object(socket.socket, "connect", deny),
        patch.object(socket, "create_connection", deny),
        patch.object(httpx.Client, "request", deny),
    ):
        for _ in range(2):
            with EvidenceStore() as store:
                import_curated_erap1(store)
                protein = TargetIdentityService(store).import_package(PROJECT)
                PharmacologyService(store).import_package(PROJECT, protein)
                CellularPharmacologyService(store).import_package(PROJECT, protein)
                service = DecisionService(store)
                assert service.import_package(PROJECT, protein) == (
                    service.import_package(PROJECT, protein)
                )
                assert store.statistics().schema_version == 10
                state = service.build(PROJECT, protein, created_at=FIXED)
                assert state == service.build(PROJECT, protein, created_at=FIXED)
                api = ReadAPI(store)
                for route in (
                    "decision",
                    "decision/history",
                    "uncertainties",
                    "explanations",
                    "candidate-experiments",
                    "decision-trace",
                ):
                    assert api.get(f"/api/projects/{PROJECT}/{route}", {})
                results.append(json.dumps(state, sort_keys=True, default=str))
    assert results[0] == results[1]
    print(
        json.dumps(
            {
                "loaded_axis": axis.__file__,
                "schema": 10,
                "manifest_sha256": digest,
                "two_store_offline_replay": True,
                "critical_uncertainty": state["critical_uncertainty_id"],
                "recommended_experiment": state["recommended_experiment_id"],
                "rules_version": state["rules_version"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
