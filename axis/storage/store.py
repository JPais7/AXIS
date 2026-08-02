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

    def __init__(self, database: str | Path = ":memory:") -> None:
        database_path = Path(database) if database != ":memory:" else None
        if database_path is not None:
            database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = duckdb.connect(
            str(database_path) if database_path is not None else ":memory:"
        )
        self._closed = False
        self._apply_migrations()
        self.claims = ClaimRepository(self)
        self.hypotheses = HypothesisRepository(self)
        self.studies = StudyRepository(self)

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
            self._connection.close()
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
        self._connection.execute("BEGIN TRANSACTION")
        try:
            yield
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        else:
            self._connection.execute("COMMIT")

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
                INSERT INTO claims VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                c.source_uri, c.checksum
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
