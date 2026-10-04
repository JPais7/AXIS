"""Immutable structural persistence and project/target-scoped reads."""

import hashlib
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from axis.domain.structure import ChainInstance, ExperimentalStructure, ProteinConstruct
from axis.storage import RecordConflictError, RecordNotFoundError

if TYPE_CHECKING:
    from axis.storage.store import EvidenceStore


class StructureRepository:
    def __init__(self, store: "EvidenceStore") -> None:
        self.store = store

    def _save(
        self,
        table: str,
        identifier: str,
        columns: list[object],
        value: object,
        extra: list[object] | None = None,
    ) -> None:
        encoded = json.dumps(value, default=str, sort_keys=True)
        id_column = {
            "residue_mappings": "chain_id",
            "observed_structure_components": "structure_id",
        }.get(table, "id")
        old = self.store._connection.execute(
            f"SELECT payload FROM {table} WHERE {id_column} = ?",
            [identifier],
        ).fetchone()
        if old:
            if json.loads(old[0]) != json.loads(encoded):
                raise RecordConflictError("immutable structure record conflict")
            return
        data = columns + [encoded] + (extra or [])
        self.store._connection.execute(
            f"INSERT INTO {table} VALUES ({','.join('?' for _ in data)})", data
        )

    def insert_construct(self, value: ProteinConstruct) -> None:
        self._save(
            "protein_constructs",
            value.id,
            [value.id, value.protein_identity_id, value.source_snapshot_id],
            asdict(value),
        )

    def insert_structure(self, value: ExperimentalStructure, raw: bytes) -> None:
        if hashlib.sha256(raw).hexdigest() != value.raw_file_checksum:
            raise ValueError("raw coordinate checksum mismatch")
        self._save(
            "experimental_structures",
            value.id,
            [value.id, value.source_snapshot_id],
            asdict(value),
            [raw],
        )
        if self.coordinates(value.id) != raw:
            raise RecordConflictError("immutable coordinate bytes conflict")

    def insert_chain(self, value: ChainInstance) -> None:
        self._save(
            "structure_chains",
            value.id,
            [value.id, value.structure_id, value.construct_id],
            asdict(value),
        )

    def insert_mapping(
        self, chain_id: str, rows: list[dict[str, Any]], transformation: dict[str, Any]
    ) -> None:
        self._save(
            "residue_mappings",
            chain_id,
            [chain_id],
            rows,
            [json.dumps(transformation, sort_keys=True)],
        )
        if self.mapping(chain_id)["transformation"] != json.loads(
            json.dumps(transformation)
        ):
            raise RecordConflictError("immutable mapping transformation conflict")

    def insert_components(self, identifier: str, rows: list[dict[str, Any]]) -> None:
        self._save("observed_structure_components", identifier, [identifier], rows)

    def structure(self, identifier: str) -> dict[str, Any]:
        row = self.store._connection.execute(
            "SELECT payload FROM experimental_structures WHERE id=?", [identifier]
        ).fetchone()
        if not row:
            raise RecordNotFoundError("structure not found")
        value: dict[str, Any] = json.loads(row[0])
        return value

    def coordinates(self, identifier: str) -> bytes:
        row = self.store._connection.execute(
            "SELECT coordinates FROM experimental_structures WHERE id=?", [identifier]
        ).fetchone()
        if not row:
            raise RecordNotFoundError("structure not found")
        return bytes(row[0])

    def chains(self, identifier: str) -> list[dict[str, Any]]:
        rows = self.store._connection.execute(
            "SELECT payload FROM structure_chains WHERE structure_id=? ORDER BY id",
            [identifier],
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def constructs(self, identifier: str) -> list[dict[str, Any]]:
        rows = self.store._connection.execute(
            "SELECT DISTINCT c.payload FROM protein_constructs c "
            "JOIN structure_chains s "
            "ON c.id=s.construct_id WHERE s.structure_id=? ORDER BY c.payload",
            [identifier],
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def mapping(self, chain: str) -> dict[str, Any]:
        row = self.store._connection.execute(
            "SELECT payload,transformation FROM residue_mappings WHERE chain_id=?",
            [chain],
        ).fetchone()
        if not row:
            raise RecordNotFoundError("chain mapping not found")
        return {"rows": json.loads(row[0]), "transformation": json.loads(row[1])}

    def components(self, identifier: str) -> list[dict[str, Any]]:
        row = self.store._connection.execute(
            "SELECT payload FROM observed_structure_components WHERE structure_id=?",
            [identifier],
        ).fetchone()
        result: list[dict[str, Any]] = json.loads(row[0]) if row else []
        return result

    def link(self, project: str, protein: str, structure: str) -> None:
        self.store.targets.require_member(project, protein)
        if any(
            c["mapped_protein_identity_id"] != protein for c in self.chains(structure)
        ):
            raise RecordConflictError("structure target mismatch")
        self.store._connection.execute(
            "INSERT INTO project_structures VALUES (?,?,?) ON CONFLICT DO NOTHING",
            [project, protein, structure],
        )

    def list_ids(self, project: str, protein: str) -> list[str]:
        self.store.targets.require_member(project, protein)
        return [
            row[0]
            for row in self.store._connection.execute(
                "SELECT structure_id FROM project_structures WHERE project_id=? "
                "AND protein_identity_id=? ORDER BY structure_id",
                [project, protein],
            ).fetchall()
        ]

    def require_member(self, project: str, protein: str, structure: str) -> None:
        if structure not in self.list_ids(project, protein):
            raise RecordNotFoundError("structure not in project/target")
