"""Append-only persistence for retrospective validation (Phase 3.7)."""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from axis.storage import RecordConflictError

if TYPE_CHECKING:
    from axis.storage import EvidenceStore


def encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)


class BenchmarkRepository:
    def __init__(self, store: "EvidenceStore") -> None:
        self.store = store

    @property
    def _db(self) -> Any:
        return self.store._connection

    # -- sets and cases ----------------------------------------------------

    def register_set(
        self, manifest: dict[str, Any], manifest_sha: str, now: datetime
    ) -> None:
        existing = self._db.execute(
            "SELECT manifest_sha256 FROM benchmark_sets WHERE set_id=?",
            [manifest["set_id"]],
        ).fetchone()
        if existing is not None:
            if existing[0] != manifest_sha:
                raise RecordConflictError(
                    f"benchmark set {manifest['set_id']!r} changed after registration"
                )
            return
        self._db.execute(
            "INSERT INTO benchmark_sets VALUES (?,?,?,?,?,?)",
            [
                manifest["set_id"],
                manifest_sha,
                manifest["benchmark_kind"],
                manifest["synthetic"],
                manifest["title"],
                now,
            ],
        )

    def seal_case(self, protocol: dict[str, Any], now: datetime) -> dict[str, Any]:
        row = self.case(protocol["case_id"], required=False)
        if row is not None:
            if row["protocol_fingerprint"] != protocol["protocol_fingerprint"]:
                raise RecordConflictError(
                    "a sealed protocol cannot be changed; register a new case id"
                )
            return row
        self._db.execute(
            "INSERT INTO benchmark_cases VALUES (?,?,?,?,?,?,?)",
            [
                protocol["case_id"],
                protocol["set_id"],
                "sealed",
                protocol["protocol_fingerprint"],
                encode(protocol),
                now,
                now,
            ],
        )
        return self.case(protocol["case_id"])  # type: ignore[return-value]

    def case(self, case_id: str, required: bool = True) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT case_id,set_id,status,protocol_fingerprint,payload,sealed_at,"
            "updated_at FROM benchmark_cases WHERE case_id=?",
            [case_id],
        ).fetchone()
        if row is None:
            if required:
                raise KeyError(f"benchmark case {case_id!r} is not registered")
            return None
        return {
            "case_id": row[0],
            "set_id": row[1],
            "status": row[2],
            "protocol_fingerprint": row[3],
            "protocol": json.loads(row[4]),
            "sealed_at": row[5].isoformat(),
            "updated_at": row[6].isoformat(),
        }

    def cases(self) -> list[dict[str, Any]]:
        ids = [
            r[0]
            for r in self._db.execute(
                "SELECT case_id FROM benchmark_cases ORDER BY case_id"
            ).fetchall()
        ]
        return [self.case(i) for i in ids]  # type: ignore[misc]

    def set_status(self, case_id: str, status: str, now: datetime) -> None:
        self._db.execute(
            "UPDATE benchmark_cases SET status=?, updated_at=? WHERE case_id=?",
            [status, now, case_id],
        )

    # -- generic append-only rows -----------------------------------------

    def add(self, table: str, row_id: str, columns: dict[str, Any]) -> None:
        names = ["id", *columns]
        values = [row_id, *columns.values()]
        existing = self._db.execute(
            f"SELECT 1 FROM {table} WHERE id=?", [row_id]
        ).fetchone()
        if existing:
            raise RecordConflictError(f"{table} row {row_id!r} already exists")
        self._db.execute(
            f"INSERT INTO {table} ({','.join(names)}) "
            f"VALUES ({','.join('?' * len(names))})",
            [encode(v) if isinstance(v, dict | list) else v for v in values],
        )

    ORDER = {
        "benchmark_baselines": "frozen_at",
        "benchmark_reviews": "reviewed_at",
    }

    def rows(self, table: str, case_id: str, order: str | None = None) -> list[Any]:
        order = order or self.ORDER.get(table, "created_at")
        cursor = self._db.execute(
            f"SELECT * FROM {table} WHERE case_id=? ORDER BY {order}, id", [case_id]
        )
        names = [d[0] for d in cursor.description]
        out = []
        for row in cursor.fetchall():
            item = dict(zip(names, row, strict=True))
            for key in ("payload", "packet", "sealed_mapping"):
                if key in item and isinstance(item[key], str):
                    item[key] = json.loads(item[key])
            for key, value in list(item.items()):
                if hasattr(value, "isoformat"):
                    item[key] = value.isoformat()
            out.append(item)
        return out

    def sets(self) -> list[dict[str, Any]]:
        cursor = self._db.execute("SELECT * FROM benchmark_sets ORDER BY set_id")
        names = [d[0] for d in cursor.description]
        return [
            {
                k: (v.isoformat() if isinstance(v, datetime) else v)
                for k, v in zip(names, row, strict=True)
            }
            for row in cursor.fetchall()
        ]

    def unblind(self, packet_id: str, now: datetime) -> None:
        self._db.execute(
            "UPDATE benchmark_blind_packets SET unblinded_at=? WHERE id=?",
            [now, packet_id],
        )
