"""Measurement-first pharmacology. No potency aggregation or efficacy inference."""

from dataclasses import dataclass, field
from math import isfinite
from typing import Any

OPERATORS = {"=", "<", "<=", ">", ">=", "~"}
CONCENTRATION = {
    "nM": 1.0,
    "uM": 1000.0,
    "µM": 1000.0,
    "μM": 1000.0,
    "mM": 1000000.0,
    "M": 1000000000.0,
}
ASSAY_TYPES = {
    "biochemical_activity",
    "binding",
    "target_engagement",
    "cellular_activity",
    "cellular_phenotype",
    "disease_relevant_phenotype",
    "other",
    "unknown",
}


@dataclass(frozen=True)
class CompoundIdentity:
    id: str
    preferred_name: str
    source_snapshot_id: str
    original_smiles: str | None = None
    canonical_smiles: str | None = None
    isomeric_smiles: str | None = None
    canonical_inchi: str | None = None
    inchi_key: str | None = None
    molecular_formula: str | None = None
    molecular_weight: float | None = None
    formal_charge: int | None = None
    stereochemistry_status: str = "unknown"
    identity_status: str = "unresolved"
    aliases: tuple[str, ...] = ()
    transformation: dict[str, Any] = field(default_factory=dict)
    depiction_svg: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.preferred_name or not self.source_snapshot_id:
            raise ValueError("compound identity requires identifiers and source")
        if self.identity_status not in {"resolved", "unresolved", "conflicting"}:
            raise ValueError("invalid chemical identity status")
        if self.stereochemistry_status not in {
            "explicit",
            "partial",
            "unknown",
            "racemic",
            "not_applicable",
        }:
            raise ValueError("invalid stereochemistry status")
        if self.identity_status == "resolved" and not self.isomeric_smiles:
            raise ValueError("resolved chemical identity requires a structure")


@dataclass(frozen=True)
class CompoundExternalIdentifier:
    id: str
    compound_id: str
    namespace: str
    external_id: str
    source_snapshot_id: str
    mapping_status: str
    notes: str = ""

    def __post_init__(self) -> None:
        if self.mapping_status not in {"resolved", "unresolved", "rejected"}:
            raise ValueError("invalid identifier mapping status")


@dataclass(frozen=True)
class ChemicalForm:
    id: str
    compound_id: str
    form_type: str
    source_snapshot_id: str
    description: str
    parent_compound_id: str | None = None

    def __post_init__(self) -> None:
        if self.form_type not in {
            "parent",
            "salt",
            "solvate",
            "mixture",
            "stereoisomer",
            "racemate",
            "prodrug",
            "isotopologue",
            "unspecified",
        }:
            raise ValueError("invalid chemical form")


@dataclass(frozen=True)
class MeasurementCondition:
    name: str
    value: str | None
    unit: str | None = None


@dataclass(frozen=True)
class Assay:
    id: str
    name: str
    assay_type: str
    target_gene: str
    source_snapshot_id: str
    source_assay_identifier: str
    locator: str
    taxon_id: int | None = None
    reported_accession: str | None = None
    target_type: str = "unknown"
    protein_identity_id: str | None = None
    protein_construct_id: str | None = None
    construct_mapping_status: str = "unknown"
    reported_construct: str | None = None
    assay_format: str | None = None
    biological_system: str | None = None
    cell_line: str | None = None
    substrate: str | None = None
    detection_method: str | None = None
    conditions: tuple[MeasurementCondition, ...] = ()
    description: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.assay_type not in ASSAY_TYPES or not self.id or not self.target_gene:
            raise ValueError("invalid assay")
        if self.construct_mapping_status not in {"unknown", "exact"}:
            raise ValueError("invalid construct mapping status")
        if (self.construct_mapping_status == "exact") != bool(
            self.protein_construct_id
        ):
            raise ValueError("exact construct mapping needs an explicit construct")


@dataclass(frozen=True)
class BioactivityMeasurement:
    id: str
    compound_id: str
    assay_id: str
    endpoint: str
    relation_operator: str
    original_value: str | None
    original_unit: str | None
    value: float | None
    source_snapshot_id: str
    source_record_id: str
    locator: str
    epistemic_type: str = "source_reported_experiment"
    normalized_value: float | None = None
    normalized_unit: str | None = None
    normalization_method: dict[str, Any] = field(default_factory=dict)
    provider_pchembl: str | None = None
    provider_snapshot_id: str | None = None
    uncertainty: str | None = None
    replicate_count: int | None = None
    limitations: str = ""
    created_at: str = ""
    chemical_form_id: str | None = None

    def __post_init__(self) -> None:
        if self.relation_operator not in OPERATORS or not self.endpoint:
            raise ValueError("invalid endpoint/operator")
        if self.value is not None:
            if not isfinite(self.value):
                raise ValueError("invalid measurement value")
            if self.original_value is None or float(self.original_value) != self.value:
                raise ValueError("original and parsed measurement disagree")
            if self.original_unit not in {*CONCENTRATION, "%", "fold", None}:
                raise ValueError("unsupported measurement unit")
            if self.endpoint in {"IC50", "EC50", "AC50", "Ki", "Kd"} and (
                self.value <= 0 or self.original_unit not in CONCENTRATION
            ):
                raise ValueError("potency requires positive concentration")
            if self.endpoint.startswith("percent") and self.original_unit != "%":
                raise ValueError("percentage endpoint requires percent unit")
        if self.replicate_count is not None and self.replicate_count < 1:
            raise ValueError("replicate count must be positive")


@dataclass(frozen=True)
class SelectivityAssessment:
    id: str
    compound_id: str
    primary_target_id: str
    comparison_target_id: str
    primary_measurement_id: str | None
    comparison_measurement_id: str | None
    comparability_status: str
    rationale: str
    assessment_type: str = "AXIS_computed_assessment"
    ratio: float | None = None
    ratio_lower_bound: float | None = None
    ratio_upper_bound: float | None = None
    lower_inclusive: bool | None = None
    upper_inclusive: bool | None = None
    transformation: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.comparability_status not in {
            "Comparable",
            "Not directly comparable",
            "Not assessed",
        }:
            raise ValueError("invalid comparability status")
        values = (self.ratio, self.ratio_lower_bound, self.ratio_upper_bound)
        if any(v is not None and (not isfinite(v) or v <= 0) for v in values):
            raise ValueError("invalid ratio")
        if self.comparability_status != "Comparable" and any(
            v is not None for v in values
        ):
            raise ValueError("incompatible measurements cannot produce a ratio")
        if any(v is not None for v in values) and (
            not self.primary_measurement_id
            or not self.comparison_measurement_id
            or not self.transformation
        ):
            raise ValueError("ratio requires traceable inputs and transformation")
