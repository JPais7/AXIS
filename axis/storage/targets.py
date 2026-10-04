"""Immutable target repositories on the EvidenceStore transaction boundary."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from axis.domain.protein import (
    GeneProteinMapping,
    MappingStatus,
    ProteinIdentity,
    ProteinIsoform,
    SourceSnapshot,
)
from axis.storage.store import RecordConflictError, RecordNotFoundError

if TYPE_CHECKING:
    from axis.storage.store import EvidenceStore


def _encode(record: object) -> str:
    if not isinstance(
        record, (SourceSnapshot, ProteinIdentity, ProteinIsoform, GeneProteinMapping)
    ):
        raise TypeError("unsupported identity record")
    return json.dumps(asdict(record), default=str, sort_keys=True)


class TargetRepository:
    def __init__(self, store: "EvidenceStore") -> None:
        self.store = store

    def _insert(self, table: str, record: object, columns: list[object]) -> None:
        encoded = _encode(record)
        identifier = json.loads(encoded)["id"]
        row = self.store._connection.execute(
            f"SELECT payload FROM {table} WHERE id = ?", [identifier]
        ).fetchone()
        if row is not None:
            if json.loads(row[0]) != json.loads(encoded):
                raise RecordConflictError("immutable target record conflict")
            return
        placeholders = ",".join("?" for _ in columns + [encoded])
        self.store._connection.execute(
            f"INSERT INTO {table} VALUES ({placeholders})", columns + [encoded]
        )

    def _read(self, table: str, identifier: str) -> dict[str, Any]:
        row = self.store._connection.execute(
            f"SELECT payload FROM {table} WHERE id = ?", [identifier]
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("target identity record not found")
        value: dict[str, Any] = json.loads(row[0])
        return value

    def insert_snapshot(self, value: SourceSnapshot) -> None:
        self._insert(
            "source_snapshots",
            value,
            [
                value.id,
                value.provider,
                value.provider_record_id,
                value.raw_content_checksum,
            ],
        )

    def snapshot(self, identifier: str) -> SourceSnapshot:
        data = self._read("source_snapshots", identifier)
        data["retrieval_timestamp"] = datetime.fromisoformat(
            data["retrieval_timestamp"]
        )
        return SourceSnapshot(**data)

    def insert_protein(self, value: ProteinIdentity) -> None:
        for old in self.by_accession(value.namespace, value.primary_accession):
            if (old.sequence_checksum, old.sequence_version, old.taxon_id) != (
                value.sequence_checksum,
                value.sequence_version,
                value.taxon_id,
            ):
                raise RecordConflictError("immutable sequence/version/taxon conflict")
        self._insert(
            "protein_identities",
            value,
            [
                value.id,
                value.namespace,
                value.primary_accession,
                value.source_snapshot_id,
            ],
        )

    def protein(self, identifier: str) -> ProteinIdentity:
        data = self._read("protein_identities", identifier)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return ProteinIdentity(**data)

    def by_accession(self, namespace: str, accession: str) -> list[ProteinIdentity]:
        rows = self.store._connection.execute(
            "SELECT id FROM protein_identities WHERE namespace = ? AND accession = ? "
            "ORDER BY id",
            [namespace, accession],
        ).fetchall()
        return [self.protein(row[0]) for row in rows]

    def insert_isoform(self, value: ProteinIsoform) -> None:
        self._insert(
            "protein_isoforms",
            value,
            [
                value.id,
                value.protein_identity_id,
                value.source_snapshot_id,
                value.accession,
            ],
        )

    def isoforms(self, identifier: str) -> list[ProteinIsoform]:
        rows = self.store._connection.execute(
            "SELECT payload FROM protein_isoforms WHERE protein_identity_id = ? "
            "ORDER BY accession",
            [identifier],
        ).fetchall()
        return [ProteinIsoform(**json.loads(row[0])) for row in rows]

    def canonical_isoform(self, identifier: str) -> ProteinIsoform | None:
        values = [value for value in self.isoforms(identifier) if value.canonical]
        if len(values) > 1:
            raise RecordConflictError("multiple canonical isoforms")
        return values[0] if values else None

    def insert_mapping(self, value: GeneProteinMapping) -> None:
        protein = self.protein(value.protein_identity_id)
        if protein.taxon_id != value.taxon_id:
            raise RecordConflictError("mapping taxon mismatch")
        self._insert(
            "gene_protein_mappings",
            value,
            [
                value.id,
                "gene",
                value.gene_namespace,
                value.gene_entity_id,
                value.protein_identity_id,
                value.source_snapshot_id,
            ],
        )

    def mappings(self, identifier: str) -> list[GeneProteinMapping]:
        rows = self.store._connection.execute(
            "SELECT payload FROM gene_protein_mappings WHERE protein_identity_id = ? "
            "ORDER BY id",
            [identifier],
        ).fetchall()
        result = []
        for row in rows:
            data = json.loads(row[0])
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            data["status"] = MappingStatus(data["status"])
            result.append(GeneProteinMapping(**data))
        return result

    def for_gene(self, namespace: str, identifier: str) -> list[ProteinIdentity]:
        rows = self.store._connection.execute(
            "SELECT DISTINCT protein_identity_id FROM gene_protein_mappings "
            "WHERE gene_namespace = ? AND gene_entity_id = ? ORDER BY 1",
            [namespace, identifier],
        ).fetchall()
        return [self.protein(row[0]) for row in rows]

    def link(self, project: str, protein: str, mapping: str) -> None:
        pair = self.store.target_disease_pairs.get(
            self.store.projects.get(project).target_disease_pair
        )
        data = self._read("gene_protein_mappings", mapping)
        if (
            data["protein_identity_id"] != protein
            or data["gene_namespace"] != pair.target.namespace
            or data["gene_entity_id"] != pair.target.identifier
            or pair.target.kind.value != "gene"
        ):
            raise RecordConflictError("project mapping ownership mismatch")
        self.store._connection.execute(
            "INSERT INTO project_protein_identities VALUES (?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [project, protein, mapping],
        )

    def project_ids(self, project: str) -> list[str]:
        self.store.projects.get(project)
        rows = self.store._connection.execute(
            "SELECT protein_identity_id FROM project_protein_identities "
            "WHERE project_id = ? ORDER BY protein_identity_id",
            [project],
        ).fetchall()
        return [row[0] for row in rows]

    def require_member(self, project: str, identifier: str) -> ProteinIdentity:
        if identifier not in self.project_ids(project):
            raise RecordNotFoundError("target not in this project")
        return self.protein(identifier)
