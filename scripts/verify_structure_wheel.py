"""Run outside the checkout with PYTHONPATH pointing at an installed AXIS wheel."""

import hashlib
import json
from importlib import resources
from unittest.mock import patch
from urllib.parse import quote

import httpx

import axis
from axis.api.server import ReadAPI
from axis.discovery.curation import import_curated_erap1
from axis.storage import EvidenceStore
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService

project = "AXIS-DD-ERAP1-CURATED-001"
root = resources.files("axis")
package = root.joinpath("resources/structures/erap1/3qnf/v1")
manifest = json.loads(package.joinpath("manifest.json").read_bytes())
assert (
    hashlib.sha256(package.joinpath("structure.cif").read_bytes()).hexdigest()
    == (manifest["raw_sha256"])
)
assert package.joinpath("README.md").is_file()
assert root.joinpath("storage/migrations/006_structure_identity.sql").is_file()
assets = root.joinpath("resources/workspace/assets")
assert any(p.name.startswith("structure-viewer-") for p in assets.iterdir())

outputs = []
with patch.object(httpx.Client, "get", side_effect=AssertionError("network disabled")):
    for _ in range(2):
        with EvidenceStore(":memory:") as store:
            import_curated_erap1(store)
            protein = TargetIdentityService(store).import_package(project)
            service = StructureIdentityService(store)
            structure = service.import_package(project, protein)
            assert service.import_package(project, protein) == structure
            detail = service.projection(project, protein, structure)
            mapping = service.mapping(project, protein, structure)
            assert store.statistics().schema_version == 10
            assert store.statistics().claims == 14
            base = (
                f"/api/projects/{project}/targets/{quote(protein, safe='')}"
                f"/structures/{quote(structure, safe='')}"
            )
            api = ReadAPI(store)
            for suffix in ("", "/chains", "/mapping", "/provenance", "/coordinates"):
                assert api.get(base + suffix, {})
            outputs.append((detail, mapping))
assert outputs[0] == outputs[1]
print(
    json.dumps(
        {
            "loaded_axis": axis.__file__,
            "schema": 8,
            "raw_sha256": manifest["raw_sha256"],
            "two_clean_stores_equal": True,
            "network_entry_point_disabled": True,
            "api_routes": 5,
            "chains": [
                {
                    "label": c["label_asym_id"],
                    "coverage": c["coverage"],
                }
                for c in outputs[0][0]["chains"]
            ],
        },
        indent=2,
    )
)
