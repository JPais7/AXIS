"""Performed cellular evidence; proposals remain in discovery.ProposedExperiment."""

from dataclasses import dataclass, field
from typing import Literal

from axis.domain.models import ClaimContext, _require_text

Edge = Literal[
    "exposure",
    "biochemical",
    "engagement",
    "functional",
    "hla",
    "immune",
    "disease",
    "clinical",
]
State = Literal[
    "supported",
    "contradicted",
    "mixed",
    "not_assessed",
    "insufficient",
    "not_applicable",
]
EDGES: tuple[Edge, ...] = (
    "exposure",
    "biochemical",
    "engagement",
    "functional",
    "hla",
    "immune",
    "disease",
    "clinical",
)


@dataclass(frozen=True)
class BiologicalContext:
    scientific_context: ClaimContext = field(default_factory=ClaimContext)
    cell_line: str | None = None
    hla_allele: str | None = None
    hla_expression: str | None = None
    disease_status: str | None = None
    erap1_allotype: str | None = None
    donor_context: str | None = None
    mhc_allele: str | None = None


@dataclass(frozen=True)
class CellularExperiment:
    id: str
    label: str
    perturbation_id: str
    context: BiologicalContext
    source_id: str
    locator: str
    controls: tuple[str, ...]
    compound_id: str | None = None
    reported_perturbagen: str | None = None
    modality: str = "other"
    concentration: str | None = None
    duration: str | None = None
    dosing_schedule: str | None = None
    vehicle: str | None = None
    limitation: str = "AI-assisted extraction; pending expert review"

    def __post_init__(self) -> None:
        for name in ("id", "label", "perturbation_id", "source_id", "locator"):
            _require_text(getattr(self, name), name)
        if self.modality not in {
            "small_molecule",
            "knockdown",
            "knockout",
            "overexpression",
            "variant_expression",
            "CRISPR",
            "antibody",
            "other",
        }:
            raise ValueError("unsupported perturbation modality")
        if self.compound_id and self.modality != "small_molecule":
            raise ValueError("compound link requires chemical perturbation")


@dataclass(frozen=True)
class ExperimentalReadout:
    id: str
    experiment_id: str
    endpoint: str
    qualitative_result: str
    direction: str
    proximity: str
    locator: str
    claim_id: str | None = None
    measurement_id: str | None = None
    original_value: str | None = None
    original_unit: str | None = None
    statistical_result: str | None = None
    replicate_information: str | None = None

    def __post_init__(self) -> None:
        if not self.claim_id and not self.measurement_id:
            raise ValueError("readout requires an existing source assertion")
        if self.direction not in {"increase", "decrease", "changed", "unchanged"}:
            raise ValueError("invalid direction")
        if self.proximity not in {
            "target_proximal",
            "pathway_proximal",
            "HLA_molecular",
            "immune_cell",
            "disease_phenotype",
            "clinical",
            "unknown",
        }:
            raise ValueError("invalid readout proximity")
        for name in ("id", "experiment_id", "endpoint", "locator"):
            _require_text(getattr(self, name), name)


@dataclass(frozen=True)
class CellularAssessment:
    """Categorical interpretation, never a measurement or validation score."""

    id: str
    experiment_id: str
    edge: Edge
    state: State
    rationale: str
    supporting_readout_ids: tuple[str, ...] = ()
    contradicting_readout_ids: tuple[str, ...] = ()
    directness: str = "not_assessed"
    dependency: str = "not_assessed"
    disease_relevance: str = "unknown"
    review_status: str = "pending_expert_review"
    created_by: str = "AXIS AI-assisted curation"
    rule_version: str = "axis-cellular-1"

    def __post_init__(self) -> None:
        if self.edge not in EDGES or self.state not in {
            "supported",
            "contradicted",
            "mixed",
            "not_assessed",
            "insufficient",
            "not_applicable",
        }:
            raise ValueError("invalid evidence edge/state")
        if self.state in {"supported", "contradicted", "mixed"} and not (
            self.supporting_readout_ids or self.contradicting_readout_ids
        ):
            raise ValueError("assessed edge requires readout inputs")
        if (
            self.edge == "engagement"
            and self.state == "supported"
            and (self.directness != "direct_cellular_interaction")
        ):
            raise ValueError("phenotype is not direct cellular engagement")
        if self.review_status != "pending_expert_review":
            raise ValueError("curation cannot auto-accept scientific review")


@dataclass(frozen=True)
class ImmunopeptidomeObservation:
    id: str
    readout_id: str
    hla_allele: str | None
    comparison: str
    aggregate_observation: str
    source_locator: str
    raw_peptide_data_imported: bool = False

    def __post_init__(self) -> None:
        if self.raw_peptide_data_imported:
            raise ValueError("this slice supports published aggregate observations")
