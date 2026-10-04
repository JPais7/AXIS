import json
import subprocess
import sys
from datetime import datetime
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import duckdb
import pytest

from axis.api.server import ReadAPI, WorkspaceServer, json_default
from axis.discovery import DiscoveryService
from axis.discovery.curation import import_curated_erap1
from axis.discovery.workspace import WorkspaceService
from axis.storage import EvidenceStore, RecordNotFoundError
from axis.storage.ownership import StoreOwnershipError

PROJECT = "AXIS-DD-ERAP1-CURATED-001"
DEMO = "AXIS-DD-ERAP1-001"


@pytest.fixture(scope="module")
def api():
    with EvidenceStore() as store:
        import_curated_erap1(store)
        DiscoveryService(store).create_erap1_demo()
        yield ReadAPI(store)


def test_project_evidence_source_drawer_and_question_experiment(api):
    project = api.get(f"/api/projects/{PROJECT}", {})
    assert project["project_kind"] == "curated"
    assert project["counts"]["claims"] == 14
    genetics = api.get(
        f"/api/projects/{PROJECT}/evidence", {"domain": ["human_genetics"]}
    )
    assert genetics["total"] == 2
    claim_id = genetics["items"][0]["claim_id"]
    drawer = api.get(f"/api/claims/{claim_id}", {"project_id": [PROJECT]})
    assert drawer["claim"]["knowledge_kind"] == "source_assertion"
    assert drawer["context"]["hla_status"]
    assert drawer["source"]["source_id"] == "PMID:21743469"
    assert drawer["claim"]["provenance"]["checksum"]
    assert drawer["assessments"][0]["role"] == "untyped_considered"
    assert drawer["package_version"] == "1.0.0"
    source = api.get("/api/sources/PMID:21743469", {"project_id": [PROJECT]})
    assert source["claims"][0]["claim_id"] == claim_id
    assert PROJECT in source["projects"]
    assert source["transformations"]
    questions = api.get(f"/api/projects/{PROJECT}/questions", {})
    experiments = api.get(f"/api/projects/{PROJECT}/experiments", {})
    question_id = questions["items"][0]["question"]["question_id"]
    assert claim_id in questions["items"][0]["links"]["claim_ids"]
    assert experiments["items"][0]["experiment"]["question_id"] == question_id
    assert len(experiments["items"][0]["outcomes"]) == 2
    assert experiments["items"][0]["experiment"]["knowledge_kind"] == "ai_suggestion"
    encoded = json.loads(json.dumps(drawer, default=json_default))
    assert datetime.fromisoformat(encoded["source"]["retrieved_at"]).tzinfo is not None


def test_project_isolation_and_unknown_states(api):
    with pytest.raises(RecordNotFoundError):
        api.get("/api/claims/AXIS-ERAP1-CURATED-C01", {"project_id": [DEMO]})
    with pytest.raises(RecordNotFoundError):
        api.get("/api/sources/PMID:21743469", {"project_id": [DEMO]})
    with pytest.raises(ValueError):
        api.get("/api/claims/AXIS-ERAP1-CURATED-C01", {})
    demo = api.get(f"/api/projects/{DEMO}", {})
    assert demo["project_kind"] == "development"
    assert all(item["state"] == "not_assessed" for item in demo["matrix"])
    curated = api.get(f"/api/projects/{PROJECT}", {})
    assert {item["state"] for item in curated["matrix"]} >= {
        "evidence_available",
        "limited_evidence",
        "mixed_context_dependent",
    }
    source = api.get(
        "/api/sources/PMID:24504800", {"project_id": [PROJECT], "limit": ["1"]}
    )
    assert source["total"] == 3 and source["has_more"]
    hypothesis = api.get(
        "/api/claims/AXIS-ERAP1-CURATED-HYPOTHESIS", {"project_id": [PROJECT]}
    )
    assert not hypothesis["is_observational_evidence"]
    assert hypothesis["mechanisms"][0]["classification"] == "hypothesized"


@pytest.mark.parametrize(
    "route",
    [
        "evidence",
        "mechanism",
        "sources",
        "strategies",
        "assessments",
        "perturbations",
        "questions",
        "experiments",
    ],
)
def test_all_collections_are_bounded_and_stably_paged(api, route):
    first = api.get(f"/api/projects/{PROJECT}/{route}", {"limit": ["1"]})
    second = api.get(
        f"/api/projects/{PROJECT}/{route}", {"limit": ["1"], "offset": ["1"]}
    )
    assert len(first["items"]) == 1
    assert first["total"] == second["total"]
    assert first["has_more"] == (first["total"] > 1)
    if second["items"]:
        assert second["items"] != first["items"]


@pytest.mark.parametrize(
    "query",
    [
        {"limit": ["0"]},
        {"limit": ["101"]},
        {"offset": ["-1"]},
        {"offset": ["100001"]},
        {"limit": ["bad"]},
        {"limit": ["1", "2"]},
        {"unknown": ["x"]},
        {"domain": ["bad"]},
    ],
)
def test_invalid_bounds_and_filters_rejected(api, query):
    with pytest.raises(ValueError):
        api.get(f"/api/projects/{PROJECT}/evidence", query)


def test_store_exclusive_ownership_readonly_and_release(tmp_path):
    database = tmp_path / "owner.duckdb"
    with EvidenceStore(database) as store:
        import_curated_erap1(store)
        with pytest.raises(StoreOwnershipError):
            EvidenceStore(database)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from axis.storage import EvidenceStore\n"
                "from axis.storage.ownership import StoreOwnershipError\n"
                "import sys\ntry: EvidenceStore(sys.argv[1])\n"
                "except StoreOwnershipError: sys.exit(23)",
                str(database),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 23, result.stderr
    with EvidenceStore(database, read_only=True) as store:
        assert WorkspaceService(store).project(PROJECT)["project_kind"] == "curated"
        with pytest.raises(StoreOwnershipError):
            EvidenceStore(database)
        with pytest.raises(duckdb.Error):
            store._connection.execute("CREATE TABLE forbidden (value INTEGER)")
    with EvidenceStore(database) as store:
        assert store.statistics().schema_version == 11
    broken = tmp_path / "broken.duckdb"
    broken.write_text("not a DuckDB database")
    for _ in range(2):
        with pytest.raises(duckdb.Error):
            EvidenceStore(broken)


def test_http_serialization_guards_and_assets(tmp_path: Path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("<title>AXIS</title>")
    with EvidenceStore() as store:
        import_curated_erap1(store)
        with WorkspaceServer(store, port=0, static_root=assets) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port)
            try:
                connection.request("GET", f"/api/projects/{PROJECT}/evidence?limit=1")
                response = connection.getresponse()
                assert response.status == 200
                assert json.loads(response.read())["total"] == 14
                assert response.getheader("Content-Security-Policy")
                for method, path, headers, status in (
                    ("POST", "/api/projects", {}, 405),
                    ("GET", "/api/projects?limit=101", {}, 400),
                    ("GET", "/api/projects", {"Host": "untrusted.example"}, 403),
                    (
                        "GET",
                        "/api/projects",
                        {"Origin": "https://foreign.example"},
                        403,
                    ),
                    ("GET", "/projects/a/overview", {}, 200),
                    ("GET", "/assets/missing.js", {}, 404),
                    ("GET", "/%2e%2e/private", {}, 400),
                    ("GET", "/C%3A/Windows/win.ini", {}, 400),
                    ("GET", "/%00", {}, 400),
                ):
                    connection.request(method, path, headers=headers)
                    response = connection.getresponse()
                    response.read()
                    assert response.status == status
            finally:
                connection.close()
                server.shutdown()
                thread.join(timeout=3)
