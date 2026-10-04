"""Run from outside the checkout with installed wheel on PYTHONPATH."""

import hashlib
import json
import socket
from importlib import resources
from unittest.mock import patch

import httpx

import axis
from axis.api.server import ReadAPI
from axis.cellular.service import CellularPharmacologyService
from axis.discovery.curation import import_curated_erap1
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"


def deny(*args: object, **kwargs: object) -> None:
    raise AssertionError("network disabled")


def main() -> None:
    root = resources.files("axis").joinpath("resources/cellular/erap1-axspa/v1")
    digest = hashlib.sha256(root.joinpath("manifest.json").read_bytes()).hexdigest()
    assert digest == root.joinpath("manifest.sha256").read_text().strip()
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
                service = CellularPharmacologyService(store)
                assert service.import_package(PROJECT, protein) == (
                    service.import_package(PROJECT, protein)
                )
                assert store.statistics().schema_version == 10
                result = [
                    store.cellular.collection(PROJECT, protein, k, 100)
                    for k in (
                        "experiments",
                        "readouts",
                        "assessments",
                        "immunopeptidome",
                    )
                ]
                result += [
                    service.chain(PROJECT, protein),
                    service.gaps(PROJECT, protein),
                    service.review_packet(PROJECT, protein),
                ]
                api = ReadAPI(store)
                assert api.get(
                    f"/api/projects/{PROJECT}/targets/{protein}/cellular", {}
                )
                results.append(result)
    assert results[0] == results[1]
    print(
        json.dumps(
            {
                "loaded_axis": axis.__file__,
                "schema": 10,
                "manifest_sha256": digest,
                "two_store_offline_replay": True,
                "experiments": results[0][0]["total"],
                "readouts": results[0][1]["total"],
                "assessments": results[0][2]["total"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
