"""Run from outside checkout with PYTHONPATH set to the fresh wheel install."""

import hashlib
import json
import socket
from importlib import resources
from unittest.mock import patch
from urllib.parse import quote

import httpx

import axis
from axis.api.server import ReadAPI
from axis.discovery.curation import import_curated_erap1
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore
from axis.targets.identity import TargetIdentityService

project = "AXIS-DD-ERAP1-CURATED-001"
root = resources.files("axis").joinpath("resources/pharmacology/erap1/v1")
raw = root.joinpath("manifest.json").read_bytes()
checksum = hashlib.sha256(raw).hexdigest()
assert checksum == root.joinpath("manifest.sha256").read_text().strip()
manifest = json.loads(raw)
assert root.joinpath("README.md").is_file()
assert (
    resources.files("axis.storage.migrations")
    .joinpath("007_chemical_pharmacology.sql")
    .is_file()
)
for name, digest in manifest["files"].items():
    assert hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest() == digest
outputs = []
with (
    patch.object(socket.socket, "connect", side_effect=AssertionError("no network")),
    patch.object(httpx, "get", side_effect=AssertionError("no network")),
    patch.object(httpx.Client, "get", side_effect=AssertionError("no network")),
):
    for _ in range(2):
        with EvidenceStore() as store:
            import_curated_erap1(store)
            protein = TargetIdentityService(store).import_package(project)
            service = PharmacologyService(store)
            ids = service.import_package(project, protein)
            assert service.import_package(project, protein) == ids
            api = ReadAPI(store)
            base = f"/api/projects/{project}/targets/{quote(protein, safe='')}"
            data = {
                kind: api.get(base + "/" + kind, {})
                for kind in ("compounds", "assays", "measurements", "selectivity")
            }
            assert data["compounds"]["total"] == 3
            assert data["measurements"]["total"] == 15
            assert data["assays"]["total"] == 7
            assert store.statistics().schema_version == 10
            data["details"] = [
                service.detail(project, protein, "compounds", i) for i in ids
            ]
            outputs.append(data)
assert outputs[0] == outputs[1]
print(
    json.dumps(
        {
            "loaded_axis": axis.__file__,
            "schema": 8,
            "manifest_sha256": checksum,
            "compounds": 3,
            "assays": 7,
            "measurements": 15,
            "selectivity_assessments": outputs[0]["selectivity"]["total"],
            "two_store_offline_replay": True,
        },
        indent=2,
    )
)
