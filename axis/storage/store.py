"""Persistence boundary for scientific evidence.

Only this module knows how AXIS domain objects map to DuckDB tables.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from types import TracebackType
from typing import Self

import duckdb

from axis.domain import (
    Claim,
    ClaimContext,
    EntityKind,
    EntityRef,
    Hypothesis,
    HypothesisRevision,
    HypothesisState,
    KnowledgeKind,
    Provenance,
    SourceKind,
    Study,
    Transformation,
)
from axis.storage.ownership import StoreOwnership


class RecordNotFoundError(LookupError):
    """Raised when a requested scientific record does not exist."""


class RecordConflictError(ValueError):
    """Raised when an immutable identifier is reused for different content."""


@dataclass(frozen=True)
class StoreStatistics:
    studies: int
    claims: int
    hypotheses: int
    schema_version: int


class EvidenceStore:
    """Owns the DuckDB connection and exposes focused repositories."""

    def __init__(
        self, database: str | Path = ":memory:", *, read_only: bool = False
    ) -> None:
        database_path = Path(database) if database != ":memory:" else None
        if read_only and database_path is None:
            raise ValueError("read-only store requires an existing database file")
        self._ownership: StoreOwnership | None = None
        if database_path is not None:
            if read_only and not database_path.is_file():
                raise ValueError(
                    "read-only database does not exist; initialize it first"
                )
            if not read_only:
                database_path.parent.mkdir(parents=True, exist_ok=True)
            self._ownership = StoreOwnership(database_path)
            self._ownership.acquire()
        try:
            self._connection = duckdb.connect(
                str(database_path) if database_path is not None else ":memory:",
                read_only=read_only,
            )
        except Exception:
            if self._ownership is not None:
                self._ownership.release()
            raise
        self._closed = False
        self._transaction_depth = 0
        self._transaction_failed = False
        try:
            if read_only:
                root = resources.files("axis.storage.migrations")
                expected = max(
                    int(item.name[:3])
                    for item in root.iterdir()
                    if item.name.endswith(".sql") and item.name[:3].isdigit()
                )
                row = self._connection.execute(
                    "SELECT coalesce(max(version),0) FROM schema_migrations"
                ).fetchone()
                if row is None or row[0] != expected:
                    raise ValueError(
                        "database requires an explicit writable migration "
                        "before read-only serving"
                    )
            else:
                self._apply_migrations()
        except Exception:
            self.close()
            raise
        self.claims = ClaimRepository(self)
        self.hypotheses = HypothesisRepository(self)
        self.studies = StudyRepository(self)
        # Import here to keep the repositories dependent on this store boundary.
        from axis.storage.discovery import (
            DiscoveryProjectRepository,
            EvidenceAssessmentRepository,
            InterventionStrategyRepository,
            MechanisticAssessmentRepository,
            OpenQuestionRepository,
            OutcomeScenarioRepository,
            PerturbationRepository,
            ProposedExperimentRepository,
            TargetDiseasePairRepository,
        )

        self.target_disease_pairs = TargetDiseasePairRepository(self)
        self.projects = DiscoveryProjectRepository(self)
        self.perturbations = PerturbationRepository(self)
        self.strategies = InterventionStrategyRepository(self)
        self.questions = OpenQuestionRepository(self)
        self.evidence_assessments = EvidenceAssessmentRepository(self)
        self.mechanistic_assessments = MechanisticAssessmentRepository(self)
        self.proposed_experiments = ProposedExperimentRepository(self)
        self.outcome_scenarios = OutcomeScenarioRepository(self)
        from axis.storage.targets import TargetRepository

        self.targets = TargetRepository(self)
        from axis.storage.structures import StructureRepository

        self.structures = StructureRepository(self)
        from axis.storage.pharmacology import PharmacologyRepository

        self.pharmacology = PharmacologyRepository(self)
        from axis.storage.cellular import CellularRepository

        self.cellular = CellularRepository(self)
        from axis.storage.decision import DecisionRepository

        self.decisions = DecisionRepository(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            try:
                self._connection.close()
            finally:
                if self._ownership is not None:
                    self._ownership.release()
                self._closed = True

    def statistics(self) -> StoreStatistics:
        studies = self._connection.execute("SELECT count(*) FROM studies").fetchone()
        claims = self._connection.execute("SELECT count(*) FROM claims").fetchone()
        hypotheses = self._connection.execute(
            "SELECT count(*) FROM hypotheses"
        ).fetchone()
        schema_version = self._connection.execute(
            "SELECT coalesce(max(version), 0) FROM schema_migrations"
        ).fetchone()
        if (
            studies is None
            or claims is None
            or hypotheses is None
            or schema_version is None
        ):
            raise RuntimeError("failed to read Evidence Store statistics")
        return StoreStatistics(
            studies=studies[0],
            claims=claims[0],
            hypotheses=hypotheses[0],
            schema_version=schema_version[0],
        )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        outermost = self._transaction_depth == 0
        if outermost:
            self._connection.execute("BEGIN TRANSACTION")
            self._transaction_failed = False
        self._transaction_depth += 1
        try:
            yield
        except Exception:
            self._transaction_failed = True
            if outermost:
                self._connection.execute("ROLLBACK")
            raise
        else:
            if outermost:
                if self._transaction_failed:
                    self._connection.execute("ROLLBACK")
                    raise RuntimeError("transaction aborted by a nested operation")
                self._connection.execute("COMMIT")
        finally:
            self._transaction_depth -= 1

    def _apply_migrations(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
            )
            """
        )
        migration_root = resources.files("axis.storage.migrations")
        migrations = sorted(
            (
                item
                for item in migration_root.iterdir()
                if item.name.endswith(".sql") and item.name[:3].isdigit()
            ),
            key=lambda item: item.name,
        )
        applied = {
            row[0]
            for row in self._connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }
        for migration in migrations:
            version = int(migration.name[:3])
            if version in applied:
                continue
            with self._transaction():
                self._connection.execute(migration.read_text(encoding="utf-8"))
                self._connection.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    [version, migration.name],
                )


class ClaimRepository:
    """Stores and reconstructs immutable contextual claims."""

    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    def add(self, claim: Claim) -> None:
        existing = self.get_optional(claim.identifier)
        if existing is not None:
            if existing == claim:
                return
            raise RecordConflictError(
                f"claim {claim.identifier!r} already exists with different content"
            )

        connection = self._store._connection
        with self._store._transaction():
            self._upsert_entity(claim.subject)
            self._upsert_entity(claim.object)
            connection.execute(
                """
                INSERT INTO claims (
                    identifier, subject_kind, subject_namespace, subject_identifier,
                    predicate, object_kind, object_namespace, object_identifier,
                    knowledge_kind, confidence, tissue, assay, population,
                    comparison, treatment, species, source_kind, source_identifier,
                    retrieved_at, source_uri, checksum,
                    cell_type, genotype, hla_status, allotype,
                    experimental_system, endpoint
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    claim.identifier,
                    claim.subject.kind.value,
                    claim.subject.namespace,
                    claim.subject.identifier,
                    claim.predicate,
                    claim.object.kind.value,
                    claim.object.namespace,
                    claim.object.identifier,
                    claim.knowledge_kind.value,
                    claim.confidence,
                    claim.context.tissue,
                    claim.context.assay,
                    claim.context.population,
                    claim.context.comparison,
                    claim.context.treatment,
                    claim.context.species,
                    claim.provenance.source_kind.value,
                    claim.provenance.source_identifier,
                    claim.provenance.retrieved_at,
                    claim.provenance.source_uri,
                    claim.provenance.checksum,
                    claim.context.cell_type,
                    claim.context.genotype,
                    claim.context.hla_status,
                    claim.context.allotype,
                    claim.context.experimental_system,
                    claim.context.endpoint,
                ],
            )
            for transformation_ordinal, transformation in enumerate(
                claim.provenance.transformations
            ):
                connection.execute(
                    "INSERT INTO claim_transformations VALUES (?, ?, ?, ?)",
                    [
                        claim.identifier,
                        transformation_ordinal,
                        transformation.name,
                        transformation.version,
                    ],
                )
                for parameter_ordinal, (key, value) in enumerate(
                    transformation.parameters
                ):
                    connection.execute(
                        """
                        INSERT INTO transformation_parameters
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        [
                            claim.identifier,
                            transformation_ordinal,
                            parameter_ordinal,
                            key,
                            value,
                        ],
                    )

    def get(self, identifier: str) -> Claim:
        claim = self.get_optional(identifier)
        if claim is None:
            raise RecordNotFoundError(f"claim {identifier!r} was not found")
        return claim

    def get_optional(self, identifier: str) -> Claim | None:
        row = self._store._connection.execute(
            """
            SELECT
                c.identifier,
                c.subject_kind, c.subject_identifier, se.label,
                c.subject_namespace,
                c.predicate,
                c.object_kind, c.object_identifier, oe.label,
                c.object_namespace,
                c.knowledge_kind, c.confidence,
                c.tissue, c.assay, c.population, c.comparison,
                c.treatment, c.species,
                c.source_kind, c.source_identifier, c.retrieved_at,
                c.source_uri, c.checksum,
                c.cell_type, c.genotype, c.hla_status, c.allotype,
                c.experimental_system, c.endpoint
            FROM claims c
            JOIN entities se ON
                se.kind = c.subject_kind
                AND se.namespace = c.subject_namespace
                AND se.identifier = c.subject_identifier
            JOIN entities oe ON
                oe.kind = c.object_kind
                AND oe.namespace = c.object_namespace
                AND oe.identifier = c.object_identifier
            WHERE c.identifier = ?
            """,
            [identifier],
        ).fetchone()
        if row is None:
            return None

        transformation_rows = self._store._connection.execute(
            """
            SELECT ordinal, name, version
            FROM claim_transformations
            WHERE claim_identifier = ?
            ORDER BY ordinal
            """,
            [identifier],
        ).fetchall()
        transformations = tuple(
            Transformation(
                name=transformation_row[1],
                version=transformation_row[2],
                parameters=tuple(
                    (parameter_row[0], parameter_row[1])
                    for parameter_row in self._store._connection.execute(
                        """
                        SELECT key, value
                        FROM transformation_parameters
                        WHERE claim_identifier = ?
                          AND transformation_ordinal = ?
                        ORDER BY ordinal
                        """,
                        [identifier, transformation_row[0]],
                    ).fetchall()
                ),
            )
            for transformation_row in transformation_rows
        )
        return Claim(
            identifier=row[0],
            subject=EntityRef(EntityKind(row[1]), row[2], row[3], row[4]),
            predicate=row[5],
            object=EntityRef(EntityKind(row[6]), row[7], row[8], row[9]),
            knowledge_kind=KnowledgeKind(row[10]),
            confidence=row[11],
            context=ClaimContext(
                tissue=row[12],
                assay=row[13],
                population=row[14],
                comparison=row[15],
                treatment=row[16],
                species=row[17],
                cell_type=row[23],
                genotype=row[24],
                hla_status=row[25],
                allotype=row[26],
                experimental_system=row[27],
                endpoint=row[28],
            ),
            provenance=Provenance(
                source_kind=SourceKind(row[18]),
                source_identifier=row[19],
                retrieved_at=row[20],
                source_uri=row[21],
                checksum=row[22],
                transformations=transformations,
            ),
        )

    def list_by_subject(self, subject: EntityRef) -> tuple[Claim, ...]:
        rows = self._store._connection.execute(
            """
            SELECT identifier
            FROM claims
            WHERE subject_kind = ?
              AND subject_namespace = ?
              AND subject_identifier = ?
            ORDER BY identifier
            """,
            [subject.kind.value, subject.namespace, subject.identifier],
        ).fetchall()
        return tuple(self.get(row[0]) for row in rows)

    def list_by_source(
        self, source_id: str, *, project_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[Claim, ...]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid source pagination")
        self._store.projects.get(project_id)
        rows = self._store._connection.execute(
            "SELECT c.identifier FROM claims c JOIN project_claims p "
            "ON p.claim_id=c.identifier WHERE p.project_id=? "
            "AND c.source_identifier=? ORDER BY c.identifier LIMIT ? OFFSET ?",
            [project_id, source_id, limit, offset],
        ).fetchall()
        return tuple(self.get(row[0]) for row in rows)

    def count_by_source(self, source_id: str, *, project_id: str) -> int:
        row = self._store._connection.execute(
            "SELECT count(*) FROM claims c JOIN project_claims p "
            "ON p.claim_id=c.identifier WHERE p.project_id=? AND c.source_identifier=?",
            [project_id, source_id],
        ).fetchone()
        assert row is not None
        return int(row[0])

    def _upsert_entity(self, entity: EntityRef) -> None:
        row = self._store._connection.execute(
            """
            SELECT label FROM entities
            WHERE kind = ? AND namespace = ? AND identifier = ?
            """,
            [entity.kind.value, entity.namespace, entity.identifier],
        ).fetchone()
        if row is None:
            self._store._connection.execute(
                "INSERT INTO entities VALUES (?, ?, ?, ?)",
                [
                    entity.kind.value,
                    entity.namespace,
                    entity.identifier,
                    entity.label,
                ],
            )
        elif row[0] != entity.label:
            raise RecordConflictError(
                f"entity {entity.namespace}:{entity.identifier} has label "
                f"{row[0]!r}, not {entity.label!r}"
            )


class StudyRepository:
    """Stores study-level metadata discovered in public repositories."""

    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    def add(self, study: Study) -> None:
        existing = self.get_optional(study.identifier)
        if existing is not None:
            if existing == study:
                return
            raise RecordConflictError(
                f"study {study.identifier!r} already exists with different content"
            )
        with self._store._transaction():
            self._store._connection.execute(
                """
                INSERT INTO studies VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                [
                    study.identifier,
                    study.title,
                    study.summary,
                    study.source.value,
                    study.experiment_type,
                    study.sample_count,
                    study.bioproject_id,
                    study.released_on,
                    study.provenance.source_kind.value,
                    study.provenance.source_identifier,
                    study.provenance.retrieved_at,
                    study.provenance.source_uri,
                    study.provenance.checksum,
                ],
            )
            self._insert_values("study_organisms", "organism", study, study.organisms)
            self._insert_values(
                "study_platforms",
                "platform_identifier",
                study,
                study.platform_ids,
            )
            self._insert_values(
                "study_publications",
                "publication_identifier",
                study,
                study.publication_ids,
            )
            for ordinal, transformation in enumerate(study.provenance.transformations):
                self._store._connection.execute(
                    "INSERT INTO study_transformations VALUES (?, ?, ?, ?)",
                    [
                        study.identifier,
                        ordinal,
                        transformation.name,
                        transformation.version,
                    ],
                )
                for parameter_ordinal, (key, value) in enumerate(
                    transformation.parameters
                ):
                    self._store._connection.execute(
                        "INSERT INTO study_transformation_parameters "
                        "VALUES (?, ?, ?, ?, ?)",
                        [study.identifier, ordinal, parameter_ordinal, key, value],
                    )

    def get(self, identifier: str) -> Study:
        study = self.get_optional(identifier)
        if study is None:
            raise RecordNotFoundError(f"study {identifier!r} was not found")
        return study

    def get_optional(self, identifier: str) -> Study | None:
        row = self._store._connection.execute(
            """
            SELECT
                identifier, title, summary, source, experiment_type,
                sample_count, bioproject_id, released_on,
                provenance_source_kind, provenance_source_identifier,
                retrieved_at, source_uri, checksum
            FROM studies
            WHERE identifier = ?
            """,
            [identifier],
        ).fetchone()
        if row is None:
            return None
        return Study(
            identifier=row[0],
            title=row[1],
            summary=row[2],
            source=SourceKind(row[3]),
            experiment_type=row[4],
            sample_count=row[5],
            bioproject_id=row[6],
            released_on=row[7],
            provenance=Provenance(
                source_kind=SourceKind(row[8]),
                source_identifier=row[9],
                retrieved_at=row[10],
                source_uri=row[11],
                checksum=row[12],
                transformations=tuple(
                    Transformation(
                        name=step[1],
                        version=step[2],
                        parameters=tuple(
                            (parameter[0], parameter[1])
                            for parameter in self._store._connection.execute(
                                "SELECT key, value "
                                "FROM study_transformation_parameters "
                                "WHERE study_identifier = ? "
                                "AND transformation_ordinal = ? ORDER BY ordinal",
                                [identifier, step[0]],
                            ).fetchall()
                        ),
                    )
                    for step in self._store._connection.execute(
                        "SELECT ordinal, name, version FROM study_transformations "
                        "WHERE study_identifier = ? ORDER BY ordinal",
                        [identifier],
                    ).fetchall()
                ),
            ),
            organisms=self._get_values("study_organisms", "organism", identifier),
            platform_ids=self._get_values(
                "study_platforms", "platform_identifier", identifier
            ),
            publication_ids=self._get_values(
                "study_publications", "publication_identifier", identifier
            ),
        )

    def list_all(self) -> tuple[Study, ...]:
        rows = self._store._connection.execute(
            "SELECT identifier FROM studies ORDER BY identifier"
        ).fetchall()
        return tuple(self.get(row[0]) for row in rows)

    def _insert_values(
        self,
        table: str,
        value_column: str,
        study: Study,
        values: tuple[str, ...],
    ) -> None:
        for ordinal, value in enumerate(values):
            self._store._connection.execute(
                f"INSERT INTO {table} "
                f"(study_identifier, ordinal, {value_column}) VALUES (?, ?, ?)",
                [study.identifier, ordinal, value],
            )

    def _get_values(
        self, table: str, value_column: str, study_identifier: str
    ) -> tuple[str, ...]:
        rows = self._store._connection.execute(
            f"SELECT {value_column} FROM {table} "
            "WHERE study_identifier = ? ORDER BY ordinal",
            [study_identifier],
        ).fetchall()
        return tuple(row[0] for row in rows)


class HypothesisRepository:
    """Persists hypothesis identity and append-only revisions."""

    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    def add(self, hypothesis: Hypothesis) -> None:
        existing = self.get_optional(hypothesis.identifier)
        if existing is not None:
            if existing == hypothesis:
                return
            raise RecordConflictError(
                f"hypothesis {hypothesis.identifier!r} already exists"
            )

        with self._store._transaction():
            self._store._connection.execute(
                "INSERT INTO hypotheses VALUES (?, ?)",
                [hypothesis.identifier, hypothesis.title],
            )
            for revision in hypothesis.revisions:
                self._insert_revision(hypothesis.identifier, revision)

    def append_revision(
        self, hypothesis_identifier: str, revision: HypothesisRevision
    ) -> Hypothesis:
        hypothesis = self.get(hypothesis_identifier)
        revised = hypothesis.revise(revision)
        with self._store._transaction():
            self._insert_revision(hypothesis_identifier, revision)
        return revised

    def get(self, identifier: str) -> Hypothesis:
        hypothesis = self.get_optional(identifier)
        if hypothesis is None:
            raise RecordNotFoundError(f"hypothesis {identifier!r} was not found")
        return hypothesis

    def get_optional(self, identifier: str) -> Hypothesis | None:
        row = self._store._connection.execute(
            "SELECT title FROM hypotheses WHERE identifier = ?",
            [identifier],
        ).fetchone()
        if row is None:
            return None
        revision_rows = self._store._connection.execute(
            """
            SELECT revision, created_at, state, description, rationale, confidence
            FROM hypothesis_revisions
            WHERE hypothesis_identifier = ?
            ORDER BY revision
            """,
            [identifier],
        ).fetchall()
        revisions = tuple(
            HypothesisRevision(
                revision=revision_row[0],
                created_at=revision_row[1],
                state=HypothesisState(revision_row[2]),
                description=revision_row[3],
                rationale=revision_row[4],
                confidence=revision_row[5],
                evidence_ids=tuple(
                    evidence_row[0]
                    for evidence_row in self._store._connection.execute(
                        """
                        SELECT claim_identifier
                        FROM hypothesis_evidence
                        WHERE hypothesis_identifier = ? AND revision = ?
                        ORDER BY ordinal
                        """,
                        [identifier, revision_row[0]],
                    ).fetchall()
                ),
            )
            for revision_row in revision_rows
        )
        return Hypothesis(identifier=identifier, title=row[0], revisions=revisions)

    def _insert_revision(
        self, hypothesis_identifier: str, revision: HypothesisRevision
    ) -> None:
        connection = self._store._connection
        for claim_identifier in revision.evidence_ids:
            if (
                connection.execute(
                    "SELECT 1 FROM claims WHERE identifier = ?", [claim_identifier]
                ).fetchone()
                is None
            ):
                raise RecordNotFoundError(
                    f"evidence claim {claim_identifier!r} was not found"
                )
        connection.execute(
            """
            INSERT INTO hypothesis_revisions VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                hypothesis_identifier,
                revision.revision,
                revision.created_at,
                revision.state.value,
                revision.description,
                revision.rationale,
                revision.confidence,
            ],
        )
        for ordinal, claim_identifier in enumerate(revision.evidence_ids):
            connection.execute(
                "INSERT INTO hypothesis_evidence VALUES (?, ?, ?, ?)",
                [
                    hypothesis_identifier,
                    revision.revision,
                    ordinal,
                    claim_identifier,
                ],
            )
