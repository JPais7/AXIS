"""Immutable, bounded, project/target-scoped pharmacology repository."""

import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from axis.domain.pharmacology import (
    Assay,
    BioactivityMeasurement,
    ChemicalForm,
    CompoundExternalIdentifier,
    CompoundIdentity,
    SelectivityAssessment,
)
from axis.storage import RecordConflictError, RecordNotFoundError

if TYPE_CHECKING:
    from axis.storage import EvidenceStore


class PharmacologyRepository:
    def __init__(self, store: "EvidenceStore") -> None:
        self.store = store

    def _save(
        self,
        table: str,
        identifier: str,
        columns: list[object],
        payload: dict[str, Any],
    ) -> None:
        encoded = json.dumps(payload, sort_keys=True)
        old = self.store._connection.execute(
            f"SELECT payload FROM {table} WHERE id=?", [identifier]
        ).fetchone()
        if old:
            if json.loads(old[0]) != json.loads(encoded):
                raise RecordConflictError("immutable pharmacology record conflict")
            return
        data = columns + [encoded]
        self.store._connection.execute(
            f"INSERT INTO {table} VALUES ({','.join('?' for _ in data)})", data
        )

    def insert_compound(self, value: CompoundIdentity) -> None:
        self._save(
            "compound_identities",
            value.id,
            [value.id, value.source_snapshot_id],
            asdict(value),
        )

    def insert_identifier(self, value: CompoundExternalIdentifier) -> None:
        if value.mapping_status == "resolved":
            old = self.store._connection.execute(
                "SELECT compound_id FROM compound_external_identifiers WHERE "
                "namespace=? AND external_id=? AND mapping_status='resolved'",
                [value.namespace, value.external_id],
            ).fetchall()
            if any(row[0] != value.compound_id for row in old):
                raise RecordConflictError("external identifier has another identity")
        self._save(
            "compound_external_identifiers",
            value.id,
            [
                value.id,
                value.compound_id,
                value.namespace,
                value.external_id,
                value.mapping_status,
                value.source_snapshot_id,
            ],
            asdict(value),
        )

    def insert_form(self, value: ChemicalForm) -> None:
        if value.parent_compound_id:
            self.record("compounds", value.parent_compound_id)
        self._save(
            "chemical_forms",
            value.id,
            [value.id, value.compound_id, value.source_snapshot_id],
            asdict(value),
        )

    def insert_assay(self, value: Assay) -> None:
        if value.protein_identity_id:
            p = self.store.targets.protein(value.protein_identity_id)
            if (
                p.gene_symbol != value.target_gene
                or p.taxon_id != value.taxon_id
                or p.primary_accession != value.reported_accession
            ):
                raise ValueError("assay target disagrees with protein snapshot")
            if value.protein_construct_id:
                row = self.store._connection.execute(
                    "SELECT protein_identity_id FROM protein_constructs WHERE id=?",
                    [value.protein_construct_id],
                ).fetchone()
                if not row or row[0] != value.protein_identity_id:
                    raise ValueError("assay construct disagrees with protein")
        elif value.protein_construct_id:
            raise ValueError("construct target requires protein identity")
        self._save(
            "assays",
            value.id,
            [
                value.id,
                value.target_gene,
                value.protein_identity_id,
                value.protein_construct_id,
                value.source_snapshot_id,
            ],
            asdict(value),
        )

    def insert_measurement(self, value: BioactivityMeasurement) -> None:
        if value.chemical_form_id:
            row = self.store._connection.execute(
                "SELECT compound_id FROM chemical_forms WHERE id=?",
                [value.chemical_form_id],
            ).fetchone()
            if not row or row[0] != value.compound_id:
                raise ValueError("measurement chemical form does not match identity")
        if value.provider_snapshot_id:
            self.store.targets.snapshot(value.provider_snapshot_id)
        self._save(
            "bioactivity_measurements",
            value.id,
            [
                value.id,
                value.compound_id,
                value.assay_id,
                value.endpoint,
                value.source_snapshot_id,
            ],
            asdict(value),
        )

    def insert_assessment(self, value: SelectivityAssessment) -> None:
        from axis.domain.pharmacology import MeasurementCondition
        from axis.pharmacology.selectivity import compare

        def inputs(
            identifier: str | None,
        ) -> tuple[BioactivityMeasurement | None, Assay | None]:
            if not identifier:
                return None, None
            m = BioactivityMeasurement(**self.record("measurements", identifier))
            data = self.record("assays", m.assay_id)
            data["conditions"] = tuple(
                MeasurementCondition(**c) for c in data["conditions"]
            )
            return m, Assay(**data)

        primary, a = inputs(value.primary_measurement_id)
        comparison, b = inputs(value.comparison_measurement_id)
        if (
            a
            and a.target_gene != value.primary_target_id
            or b
            and b.target_gene != value.comparison_target_id
        ):
            raise ValueError("selectivity target does not match input")
        computed = compare(primary, comparison, a, b)
        payload = asdict(value)
        if any(payload[key] != computed[key] for key in computed):
            raise ValueError("selectivity assessment disagrees with computed inputs")
        for identifier in (
            value.primary_measurement_id,
            value.comparison_measurement_id,
        ):
            if (
                identifier
                and self.record("measurements", identifier)["compound_id"]
                != value.compound_id
            ):
                raise ValueError("selectivity input belongs to another compound")
        self._save(
            "selectivity_assessments",
            value.id,
            [
                value.id,
                value.compound_id,
                value.primary_measurement_id,
                value.comparison_measurement_id,
            ],
            asdict(value),
        )

    def disagreements(
        self, project: str, protein: str, measurement: str
    ) -> dict[str, Any]:
        self.require_scoped(project, protein, "measurements", measurement)
        row = self.record("measurements", measurement)
        rows = self.store._connection.execute(
            "SELECT m.payload FROM bioactivity_measurements m "
            "JOIN project_pharmacology_measurements p ON p.measurement_id=m.id "
            "WHERE p.project_id=? AND p.protein_identity_id=? AND "
            "m.compound_id=? AND m.assay_id=? AND m.endpoint=? AND m.id<>? "
            "AND (json_extract_string(m.payload,'$.original_value') "
            "IS DISTINCT FROM ? OR "
            "json_extract_string(m.payload,'$.relation_operator')<>?) "
            "ORDER BY m.id LIMIT 101",
            [
                project,
                protein,
                row["compound_id"],
                row["assay_id"],
                row["endpoint"],
                measurement,
                row["original_value"],
                row["relation_operator"],
            ],
        ).fetchall()
        return {
            "items": [json.loads(r[0]) for r in rows[:100]],
            "has_more": len(rows) > 100,
            "interpretation": "Potential disagreement; inspect source and "
            "units. Values are never averaged.",
        }

    def link(self, project: str, protein: str, compound: str) -> None:
        self.store.targets.require_member(project, protein)
        self.store._connection.execute(
            "INSERT INTO project_pharmacology VALUES (?,?,?) ON CONFLICT DO NOTHING",
            [project, protein, compound],
        )

    @staticmethod
    def table(kind: str) -> str:
        tables = {
            "compounds": "compound_identities",
            "assays": "assays",
            "measurements": "bioactivity_measurements",
            "selectivity": "selectivity_assessments",
        }
        if kind not in tables:
            raise RecordNotFoundError("pharmacology collection not found")
        return tables[kind]

    def link_measurement(self, project: str, protein: str, measurement: str) -> None:
        self.store.targets.require_member(project, protein)
        self.store._connection.execute(
            "INSERT INTO project_pharmacology_measurements VALUES (?,?,?) "
            "ON CONFLICT DO NOTHING",
            [project, protein, measurement],
        )

    def require_scoped(
        self, project: str, protein: str, kind: str, identifier: str
    ) -> None:
        scoped = self.collection(
            project, protein, kind, 1, 0, {"record_id": identifier}
        )
        if not scoped["items"]:
            raise RecordNotFoundError("pharmacology record not in project/target")

    def record(self, kind: str, identifier: str) -> dict[str, Any]:
        row = self.store._connection.execute(
            f"SELECT payload FROM {self.table(kind)} WHERE id=?", [identifier]
        ).fetchone()
        if not row:
            raise RecordNotFoundError("pharmacology record not found")
        result: dict[str, Any] = json.loads(row[0])
        return result

    def collection(
        self,
        project: str,
        protein: str,
        kind: str,
        limit: int,
        offset: int,
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.store.targets.require_member(project, protein)
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError("invalid pagination")
        table = self.table(kind)
        relation = {
            "compounds": "c.id=p.compound_id",
            "measurements": "c.compound_id=p.compound_id",
            "selectivity": "c.compound_id=p.compound_id",
            "assays": "c.id IN (SELECT assay_id FROM bioactivity_measurements "
            "WHERE compound_id=p.compound_id)",
        }[kind]
        clause = (
            f"FROM {table} c WHERE EXISTS "
            "(SELECT 1 FROM project_pharmacology p WHERE project_id=? "
            f"AND protein_identity_id=? AND {relation})"
        )
        params: list[object] = [project, protein]
        if kind != "compounds":
            scoped_relation = {
                "measurements": "pm.measurement_id=c.id",
                "assays": "pm.measurement_id IN (SELECT id FROM "
                "bioactivity_measurements WHERE assay_id=c.id)",
                "selectivity": "pm.measurement_id=c.primary_measurement_id",
            }[kind]
            clause += (
                " AND EXISTS (SELECT 1 FROM project_pharmacology_measurements "
                "pm WHERE pm.project_id=? AND pm.protein_identity_id=? "
                f"AND {scoped_relation})"
            )
            params += [project, protein]
        if kind == "selectivity":
            clause += (
                " AND (c.comparison_measurement_id IS NULL OR EXISTS "
                "(SELECT 1 FROM project_pharmacology_measurements q "
                "WHERE q.project_id=? AND q.protein_identity_id=? "
                "AND q.measurement_id=c.comparison_measurement_id))"
            )
            params += [project, protein]
        for key, value in (filters or {}).items():
            if key == "record_id":
                clause += " AND c.id=?"
            elif key == "compound" and kind != "assays":
                clause += (
                    " AND c." + ("id" if kind == "compounds" else "compound_id") + "=?"
                )
            elif key == "endpoint" and kind == "measurements":
                clause += " AND c.endpoint=?"
            elif key == "source":
                if kind == "selectivity":
                    raise ValueError(
                        "source filter unavailable for computed assessment"
                    )
                clause += " AND c.source_snapshot_id=?"
            elif key in {"target", "assay_type"} and kind in {"assays", "measurements"}:
                expr = (
                    "c.payload"
                    if kind == "assays"
                    else "(SELECT payload FROM assays WHERE id=c.assay_id)"
                )
                field_name = "target_gene" if key == "target" else "assay_type"
                clause += f" AND json_extract_string({expr}, '$.{field_name}')=?"
            else:
                raise ValueError("unsupported pharmacology filter for collection")
            params.append(value)
        count = self.store._connection.execute(
            "SELECT count(*) " + clause, params
        ).fetchone()
        rows = self.store._connection.execute(
            "SELECT c.payload " + clause + " ORDER BY c.id LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        total = int(count[0]) if count else 0
        return {
            "items": [json.loads(row[0]) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }

    def compound_detail(
        self, project: str, protein: str, identifier: str
    ) -> dict[str, Any]:
        scoped = self.collection(
            project, protein, "compounds", 1, 0, {"compound": identifier}
        )
        if not scoped["items"]:
            raise RecordNotFoundError("compound not in project/target")

        def related(table: str) -> list[dict[str, Any]]:
            return [
                json.loads(r[0])
                for r in self.store._connection.execute(
                    f"SELECT payload FROM {table} WHERE compound_id=? "
                    "ORDER BY id LIMIT 100",
                    [identifier],
                ).fetchall()
            ]

        compound = scoped["items"][0]
        measured = self.collection(
            project, protein, "measurements", 100, 0, {"compound": identifier}
        )
        nodes = [{"id": identifier, "type": "CompoundIdentity"}]
        edges = []
        seen = set()
        for m in measured["items"]:
            nodes.append({"id": m["id"], "type": "BioactivityMeasurement"})
            edges.extend(
                [
                    {"from": identifier, "to": m["assay_id"], "relation": "tested_in"},
                    {"from": m["assay_id"], "to": m["id"], "relation": "produced"},
                    {"from": identifier, "to": m["id"], "relation": "has_measurement"},
                ]
            )
            if m["assay_id"] not in seen:
                seen.add(m["assay_id"])
                a = self.record("assays", m["assay_id"])
                target = (
                    a["protein_construct_id"]
                    or a["protein_identity_id"]
                    or f"reported-target:{a['reported_accession']}:{a['taxon_id']}"
                )
                nodes.extend(
                    [
                        {"id": m["assay_id"], "type": "Assay"},
                        {"id": target, "type": "ReportedTargetContext"},
                    ]
                )
                edges.append(
                    {
                        "from": m["assay_id"],
                        "to": target,
                        "relation": "reported_target_context",
                    }
                )
        assessments = self.collection(
            project, protein, "selectivity", 100, 0, {"compound": identifier}
        )
        for s in assessments["items"]:
            nodes.append({"id": s["id"], "type": "SelectivityAssessment"})
            for key in ("primary_measurement_id", "comparison_measurement_id"):
                if s[key]:
                    edges.append(
                        {"from": s["id"], "to": s[key], "relation": "compares"}
                    )
        nodes = list({n["id"]: n for n in nodes}.values())
        edges = list({(e["from"], e["to"], e["relation"]): e for e in edges}.values())
        return {
            "compound": compound,
            "identifiers": related("compound_external_identifiers"),
            "forms": related("chemical_forms"),
            "snapshot": asdict(
                self.store.targets.snapshot(compound["source_snapshot_id"])
            ),
            "related_limit": 100,
            "identity_graph": {
                "nodes": nodes,
                "edges": edges,
                "has_more": measured["has_more"] or assessments["has_more"],
                "boundary": "No therapeutic or observed-ligand edge.",
            },
        }
