"""Focused discovery repositories sharing the existing EvidenceStore connection.

Scalar fields and relationships are relational. Only nested context/provenance
use JSON, preserving ordered transformations without another identity system.
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from axis.domain.discovery import (
    DiscoveryProject,
    EvidenceAssessment,
    EvidenceRole,
    InterventionStrategy,
    MechanismClassification,
    MechanisticAssessment,
    OpenQuestion,
    OutcomeScenario,
    Perturbation,
    PerturbationDirection,
    PerturbationStatus,
    PerturbationType,
    ProjectStatus,
    ProposalOrigin,
    ProposalStatus,
    ProposedExperiment,
    QuestionLinks,
    QuestionStatus,
    StrategyStatus,
    StrategyType,
    TargetDiseasePair,
)
from axis.domain.models import (
    Claim,
    ClaimContext,
    EntityKind,
    EntityRef,
    KnowledgeKind,
    Provenance,
    SourceKind,
    Transformation,
)
from axis.storage.store import RecordConflictError, RecordNotFoundError

if TYPE_CHECKING:
    from axis.storage.store import EvidenceStore


def _bounds(limit: int | None, offset: int) -> tuple[str, list[int]]:
    if offset < 0 or (limit is not None and not 1 <= limit <= 100):
        raise ValueError("limit must be 1–100 and offset must be nonnegative")
    if limit is None:
        if offset:
            raise ValueError("offset requires a limit")
        return "", []
    return " LIMIT ? OFFSET ?", [limit, offset]


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot encode {type(value).__name__}")


def _provenance(payload: str) -> Provenance:
    value = json.loads(payload)
    return Provenance(
        source_kind=SourceKind(value["source_kind"]),
        source_identifier=value["source_identifier"],
        retrieved_at=datetime.fromisoformat(value["retrieved_at"]),
        source_uri=value["source_uri"],
        checksum=value["checksum"],
        transformations=tuple(
            Transformation(
                step["name"],
                step["version"],
                tuple((key, item) for key, item in step["parameters"]),
            )
            for step in value["transformations"]
        ),
    )


class _ImmutableRepository[
    Record: (
        TargetDiseasePair,
        DiscoveryProject,
        Perturbation,
        InterventionStrategy,
        OpenQuestion,
        EvidenceAssessment,
        MechanisticAssessment,
        ProposedExperiment,
        OutcomeScenario,
    )
]:
    """Small storage helper; table/column names are internal constants only."""

    table: str
    key: str
    model: type[Record]
    enums: dict[str, type[StrEnum]] = {}
    entity_fields: tuple[str, ...] = ()

    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    def _entity(self, kind: str, namespace: str, identifier: str) -> EntityRef:
        row = self._store._connection.execute(
            "SELECT label FROM entities WHERE kind=? AND namespace=? AND identifier=?",
            [kind, namespace, identifier],
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"entity {namespace}:{identifier} not found")
        return EntityRef(EntityKind(kind), identifier, row[0], namespace)

    def get_optional(self, identifier: str) -> Record | None:
        connection = self._store._connection
        cursor = connection.execute(
            f"SELECT * FROM {self.table} WHERE {self.key}=?", [identifier]
        )
        row = cursor.fetchone()
        if row is None:
            return None
        value: dict[str, Any] = dict(
            zip((column[0] for column in cursor.description), row, strict=True)
        )
        value.pop("identity_key", None)
        for name in self.entity_fields:
            kind = value.pop(f"{name}_kind")
            namespace = value.pop(f"{name}_namespace")
            entity_id = value.pop(f"{name}_identifier")
            value[name] = (
                None if kind is None else self._entity(kind, namespace, entity_id)
            )
        for name, enum in self.enums.items():
            value[name] = enum(value[name])
        if "provenance" in value:
            value["provenance"] = _provenance(value["provenance"])
        if "scientific_context" in value:
            value["scientific_context"] = ClaimContext(
                **json.loads(value["scientific_context"])
            )
        return self.model(**value)

    def get(self, identifier: str) -> Record:
        record = self.get_optional(identifier)
        if record is None:
            raise RecordNotFoundError(f"{self.table} record {identifier!r} not found")
        return record

    def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> tuple[Record, ...]:
        bounds, parameters = _bounds(limit, offset)
        rows = self._store._connection.execute(
            f"SELECT {self.key} FROM {self.table} ORDER BY {self.key}" + bounds,
            parameters,
        ).fetchall()
        return tuple(self.get(row[0]) for row in rows)

    def list_for_project(
        self, project_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[Record, ...]:
        self._store.projects.get(project_id)
        parameters: list[int]
        bounds, parameters = _bounds(limit, offset)
        rows = self._store._connection.execute(
            f"SELECT {self.key} FROM {self.table} "
            f"WHERE project_id=? ORDER BY {self.key}" + bounds,
            [project_id, *parameters],
        ).fetchall()
        return tuple(self.get(row[0]) for row in rows)

    def _validate(self, record: Record) -> None:
        pass

    def count(self, project_id: str | None = None) -> int:
        clause = " WHERE project_id=?" if project_id is not None else ""
        row = self._store._connection.execute(
            f"SELECT count(*) FROM {self.table}" + clause,
            [project_id] if project_id is not None else [],
        ).fetchone()
        assert row is not None
        return int(row[0])

    def list_for_claim(
        self, project_id: str, claim_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[Record, ...]:
        self._store.projects._require_claim(project_id, claim_id)
        parameters: list[int]
        bounds, parameters = _bounds(limit, offset)
        rows = self._store._connection.execute(
            f"SELECT {self.key} FROM {self.table} "
            f"WHERE project_id=? AND claim_id=? ORDER BY {self.key}" + bounds,
            [project_id, claim_id, *parameters],
        ).fetchall()
        return tuple(self.get(row[0]) for row in rows)

    def add(self, record: Record) -> None:
        if not isinstance(record, self.model):
            raise TypeError(f"expected {self.model.__name__}")
        identifier = str(getattr(record, self.key))
        existing = self.get_optional(identifier)
        if existing is not None:
            if existing == record:
                return
            raise RecordConflictError(f"{self.table} {identifier!r} is immutable")
        with self._store._transaction():
            self._validate(record)
            values: dict[str, Any] = {}
            for item in fields(record):
                value = getattr(record, item.name)
                if item.name in self.entity_fields:
                    if value is not None:
                        self._store.claims._upsert_entity(value)
                    values[f"{item.name}_kind"] = value.kind.value if value else None
                    values[f"{item.name}_namespace"] = (
                        value.namespace if value else None
                    )
                    values[f"{item.name}_identifier"] = (
                        value.identifier if value else None
                    )
                elif isinstance(value, (Provenance, ClaimContext)):
                    values[item.name] = json.dumps(asdict(value), default=_json_default)
                else:
                    values[item.name] = (
                        value.value if isinstance(value, StrEnum) else value
                    )
            if isinstance(record, TargetDiseasePair):
                values["identity_key"] = record.identity_key
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            self._store._connection.execute(
                f"INSERT INTO {self.table} ({columns}) VALUES ({placeholders})",
                list(values.values()),
            )


class TargetDiseasePairRepository(_ImmutableRepository[TargetDiseasePair]):
    table, key, model = "target_disease_pairs", "pair_id", TargetDiseasePair
    entity_fields = ("target", "disease")

    def _validate(self, record: TargetDiseasePair) -> None:
        row = self._store._connection.execute(
            "SELECT pair_id FROM target_disease_pairs WHERE identity_key=?",
            [record.identity_key],
        ).fetchone()
        if row is not None:
            raise RecordConflictError(
                f"target/disease/scope already exists as {row[0]}"
            )


class DiscoveryProjectRepository(_ImmutableRepository[DiscoveryProject]):
    table, key, model = "discovery_projects", "project_id", DiscoveryProject
    enums = {"status": ProjectStatus}

    def _validate(self, record: DiscoveryProject) -> None:
        self._store.target_disease_pairs.get(record.target_disease_pair)

    def add_claim(self, project_id: str, claim_id: str) -> None:
        with self._store._transaction():
            self.get(project_id)
            self._store.claims.get(claim_id)
            self._store._connection.execute(
                "INSERT INTO project_claims VALUES (?, ?) ON CONFLICT DO NOTHING",
                [project_id, claim_id],
            )

    def claims(
        self, project_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[Claim, ...]:
        self.get(project_id)
        bounds, parameters = _bounds(limit, offset)
        rows = self._store._connection.execute(
            "SELECT claim_id FROM project_claims WHERE project_id=? ORDER BY claim_id"
            + bounds,
            [project_id, *parameters],
        ).fetchall()
        return tuple(self._store.claims.get(row[0]) for row in rows)

    def _require_claim(self, project_id: str, claim_id: str) -> Claim:
        self.get(project_id)
        claim = self._store.claims.get(claim_id)
        if (
            self._store._connection.execute(
                "SELECT 1 FROM project_claims WHERE project_id=? AND claim_id=?",
                [project_id, claim_id],
            ).fetchone()
            is None
        ):
            raise RecordNotFoundError("claim is not a member of this project")
        return claim

    def evidence_page(
        self,
        project_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        domain: str | None = None,
    ) -> tuple[tuple[Claim, ...], int]:
        self.get(project_id)
        bounds, parameters = _bounds(limit, offset)
        clause = ""
        arguments: list[str | int] = [project_id]
        if domain is not None:
            clause = " AND EXISTS (SELECT 1 FROM transformation_parameters t "
            clause += (
                "WHERE t.claim_identifier=p.claim_id AND t.key='domain' AND t.value=?)"
            )
            arguments.append(domain)
        query = " FROM project_claims p WHERE p.project_id=?" + clause
        count = self._store._connection.execute(
            "SELECT count(*)" + query, arguments
        ).fetchone()
        assert count is not None
        rows = self._store._connection.execute(
            "SELECT p.claim_id" + query + " ORDER BY p.claim_id" + bounds,
            [*arguments, *parameters],
        ).fetchall()
        return tuple(self._store.claims.get(row[0]) for row in rows), int(count[0])

    def evidence_domains(self, project_id: str) -> tuple[dict[str, Any], ...]:
        self.get(project_id)
        rows = self._store._connection.execute(
            "SELECT t.value, count(DISTINCT c.identifier), "
            "count(DISTINCT c.source_identifier), "
            "bool_or(c.predicate LIKE '%increases%'), "
            "bool_or(c.predicate LIKE '%decreases%') "
            "FROM project_claims p JOIN claims c ON c.identifier=p.claim_id "
            "JOIN transformation_parameters t ON t.claim_identifier=c.identifier "
            "WHERE p.project_id=? AND t.key='domain' "
            "AND c.knowledge_kind='source_assertion' GROUP BY t.value ORDER BY t.value",
            [project_id],
        ).fetchall()
        return tuple(
            dict(
                domain=row[0],
                claims=int(row[1]),
                sources=int(row[2]),
                increasing=bool(row[3]),
                decreasing=bool(row[4]),
            )
            for row in rows
        )

    def source_page(
        self, project_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[tuple[dict[str, Any], ...], int]:
        self.get(project_id)
        bounds, parameters = _bounds(limit, offset)
        total = self._store._connection.execute(
            "SELECT count(DISTINCT c.source_identifier) FROM project_claims p "
            "JOIN claims c ON c.identifier=p.claim_id WHERE p.project_id=?",
            [project_id],
        ).fetchone()
        assert total is not None
        rows = self._store._connection.execute(
            "SELECT c.source_identifier, c.source_kind, max(c.source_uri), "
            "max(c.retrieved_at), count(DISTINCT c.identifier), max(t.value) "
            "FROM project_claims p JOIN claims c ON c.identifier=p.claim_id "
            "LEFT JOIN transformation_parameters t ON t.claim_identifier=c.identifier "
            "AND t.key='source_title' WHERE p.project_id=? "
            "GROUP BY c.source_identifier,c.source_kind ORDER BY c.source_identifier"
            + bounds,
            [project_id, *parameters],
        ).fetchall()
        return tuple(
            dict(
                source_id=row[0],
                source_kind=row[1],
                source_uri=row[2],
                retrieved_at=row[3],
                claim_count=int(row[4]),
                title=row[5] or row[0],
            )
            for row in rows
        ), int(total[0])

    def source_projects(self, source_id: str, *, limit: int = 100) -> tuple[str, ...]:
        bounds, parameters = _bounds(limit, 0)
        rows = self._store._connection.execute(
            "SELECT DISTINCT p.project_id FROM project_claims p "
            "JOIN claims c ON c.identifier=p.claim_id WHERE c.source_identifier=? "
            "ORDER BY p.project_id" + bounds,
            [source_id, *parameters],
        ).fetchall()
        return tuple(row[0] for row in rows)


class PerturbationRepository(_ImmutableRepository[Perturbation]):
    table, key, model = "discovery_perturbations", "perturbation_id", Perturbation
    entity_fields = ("target", "intervention")
    enums = {
        "perturbation_type": PerturbationType,
        "direction": PerturbationDirection,
        "status": PerturbationStatus,
        "knowledge_kind": KnowledgeKind,
    }

    def _validate(self, record: Perturbation) -> None:
        if record.observed_effect_claim_id is not None:
            claim = self._store.claims.get(record.observed_effect_claim_id)
            if (
                claim.knowledge_kind
                not in (
                    KnowledgeKind.SOURCE_ASSERTION,
                    KnowledgeKind.AXIS_OBSERVATION,
                    KnowledgeKind.EXPERIMENTAL_RESULT,
                )
                or claim.provenance.source_kind == SourceKind.AI_MODEL
            ):
                raise ValueError("observed effects require an observational claim")

    def add_to_project(self, project_id: str, perturbation_id: str) -> None:
        with self._store._transaction():
            project = self._store.projects.get(project_id)
            pair = self._store.target_disease_pairs.get(project.target_disease_pair)
            perturbation = self.get(perturbation_id)
            if perturbation.target != pair.target:
                raise ValueError("perturbation target differs from project target")
            if perturbation.observed_effect_claim_id is not None:
                self._store.projects._require_claim(
                    project_id, perturbation.observed_effect_claim_id
                )
            self._store._connection.execute(
                "INSERT INTO project_perturbations VALUES (?, ?) "
                "ON CONFLICT DO NOTHING",
                [project_id, perturbation_id],
            )

    def list_for_project(
        self, project_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[Perturbation, ...]:
        self._store.projects.get(project_id)
        bounds, parameters = _bounds(limit, offset)
        rows = self._store._connection.execute(
            "SELECT perturbation_id FROM project_perturbations "
            "WHERE project_id=? ORDER BY perturbation_id" + bounds,
            [project_id, *parameters],
        ).fetchall()
        return tuple(self.get(row[0]) for row in rows)

    def count(self, project_id: str | None = None) -> int:
        if project_id is None:
            return super().count()
        row = self._store._connection.execute(
            "SELECT count(*) FROM project_perturbations WHERE project_id=?",
            [project_id],
        ).fetchone()
        assert row is not None
        return int(row[0])

    def for_effect(
        self, project_id: str, claim_id: str, *, limit: int = 100
    ) -> tuple[Perturbation, ...]:
        """Bounded stored perturbations linked to a project-member effect."""
        self._store.projects._require_claim(project_id, claim_id)
        bounds, parameters = _bounds(limit, 0)
        rows = self._store._connection.execute(
            "SELECT d.perturbation_id FROM discovery_perturbations d "
            "JOIN project_perturbations p ON p.perturbation_id=d.perturbation_id "
            "WHERE p.project_id=? AND d.observed_effect_claim_id=? "
            "ORDER BY d.perturbation_id" + bounds,
            [project_id, claim_id, *parameters],
        ).fetchall()
        return tuple(self.get(row[0]) for row in rows)


class InterventionStrategyRepository(_ImmutableRepository[InterventionStrategy]):
    table, key, model = "intervention_strategies", "strategy_id", InterventionStrategy
    enums = {
        "strategy_type": StrategyType,
        "status": StrategyStatus,
        "knowledge_kind": KnowledgeKind,
    }

    def _validate(self, record: InterventionStrategy) -> None:
        self._store.projects.get(record.project_id)


class OpenQuestionRepository(_ImmutableRepository[OpenQuestion]):
    table, key, model = "open_questions", "question_id", OpenQuestion
    enums = {"status": QuestionStatus}

    def _validate(self, record: OpenQuestion) -> None:
        self._store.projects.get(record.project_id)

    def link(self, question_id: str, links: QuestionLinks) -> None:
        """Validate the entire batch before writing any links; idempotent union."""
        with self._store._transaction():
            question = self.get(question_id)
            for claim_id in links.claim_ids:
                self._store.projects._require_claim(question.project_id, claim_id)
            for hypothesis_id in links.hypothesis_ids:
                self._store.hypotheses.get(hypothesis_id)
            for strategy_id in links.strategy_ids:
                if (
                    self._store.strategies.get(strategy_id).project_id
                    != question.project_id
                ):
                    raise ValueError("strategy belongs to a different project")
            project_perturbations = {
                row.perturbation_id
                for row in self._store.perturbations.list_for_project(
                    question.project_id
                )
            }
            for perturbation_id in links.perturbation_ids:
                self._store.perturbations.get(perturbation_id)
                if perturbation_id not in project_perturbations:
                    raise ValueError("perturbation is not a member of this project")
            for table, identifiers in (
                ("question_claims", links.claim_ids),
                ("question_hypotheses", links.hypothesis_ids),
                ("question_strategies", links.strategy_ids),
                ("question_perturbations", links.perturbation_ids),
            ):
                for identifier in identifiers:
                    self._store._connection.execute(
                        f"INSERT INTO {table} VALUES (?, ?) ON CONFLICT DO NOTHING",
                        [question_id, identifier],
                    )

    def links(self, question_id: str, *, limit: int | None = None) -> QuestionLinks:
        self.get(question_id)

        def identifiers(table: str, column: str) -> tuple[str, ...]:
            bounds, parameters = _bounds(limit, 0)
            rows = self._store._connection.execute(
                f"SELECT {column} FROM {table} WHERE question_id=? ORDER BY {column}"
                + bounds,
                [question_id, *parameters],
            ).fetchall()
            return tuple(row[0] for row in rows)

        return QuestionLinks(
            claim_ids=identifiers("question_claims", "claim_id"),
            hypothesis_ids=identifiers("question_hypotheses", "hypothesis_id"),
            strategy_ids=identifiers("question_strategies", "strategy_id"),
            perturbation_ids=identifiers("question_perturbations", "perturbation_id"),
        )


class EvidenceAssessmentRepository(_ImmutableRepository[EvidenceAssessment]):
    table, key, model = "evidence_assessments", "assessment_id", EvidenceAssessment
    enums = {"role": EvidenceRole}

    def _validate(self, record: EvidenceAssessment) -> None:
        claim = self._store.projects._require_claim(record.project_id, record.claim_id)
        if record.role != EvidenceRole.UNTYPED_CONSIDERED and (
            claim.knowledge_kind
            in (KnowledgeKind.AI_SUGGESTION, KnowledgeKind.RESEARCHER_HYPOTHESIS)
            or claim.provenance.source_kind == SourceKind.AI_MODEL
        ):
            raise ValueError("proposals cannot be assessed as observational evidence")
        if record.strategy_id is not None and (
            self._store.strategies.get(record.strategy_id).project_id
            != record.project_id
        ):
            raise ValueError("strategy belongs to a different project")
        if record.question_id is not None and (
            self._store.questions.get(record.question_id).project_id
            != record.project_id
        ):
            raise ValueError("question belongs to a different project")
        if record.hypothesis_id is not None:
            hypothesis = self._store.hypotheses.get(record.hypothesis_id)
            assert record.hypothesis_revision is not None
            if record.hypothesis_revision not in (
                revision.revision for revision in hypothesis.revisions
            ):
                raise RecordNotFoundError("hypothesis revision not found")


class MechanisticAssessmentRepository(_ImmutableRepository[MechanisticAssessment]):
    table, key, model = (
        "mechanistic_assessments",
        "assessment_id",
        MechanisticAssessment,
    )
    enums = {"classification": MechanismClassification}

    def _validate(self, record: MechanisticAssessment) -> None:
        claim = self._store.projects._require_claim(record.project_id, record.claim_id)
        allowed = {
            MechanismClassification.DIRECTLY_DEMONSTRATED: (
                KnowledgeKind.SOURCE_ASSERTION,
                KnowledgeKind.EXPERIMENTAL_RESULT,
                KnowledgeKind.AXIS_OBSERVATION,
            ),
            MechanismClassification.INFERRED: (KnowledgeKind.AXIS_INFERENCE,),
            MechanismClassification.COMPUTATIONALLY_PREDICTED: (
                KnowledgeKind.AXIS_OBSERVATION,
                KnowledgeKind.AXIS_INFERENCE,
            ),
            MechanismClassification.HYPOTHESIZED: (
                KnowledgeKind.RESEARCHER_HYPOTHESIS,
                KnowledgeKind.AI_SUGGESTION,
                KnowledgeKind.AXIS_INFERENCE,
            ),
        }
        if claim.knowledge_kind not in allowed[record.classification]:
            raise ValueError("mechanism classification is incompatible with claim kind")
        if claim.provenance.source_kind == SourceKind.AI_MODEL and (
            record.classification != MechanismClassification.HYPOTHESIZED
        ):
            raise ValueError("AI suggestions cannot establish mechanisms")


class ProposedExperimentRepository(_ImmutableRepository[ProposedExperiment]):
    table, key, model = "proposed_experiments", "experiment_id", ProposedExperiment
    enums = {
        "suggestion_origin": ProposalOrigin,
        "knowledge_kind": KnowledgeKind,
        "status": ProposalStatus,
    }

    def _validate(self, record: ProposedExperiment) -> None:
        self._store.projects.get(record.project_id)
        if (
            self._store.questions.get(record.question_id).project_id
            != record.project_id
        ):
            raise ValueError("question belongs to a different project")


class OutcomeScenarioRepository(_ImmutableRepository[OutcomeScenario]):
    table, key, model = "outcome_scenarios", "scenario_id", OutcomeScenario

    def _validate(self, record: OutcomeScenario) -> None:
        self._store.proposed_experiments.get(record.experiment_id)

    def list_for_experiment(
        self, experiment_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[OutcomeScenario, ...]:
        self._store.proposed_experiments.get(experiment_id)
        bounds, parameters = _bounds(limit, offset)
        rows = self._store._connection.execute(
            "SELECT scenario_id FROM outcome_scenarios "
            "WHERE experiment_id=? ORDER BY scenario_id" + bounds,
            [experiment_id, *parameters],
        ).fetchall()
        return tuple(self.get(row[0]) for row in rows)
