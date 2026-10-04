"""Immutable cellular observations, bounded and project/target scoped."""

import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from axis.domain.cellular import (
    CellularAssessment,
    CellularExperiment,
    ExperimentalReadout,
    ImmunopeptidomeObservation,
)
from axis.storage import RecordConflictError, RecordNotFoundError

if TYPE_CHECKING:
    from axis.storage import EvidenceStore

TABLES = {
    "experiments": "cellular_experiments",
    "readouts": "experimental_readouts",
    "assessments": "cellular_assessments",
    "immunopeptidome": "immunopeptidome_observations",
}


class CellularRepository:
    def __init__(self, store: "EvidenceStore") -> None:
        self.store = store

    def save(
        self, kind: str, identifier: str, columns: list[object], payload: dict[str, Any]
    ) -> None:
        table = TABLES[kind]
        old = self.store._connection.execute(
            f"SELECT payload FROM {table} WHERE id=?", [identifier]
        ).fetchone()
        encoded = json.dumps(payload, sort_keys=True)
        if old:
            if json.loads(old[0]) != json.loads(encoded):
                raise RecordConflictError("immutable cellular record conflict")
            return
        values = columns + [encoded]
        self.store._connection.execute(
            f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
        )

    def add_experiment(
        self, project: str, protein: str, value: CellularExperiment
    ) -> None:
        self.store.targets.require_member(project, protein)
        membership = self.store._connection.execute(
            "SELECT 1 FROM project_perturbations WHERE project_id=? "
            "AND perturbation_id=?",
            [project, value.perturbation_id],
        ).fetchone()
        if not membership:
            raise ValueError("perturbation outside project")
        if value.compound_id:
            self.store.pharmacology.require_scoped(
                project, protein, "compounds", value.compound_id
            )
        self.save(
            "experiments",
            value.id,
            [value.id, project, protein, value.perturbation_id, value.compound_id],
            asdict(value),
        )

    def add_readout(
        self, project: str, protein: str, value: ExperimentalReadout
    ) -> None:
        experiment = self.detail(project, protein, "experiments", value.experiment_id)
        if value.claim_id:
            self.store.projects._require_claim(project, value.claim_id)
            claim = self.store.claims.get(value.claim_id)
            if claim.provenance.source_identifier != experiment["source_id"]:
                raise ValueError("readout source does not match experiment")
        if value.measurement_id:
            self.store.pharmacology.require_scoped(
                project, protein, "measurements", value.measurement_id
            )
            measurement = self.store.pharmacology.record(
                "measurements", value.measurement_id
            )
            if measurement["compound_id"] != experiment["compound_id"]:
                raise ValueError("measurement chemical identity mismatch")
        self.save(
            "readouts",
            value.id,
            [value.id, value.experiment_id, value.claim_id, value.measurement_id],
            asdict(value),
        )

    def add_assessment(
        self, project: str, protein: str, value: CellularAssessment
    ) -> None:
        self.detail(project, protein, "experiments", value.experiment_id)
        for identifier in (
            *value.supporting_readout_ids,
            *value.contradicting_readout_ids,
        ):
            readout = self.detail(project, protein, "readouts", identifier)
            if readout["experiment_id"] != value.experiment_id:
                raise ValueError("assessment input outside experiment")
            if (
                value.edge == "engagement"
                and value.state == "supported"
                and (readout["proximity"] != "target_proximal")
            ):
                raise ValueError("downstream phenotype cannot demonstrate engagement")
        self.save(
            "assessments",
            value.id,
            [value.id, value.experiment_id, value.edge],
            asdict(value),
        )

    def add_immunopeptidome(
        self, project: str, protein: str, value: ImmunopeptidomeObservation
    ) -> None:
        self.detail(project, protein, "readouts", value.readout_id)
        self.save(
            "immunopeptidome", value.id, [value.id, value.readout_id], asdict(value)
        )

    def _scope(self, kind: str) -> str:
        if kind == "experiments":
            return "cellular_experiments t"
        if kind == "immunopeptidome":
            return (
                "immunopeptidome_observations t JOIN experimental_readouts r "
                "ON t.readout_id=r.id JOIN cellular_experiments e "
                "ON r.experiment_id=e.id"
            )
        return f"{TABLES[kind]} t JOIN cellular_experiments e ON t.experiment_id=e.id"

    def collection(
        self,
        project: str,
        protein: str,
        kind: str,
        limit: int = 20,
        offset: int = 0,
        compound: str | None = None,
    ) -> dict[str, Any]:
        self.store.targets.require_member(project, protein)
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError("invalid collection bounds")
        scope = "t" if kind == "experiments" else "e"
        where = f"{scope}.project_id=? AND {scope}.protein_id=?"
        args: list[object] = [project, protein]
        if compound:
            self.store.pharmacology.require_scoped(
                project, protein, "compounds", compound
            )
            where += f" AND {scope}.compound_id=?"
            args.append(compound)
        source = self._scope(kind)
        total_row = self.store._connection.execute(
            f"SELECT count(*) FROM {source} WHERE {where}", args
        ).fetchone()
        total = int(total_row[0]) if total_row else 0
        rows = self.store._connection.execute(
            f"SELECT t.payload FROM {source} WHERE {where} "
            "ORDER BY t.id LIMIT ? OFFSET ?",
            args + [limit, offset],
        ).fetchall()
        return {
            "items": [json.loads(r[0]) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }

    def detail(
        self, project: str, protein: str, kind: str, identifier: str
    ) -> dict[str, Any]:
        self.store.targets.require_member(project, protein)
        scope = "t" if kind == "experiments" else "e"
        row = self.store._connection.execute(
            f"SELECT t.payload FROM {self._scope(kind)} WHERE t.id=? "
            f"AND {scope}.project_id=? AND {scope}.protein_id=?",
            [identifier, project, protein],
        ).fetchone()
        if not row:
            raise RecordNotFoundError("cellular record outside scope or not found")
        return dict(json.loads(row[0]))
