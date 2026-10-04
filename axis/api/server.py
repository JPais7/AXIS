"""Loopback-only, single-owner local server with bounded read endpoints."""

from __future__ import annotations

import json
import mimetypes
from dataclasses import asdict
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from axis.cellular.service import CellularPharmacologyService
from axis.decision.service import DecisionService
from axis.discovery.workspace import WorkspaceService, page
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore, RecordNotFoundError
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService


def json_default(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"cannot encode {type(value).__name__}")


class ReadAPI:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store
        self.workspace = WorkspaceService(store)

    def _decision(self, parts: list[str], limit: int, offset: int) -> dict[str, Any]:
        project, kind = parts[2], parts[3]
        proteins = self.store.targets.project_ids(project)
        if len(proteins) != 1:
            raise RecordNotFoundError("decision requires exactly one project protein")
        protein = proteins[0]
        service = DecisionService(self.store)
        tail = parts[4:]
        if kind == "decision" and tail == ["history"]:
            return self.store.decisions.history(project, protein, limit, offset)
        if kind == "candidate-experiments" and len(tail) == 1:
            return service.candidate(project, protein, tail[0])
        if tail:
            raise RecordNotFoundError("decision route not found")
        if kind == "decision":
            state = self.store.decisions.latest_state(project, protein)
            if state is None:
                return {
                    "state": None,
                    "message": "No DecisionState has been built for this project; "
                    "run `axis decision build`.",
                }
            return {"state": state}
        state = service.current(project, protein)
        if kind == "uncertainties":
            return {
                "items": state["uncertainties"],
                "critical": state["critical"],
                "state_id": state["id"],
            }
        if kind == "explanations":
            return {
                "items": state["explanations"],
                "not_admitted": state["excluded_explanations"],
                "state_id": state["id"],
            }
        if kind == "candidate-experiments":
            return {
                "items": state["candidates"],
                "recommended_experiment_id": state["recommended_experiment_id"],
                "constraints": state["constraints"],
                "state_id": state["id"],
            }
        return {
            "state_id": state["id"],
            "trace": state["trace"],
            "graph": state["graph"],
            "diff": state["diff"],
        }

    def get(self, path: str, query: dict[str, list[str]]) -> dict[str, Any]:
        if any(
            key
            not in (
                "limit",
                "offset",
                "project_id",
                "domain",
                "claim_ids",
                "compound",
                "target",
                "endpoint",
                "assay_type",
                "source",
            )
            for key in query
        ):
            raise ValueError("unsupported query parameter")
        if any(len(values) != 1 for values in query.values()):
            raise ValueError("query parameters must not be repeated")
        if "claim_ids" in query and not path.endswith("/compare"):
            raise ValueError("claim_ids is only supported for comparison")
        limit = int(query.get("limit", ["50"])[0])
        offset = int(query.get("offset", ["0"])[0])
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError("limit must be 1–100; offset must be 0–100000")
        parts = [unquote(part) for part in path.strip("/").split("/")]
        chemical_filters: dict[str, str] = {
            key: query[key][0]
            for key in ("compound", "target", "endpoint", "assay_type", "source")
            if key in query
        }
        chemical_route = (
            len(parts) >= 6
            and parts[:2] == ["api", "projects"]
            and parts[3] == "targets"
            and parts[5] in {"compounds", "assays", "measurements", "selectivity"}
        )
        cellular_route = (
            len(parts) >= 6
            and parts[:2] == ["api", "projects"]
            and parts[3] == "targets"
            and parts[5] == "cellular"
        )
        decision_route = (
            len(parts) >= 4
            and parts[:2] == ["api", "projects"]
            and parts[3]
            in {
                "decision",
                "uncertainties",
                "explanations",
                "candidate-experiments",
                "decision-trace",
            }
        )
        if decision_route:
            if chemical_filters:
                raise ValueError("decision routes do not support filters")
            return self._decision(parts, limit, offset)
        if cellular_route:
            if any(k != "compound" for k in chemical_filters):
                raise ValueError("cellular route only supports compound filter")
            project, protein = parts[2], parts[4]
            cellular_service = CellularPharmacologyService(self.store)
            compound = chemical_filters.get("compound")
            kind = parts[6] if len(parts) > 6 else "overview"
            if len(parts) == 8 and kind == "experiments" and not compound:
                return cellular_service.detail(project, protein, parts[7])
            if len(parts) > 7:
                raise RecordNotFoundError("cellular route not found")
            if kind in {"experiments", "readouts", "assessments", "immunopeptidome"}:
                return self.store.cellular.collection(
                    project, protein, kind, limit, offset, compound
                )
            if kind in {"overview", "evidence-chain", "engagement", "decision"}:
                return cellular_service.chain(project, protein, compound)
            if kind == "gaps":
                return cellular_service.gaps(project, protein, compound)
            if kind == "concordance" and not compound:
                return cellular_service.comparisons(project, protein)
            if kind == "review-packet" and not compound:
                return cellular_service.review_packet(project, protein)
            raise RecordNotFoundError("cellular route not found")
        if chemical_filters and not chemical_route:
            raise ValueError("pharmacology filters require a pharmacology route")
        if chemical_route:
            project, protein, kind = parts[2], parts[4], parts[5]
            if len(parts) == 6:
                result = self.store.pharmacology.collection(
                    project, protein, kind, limit, offset, chemical_filters
                )
                if kind == "measurements":
                    for item in result["items"]:
                        item["assay"] = self.store.pharmacology.record(
                            "assays", item["assay_id"]
                        )
                        item["compound_name"] = self.store.pharmacology.record(
                            "compounds", item["compound_id"]
                        )["preferred_name"]
                return result
            if chemical_filters:
                raise ValueError("filters apply only to collections")
            if len(parts) == 7 or len(parts) == 8 and parts[7] == "provenance":
                return PharmacologyService(self.store).detail(
                    project, protein, kind, parts[6]
                )
            raise RecordNotFoundError("pharmacology route not found")
        if parts == ["api", "projects"]:
            projects = self.store.projects.list_all(limit=limit, offset=offset)
            return page(
                [
                    {
                        "project": asdict(item),
                        "pair": asdict(
                            self.store.target_disease_pairs.get(
                                item.target_disease_pair
                            )
                        ),
                    }
                    for item in projects
                ],
                self.store.projects.count(),
                limit,
                offset,
            )
        if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
            project_id = parts[2]
            if len(parts) == 3:
                return self.workspace.project(project_id)
            if len(parts) >= 4 and parts[3] == "targets":
                service = TargetIdentityService(self.store)
                if len(parts) == 4:
                    identifiers = self.store.targets.project_ids(project_id)
                    return page(
                        [
                            service.projection(project_id, identifier)
                            for identifier in identifiers[offset : offset + limit]
                        ],
                        len(identifiers),
                        limit,
                        offset,
                    )
                if len(parts) >= 6 and parts[5] == "structures":
                    structural = StructureIdentityService(self.store)
                    protein = parts[4]
                    if len(parts) == 6:
                        ids = self.store.structures.list_ids(project_id, protein)
                        return page(
                            [
                                structural.projection(project_id, protein, i)
                                for i in ids[offset : offset + limit]
                            ],
                            len(ids),
                            limit,
                            offset,
                        )
                    if len(parts) not in (7, 8):
                        raise RecordNotFoundError("structure route not found")
                    identity = parts[6]
                    data = structural.projection(project_id, protein, identity)
                    if len(parts) == 7:
                        return data
                    if parts[7] == "chains":
                        return {"chains": data["chains"]}
                    if parts[7] == "mapping":
                        return structural.mapping(project_id, protein, identity)
                    if parts[7] == "provenance":
                        return {
                            "snapshot": data["snapshot"],
                            "mappings": structural.mapping(
                                project_id, protein, identity
                            ),
                        }
                    if parts[7] == "coordinates":
                        return {
                            "format": "mmcif",
                            "raw_sha256": data["structure"]["raw_file_checksum"],
                            "content": self.store.structures.coordinates(
                                identity
                            ).decode(),
                        }
                    raise RecordNotFoundError("structure route not found")
                if len(parts) not in (5, 6):
                    raise RecordNotFoundError("target route not found")
                projection = service.projection(project_id, parts[4])
                if len(parts) == 5:
                    return projection
                if parts[5] == "protein":
                    return {"protein": projection["protein"]}
                if parts[5] == "isoforms":
                    return {"isoforms": projection["isoforms"]}
                if parts[5] == "provenance":
                    return {
                        "snapshot": projection["snapshot"],
                        "mappings": projection["mappings"],
                        "sequence_checksum": projection["protein"]["sequence_checksum"],
                    }
                raise RecordNotFoundError("target route not found")
            if len(parts) != 4:
                raise RecordNotFoundError("API route not found")
            route = parts[3]
            self.store.projects.get(project_id)
            if route == "compare":
                return self.workspace.compare(
                    project_id, query.get("claim_ids", [""])[0].split(",")
                )
            if route == "evidence":
                return self.workspace.evidence(
                    project_id, limit, offset, query.get("domain", [None])[0]
                )
            if route == "mechanism":
                return self.workspace.mechanisms(project_id, limit, offset)
            if route == "sources":
                return self.workspace.sources(project_id, limit, offset)
            if route == "strategies":
                items = self.store.strategies.list_for_project(
                    project_id, limit=limit, offset=offset
                )
                return page(
                    [asdict(item) for item in items],
                    self.store.strategies.count(project_id),
                    limit,
                    offset,
                )
            if route == "assessments":
                assessments = self.store.evidence_assessments.list_for_project(
                    project_id, limit=limit, offset=offset
                )
                return page(
                    [asdict(item) for item in assessments],
                    self.store.evidence_assessments.count(project_id),
                    limit,
                    offset,
                )
            if route == "perturbations":
                perturbations = self.store.perturbations.list_for_project(
                    project_id, limit=limit, offset=offset
                )
                return page(
                    [asdict(item) for item in perturbations],
                    self.store.perturbations.count(project_id),
                    limit,
                    offset,
                )
            if route == "questions":
                questions = self.store.questions.list_for_project(
                    project_id, limit=limit, offset=offset
                )
                return page(
                    [
                        {
                            "question": asdict(item),
                            "links": asdict(
                                self.store.questions.links(item.question_id, limit=100)
                            ),
                            "link_limit": 100,
                        }
                        for item in questions
                    ],
                    self.store.questions.count(project_id),
                    limit,
                    offset,
                )
            if route == "experiments":
                outcome_repository = self.store.outcome_scenarios
                experiments = self.store.proposed_experiments.list_for_project(
                    project_id, limit=limit, offset=offset
                )
                return page(
                    [
                        {
                            "experiment": asdict(item),
                            "outcomes": [
                                asdict(outcome)
                                for outcome in outcome_repository.list_for_experiment(
                                    item.experiment_id, limit=100
                                )
                            ],
                            "outcome_limit": 100,
                        }
                        for item in experiments
                    ],
                    self.store.proposed_experiments.count(project_id),
                    limit,
                    offset,
                )
        if len(parts) == 3 and parts[:2] in (["api", "claims"], ["api", "sources"]):
            project_id = query.get("project_id", [""])[0]
            if not project_id:
                raise ValueError("project_id is required for evidence/source isolation")
            if parts[1] == "claims":
                return self.workspace.claim(project_id, parts[2])
            return self.workspace.source(project_id, parts[2], limit, offset)
        raise RecordNotFoundError("API route not found")


class WorkspaceServer(HTTPServer):
    def __init__(
        self, store: EvidenceStore, port: int = 8765, static_root: Path | None = None
    ) -> None:
        self.api = ReadAPI(store)
        self.static_root = static_root
        super().__init__(("127.0.0.1", port), WorkspaceHandler)


class WorkspaceHandler(BaseHTTPRequestHandler):
    server: WorkspaceServer

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict[str, Any]) -> None:
        self._send(
            status,
            json.dumps(value, default=json_default).encode(),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            self._json(403, {"error": "local host header required"})
            return
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in hosts}:
            self._json(403, {"error": "cross-origin request rejected"})
            return
        parsed = urlsplit(self.path)
        if parsed.path.startswith("/api/"):
            try:
                self._json(
                    200,
                    self.server.api.get(
                        parsed.path, parse_qs(parsed.query, keep_blank_values=True)
                    ),
                )
            except RecordNotFoundError as error:
                self._json(404, {"error": str(error)})
            except ValueError as error:
                self._json(400, {"error": str(error)})
            return
        name = unquote(parsed.path).lstrip("/")
        if ".." in name.split("/") or "\\" in name or ":" in name or "\x00" in name:
            self._json(400, {"error": "invalid asset path"})
            return
        if self.server.static_root is not None:
            root = self.server.static_root.resolve()
            asset = (root / name).resolve()
            if not asset.is_relative_to(root):
                self._json(400, {"error": "invalid asset path"})
                return
            if not asset.is_file():
                if "." in Path(name).name:
                    self._json(404, {"error": "asset not found"})
                    return
                asset = root / "index.html"
                name = "index.html"
            if not asset.is_file():
                self._json(503, {"error": "workspace assets not built"})
                return
            body = asset.read_bytes()
        else:
            root_resource = resources.files("axis").joinpath("resources/workspace")
            resource = root_resource.joinpath(name or "index.html")
            if not resource.is_file():
                if "." in Path(name).name:
                    self._json(404, {"error": "asset not found"})
                    return
                resource = root_resource.joinpath("index.html")
                name = "index.html"
            if not resource.is_file():
                self._json(503, {"error": "workspace assets not built"})
                return
            body = resource.read_bytes()
        content_type = mimetypes.guess_type(name or "index.html")[0] or "text/html"
        if name.endswith(".js"):
            content_type = "application/javascript"
        self._send(200, body, content_type)

    def do_POST(self) -> None:
        self._json(405, {"error": "read-first API does not accept writes"})

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

    def log_message(self, format: str, *args: Any) -> None:
        pass
