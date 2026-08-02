"""Small, immutable scientific domain primitives.

These models describe knowledge before choosing a database representation.
They intentionally contain no persistence or connector behaviour.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class EntityKind(StrEnum):
    DISEASE = "disease"
    DATASET = "dataset"
    STUDY = "study"
    SAMPLE = "sample"
    GENE = "gene"
    PROTEIN = "protein"
    DRUG = "drug"
    PUBLICATION = "publication"
    PATHWAY = "pathway"
    BIOMARKER = "biomarker"


class KnowledgeKind(StrEnum):
    """The epistemic status of a knowledge record."""

    SOURCE_ASSERTION = "source_assertion"
    AXIS_OBSERVATION = "axis_observation"
    AXIS_INFERENCE = "axis_inference"
    AI_SUGGESTION = "ai_suggestion"
    RESEARCHER_HYPOTHESIS = "researcher_hypothesis"


class SourceKind(StrEnum):
    GEO = "geo"
    PUBLICATION = "publication"
    AXIS_PIPELINE = "axis_pipeline"
    AI_MODEL = "ai_model"
    RESEARCHER = "researcher"


class HypothesisState(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPPORTED = "supported"
    CHALLENGED = "challenged"
    REJECTED = "rejected"
    ARCHIVED = "archived"


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


@dataclass(frozen=True)
class EntityRef:
    kind: EntityKind
    identifier: str
    label: str
    namespace: str

    def __post_init__(self) -> None:
        _require_text(self.identifier, "identifier")
        _require_text(self.label, "label")
        _require_text(self.namespace, "namespace")


@dataclass(frozen=True)
class Transformation:
    name: str
    version: str
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.name, "transformation name")
        _require_text(self.version, "transformation version")


@dataclass(frozen=True)
class Provenance:
    source_kind: SourceKind
    source_identifier: str
    retrieved_at: datetime
    source_uri: str | None = None
    checksum: str | None = None
    transformations: tuple[Transformation, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.source_identifier, "source_identifier")
        _require_aware_datetime(self.retrieved_at, "retrieved_at")
        if self.source_uri is not None:
            _require_text(self.source_uri, "source_uri")
        if self.checksum is not None:
            _require_text(self.checksum, "checksum")


@dataclass(frozen=True)
class ClaimContext:
    """Experimental context; unknown values remain explicit as ``None``."""

    tissue: str | None = None
    assay: str | None = None
    population: str | None = None
    comparison: str | None = None
    treatment: str | None = None
    species: str | None = None


@dataclass(frozen=True)
class Claim:
    identifier: str
    subject: EntityRef
    predicate: str
    object: EntityRef
    knowledge_kind: KnowledgeKind
    provenance: Provenance
    context: ClaimContext = field(default_factory=ClaimContext)
    confidence: float | None = None

    def __post_init__(self) -> None:
        _require_text(self.identifier, "claim identifier")
        _require_text(self.predicate, "predicate")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class Study:
    """Minimal source-independent study metadata used for discovery."""

    identifier: str
    title: str
    summary: str
    source: SourceKind
    provenance: Provenance
    organisms: tuple[str, ...] = ()
    experiment_type: str | None = None
    sample_count: int | None = None
    platform_ids: tuple[str, ...] = ()
    publication_ids: tuple[str, ...] = ()
    bioproject_id: str | None = None
    released_on: date | None = None

    def __post_init__(self) -> None:
        _require_text(self.identifier, "study identifier")
        _require_text(self.title, "study title")
        if self.sample_count is not None and self.sample_count < 0:
            raise ValueError("sample_count must not be negative")
        if any(not value.strip() for value in self.organisms):
            raise ValueError("organisms must not contain empty values")
        if any(not value.strip() for value in self.platform_ids):
            raise ValueError("platform_ids must not contain empty values")
        if any(not value.strip() for value in self.publication_ids):
            raise ValueError("publication_ids must not contain empty values")


@dataclass(frozen=True)
class HypothesisRevision:
    revision: int
    created_at: datetime
    state: HypothesisState
    description: str
    rationale: str
    evidence_ids: tuple[str, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise ValueError("revision must be at least 1")
        _require_aware_datetime(self.created_at, "created_at")
        _require_text(self.description, "description")
        _require_text(self.rationale, "rationale")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if any(not evidence_id.strip() for evidence_id in self.evidence_ids):
            raise ValueError("evidence identifiers must not be empty")


@dataclass(frozen=True)
class Hypothesis:
    identifier: str
    title: str
    revisions: tuple[HypothesisRevision, ...]

    def __post_init__(self) -> None:
        _require_text(self.identifier, "hypothesis identifier")
        _require_text(self.title, "title")
        if not self.revisions:
            raise ValueError("a hypothesis requires at least one revision")
        expected = tuple(range(1, len(self.revisions) + 1))
        actual = tuple(revision.revision for revision in self.revisions)
        if actual != expected:
            raise ValueError("hypothesis revisions must be sequential")
        timestamps = tuple(revision.created_at for revision in self.revisions)
        if timestamps != tuple(sorted(timestamps)):
            raise ValueError("hypothesis revisions must be chronological")

    @property
    def current(self) -> HypothesisRevision:
        return self.revisions[-1]

    def revise(self, revision: HypothesisRevision) -> "Hypothesis":
        expected_revision = len(self.revisions) + 1
        if revision.revision != expected_revision:
            raise ValueError(f"next revision must be {expected_revision}")
        if revision.created_at < self.current.created_at:
            raise ValueError("new revision cannot predate the current revision")
        return Hypothesis(
            identifier=self.identifier,
            title=self.title,
            revisions=self.revisions + (revision,),
        )
