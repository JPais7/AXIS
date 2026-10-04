"""Immutable decision records; project and protein scoped, append-only history."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from axis.domain.decision import (
    CandidateExperimentProfile,
    CompetingExplanation,
    DecisionConsequence,
    DecisionConstraints,
    DecisionState,
    OutcomeInterpretation,
)
from axis.storage import RecordConflictError, RecordNotFoundError

if TYPE_CHECKING:
    from axis.storage import EvidenceStore


def _encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)


class DecisionRepository:
    def __init__(self, store: "EvidenceStore") -> None:
        self.store = store

    @property
    def _db(self) -> Any:
        return self.store._connection

    def _same(self, table: str, key: str, identifier: str, payload: object) -> bool:
        row = self._db.execute(
            f"SELECT payload FROM {table} WHERE {key}=?", [identifier]
        ).fetchone()
        if row is None:
            return False
        if json.loads(row[0]) != json.loads(_encode(payload)):
            raise RecordConflictError(f"immutable decision record conflict: {table}")
        return True

    def add_explanation(self, protein: str, value: CompetingExplanation) -> None:
        self.store.targets.require_member(value.project_id, protein)
        self.store.hypotheses.get(value.hypothesis_id)
        payload = asdict(value) | {"knowledge_kind": value.knowledge_kind.value}
        if self._same("decision_explanations", "id", value.id, payload):
            return
        self._db.execute(
            "INSERT INTO decision_explanations VALUES (?,?,?,?,?,?,?)",
            [
                value.id,
                value.project_id,
                protein,
                value.hypothesis_id,
                value.hypothesis_revision,
                value.ground,
                _encode(payload),
            ],
        )

    def explanations(self, project: str, protein: str) -> list[dict[str, Any]]:
        self.store.targets.require_member(project, protein)
        rows = self._db.execute(
            "SELECT payload FROM decision_explanations WHERE project_id=? "
            "AND protein_id=? ORDER BY id",
            [project, protein],
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def add_profile(
        self,
        project: str,
        protein: str,
        profile: CandidateExperimentProfile,
        discriminates: tuple[str, ...],
    ) -> None:
        self.store.targets.require_member(project, protein)
        experiment = self.store.proposed_experiments.get(profile.experiment_id)
        if experiment.project_id != project:
            raise ValueError("experiment belongs to a different project")
        payload = asdict(profile)
        if not self._same(
            "candidate_experiment_profiles",
            "experiment_id",
            profile.experiment_id,
            payload,
        ):
            self._db.execute(
                "INSERT INTO candidate_experiment_profiles VALUES (?,?,?,?,?)",
                [
                    profile.experiment_id,
                    project,
                    protein,
                    profile.purpose,
                    _encode(payload),
                ],
            )
        for gap in profile.addressed_gap_ids:
            self._db.execute(
                "INSERT INTO decision_experiment_gaps VALUES (?,?) "
                "ON CONFLICT DO NOTHING",
                [profile.experiment_id, gap],
            )
        for explanation in discriminates:
            self._db.execute(
                "INSERT INTO decision_experiment_discriminates VALUES (?,?) "
                "ON CONFLICT DO NOTHING",
                [profile.experiment_id, explanation],
            )

    def add_interpretation(self, value: OutcomeInterpretation) -> None:
        row = self._db.execute(
            "SELECT effect, rationale FROM outcome_interpretations "
            "WHERE scenario_id=? AND explanation_id=?",
            [value.scenario_id, value.explanation_id],
        ).fetchone()
        if row:
            if tuple(row) != (value.effect, value.rationale):
                raise RecordConflictError("immutable outcome interpretation conflict")
            return
        self._db.execute(
            "INSERT INTO outcome_interpretations VALUES (?,?,?,?)",
            [value.scenario_id, value.explanation_id, value.effect, value.rationale],
        )

    def add_consequence(self, value: DecisionConsequence) -> None:
        payload = asdict(value)
        if self._same(
            "decision_consequences", "scenario_id", value.scenario_id, payload
        ):
            return
        self._db.execute(
            "INSERT INTO decision_consequences VALUES (?,?,?,?)",
            [value.scenario_id, value.scenario_kind, value.category, _encode(payload)],
        )

    def profile(self, project: str, protein: str, experiment_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT payload FROM candidate_experiment_profiles "
            "WHERE experiment_id=? AND project_id=? AND protein_id=?",
            [experiment_id, project, protein],
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("candidate experiment outside scope or not found")
        return dict(json.loads(row[0]))

    def profiles(self, project: str, protein: str) -> list[dict[str, Any]]:
        self.store.targets.require_member(project, protein)
        rows = self._db.execute(
            "SELECT experiment_id FROM candidate_experiment_profiles "
            "WHERE project_id=? AND protein_id=? ORDER BY experiment_id",
            [project, protein],
        ).fetchall()
        return [self.profile(project, protein, row[0]) for row in rows]

    def interpretations(self, experiment_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT i.scenario_id, i.explanation_id, i.effect, i.rationale "
            "FROM outcome_interpretations i JOIN outcome_scenarios s "
            "ON i.scenario_id=s.scenario_id WHERE s.experiment_id=? "
            "ORDER BY i.scenario_id, i.explanation_id",
            [experiment_id],
        ).fetchall()
        return [
            {
                "scenario_id": r[0],
                "explanation_id": r[1],
                "effect": r[2],
                "rationale": r[3],
            }
            for r in rows
        ]

    def consequences(self, experiment_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT c.payload FROM decision_consequences c JOIN outcome_scenarios s "
            "ON c.scenario_id=s.scenario_id WHERE s.experiment_id=? "
            "ORDER BY c.scenario_id",
            [experiment_id],
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def gap_links(self, experiment_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT gap_id FROM decision_experiment_gaps WHERE experiment_id=? "
            "ORDER BY gap_id",
            [experiment_id],
        ).fetchall()
        return [row[0] for row in rows]

    def discriminates(self, experiment_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT explanation_id FROM decision_experiment_discriminates "
            "WHERE experiment_id=? ORDER BY explanation_id",
            [experiment_id],
        ).fetchall()
        return [row[0] for row in rows]

    # -- constraints -------------------------------------------------------

    def add_constraints(self, value: DecisionConstraints) -> None:
        self.store.projects.get(value.project_id)
        latest = self.latest_constraints(value.project_id)
        expected = 1 if latest is None else latest["version"] + 1
        if value.version != expected or value.supersedes_id != (
            latest["id"] if latest else None
        ):
            raise ValueError("constraints must append the next version")
        payload = asdict(value) | {"created_at": value.created_at.isoformat()}
        self._db.execute(
            "INSERT INTO decision_constraints VALUES (?,?,?,?,?)",
            [
                value.id,
                value.project_id,
                value.version,
                value.supersedes_id,
                _encode(payload),
            ],
        )

    def latest_constraints(self, project: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT payload FROM decision_constraints WHERE project_id=? "
            "ORDER BY version DESC LIMIT 1",
            [project],
        ).fetchone()
        return None if row is None else dict(json.loads(row[0]))

    # -- decision states ---------------------------------------------------

    def add_state(self, state: DecisionState, payload: dict[str, Any]) -> None:
        self.store.targets.require_member(state.project_id, state.protein_id)
        if self._same("decision_states", "id", state.id, payload):
            return
        latest = self.latest_state(state.project_id, state.protein_id)
        expected = 1 if latest is None else latest["version"] + 1
        if state.version != expected or state.supersedes_id != (
            latest["id"] if latest else None
        ):
            raise ValueError("a DecisionState must append the next version")
        self._db.execute(
            "INSERT INTO decision_states VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                state.id,
                state.project_id,
                state.protein_id,
                state.version,
                state.supersedes_id,
                state.hypothesis_id,
                state.hypothesis_revision,
                state.critical_uncertainty_id,
                state.recommended_experiment_id,
                state.evidence_digest,
                state.rules_version,
                state.status,
                state.created_at,
                _encode(payload),
            ],
        )
        for item in payload["uncertainties"]:
            self._db.execute(
                "INSERT INTO decision_uncertainties VALUES (?,?,?,?,?,?,?)",
                [
                    state.id,
                    item["id"],
                    item["category"],
                    item["status"],
                    item["decision_relevance"],
                    item["resolvability"],
                    _encode(item),
                ],
            )
            for gap in item["source_gap_ids"]:
                self._db.execute(
                    "INSERT INTO decision_uncertainty_gaps VALUES (?,?,?)",
                    [state.id, item["id"], gap],
                )
        for item in payload["explanations"]:
            self._db.execute(
                "INSERT INTO decision_explanation_states VALUES (?,?,?,?)",
                [state.id, item["id"], item["status"], _encode(item)],
            )
            for ordinal, link in enumerate(item["links"]):
                self._db.execute(
                    "INSERT INTO decision_explanation_links VALUES (?,?,?,?,?,?,?,?)",
                    [
                        state.id,
                        item["id"],
                        ordinal,
                        link["relationship"],
                        link["evidence_type"],
                        link["evidence_id"],
                        link["rule_id"],
                        link["rationale"],
                    ],
                )
        self._db.execute(
            "INSERT INTO critical_uncertainty_assessments VALUES (?,?,?)",
            [state.id, state.critical_uncertainty_id, _encode(payload["critical"])],
        )

    def latest_state(self, project: str, protein: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT payload FROM decision_states WHERE project_id=? AND protein_id=? "
            "ORDER BY version DESC LIMIT 1",
            [project, protein],
        ).fetchone()
        return None if row is None else dict(json.loads(row[0]))

    def state(self, project: str, protein: str, identifier: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT payload FROM decision_states WHERE id=? AND project_id=? "
            "AND protein_id=?",
            [identifier, project, protein],
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("decision state outside scope or not found")
        return dict(json.loads(row[0]))

    def history(
        self, project: str, protein: str, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        self.store.targets.require_member(project, protein)
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError("invalid collection bounds")
        total_row = self._db.execute(
            "SELECT count(*) FROM decision_states WHERE project_id=? AND protein_id=?",
            [project, protein],
        ).fetchone()
        total = int(total_row[0]) if total_row else 0
        rows = self._db.execute(
            "SELECT payload FROM decision_states WHERE project_id=? AND protein_id=? "
            "ORDER BY version DESC LIMIT ? OFFSET ?",
            [project, protein, limit, offset],
        ).fetchall()
        return {
            "items": [json.loads(r[0]) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }

    # -- append-only events ------------------------------------------------

    def add_event(
        self,
        identifier: str,
        project: str,
        subject_type: str,
        subject_id: str,
        event_type: str,
        from_value: str,
        to_value: str,
        actor: str,
        note: str,
        created_at: datetime,
        result_claim_id: str | None = None,
    ) -> None:
        self._db.execute(
            "INSERT INTO decision_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                identifier,
                project,
                subject_type,
                subject_id,
                event_type,
                from_value,
                to_value,
                actor,
                note,
                result_claim_id,
                created_at,
            ],
        )

    def events(
        self, project: str, subject_id: str | None = None
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, subject_type, subject_id, event_type, from_value, to_value, "
            "actor, note, result_claim_id, created_at FROM decision_events "
            "WHERE project_id=?"
        )
        args: list[object] = [project]
        if subject_id:
            query += " AND subject_id=?"
            args.append(subject_id)
        rows = self._db.execute(query + " ORDER BY created_at, id", args).fetchall()
        keys = (
            "id",
            "subject_type",
            "subject_id",
            "event_type",
            "from_value",
            "to_value",
            "actor",
            "note",
            "result_claim_id",
            "created_at",
        )
        return [
            dict(zip(keys, row, strict=True)) | {"created_at": row[-1].isoformat()}
            for row in rows
        ]
