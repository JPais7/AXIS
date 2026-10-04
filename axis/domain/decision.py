"""Experimental decision records; categorical, never scored.

Hypotheses, proposed experiments and outcome scenarios stay in
``axis.domain.models`` / ``axis.domain.discovery``. Nothing here is a probability,
an information-gain figure or a ranking score.
"""

from dataclasses import dataclass, field
from datetime import datetime

from axis.domain.models import (
    KnowledgeKind,
    _require_aware_datetime,
    _require_text,
)

EXPLANATION_STATUSES = (
    "supported",
    "partially_supported",
    "viable",
    "weakened",
    "contradicted",
    "unresolved",
)
LINK_RELATIONSHIPS = ("supports", "contradicts", "leaves_unresolved", "context_limits")
UNCERTAINTY_CATEGORIES = (
    "target_engagement",
    "target_dependency",
    "selectivity",
    "mechanistic_bridge",
    "genetic_context",
    "disease_relevance",
    "reproducibility",
    "assay_translation",
    "structural_mechanism",
    "clinical_translation",
    "other",
)
UNCERTAINTY_STATUSES = (
    "open",
    "partially_resolved",
    "resolved_for_current_decision",
    "superseded",
    "not_actionable",
)
DECISION_RELEVANCE = (
    "decision_blocking",
    "decision_material",
    "informative",
    "peripheral",
)
RESOLVABILITY = (
    "directly_testable",
    "indirectly_testable",
    "requires_multiple_experiments",
    "currently_not_testable",
    "unknown",
)
OUTCOME_EFFECTS = (
    "strengthens",
    "weakens",
    "does_not_discriminate",
    "contradicts",
    "resolves_for_current_decision",
)
SCENARIO_KINDS = ("supportive", "negative", "alternative", "non_interpretable")
CONSEQUENCES = (
    "continue_current_strategy",
    "strengthen_current_strategy",
    "weaken_current_strategy",
    "deprioritize_current_strategy",
    "change_mechanistic_model",
    "require_replication",
    "require_orthogonal_validation",
    "investigate_context_dependence",
    "advance_to_next_evidence_layer",
    "stop_for_now",
)
PURPOSES = (
    "discriminate_mechanism",
    "establish_target_engagement",
    "establish_target_dependency",
    "resolve_selectivity",
    "test_context_dependence",
    "validate_disease_relevance",
    "replicate_finding",
    "characterize_pharmacology",
    "other",
)
PROXIMITY = (
    "direct_target",
    "target_proximal",
    "pathway_proximal",
    "downstream",
    "disease_phenotype",
)
LEVELS = ("high", "moderate", "low", "unknown")
TIMES = ("short", "medium", "long", "unknown")
FEASIBILITY = (
    "feasible_with_current_resources",
    "requires_new_capability",
    "external_collaboration",
    "blocked",
    "unknown",
)
EXPERIMENT_STATUSES = (
    "proposed",
    "investigator_selected",
    "planned",
    "in_progress",
    "completed",
    "cancelled",
)
DISCRIMINATION_ROLES = (
    "mechanism_discrimination",
    "characterization",
    "replication",
    "precision_improvement",
    "exploratory",
)


def _in(value: str, allowed: tuple[str, ...], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"invalid {name}: {value!r}")


@dataclass(frozen=True)
class CompetingExplanation:
    """AXIS suggestion that is admitted only through rule-derived grounding."""

    id: str
    project_id: str
    hypothesis_id: str
    hypothesis_revision: int
    ground: str
    label: str
    statement: str
    knowledge_kind: KnowledgeKind = KnowledgeKind.AI_SUGGESTION
    epistemic_kind: str = "alternative_mechanistic_explanation"
    created_by: str = "AXIS AI-assisted suggestion"
    supersedes_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("id", "project_id", "hypothesis_id", "ground", "label"):
            _require_text(getattr(self, name), name)
        _require_text(self.statement, "statement")
        if self.hypothesis_revision < 1:
            raise ValueError("hypothesis_revision must be positive")
        if self.knowledge_kind not in (
            KnowledgeKind.AI_SUGGESTION,
            KnowledgeKind.RESEARCHER_HYPOTHESIS,
        ):
            raise ValueError("explanations are suggestions or researcher hypotheses")


@dataclass(frozen=True)
class ExplanationEvidenceLink:
    explanation_id: str
    relationship: str
    evidence_type: str
    evidence_id: str
    rule_id: str
    rationale: str

    def __post_init__(self) -> None:
        _in(self.relationship, LINK_RELATIONSHIPS, "relationship")
        for name in ("explanation_id", "evidence_type", "evidence_id", "rule_id"):
            _require_text(getattr(self, name), name)
        _require_text(self.rationale, "rationale")


@dataclass(frozen=True)
class ScientificUncertainty:
    id: str
    category: str
    question: str
    status: str
    decision_relevance: str
    resolvability: str
    rationale: str
    fired_rules: tuple[str, ...]
    reasons: tuple[str, ...] = ()
    source_gap_ids: tuple[str, ...] = ()
    affected_explanation_ids: tuple[str, ...] = ()
    evidence_refs: tuple[tuple[str, str], ...] = ()
    affected_grounds: tuple[str, ...] = ()
    epistemic_kind: str = "axis_inference"

    def __post_init__(self) -> None:
        _in(self.category, UNCERTAINTY_CATEGORIES, "category")
        _in(self.status, UNCERTAINTY_STATUSES, "status")
        _in(self.decision_relevance, DECISION_RELEVANCE, "decision_relevance")
        _in(self.resolvability, RESOLVABILITY, "resolvability")
        _require_text(self.id, "id")
        _require_text(self.question, "question")
        _require_text(self.rationale, "rationale")
        if not self.fired_rules:
            raise ValueError("an uncertainty must name the rule that produced it")


@dataclass(frozen=True)
class OutcomeInterpretation:
    scenario_id: str
    explanation_id: str
    effect: str
    rationale: str

    def __post_init__(self) -> None:
        _in(self.effect, OUTCOME_EFFECTS, "effect")
        _require_text(self.scenario_id, "scenario_id")
        _require_text(self.explanation_id, "explanation_id")
        _require_text(self.rationale, "rationale")


@dataclass(frozen=True)
class DecisionConsequence:
    """Conditional: what changes *if* the scenario were observed."""

    scenario_id: str
    scenario_kind: str
    category: str
    conditional_statement: str
    new_uncertainty: str | None = None
    prospective: bool = True

    def __post_init__(self) -> None:
        _in(self.scenario_kind, SCENARIO_KINDS, "scenario_kind")
        _in(self.category, CONSEQUENCES, "consequence category")
        _require_text(self.conditional_statement, "conditional_statement")
        if not self.conditional_statement.lower().startswith("if "):
            raise ValueError("consequences must be stated conditionally")
        if not self.prospective:
            raise ValueError("no performed result exists in this layer")


@dataclass(frozen=True)
class CandidateExperimentProfile:
    experiment_id: str
    purpose: str
    role: str
    target_proximity: str
    disease_relevance: str
    considered_for: tuple[str, ...]
    addressed_gap_ids: tuple[str, ...]
    controls_negative: tuple[str, ...]
    controls_positive: tuple[str, ...]
    primary_endpoint: str
    secondary_endpoints: tuple[str, ...]
    limitations: tuple[str, ...]
    prerequisites: tuple[tuple[str, str], ...]
    required: dict[str, tuple[str, ...]] = field(default_factory=dict)
    confounders_addressed: tuple[str, ...] = ()
    context_requirements: dict[str, str] = field(default_factory=dict)
    complexity: str = "unknown"
    time_estimate: str = "unknown"
    cost: dict[str, str] | None = None

    def __post_init__(self) -> None:
        _in(self.purpose, PURPOSES, "purpose")
        _in(self.role, DISCRIMINATION_ROLES, "role")
        _in(self.target_proximity, PROXIMITY, "target_proximity")
        _in(self.complexity, LEVELS, "complexity")
        _in(self.time_estimate, TIMES, "time_estimate")
        _require_text(self.primary_endpoint, "primary_endpoint")
        for status in (status for _, status in self.prerequisites):
            _in(status, ("available_in_corpus", "not_established", "unknown"), "status")


@dataclass(frozen=True)
class DecisionConstraints:
    """Investigator-entered facts only; absence is reported, never filled."""

    id: str
    project_id: str
    version: int
    created_at: datetime
    created_by: str
    available_models: tuple[str, ...] = ()
    available_compounds: tuple[str, ...] = ()
    available_assays: tuple[str, ...] = ()
    available_equipment: tuple[str, ...] = ()
    external_collaborations: tuple[str, ...] = ()
    time_constraints: str | None = None
    cost_constraints: str | None = None
    ethical_constraints: str | None = None
    strategic_constraints: str | None = None
    excluded_experiment_ids: tuple[str, ...] = ()
    supersedes_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.created_by, "created_by")
        _require_aware_datetime(self.created_at, "created_at")
        if self.version < 1:
            raise ValueError("version must be positive")


@dataclass(frozen=True)
class DecisionState:
    """Immutable framing of the decision *given the evidence represented in AXIS*.

    It is not scientific truth; a changed evidence digest creates a new version.
    """

    id: str
    project_id: str
    protein_id: str
    version: int
    hypothesis_id: str
    hypothesis_revision: int
    created_at: datetime
    created_by: str
    evidence_digest: str
    rules_version: str
    rationale: str
    critical_uncertainty_id: str | None = None
    recommended_experiment_id: str | None = None
    supersedes_id: str | None = None
    status: str = "recorded"

    def __post_init__(self) -> None:
        for name in ("id", "project_id", "protein_id", "evidence_digest", "created_by"):
            _require_text(getattr(self, name), name)
        _require_aware_datetime(self.created_at, "created_at")
        if self.version < 1 or (self.version == 1) != (self.supersedes_id is None):
            raise ValueError("version and supersedes_id disagree")
        if self.status != "recorded":
            raise ValueError("a DecisionState is immutable once recorded")
