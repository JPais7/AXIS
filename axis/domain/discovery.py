"""Immutable discovery records built around contextual Claims, not replacing them."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from axis.domain.models import (
    ClaimContext,
    EntityKind,
    EntityRef,
    KnowledgeKind,
    Provenance,
    SourceKind,
    _require_aware_datetime,
    _require_text,
)


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class StrategyStatus(StrEnum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    ARCHIVED = "archived"


class QuestionStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


class PerturbationStatus(StrEnum):
    PROPOSED = "proposed"
    PERFORMED = "performed"


class PerturbationType(StrEnum):
    KNOCKOUT = "knockout"
    KNOCKDOWN = "knockdown"
    CRISPR = "CRISPR"
    OVEREXPRESSION = "overexpression"
    INHIBITOR = "inhibitor"
    ACTIVATOR = "activator"
    DEGRADER = "degrader"
    GENETIC_VARIANT = "genetic_variant"
    ALLOSTERIC_MODULATOR = "allosteric_modulator"
    OTHER = "other"


class PerturbationDirection(StrEnum):
    DECREASE = "decrease"
    INCREASE = "increase"
    MODULATE = "modulate"
    UNKNOWN = "unknown"


class StrategyType(StrEnum):
    INHIBIT = "inhibit"
    PARTIALLY_INHIBIT = "partially_inhibit"
    ACTIVATE = "activate"
    DEGRADE = "degrade"
    STABILIZE = "stabilize"
    DESTABILIZE = "destabilize"
    ALLOSTERICALLY_MODULATE = "allosterically_modulate"
    BLOCK_INTERACTION = "block_interaction"
    ALLELE_SPECIFIC_MODULATION = "allele_specific_modulation"
    EXPRESSION_MODULATION = "expression_modulation"
    OTHER = "other"


class EvidenceRole(StrEnum):
    SUPPORTS = "supports"
    WEAKLY_SUPPORTS = "weakly_supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
    INCONCLUSIVE = "inconclusive"
    UNTYPED_CONSIDERED = "untyped_considered"


class MechanismClassification(StrEnum):
    DIRECTLY_DEMONSTRATED = "directly_demonstrated"
    INFERRED = "inferred"
    COMPUTATIONALLY_PREDICTED = "computationally_predicted"
    HYPOTHESIZED = "hypothesized"


class ProposalOrigin(StrEnum):
    AXIS = "axis_suggestion"
    RESEARCHER = "researcher_proposal"
    OTHER = "other_proposal"


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    ARCHIVED = "archived"


def _target(target: EntityRef) -> None:
    if target.kind not in (EntityKind.GENE, EntityKind.PROTEIN):
        raise ValueError("target must be a gene or protein EntityRef")


def _dates(created: datetime, updated: datetime) -> None:
    _require_aware_datetime(created, "created_at")
    _require_aware_datetime(updated, "updated_at")
    if updated < created:
        raise ValueError("updated_at cannot predate created_at")


def _enum(value: StrEnum, enum: type[StrEnum]) -> None:
    if not isinstance(value, enum):
        raise ValueError(f"expected {enum.__name__}, got {value!r}")


def _epistemic(kind: KnowledgeKind, provenance: Provenance) -> None:
    _enum(kind, KnowledgeKind)
    if (
        provenance.source_kind == SourceKind.AI_MODEL
        and kind != KnowledgeKind.AI_SUGGESTION
    ):
        raise ValueError("AI source must remain an AI suggestion")


@dataclass(frozen=True)
class TargetDiseasePair:
    pair_id: str
    target: EntityRef
    disease: EntityRef
    indication_scope: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.pair_id, "pair_id")
        _target(self.target)
        if self.disease.kind != EntityKind.DISEASE:
            raise ValueError("disease must be a disease EntityRef")
        _require_text(self.indication_scope, "indication_scope")
        _require_aware_datetime(self.created_at, "created_at")

    @property
    def identity_key(self) -> str:
        """Stable namespace-aware key; labels and creation dates are not identity."""
        identity = (
            self.target.kind.value,
            self.target.namespace,
            self.target.identifier,
            self.disease.kind.value,
            self.disease.namespace,
            self.disease.identifier,
            " ".join(self.indication_scope.split()).casefold(),
        )
        return sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class DiscoveryProject:
    project_id: str
    target_disease_pair: str
    objective: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for name in ("project_id", "target_disease_pair", "objective"):
            _require_text(getattr(self, name), name)
        _enum(self.status, ProjectStatus)
        _dates(self.created_at, self.updated_at)


@dataclass(frozen=True)
class Perturbation:
    perturbation_id: str
    target: EntityRef
    perturbation_type: PerturbationType
    direction: PerturbationDirection
    status: PerturbationStatus
    provenance: Provenance
    knowledge_kind: KnowledgeKind
    scientific_context: ClaimContext = field(default_factory=ClaimContext)
    intervention: EntityRef | None = None
    observed_effect_claim_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.perturbation_id, "perturbation_id")
        _target(self.target)
        _enum(self.perturbation_type, PerturbationType)
        _enum(self.direction, PerturbationDirection)
        _enum(self.status, PerturbationStatus)
        _epistemic(self.knowledge_kind, self.provenance)
        if self.observed_effect_claim_id is not None:
            _require_text(self.observed_effect_claim_id, "observed_effect_claim_id")
            if self.status != PerturbationStatus.PERFORMED:
                raise ValueError("proposed perturbations cannot have observed effects")
        if self.status == PerturbationStatus.PROPOSED:
            if self.knowledge_kind not in (
                KnowledgeKind.AI_SUGGESTION,
                KnowledgeKind.RESEARCHER_HYPOTHESIS,
                KnowledgeKind.AXIS_INFERENCE,
            ):
                raise ValueError("proposed perturbations must have a proposal kind")
        elif self.knowledge_kind not in (
            KnowledgeKind.SOURCE_ASSERTION,
            KnowledgeKind.AXIS_OBSERVATION,
            KnowledgeKind.EXPERIMENTAL_RESULT,
        ):
            raise ValueError("performed perturbations require observational evidence")


@dataclass(frozen=True)
class InterventionStrategy:
    strategy_id: str
    project_id: str
    strategy_type: StrategyType
    description: str
    rationale: str
    status: StrategyStatus
    provenance: Provenance
    knowledge_kind: KnowledgeKind = KnowledgeKind.RESEARCHER_HYPOTHESIS

    def __post_init__(self) -> None:
        for name in ("strategy_id", "project_id", "description", "rationale"):
            _require_text(getattr(self, name), name)
        _enum(self.strategy_type, StrategyType)
        _enum(self.status, StrategyStatus)
        _epistemic(self.knowledge_kind, self.provenance)
        if self.knowledge_kind not in (
            KnowledgeKind.RESEARCHER_HYPOTHESIS,
            KnowledgeKind.AI_SUGGESTION,
            KnowledgeKind.AXIS_INFERENCE,
        ):
            raise ValueError(
                "strategies are interpretations/proposals, not source facts"
            )


@dataclass(frozen=True)
class OpenQuestion:
    question_id: str
    project_id: str
    question: str
    uncertainty_type: str
    status: QuestionStatus
    created_at: datetime
    updated_at: datetime
    scientific_context: ClaimContext = field(default_factory=ClaimContext)

    def __post_init__(self) -> None:
        for name in ("question_id", "project_id", "question", "uncertainty_type"):
            _require_text(getattr(self, name), name)
        _enum(self.status, QuestionStatus)
        _dates(self.created_at, self.updated_at)


@dataclass(frozen=True)
class EvidenceAssessment:
    assessment_id: str
    project_id: str
    claim_id: str
    role: EvidenceRole
    reasoning: str
    provenance: Provenance
    strategy_id: str | None = None
    question_id: str | None = None
    hypothesis_id: str | None = None
    hypothesis_revision: int | None = None

    def __post_init__(self) -> None:
        for name in ("assessment_id", "project_id", "claim_id", "reasoning"):
            _require_text(getattr(self, name), name)
        _enum(self.role, EvidenceRole)
        if (
            sum(
                value is not None
                for value in (self.strategy_id, self.question_id, self.hypothesis_id)
            )
            != 1
        ):
            raise ValueError("assessment requires exactly one typed subject")
        for value in (self.strategy_id, self.question_id, self.hypothesis_id):
            if value is not None:
                _require_text(value, "assessment subject")
        if (self.hypothesis_id is None) != (self.hypothesis_revision is None):
            raise ValueError("hypothesis assessment requires a revision")
        if self.hypothesis_revision is not None and self.hypothesis_revision < 1:
            raise ValueError("hypothesis_revision must be positive")
        if (
            self.provenance.source_kind == SourceKind.AI_MODEL
            and self.role != EvidenceRole.UNTYPED_CONSIDERED
        ):
            raise ValueError(
                "AI assessments require researcher review before persistence"
            )


@dataclass(frozen=True)
class MechanisticAssessment:
    assessment_id: str
    project_id: str
    claim_id: str
    classification: MechanismClassification
    reasoning: str
    provenance: Provenance

    def __post_init__(self) -> None:
        for name in ("assessment_id", "project_id", "claim_id", "reasoning"):
            _require_text(getattr(self, name), name)
        _enum(self.classification, MechanismClassification)
        if (
            self.provenance.source_kind == SourceKind.AI_MODEL
            and self.classification != MechanismClassification.HYPOTHESIZED
        ):
            raise ValueError("AI mechanism assessments require researcher review")


@dataclass(frozen=True)
class ProposedExperiment:
    experiment_id: str
    project_id: str
    question_id: str
    title: str
    rationale: str
    experimental_system: str
    intervention_description: str
    endpoint_description: str
    provenance: Provenance
    suggestion_origin: ProposalOrigin
    knowledge_kind: KnowledgeKind
    status: ProposalStatus
    scientific_context: ClaimContext = field(default_factory=ClaimContext)

    def __post_init__(self) -> None:
        for name in (
            "experiment_id",
            "project_id",
            "question_id",
            "title",
            "rationale",
            "experimental_system",
            "intervention_description",
            "endpoint_description",
        ):
            _require_text(getattr(self, name), name)
        _enum(self.suggestion_origin, ProposalOrigin)
        _enum(self.status, ProposalStatus)
        _epistemic(self.knowledge_kind, self.provenance)
        expected = {
            ProposalOrigin.AXIS: (
                KnowledgeKind.AI_SUGGESTION,
                KnowledgeKind.AXIS_INFERENCE,
            ),
            ProposalOrigin.RESEARCHER: (KnowledgeKind.RESEARCHER_HYPOTHESIS,),
            ProposalOrigin.OTHER: (
                KnowledgeKind.AI_SUGGESTION,
                KnowledgeKind.RESEARCHER_HYPOTHESIS,
            ),
        }
        if self.knowledge_kind not in expected[self.suggestion_origin]:
            raise ValueError("proposed experiment requires a compatible proposal kind")


@dataclass(frozen=True)
class OutcomeScenario:
    scenario_id: str
    experiment_id: str
    possible_outcome: str
    interpretation: str

    def __post_init__(self) -> None:
        for name in (
            "scenario_id",
            "experiment_id",
            "possible_outcome",
            "interpretation",
        ):
            _require_text(getattr(self, name), name)


@dataclass(frozen=True)
class QuestionLinks:
    claim_ids: tuple[str, ...] = ()
    hypothesis_ids: tuple[str, ...] = ()
    strategy_ids: tuple[str, ...] = ()
    perturbation_ids: tuple[str, ...] = ()
