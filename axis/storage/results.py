"""Immutable experimental results, interpretations and append-only review history."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

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
from axis.storage import RecordConflictError, RecordNotFoundError

if TYPE_CHECKING:
    from axis.storage import EvidenceStore


def encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=_default)


def _default(value: object) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"not serializable: {type(value)!r}")


def row_id(logical_id: str, version: int) -> str:
    return f"{logical_id}@v{version}"


class ResultsRepository:
    def __init__(self, store: "EvidenceStore") -> None:
        self.store = store

    @property
    def _db(self) -> Any:
        return self.store._connection

    def _same(
        self, table: str, identifier: str, payload: object, key: str = "id"
    ) -> bool:
        row = self._db.execute(
            f"SELECT payload FROM {table} WHERE {key}=?", [identifier]
        ).fetchone()
        if row is None:
            return False
        if json.loads(row[0]) != json.loads(encode(payload)):
            raise RecordConflictError(
                f"immutable record conflict in {table}: {identifier}"
            )
        return True

    # -- artifacts -----------------------------------------------------------

    def add_artifact(self, value: ExperimentalArtifact) -> None:
        self.store.projects.get(value.project_id)
        row = self._db.execute(
            "SELECT uri, sha256, media_type, size_bytes, role, description "
            "FROM experiment_artifacts WHERE id=?",
            [value.id],
        ).fetchone()
        wanted = (
            value.uri,
            value.sha256,
            value.media_type,
            value.size_bytes,
            value.role,
            value.description,
        )
        if row:
            if tuple(row) != wanted:
                raise RecordConflictError(
                    f"artifact {value.id!r} already recorded with different content"
                )
            return
        self._db.execute(
            "INSERT INTO experiment_artifacts VALUES (?,?,?,?,?,?,?,?)",
            [value.id, value.project_id, *wanted],
        )

    def artifact(self, identifier: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT id, project_id, uri, sha256, media_type, size_bytes, role, "
            "description FROM experiment_artifacts WHERE id=?",
            [identifier],
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"artifact {identifier!r} not found")
        keys = (
            "id",
            "project_id",
            "uri",
            "sha256",
            "media_type",
            "size_bytes",
            "role",
            "description",
        )
        return dict(zip(keys, row, strict=True))

    # -- performed experiments ----------------------------------------------

    def add_experiment(self, value: PerformedExperiment) -> None:
        self.store.projects.get(value.project_id)
        if value.protein_id:
            self.store.targets.require_member(value.project_id, value.protein_id)
        if value.proposal_id:
            proposal = self.store.proposed_experiments.get(value.proposal_id)
            if proposal.project_id != value.project_id:
                raise ValueError("proposal belongs to a different project")
        for artifact in value.source_artifact_ids:
            self.artifact(artifact)
        payload = asdict(value)
        if self._same("performed_experiments", value.id, payload):
            return
        self._db.execute(
            "INSERT INTO performed_experiments VALUES (?,?,?,?,?,?,?,?)",
            [
                value.id,
                value.project_id,
                value.protein_id,
                value.proposal_id,
                value.scope_type,
                value.scope_id,
                value.scientific_status,
                encode(payload),
            ],
        )

    def experiment(self, project: str, identifier: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT payload FROM performed_experiments WHERE id=? AND project_id=?",
            [identifier, project],
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("performed experiment outside scope or not found")
        return dict(json.loads(row[0]))

    def experiments(self, project: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT payload FROM performed_experiments WHERE project_id=? ORDER BY id",
            [project],
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def add_deviation(self, value: DesignDeviation) -> None:
        payload = asdict(value)
        if self._same("experiment_design_deviations", value.id, payload):
            return
        self._db.execute(
            "INSERT INTO experiment_design_deviations VALUES (?,?,?,?)",
            [
                value.id,
                value.performed_experiment_id,
                value.proposed_experiment_id,
                encode(payload),
            ],
        )

    def deviations(self, experiment_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT payload FROM experiment_design_deviations "
            "WHERE performed_experiment_id=? ORDER BY id",
            [experiment_id],
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def add_qc(self, value: QualityAssessment) -> None:
        payload = asdict(value)
        if self._same("experimental_quality_assessments", value.id, payload):
            return
        self._db.execute(
            "INSERT INTO experimental_quality_assessments VALUES (?,?,?,?,?)",
            [
                value.id,
                value.performed_experiment_id,
                value.supersedes_id,
                value.assessment,
                encode(payload),
            ],
        )

    def qc(self, experiment_id: str) -> dict[str, Any] | None:
        rows = self._db.execute(
            "SELECT id, payload FROM experimental_quality_assessments "
            "WHERE performed_experiment_id=?",
            [experiment_id],
        ).fetchall()
        superseded = {json.loads(p).get("supersedes_id") for _, p in rows}
        current = [json.loads(p) for i, p in rows if i not in superseded]
        return current[-1] if current else None

    # -- results ---------------------------------------------------------------

    def add_result(self, value: ExperimentalResult) -> str:
        experiment = self._db.execute(
            "SELECT project_id FROM performed_experiments WHERE id=?",
            [value.performed_experiment_id],
        ).fetchone()
        if experiment is None or experiment[0] != value.project_id:
            raise ValueError(
                "result experiment is unknown or belongs to another project"
            )
        for artifact in (*value.raw_artifact_ids, *value.processed_artifact_ids):
            self.artifact(artifact)
        identifier = row_id(value.id, value.version)
        payload = asdict(value)
        if self._same("experimental_results", identifier, payload):
            return identifier
        if value.version > 1:
            previous = row_id(value.id, value.version - 1)
            if (
                value.supersedes_id != previous
                or not self._db.execute(
                    "SELECT 1 FROM experimental_results WHERE id=?", [previous]
                ).fetchone()
            ):
                raise ValueError("a correction must supersede the previous version")
        self._db.execute(
            "INSERT INTO experimental_results VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                identifier,
                value.project_id,
                value.id,
                value.version,
                value.supersedes_id,
                value.performed_experiment_id,
                value.endpoint,
                value.result_type,
                value.knowledge_kind.value,
                value.recorded_at,
                encode(payload),
            ],
        )
        for role, ids in (
            ("raw", value.raw_artifact_ids),
            ("processed", value.processed_artifact_ids),
        ):
            for artifact in ids:
                self._db.execute(
                    "INSERT INTO result_artifacts VALUES (?,?,?) ON CONFLICT DO NOTHING",
                    [identifier, artifact, role],
                )
        return identifier

    def result(self, project: str, identifier: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT payload FROM experimental_results WHERE id=? AND project_id=?",
            [identifier, project],
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("result outside scope or not found")
        return dict(json.loads(row[0])) | {"row_id": identifier}

    def results(
        self, project: str, experiment_id: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT id, payload FROM experimental_results WHERE project_id=?"
        args: list[object] = [project]
        if experiment_id:
            query += " AND performed_experiment_id=?"
            args.append(experiment_id)
        rows = self._db.execute(
            query + " ORDER BY logical_id, version", args
        ).fetchall()
        return [dict(json.loads(p)) | {"row_id": i} for i, p in rows]

    def latest_version(self, project: str, logical_id: str) -> int | None:
        row = self._db.execute(
            "SELECT max(version) FROM experimental_results WHERE project_id=? AND logical_id=?",
            [project, logical_id],
        ).fetchone()
        return None if row is None or row[0] is None else int(row[0])

    def artifacts_of(self, result_row: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT artifact_id, role FROM result_artifacts WHERE result_id=? ORDER BY 1,2",
            [result_row],
        ).fetchall()
        return [self.artifact(a) | {"link_role": r} for a, r in rows]

    def add_event(
        self,
        identifier: str,
        project: str,
        result_row: str,
        event_type: str,
        actor: str,
        note: str,
        created_at: datetime,
    ) -> None:
        if event_type != "withdrawn":
            raise ValueError("unsupported result event")
        if not actor.strip():
            raise ValueError("an investigator is required")
        self._db.execute(
            "INSERT INTO result_events VALUES (?,?,?,?,?,?,?)",
            [identifier, project, result_row, event_type, actor, note, created_at],
        )

    def events(
        self, project: str, result_row: str | None = None
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, result_id, event_type, actor, note, created_at "
            "FROM result_events WHERE project_id=?"
        )
        args: list[object] = [project]
        if result_row:
            query += " AND result_id=?"
            args.append(result_row)
        rows = self._db.execute(query + " ORDER BY created_at, id", args).fetchall()
        keys = ("id", "result_id", "event_type", "actor", "note", "created_at")
        return [
            dict(zip(keys, r, strict=True)) | {"created_at": r[-1].isoformat()}
            for r in rows
        ]

    # -- interpretations, matches, signatures -----------------------------------

    def add_interpretation(self, value: ResultInterpretation) -> None:
        payload = asdict(value) | {"knowledge_kind": value.knowledge_kind.value}
        if self._same("result_interpretations", value.id, payload):
            return
        self._db.execute(
            "INSERT INTO result_interpretations VALUES (?,?,?,?,?,?,?)",
            [
                value.id,
                value.result_id,
                value.edge,
                value.scope_type,
                value.scope_id,
                value.knowledge_kind.value,
                encode(payload),
            ],
        )

    def interpretations(
        self, result_row: str | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        if result_row:
            rows = self._db.execute(
                "SELECT payload FROM result_interpretations WHERE result_id=? ORDER BY id",
                [result_row],
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT i.payload FROM result_interpretations i JOIN experimental_results r "
                "ON i.result_id=r.id WHERE r.project_id=? ORDER BY i.id",
                [project],
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def interpretation(self, identifier: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT payload FROM result_interpretations WHERE id=?", [identifier]
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"interpretation {identifier!r} not found")
        return dict(json.loads(row[0]))

    def add_signature(self, scenario_id: str, payload: dict[str, Any]) -> None:
        if self._same("scenario_signatures", scenario_id, payload, key="scenario_id"):
            return
        self._db.execute(
            "INSERT INTO scenario_signatures VALUES (?,?)",
            [scenario_id, encode(payload)],
        )

    def signatures(self, proposal_id: str) -> dict[str, dict[str, str]]:
        rows = self._db.execute(
            "SELECT s.scenario_id, s.payload FROM scenario_signatures s "
            "JOIN outcome_scenarios o ON s.scenario_id=o.scenario_id "
            "WHERE o.experiment_id=? ORDER BY 1",
            [proposal_id],
        ).fetchall()
        return {sid: dict(json.loads(p)["facets"]) for sid, p in rows}

    def add_match(self, value: ScenarioMatch) -> None:
        payload = asdict(value)
        if self._same("scenario_match_assessments", value.id, payload):
            return
        self._db.execute(
            "INSERT INTO scenario_match_assessments VALUES (?,?,?,?,?,?)",
            [
                value.id,
                value.result_id,
                value.outcome_scenario_id,
                value.relationship,
                value.rule_version,
                encode(payload),
            ],
        )

    def matches(self, result_row: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT payload FROM scenario_match_assessments WHERE result_id=? ORDER BY id",
            [result_row],
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    # -- reviews ------------------------------------------------------------------

    def add_review(self, value: ScientificReview) -> None:
        self.store.projects.get(value.project_id)
        if value.supersedes_review_id:
            previous = self._db.execute(
                "SELECT reviewer, object_type, object_id FROM scientific_reviews WHERE id=?",
                [value.supersedes_review_id],
            ).fetchone()
            if previous is None or tuple(previous) != (
                value.reviewer,
                value.object_type,
                value.object_id,
            ):
                raise ValueError(
                    "a review may only supersede the same reviewer's review"
                )
        existing = self._db.execute(
            "SELECT 1 FROM scientific_reviews WHERE id=?", [value.id]
        ).fetchone()
        if existing:
            raise RecordConflictError(
                f"review {value.id!r} already exists (append-only)"
            )
        self._db.execute(
            "INSERT INTO scientific_reviews VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                value.id,
                value.project_id,
                value.object_type,
                value.object_id,
                value.reviewer,
                value.decision,
                value.rationale,
                value.caveat,
                value.supersedes_review_id,
                value.reviewed_at,
            ],
        )

    def reviews(
        self, project: str, object_type: str | None = None, object_id: str | None = None
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, object_type, object_id, reviewer, decision, rationale, caveat, "
            "supersedes_review_id, reviewed_at FROM scientific_reviews WHERE project_id=?"
        )
        args: list[object] = [project]
        if object_type:
            query += " AND object_type=?"
            args.append(object_type)
        if object_id:
            query += " AND object_id=?"
            args.append(object_id)
        rows = self._db.execute(query + " ORDER BY reviewed_at, id", args).fetchall()
        keys = (
            "id",
            "object_type",
            "object_id",
            "reviewer",
            "decision",
            "rationale",
            "caveat",
            "supersedes_review_id",
            "reviewed_at",
        )
        return [
            dict(zip(keys, r, strict=True)) | {"reviewed_at": r[-1].isoformat()}
            for r in rows
        ]

    # -- links to decision states ----------------------------------------------------

    def link_state(
        self,
        state_id: str,
        result_row: str,
        interpretation_id: str,
        eligibility: str,
        review_state: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO decision_result_links VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
            [state_id, result_row, interpretation_id, eligibility, review_state],
        )

    def state_links(self, state_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT result_id, interpretation_id, eligibility, review_state "
            "FROM decision_result_links WHERE decision_state_id=? ORDER BY 1,2",
            [state_id],
        ).fetchall()
        keys = ("result_id", "interpretation_id", "eligibility", "review_state")
        return [dict(zip(keys, r, strict=True)) for r in rows]
