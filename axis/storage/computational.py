"""Immutable persistence for computational discovery campaigns (Phase 3.8)."""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from axis.storage import RecordConflictError

if TYPE_CHECKING:
    from axis.storage import EvidenceStore


def encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)


class ComputationalRepository:
    def __init__(self, store: "EvidenceStore") -> None:
        self.store = store

    @property
    def _db(self) -> Any:
        return self.store._connection

    def put(
        self,
        table: str,
        row_id: str,
        columns: dict[str, Any],
        payload: dict[str, Any],
        key: str = "id",
    ) -> bool:
        """Insert once. Identical re-insert is a no-op; a change is a conflict."""
        row = self._db.execute(
            f"SELECT payload FROM {table} WHERE {key}=?", [row_id]
        ).fetchone()
        if row is not None:
            if json.loads(row[0]) != json.loads(encode(payload)):
                raise RecordConflictError(
                    f"immutable computational record changed: {table} {row_id}"
                )
            return False
        names = [key, *columns, "payload"]
        values = [row_id, *columns.values(), encode(payload)]
        self._db.execute(
            f"INSERT INTO {table} ({','.join(names)}) "
            f"VALUES ({','.join('?' * len(names))})",
            values,
        )
        return True

    def get(self, table: str, row_id: str, key: str = "id") -> dict[str, Any] | None:
        row = self._db.execute(
            f"SELECT payload FROM {table} WHERE {key}=?", [row_id]
        ).fetchone()
        return None if row is None else dict(json.loads(row[0]))

    def rows(
        self, table: str, where: str = "", params: list[Any] | None = None
    ) -> list[dict[str, Any]]:
        cursor = self._db.execute(
            f"SELECT * FROM {table} {where} ORDER BY 1, 2", params or []
        )
        names = [d[0] for d in cursor.description]
        out = []
        for raw in cursor.fetchall():
            item = dict(zip(names, raw, strict=True))
            item["payload"] = json.loads(item["payload"])
            for k, v in list(item.items()):
                if isinstance(v, datetime):
                    item[k] = v.isoformat()
            out.append(item)
        return out

    def set_status(self, campaign_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE computational_campaigns SET status=? WHERE id=?",
            [status, campaign_id],
        )
