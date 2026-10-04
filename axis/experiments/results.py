"""Result package validation and import; review recording; read projections.

Importing never rebuilds a DecisionState. Eligibility is *computed* from stored,
append-only facts (results, QC, interpretations, reviews, events) by the pure rules
in :mod:`axis.experiments.policy`.
"""

import csv
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.domain.models import KnowledgeKind
from axis.domain.results import (
    DesignDeviation,
    ExperimentalArtifact,
    ExperimentalResult,
    PerformedExperiment,
    QualityAssessment,
    ResultInterpretation,
    ScenarioMatch,
    ScientificReview,
)
from axis.experiments import policy
from axis.storage import EvidenceStore, RecordNotFoundError
from axis.storage.results import row_id

IMPORTER_VERSION = "axis-results-1"
SIGNATURE_IMPORTER_VERSION = "axis-scenario-signatures-1"
SIGNATURES = "resources/experimental-results/scenario-signatures/erap1-axspa/v1"
SYNTHETIC = "resources/experimental-results/synthetic/erap1-decision-loop/v1"


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class ResultsService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    # -- packages -----------------------------------------------------------

    @staticmethod
    def package_root(default: str, directory: Path | None) -> Any:
        return directory or resources.files("axis").joinpath(default)

    def _load(self, root: Any) -> tuple[dict[str, Any], str]:
        raw = root.joinpath("manifest.json").read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != root.joinpath("manifest.sha256").read_text().strip():
            raise ValueError("experimental result package checksum mismatch")
        return json.loads(raw), digest

    def import_signatures(
        self, project: str, directory: Path | None = None
    ) -> dict[str, Any]:
        """Frozen anticipated-outcome signatures (AI-suggested, review pending)."""
        root = self.package_root(SIGNATURES, directory)
        package, digest = self._load(root)
        if package["importer_version"] != SIGNATURE_IMPORTER_VERSION:
            raise ValueError("unsupported scenario-signature importer")
        with self.store._transaction():
            for scenario, facets in sorted(package["signatures"].items()):
                self.store.results.add_signature(
                    scenario,
                    {
                        "facets": facets,
                        "knowledge_kind": "ai_suggestion",
                        "package_checksum": digest,
                        "review_status": "pending_expert_review",
                    },
                )
        return {"manifest_sha256": digest, "signatures": len(package["signatures"])}

    def validate_package(
        self,
        project: str,
        directory: Path | None = None,
        *,
        allow_synthetic: bool = False,
        base: Path | None = None,
    ) -> dict[str, Any]:
        """Validate without writing. Raises ValueError with an explicit message."""
        root = self.package_root(SYNTHETIC, directory)
        package, digest = self._load(root)
        problems = self._problems(project, package, root, allow_synthetic)
        if problems:
            raise ValueError("invalid result package: " + "; ".join(problems))
        return {
            "manifest_sha256": digest,
            "package_id": package["package_id"],
            "experiments": len(package["experiments"]),
            "results": len(package["results"]),
            "scientific_status": package["scientific_status"],
        }

    def _problems(
        self, project: str, package: dict[str, Any], root: Any, allow_synthetic: bool
    ) -> list[str]:
        problems: list[str] = []
        try:
            self.store.projects.get(project)
        except RecordNotFoundError:
            return [f"unknown project {project!r}"]
        if package.get("importer_version") != IMPORTER_VERSION:
            problems.append("unsupported result importer version")
        if package.get("project_id") != project:
            problems.append("package project does not match the target project")
        status = package.get("scientific_status")
        if status not in ("real", "synthetic_test_fixture"):
            problems.append(
                "scientific_status must be 'real' or 'synthetic_test_fixture'"
            )
        if status == "synthetic_test_fixture":
            if package.get("not_real_experimental_evidence") is not True:
                problems.append(
                    "a synthetic package must state not_real_experimental_evidence: true"
                )
            if not allow_synthetic:
                problems.append(
                    "synthetic test fixtures require explicit --allow-synthetic"
                )
        elif package.get("not_real_experimental_evidence"):
            problems.append("a real package cannot declare itself not real evidence")
        compounds = {
            c["id"]
            for p in self.store.targets.project_ids(project)
            for c in self.store.pharmacology.collection(
                project, p, "compounds", 100, 0
            )["items"]
        }
        experiments = {e["id"]: e for e in package["experiments"]}
        for e in package["experiments"]:
            if e.get("compound_id") and e["compound_id"] not in compounds:
                problems.append(
                    f"experiment {e['id']}: unknown compound {e['compound_id']!r}"
                )
            if not e.get("measures_edges"):
                problems.append(f"experiment {e['id']}: measures_edges is required")
        for r in package["results"]:
            e = experiments.get(r.get("experiment_id", ""))
            if e is None:
                problems.append(
                    f"result {r.get('id')}: unknown experiment {r.get('experiment_id')!r}"
                )
                continue
            if r.get("endpoint") not in e["endpoints"]:
                problems.append(
                    f"result {r['id']}: endpoint {r.get('endpoint')!r} is not an endpoint of {e['id']}"
                )
            if r.get("knowledge_kind", "experimental_result") != "experimental_result":
                problems.append(
                    f"result {r['id']}: epistemic class must be experimental_result"
                )
            if not r.get("recorded_by") and not package.get("recorded_by"):
                problems.append(f"result {r['id']}: recorded_by is required")
        known = {a["id"] for a in package["artifacts"]}
        for a in package["artifacts"]:
            path = root.joinpath(a["path"])
            try:
                data = path.read_bytes()
            except OSError:
                problems.append(f"artifact {a['id']}: file {a['path']!r} is missing")
                continue
            if hashlib.sha256(data).hexdigest() != a["sha256"]:
                problems.append(
                    f"artifact {a['id']}: checksum mismatch (file modified)"
                )
        for r in package["results"]:
            for a in (
                *r.get("raw_artifact_ids", []),
                *r.get("processed_artifact_ids", []),
            ):
                if a not in known:
                    problems.append(f"result {r['id']}: unknown artifact {a!r}")
        result_ids = {r["id"] for r in package["results"]}
        for i in package["interpretations"]:
            if i["result_id"] not in result_ids:
                problems.append(
                    f"interpretation {i['id']}: unknown result {i['result_id']!r}"
                )
        return problems

    def import_package(
        self,
        project: str,
        directory: Path | None = None,
        *,
        allow_synthetic: bool = False,
        protein: str | None = None,
    ) -> dict[str, Any]:
        """Idempotent, transactional import. Does not touch any DecisionState."""
        root = self.package_root(SYNTHETIC, directory)
        package, digest = self._load(root)
        problems = self._problems(project, package, root, allow_synthetic)
        if problems:
            raise ValueError("invalid result package: " + "; ".join(problems))
        status = package["scientific_status"]
        proteins = self.store.targets.project_ids(project)
        protein_id = protein or (proteins[0] if len(proteins) == 1 else None)
        default_actor = package.get("recorded_by", "unknown")
        now = _when(package.get("recorded_at")) or datetime.now(UTC)
        counts = {"artifacts": 0, "experiments": 0, "results": 0, "interpretations": 0}
        with self.store._transaction():
            for a in package["artifacts"]:
                self.store.results.add_artifact(
                    ExperimentalArtifact(
                        a["id"],
                        project,
                        f"{package['package_id']}/{a['path']}",
                        a["sha256"],
                        a["media_type"],
                        len(root.joinpath(a["path"]).read_bytes()),
                        a.get("role", "raw"),
                        a.get("description", ""),
                    )
                )
                counts["artifacts"] += 1
            for e in package["experiments"]:
                experiment = PerformedExperiment(
                    id=e["id"],
                    project_id=project,
                    protein_id=protein_id,
                    scope_type=e["scope"]["scope_type"],
                    scope_id=e["scope"]["scope_id"],
                    measures_edges=tuple(e["measures_edges"]),
                    endpoints=tuple(e["endpoints"]),
                    scientific_status=status,
                    proposal_id=e.get("proposal_id"),
                    executed_at=_when(e.get("executed_at")),
                    performed_by=e.get("performed_by"),
                    context=e.get("context", {}),
                    perturbation=e.get("perturbation"),
                    compound_id=e.get("compound_id"),
                    reported_perturbagen=e.get("reported_perturbagen"),
                    target_label=e.get("target_label"),
                    construct=e.get("construct", "not reported"),
                    assay=e.get("assay"),
                    controls=tuple(e.get("controls", [])),
                    exposure=e.get("exposure"),
                    protocol_reference=e.get("protocol_reference"),
                    source_artifact_ids=tuple(e.get("source_artifact_ids", [])),
                )
                self.store.results.add_experiment(experiment)
                counts["experiments"] += 1
                for d in e.get("deviations", []):
                    self.store.results.add_deviation(
                        DesignDeviation(
                            f"{e['id']}:dev:{d['field']}",
                            e["id"],
                            d["field"],
                            d["proposed"],
                            d["actual"],
                            d["type"],
                            d["rationale"],
                            d.get("relevance", "limits_interpretation"),
                            e.get("proposal_id"),
                        )
                    )
                if "qc" in e:
                    q = e["qc"]
                    self.store.results.add_qc(
                        QualityAssessment(
                            f"{e['id']}:qc",
                            e["id"],
                            q["control_status"],
                            q["technical_validity"],
                            q["replicate_quality"],
                            q["assessment"],
                            q["rationale"],
                            q.get("missing_data", "none reported"),
                        )
                    )
            rows: dict[str, str] = {}
            for r in package["results"]:
                value = ExperimentalResult(
                    id=r["id"],
                    version=r.get("version", 1),
                    project_id=project,
                    performed_experiment_id=r["experiment_id"],
                    endpoint=r["endpoint"],
                    result_type=r["result_type"],
                    recorded_at=now,
                    recorded_by=r.get("recorded_by", default_actor),
                    qualitative_result=r.get("qualitative_result"),
                    numeric_value=r.get("numeric_value"),
                    operator=r.get("operator", "="),
                    unit=r.get("unit"),
                    uncertainty=r.get("uncertainty"),
                    replicate_summary=r.get("replicates", {}),
                    statistics=r.get("statistics", {}),
                    raw_artifact_ids=tuple(r.get("raw_artifact_ids", [])),
                    processed_artifact_ids=tuple(r.get("processed_artifact_ids", [])),
                    transformations=tuple(r.get("transformations", [])),
                    analysis_method=r.get("analysis", {}).get("method"),
                    analysis_version=r.get("analysis", {}).get("version"),
                    observed_at=_when(r.get("observed_at")),
                    facets=r.get("facets", {}),
                    supersedes_id=r.get("supersedes_id"),
                )
                rows[r["id"]] = self.store.results.add_result(value)
                counts["results"] += 1
                self._match(project, rows[r["id"]], value, package)
            for i in package["interpretations"]:
                self.store.results.add_interpretation(
                    ResultInterpretation(
                        i["id"],
                        rows[i["result_id"]],
                        i["edge"],
                        i["scope_type"],
                        i["scope_id"],
                        i["proposed_state"],
                        i["statement"],
                        i["rationale"],
                        KnowledgeKind(i.get("knowledge_kind", "ai_suggestion")),
                        i.get("generated_by", "AXIS AI-assisted suggestion"),
                        tuple(i.get("caveats", [])),
                    )
                )
                counts["interpretations"] += 1
        return {
            "manifest_sha256": digest,
            "package_id": package["package_id"],
            "scientific_status": status,
            **counts,
            "decision_state_changed": False,
            "next": "review the result and interpretation, then run `axis decision rebuild`",
        }

    def _match(
        self, project: str, row: str, value: ExperimentalResult, package: dict[str, Any]
    ) -> None:
        experiment = self.store.results.experiment(
            project, value.performed_experiment_id
        )
        qc = self.store.results.qc(value.performed_experiment_id)
        signatures = (
            self.store.results.signatures(experiment["proposal_id"])
            if experiment.get("proposal_id")
            else {}
        )
        outcome = policy.match_scenarios(
            value.facets,
            signatures,
            non_interpretable=value.result_type
            in ("technical_failure", "non_interpretable")
            or bool(qc and qc["assessment"] == "non_interpretable"),
        )
        for item in outcome["per_scenario"]:
            if item["relationship"] == "ambiguous":
                continue
            self.store.results.add_match(
                ScenarioMatch(
                    f"{row}:match:{item['scenario_id']}",
                    row,
                    item["relationship"],
                    f"matched {item['matched']}; conflicting {item['conflicting']}; "
                    f"unobserved {item['unobserved']}",
                    outcome["rule_version"],
                    item["scenario_id"],
                    tuple(item["matched"]),
                    tuple(item["conflicting"]),
                    tuple(item["unobserved"]),
                )
            )
        text = {
            "matches": "The observation matches an anticipated outcome scenario.",
            "partially_matches": "The observation matches part of an anticipated scenario.",
            "outside_predefined_scenarios": "Observed result falls outside the predefined outcome scenarios.",
            "ambiguous": "No anticipated scenario can be compared with the observed facets.",
            "non_interpretable": "The result is non-interpretable; no scenario comparison is made.",
            "contradicts": "The observation contradicts the anticipated scenarios.",
        }[outcome["overall"]]
        self.store.results.add_match(
            ScenarioMatch(
                f"{row}:match:overall",
                row,
                outcome["overall"],
                text,
                outcome["rule_version"],
            )
        )

    # -- reviews --------------------------------------------------------------------

    def record_review(
        self,
        project: str,
        object_type: str,
        object_id: str,
        reviewer: str,
        decision: str,
        rationale: str,
        caveat: str | None = None,
        *,
        reviewed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Explicit investigator action. History is append-only; nothing is deleted."""
        self._require_object(project, object_type, object_id)
        previous = [
            r
            for r in self.store.results.reviews(project, object_type, object_id)
            if r["reviewer"] == reviewer
        ]
        count = len(self.store.results.reviews(project, object_type, object_id))
        value = ScientificReview(
            f"review:{object_type}:{object_id}:{count + 1}",
            project,
            object_type,
            object_id,
            reviewer,
            decision,
            rationale,
            reviewed_at or datetime.now(UTC),
            caveat,
            previous[-1]["id"] if previous else None,
        )
        self.store.results.add_review(value)
        return self.review_state(project, object_type, object_id) | {
            "review_id": value.id
        }

    def _require_object(self, project: str, object_type: str, object_id: str) -> None:
        if object_type == "experimental_result":
            self.store.results.result(project, object_id)
        elif object_type == "result_interpretation":
            self.store.results.interpretation(object_id)
        elif object_type == "scenario_mapping":
            scenario, _, explanation = object_id.partition("|")
            row = self.store._connection.execute(
                "SELECT 1 FROM outcome_interpretations WHERE scenario_id=? AND explanation_id=?",
                [scenario, explanation],
            ).fetchone()
            if row is None:
                raise RecordNotFoundError(
                    "scenario mapping not found (use 'scenario|explanation')"
                )
        elif object_type == "candidate_design":
            self.store.proposed_experiments.get(object_id)
        elif object_type == "evidence_assessment":
            row = self.store._connection.execute(
                "SELECT 1 FROM cellular_assessments WHERE id=?", [object_id]
            ).fetchone()
            if row is None:
                raise RecordNotFoundError("evidence assessment not found")

    def review_state(
        self, project: str, object_type: str, object_id: str
    ) -> dict[str, Any]:
        reviews = self.store.results.reviews(project, object_type, object_id)
        return policy.review_state(reviews) | {"history": reviews}

    def withdraw(
        self, project: str, result_row: str, actor: str, note: str = ""
    ) -> dict[str, Any]:
        self.store.results.result(project, result_row)
        self.store.results.add_event(
            f"event:{result_row}:withdrawn",
            project,
            result_row,
            "withdrawn",
            actor,
            note,
            datetime.now(UTC),
        )
        return {"result": result_row, "event": "withdrawn"}

    def correct(self, project: str, corrected: ExperimentalResult) -> str:
        """Record a correction as a new superseding version (never an overwrite)."""
        return self.store.results.add_result(corrected)

    # -- projections ------------------------------------------------------------------

    def ledger(
        self,
        project: str,
        mode: str = "exploratory",
        overrides: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Every (result, interpretation) with its eligibility under ``mode``.

        ``overrides`` maps interpretation id -> hypothetical review state and is used
        only by the decision-impact preview; nothing is persisted.
        """
        overrides = overrides or {}
        events = {
            e["result_id"]
            for e in self.store.results.events(project)
            if e["event_type"] == "withdrawn"
        }
        out: list[dict[str, Any]] = []
        for result in self.store.results.results(project):
            experiment = self.store.results.experiment(
                project, result["performed_experiment_id"]
            )
            qc = self.store.results.qc(experiment["id"])
            deviations = self.store.results.deviations(experiment["id"])
            latest = self.store.results.latest_version(project, result["id"])
            result_review = self.review_state(
                project, "experimental_result", result["row_id"]
            )
            for interpretation in self.store.results.interpretations(result["row_id"]):
                interp_review = self.review_state(
                    project, "result_interpretation", interpretation["id"]
                )
                if interpretation["id"] in overrides:
                    interp_review = {
                        "state": overrides[interpretation["id"]],
                        "reviewers": ["preview"],
                        "caveats": [],
                        "history": [],
                    }
                    if result_review["state"] == "pending":
                        result_review = {
                            "state": overrides[interpretation["id"]],
                            "reviewers": ["preview"],
                            "caveats": [],
                            "history": [],
                        }
                verdict = policy.contribution_eligibility(
                    result=result,
                    qc=qc,
                    interpretation=interpretation,
                    experiment=experiment,
                    result_review=result_review,
                    interpretation_review=interp_review,
                    superseded=latest is not None and latest > result["version"],
                    withdrawn=result["row_id"] in events,
                    deviations=deviations,
                    mode=mode,
                )
                matches = self.store.results.matches(result["row_id"])
                overall = next(
                    (m for m in matches if m["outcome_scenario_id"] is None), None
                )
                out.append(
                    {
                        "result_row": result["row_id"],
                        "result_id": result["id"],
                        "version": result["version"],
                        "interpretation_id": interpretation["id"],
                        "experiment_id": experiment["id"],
                        "proposal_id": experiment.get("proposal_id"),
                        "edge": interpretation["edge"],
                        "scope_type": interpretation["scope_type"],
                        "scope_id": interpretation["scope_id"],
                        "state": interpretation["proposed_state"],
                        "statement": interpretation["statement"],
                        "context": experiment["context"],
                        "synthetic": experiment["scientific_status"] != "real",
                        "scientific_status": experiment["scientific_status"],
                        "independent_replicates": _independent(result),
                        "scenario_match": overall["relationship"]
                        if overall
                        else "ambiguous",
                        "matched_scenarios": [
                            m["outcome_scenario_id"]
                            for m in matches
                            if m["outcome_scenario_id"]
                            and m["relationship"] in ("matches", "partially_matches")
                        ],
                        "eligibility": verdict,
                        "result_review": result_review["state"],
                        "interpretation_review": interp_review["state"],
                    }
                )
        return out

    def experiment_detail(self, project: str, experiment_id: str) -> dict[str, Any]:
        experiment = self.store.results.experiment(project, experiment_id)
        results = self.store.results.results(project, experiment_id)
        return {
            "experiment": experiment,
            "proposal": self._proposal(experiment.get("proposal_id")),
            "deviations": self.store.results.deviations(experiment_id),
            "qc": self.store.results.qc(experiment_id),
            "results": [
                self.result_detail(project, r["row_id"], summary=True) for r in results
            ],
            "synthetic": experiment["scientific_status"] != "real",
        }

    def _proposal(self, identifier: str | None) -> dict[str, Any] | None:
        if not identifier:
            return None
        p = self.store.proposed_experiments.get(identifier)
        return {
            "experiment_id": p.experiment_id,
            "title": p.title,
            "knowledge_kind": p.knowledge_kind.value,
            "status": p.status.value,
        }

    def result_detail(
        self, project: str, row: str, *, summary: bool = False
    ) -> dict[str, Any]:
        result = self.store.results.result(project, row)
        entries = [
            e for e in self.ledger(project, "exploratory") if e["result_row"] == row
        ]
        detail: dict[str, Any] = {
            "result": result,
            "observed": {
                k: result[k]
                for k in (
                    "endpoint",
                    "result_type",
                    "qualitative_result",
                    "numeric_value",
                    "operator",
                    "unit",
                    "uncertainty",
                    "replicate_summary",
                    "statistics",
                    "facets",
                )
            },
            "interpretations": [
                self.store.results.interpretation(e["interpretation_id"])
                | {
                    "review": self.review_state(
                        project, "result_interpretation", e["interpretation_id"]
                    ),
                    "eligibility": e["eligibility"],
                }
                for e in entries
            ],
            "scenario_matches": self.store.results.matches(row),
            "review": self.review_state(project, "experimental_result", row),
            "events": self.store.results.events(project, row),
            "superseded_by": self._superseded_by(project, result),
        }
        if not summary:
            experiment = self.store.results.experiment(
                project, result["performed_experiment_id"]
            )
            detail["artifacts"] = self.store.results.artifacts_of(row)
            detail["qc"] = self.store.results.qc(experiment["id"])
            detail["deviations"] = self.store.results.deviations(experiment["id"])
            detail["experiment"] = experiment
            detail["synthetic"] = experiment["scientific_status"] != "real"
        return detail

    def _superseded_by(self, project: str, result: dict[str, Any]) -> str | None:
        latest = self.store.results.latest_version(project, result["id"])
        return (
            row_id(result["id"], latest)
            if latest and latest > result["version"]
            else None
        )

    def review_packet(self, project: str, row: str) -> dict[str, Any]:
        detail = self.result_detail(project, row)
        experiment = detail["experiment"]
        return {
            "experiment": {
                "id": experiment["id"],
                "what_was_done": {
                    k: experiment.get(k)
                    for k in (
                        "assay",
                        "controls",
                        "exposure",
                        "context",
                        "perturbation",
                    )
                },
            },
            "deviations": detail["deviations"],
            "results": detail["observed"],
            "qc": detail["qc"],
            "scenario_match": detail["scenario_matches"],
            "proposed_interpretations": [
                {
                    k: i[k]
                    for k in (
                        "id",
                        "statement",
                        "edge",
                        "scope_type",
                        "scope_id",
                        "proposed_state",
                        "caveats",
                        "knowledge_kind",
                    )
                }
                for i in detail["interpretations"]
            ],
            "evidence_update": [
                {
                    "edge": i["edge"],
                    "scope": f"{i['scope_type']}:{i['scope_id']}",
                    "proposed_state": i["proposed_state"],
                }
                for i in detail["interpretations"]
            ],
            "reviewer_decision": detail["review"]["state"],
            "artifacts": detail["artifacts"],
            "synthetic": detail["synthetic"],
            "decision_impact": "use `axis experiment result impact` (preview; not applied)",
        }

    def verify_artifacts(self, project: str, base: Path) -> list[dict[str, str]]:
        """Re-hash artifact files under ``base``; report every mismatch or missing file."""
        problems = []
        rows = self.store._connection.execute(
            "SELECT id, uri, sha256 FROM experiment_artifacts WHERE project_id=?",
            [project],
        ).fetchall()
        for identifier, uri, expected in rows:
            path = base / uri.split("/", 1)[-1]
            if not path.is_file():
                problems.append({"artifact": identifier, "problem": "file missing"})
            elif sha256_file(path) != expected:
                problems.append(
                    {"artifact": identifier, "problem": "checksum mismatch"}
                )
        return problems


def _independent(result: dict[str, Any]) -> int:
    summary = result.get("replicate_summary", {})
    return (
        int(summary.get("independent_experiments") or 1)
        if summary.get("type") == "independent_experiment"
        else 1
    )


def asdict_result(value: ExperimentalResult) -> dict[str, Any]:
    return asdict(value)
