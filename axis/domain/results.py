"""Performed experiments, observed results, interpretations and reviews.

Deliberately target-neutral: target-specific biology travels in ``context`` and
``facets`` dictionaries, never in object or field names. A proposal, an
anticipated outcome, an observation, an interpretation, a review and a decision are
different objects (see ``docs/phase36-experimental-results-loop.md``).
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from axis.domain.models import KnowledgeKind, _require_aware_datetime, _require_text

RESULT_TYPES = (
    "numeric_measurement",
    "categorical_observation",
    "qualitative_observation",
    "image_derived_measurement",
    "omics_summary",
    "count",
    "ratio",
    "binary_detection",
    "technical_failure",
    "non_interpretable",
    "other",
)
OPERATORS = ("=", "<", "<=", ">", ">=", "~")
CONTROL_STATUSES = ("passed", "failed", "not_run", "not_reported")
VALIDITY = ("valid", "invalid", "uncertain")
REPLICATE_QUALITY = ("adequate", "limited", "inadequate", "not_reported")
QC_ASSESSMENTS = ("interpretable", "interpretable_with_caveat", "non_interpretable")
REPLICATE_TYPES = ("technical", "biological", "independent_experiment", "not_reported")
SCOPE_TYPES = ("compound", "perturbagen", "target", "context")
INTERPRETED_STATES = ("supported", "contradicted", "mixed", "insufficient")
REVIEW_DECISIONS = (
    "pending",
    "accepted",
    "accepted_with_caveat",
    "rejected",
    "needs_revision",
)
REVIEW_OBJECTS = (
    "experimental_result",
    "result_interpretation",
    "scenario_mapping",
    "candidate_design",
    "evidence_assessment",
)
MATCH_RELATIONSHIPS = (
    "matches",
    "partially_matches",
    "contradicts",
    "ambiguous",
    "outside_predefined_scenarios",
    "non_interpretable",
)
SCIENTIFIC_STATUSES = ("real", "synthetic_test_fixture")
ARTIFACT_ROLES = ("raw", "processed", "analysis", "report", "other")


def _in(value: str, allowed: tuple[str, ...], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"invalid {name}: {value!r}")


@dataclass(frozen=True)
class ExperimentalArtifact:
    """Reference to a file; contents never live in a database row."""

    id: str
    project_id: str
    uri: str
    sha256: str
    media_type: str
    size_bytes: int
    role: str = "raw"
    description: str = ""

    def __post_init__(self) -> None:
        for name in ("id", "project_id", "uri", "media_type"):
            _require_text(getattr(self, name), name)
        if len(self.sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.sha256
        ):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")
        _in(self.role, ARTIFACT_ROLES, "artifact role")


@dataclass(frozen=True)
class DesignDeviation:
    """A difference between the proposed and the performed design."""

    id: str
    performed_experiment_id: str
    field: str
    proposed_value: str
    actual_value: str
    deviation_type: str
    rationale: str
    interpretation_relevance: str = "limits_interpretation"
    proposed_experiment_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("id", "performed_experiment_id", "field", "deviation_type"):
            _require_text(getattr(self, name), name)
        _in(
            self.interpretation_relevance,
            ("none", "limits_interpretation", "invalidates_comparison"),
            "interpretation_relevance",
        )


@dataclass(frozen=True)
class PerformedExperiment:
    """An experiment that was actually executed; unknown stays unknown."""

    id: str
    project_id: str
    protein_id: str | None
    scope_type: str
    scope_id: str
    measures_edges: tuple[str, ...]
    endpoints: tuple[str, ...]
    scientific_status: str = "real"
    proposal_id: str | None = None
    executed_at: datetime | None = None
    performed_by: str | None = None
    context: dict[str, str | None] = field(default_factory=dict)
    perturbation: str | None = None
    compound_id: str | None = None
    reported_perturbagen: str | None = None
    target_label: str | None = None
    construct: str = "not reported"
    assay: str | None = None
    controls: tuple[str, ...] = ()
    exposure: str | None = None
    protocol_reference: str | None = None
    source_artifact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "project_id", "scope_id"):
            _require_text(getattr(self, name), name)
        _in(self.scope_type, SCOPE_TYPES, "scope_type")
        _in(self.scientific_status, SCIENTIFIC_STATUSES, "scientific_status")
        if not self.measures_edges:
            raise ValueError(
                "a performed experiment must declare the edge(s) it measures"
            )
        if self.executed_at is not None:
            _require_aware_datetime(self.executed_at, "executed_at")
        if self.scope_type == "compound" and self.compound_id != self.scope_id:
            raise ValueError("compound scope requires the matching compound_id")
        if self.scope_type == "perturbagen" and not self.reported_perturbagen:
            raise ValueError("perturbagen scope requires a source-reported perturbagen")
        if self.compound_id and self.reported_perturbagen:
            raise ValueError(
                "a resolved compound and an unresolved perturbagen are exclusive"
            )


@dataclass(frozen=True)
class QualityAssessment:
    """Categorical QC; there is deliberately no composite score."""

    id: str
    performed_experiment_id: str
    control_status: str
    technical_validity: str
    replicate_quality: str
    assessment: str
    rationale: str
    missing_data: str = "none reported"
    supersedes_id: str | None = None

    def __post_init__(self) -> None:
        _in(self.control_status, CONTROL_STATUSES, "control_status")
        _in(self.technical_validity, VALIDITY, "technical_validity")
        _in(self.replicate_quality, REPLICATE_QUALITY, "replicate_quality")
        _in(self.assessment, QC_ASSESSMENTS, "assessment")
        _require_text(self.rationale, "rationale")
        if self.assessment != "non_interpretable" and (
            self.control_status == "failed" or self.technical_validity == "invalid"
        ):
            raise ValueError("failed controls or invalid assay cannot be interpretable")


@dataclass(frozen=True)
class ExperimentalResult:
    """What was observed. Immutable; corrections are new versions."""

    id: str
    version: int
    project_id: str
    performed_experiment_id: str
    endpoint: str
    result_type: str
    recorded_at: datetime
    recorded_by: str
    qualitative_result: str | None = None
    numeric_value: float | None = None
    operator: str = "="
    unit: str | None = None
    uncertainty: str | None = None
    replicate_summary: dict[str, str | int | None] = field(default_factory=dict)
    statistics: dict[str, str | float | int | None] = field(default_factory=dict)
    raw_artifact_ids: tuple[str, ...] = ()
    processed_artifact_ids: tuple[str, ...] = ()
    transformations: tuple[dict[str, str], ...] = ()
    analysis_method: str | None = None
    analysis_version: str | None = None
    observed_at: datetime | None = None
    facets: dict[str, str] = field(default_factory=dict)
    supersedes_id: str | None = None
    knowledge_kind: KnowledgeKind = KnowledgeKind.EXPERIMENTAL_RESULT

    def __post_init__(self) -> None:
        for name in (
            "id",
            "project_id",
            "performed_experiment_id",
            "endpoint",
            "recorded_by",
        ):
            _require_text(getattr(self, name), name)
        _in(self.result_type, RESULT_TYPES, "result_type")
        _in(self.operator, OPERATORS, "operator")
        _require_aware_datetime(self.recorded_at, "recorded_at")
        if self.observed_at is not None:
            _require_aware_datetime(self.observed_at, "observed_at")
        if self.version < 1 or (self.version == 1) != (self.supersedes_id is None):
            raise ValueError("version and supersedes_id disagree")
        if self.knowledge_kind != KnowledgeKind.EXPERIMENTAL_RESULT:
            raise ValueError(
                "a performed result is an experimental_result, nothing else"
            )
        if self.numeric_value is not None:
            if self.numeric_value != self.numeric_value or abs(
                self.numeric_value
            ) == float("inf"):
                raise ValueError("numeric_value must be finite")
            if self.result_type not in (
                "numeric_measurement",
                "image_derived_measurement",
                "count",
                "ratio",
                "omics_summary",
            ):
                raise ValueError("this result type does not carry a number")
            if not self.unit and self.result_type == "numeric_measurement":
                raise ValueError(
                    "a numeric measurement requires a unit (use 'dimensionless')"
                )
        if (
            self.numeric_value is None
            and not self.qualitative_result
            and self.result_type
            not in (
                "technical_failure",
                "non_interpretable",
            )
        ):
            raise ValueError("a result needs a value or a qualitative observation")
        for key in ("n",):
            n = self.replicate_summary.get(key)
            if n is not None and (not isinstance(n, int) or n < 1):
                raise ValueError("replicate n must be a positive integer")
        rtype = self.replicate_summary.get("type")
        if rtype is not None:
            _in(str(rtype), REPLICATE_TYPES, "replicate type")


@dataclass(frozen=True)
class ResultInterpretation:
    """What the observation might mean; never an observation itself."""

    id: str
    result_id: str
    edge: str
    scope_type: str
    scope_id: str
    proposed_state: str
    statement: str
    rationale: str
    knowledge_kind: KnowledgeKind = KnowledgeKind.AI_SUGGESTION
    generated_by: str = "AXIS AI-assisted suggestion"
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "result_id", "edge", "scope_id", "statement", "rationale"):
            _require_text(getattr(self, name), name)
        _in(self.scope_type, SCOPE_TYPES, "scope_type")
        _in(self.proposed_state, INTERPRETED_STATES, "proposed_state")
        if self.knowledge_kind not in (
            KnowledgeKind.AI_SUGGESTION,
            KnowledgeKind.RESEARCHER_HYPOTHESIS,
        ):
            raise ValueError(
                "an interpretation is a suggestion or a researcher hypothesis"
            )


@dataclass(frozen=True)
class ScenarioMatch:
    id: str
    result_id: str
    relationship: str
    rationale: str
    rule_version: str
    outcome_scenario_id: str | None = None
    matched: tuple[str, ...] = ()
    conflicting: tuple[str, ...] = ()
    unobserved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _in(self.relationship, MATCH_RELATIONSHIPS, "relationship")
        _require_text(self.rationale, "rationale")


@dataclass(frozen=True)
class ScientificReview:
    """One reviewer's decision about one object; history is append-only."""

    id: str
    project_id: str
    object_type: str
    object_id: str
    reviewer: str
    decision: str
    rationale: str
    reviewed_at: datetime
    caveat: str | None = None
    supersedes_review_id: str | None = None
    reviewer_kind: str = "investigator"

    def __post_init__(self) -> None:
        for name in ("id", "project_id", "object_id", "reviewer", "rationale"):
            _require_text(getattr(self, name), name)
        _in(self.object_type, REVIEW_OBJECTS, "object_type")
        _in(self.decision, REVIEW_DECISIONS, "decision")
        _require_aware_datetime(self.reviewed_at, "reviewed_at")
        if self.reviewer_kind != "investigator":
            raise ValueError("only an explicit investigator action can review science")
        if re.search(
            r"\b(ai|axis|assistant|claude|gpt|llm|model)\b",
            self.reviewer,
            re.IGNORECASE,
        ):
            raise ValueError("AI cannot accept its own science")
        if self.decision == "accepted_with_caveat" and not self.caveat:
            raise ValueError("accepted_with_caveat requires the caveat")
