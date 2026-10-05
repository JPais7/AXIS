"""Atomic, checksum-verified offline imports and bounded read projections."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.case_config import reference_case
from axis.domain.pharmacology import (
    Assay,
    BioactivityMeasurement,
    ChemicalForm,
    CompoundExternalIdentifier,
    CompoundIdentity,
    MeasurementCondition,
    SelectivityAssessment,
)
from axis.domain.protein import SourceSnapshot
from axis.pharmacology.chemistry import resolve_structure
from axis.pharmacology.selectivity import compare, normalize
from axis.sources.chembl import parse_frozen
from axis.storage import EvidenceStore

VERSION = "axis-pharmacology-1"


class PharmacologyService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def import_package(
        self, project: str, protein: str, directory: Path | None = None
    ) -> list[str]:
        p = self.store.targets.require_member(project, protein)
        if p.primary_accession != "Q9NZ08" or p.taxon_id != 9606:
            raise ValueError("ERAP1 reference package requires human Q9NZ08")
        root = directory or resources.files("axis").joinpath(
            "resources/pharmacology/erap1/v1"
        )
        raw_manifest = root.joinpath("manifest.json").read_bytes()
        if (
            hashlib.sha256(raw_manifest).hexdigest()
            != root.joinpath("manifest.sha256").read_text().strip()
        ):
            raise ValueError("pharmacology manifest checksum mismatch")
        manifest = json.loads(raw_manifest)
        case = reference_case("erap1-axspa")
        if manifest["importer_version"] != VERSION:
            raise ValueError("unsupported pharmacology importer")
        from rdkit import rdBase

        if manifest["rdkit_version"] != rdBase.rdkitVersion:
            raise ValueError("frozen chemistry requires pinned RDKit version")
        data = {}
        for name, digest in manifest["files"].items():
            if Path(name).name != name:
                raise ValueError("invalid resource filename")
            raw = root.joinpath(name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("pharmacology resource checksum mismatch")
            if name.endswith(".json"):
                data[name] = json.loads(raw)
        parse_frozen(root.joinpath("chembl-extract.json").read_bytes())
        now = manifest["retrieved_at"]
        with self.store._transaction():
            for item in manifest["snapshots"]:
                values = item | {
                    "retrieval_timestamp": datetime.fromisoformat(
                        item["retrieval_timestamp"]
                    )
                }
                self.store.targets.insert_snapshot(SourceSnapshot(**values))
            compounds = []
            for item in data["compounds.json"]:
                values = dict(item)
                if values.get("original_smiles"):
                    resolved = resolve_structure(values["original_smiles"])
                    stereo = resolved["transformation"]["stereochemistry_features"]
                    if values["stereochemistry_status"] == "not_applicable" and stereo:
                        raise ValueError("source stereochemistry marked inapplicable")
                    if values["stereochemistry_status"] == "explicit" and any(
                        s["specified"] == "Unspecified" for s in stereo
                    ):
                        raise ValueError("source stereochemistry is not fully explicit")
                    if resolved["molecular_formula"] != values["expected_formula"]:
                        raise ValueError("source chemical formula conflict")
                    values.update(resolved)
                values.pop("expected_formula", None)
                compound = CompoundIdentity(**(values | {"created_at": now}))
                self.store.pharmacology.insert_compound(compound)
                compounds.append(compound.id)
            for item in data["identifiers.json"]:
                self.store.pharmacology.insert_identifier(
                    CompoundExternalIdentifier(**item)
                )
            for item in data["forms.json"]:
                self.store.pharmacology.insert_form(ChemicalForm(**item))
            assays = {}
            for item in data["assays.json"]:
                # Source-reported recombinant variants are NOT the displayed
                # canonical snapshot/3QNF construct. Leave exact FK unresolved.
                assay = Assay(
                    **(
                        item
                        | {
                            "conditions": tuple(
                                MeasurementCondition(**c) for c in item["conditions"]
                            ),
                            "created_at": now,
                        }
                    )
                )
                self.store.pharmacology.insert_assay(assay)
                assays[assay.id] = assay
            measurements = []
            for item in data["measurements.json"]:
                measurement = normalize(
                    BioactivityMeasurement(**(item | {"created_at": now}))
                )
                self.store.pharmacology.insert_measurement(measurement)
                measurements.append(measurement)
            for compound_id in compounds:
                self.store.pharmacology.link(project, protein, compound_id)
                for measurement in measurements:
                    if measurement.compound_id == compound_id:
                        self.store.pharmacology.link_measurement(
                            project, protein, measurement.id
                        )
                primary = [
                    m
                    for m in measurements
                    if m.compound_id == compound_id
                    and assays[m.assay_id].target_gene == case["primary_target"]
                    and assays[m.assay_id].assay_type == "biochemical_activity"
                ]
                for target in case["comparison_targets"]:
                    off = [
                        m
                        for m in measurements
                        if m.compound_id == compound_id
                        and assays[m.assay_id].target_gene == target
                    ]
                    for x in primary:
                        comparisons: list[BioactivityMeasurement | None] = list(off)
                        for y in comparisons or [None]:
                            assessment = SelectivityAssessment(
                                id=f"selectivity:{x.id}:{y.id if y else target}",
                                compound_id=compound_id,
                                primary_target_id=case["primary_target"],
                                comparison_target_id=target,
                                primary_measurement_id=x.id,
                                comparison_measurement_id=y.id if y else None,
                                **compare(
                                    x,
                                    y,
                                    assays[x.assay_id],
                                    assays[y.assay_id] if y else None,
                                ),
                            )
                            self.store.pharmacology.insert_assessment(assessment)
        return compounds

    def detail(
        self, project: str, protein: str, kind: str, identifier: str
    ) -> dict[str, Any]:
        if kind == "compounds":
            return self.store.pharmacology.compound_detail(project, protein, identifier)
        value = self.store.pharmacology.record(kind, identifier)
        self.store.pharmacology.require_scoped(project, protein, kind, identifier)
        result: dict[str, Any] = {"record": value}
        if kind == "measurements":
            result["potential_disagreements"] = self.store.pharmacology.disagreements(
                project, protein, identifier
            )
            result["assay"] = self.store.pharmacology.record(
                "assays", value["assay_id"]
            )
            result["chemical_identity"] = self.store.pharmacology.record(
                "compounds", value["compound_id"]
            )
        if "source_snapshot_id" in value:
            result["snapshot"] = asdict(
                self.store.targets.snapshot(value["source_snapshot_id"])
            )
        if value.get("provider_snapshot_id"):
            result["provider_snapshot"] = asdict(
                self.store.targets.snapshot(value["provider_snapshot_id"])
            )
        result["boundary"] = (
            "Measurement context is not evidence of axSpA treatment, "
            "safety or target engagement."
        )
        return result
