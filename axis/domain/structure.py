"""Experimental structural objects, distinct from proteins and pharmacology."""

import re
from dataclasses import dataclass
from enum import StrEnum

from axis.domain.models import _require_text
from axis.domain.protein import _sequence


class ResidueStatus(StrEnum):
    EXACT = "exact_match"
    MISMATCH = "mapping_mismatch"
    SUBSTITUTION = "source_reported_substitution"
    ENGINEERED = "engineered_substitution"
    UNRESOLVED = "unresolved_coordinate"
    OUTSIDE = "not_in_construct"
    DELETION = "deletion"
    INSERTION = "insertion"
    AMBIGUOUS = "ambiguous"
    UNMAPPED = "unmapped"


@dataclass(frozen=True)
class ProteinConstruct:
    id: str
    protein_identity_id: str
    isoform_id: str | None
    name: str
    start_residue: int
    end_residue: int
    construct_sequence: str
    construct_sequence_checksum: str
    expression_system: str | None
    engineered: bool | None
    substitutions: tuple[str, ...]
    deletions: tuple[int, ...]
    insertions: tuple[int, ...]
    tags: tuple[str, ...]
    fusion_partners: tuple[str, ...] | None
    notes: str
    source_snapshot_id: str

    def __post_init__(self) -> None:
        for key in ("id", "protein_identity_id", "name", "source_snapshot_id"):
            _require_text(getattr(self, key), key)
        if not 1 <= self.start_residue <= self.end_residue:
            raise ValueError("invalid construct canonical range")
        if any(p < 1 for p in (*self.deletions, *self.insertions)):
            raise ValueError("construct edit positions are one based")
        _sequence(
            self.construct_sequence,
            len(self.construct_sequence),
            self.construct_sequence_checksum,
        )


@dataclass(frozen=True)
class ExperimentalStructure:
    id: str
    provider: str
    provider_structure_id: str
    title: str
    experimental_method: str
    resolution: float | None
    deposition_date: str | None
    release_date: str | None
    revision: str | None
    revision_date: str | None
    structure_origin: str
    source_snapshot_id: str
    raw_file_checksum: str

    def __post_init__(self) -> None:
        for key in (
            "id",
            "provider",
            "provider_structure_id",
            "title",
            "experimental_method",
            "source_snapshot_id",
        ):
            _require_text(getattr(self, key), key)
        if self.structure_origin not in ("experimental", "predicted"):
            raise ValueError("unknown structure origin")
        if self.resolution is not None and self.resolution <= 0:
            raise ValueError("invalid resolution")
        if re.fullmatch(r"[a-f0-9]{64}", self.raw_file_checksum) is None:
            raise ValueError("structure requires SHA-256")


@dataclass(frozen=True)
class ChainInstance:
    id: str
    structure_id: str
    construct_id: str
    label_asym_id: str
    auth_asym_id: str
    entity_id: str
    chain_sequence: str
    sequence_checksum: str
    polymer_type: str
    mapped_protein_identity_id: str
    mapping_status: str

    def __post_init__(self) -> None:
        for key in (
            "id",
            "structure_id",
            "construct_id",
            "label_asym_id",
            "auth_asym_id",
            "entity_id",
            "mapped_protein_identity_id",
            "polymer_type",
            "mapping_status",
        ):
            _require_text(getattr(self, key), key)
        _sequence(self.chain_sequence, len(self.chain_sequence), self.sequence_checksum)


@dataclass(frozen=True)
class ResidueMapping:
    chain_id: str
    canonical_position: int | None
    construct_position: int | None
    structural_sequence_position: int | None
    author_residue_number: str | None
    insertion_code: str | None
    residue_identity: str | None
    canonical_identity: str | None
    coordinate_present: bool
    status: ResidueStatus
    source_difference: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.chain_id, "chain_id")
        for position in (
            self.canonical_position,
            self.construct_position,
            self.structural_sequence_position,
        ):
            if position is not None and position < 1:
                raise ValueError("sequence positions are one based")
        if not isinstance(self.status, ResidueStatus):
            raise ValueError("invalid mapping classification")
        if self.coordinate_present and (
            self.structural_sequence_position is None
            or self.author_residue_number is None
        ):
            raise ValueError("coordinates require structural and author identifiers")
        if self.status == ResidueStatus.EXACT and (
            self.canonical_position is None
            or self.canonical_identity != self.residue_identity
        ):
            raise ValueError("invalid exact residue mapping")


@dataclass(frozen=True)
class ObservedStructureComponent:
    structure_id: str
    label_asym_id: str
    auth_asym_id: str
    author_residue_number: str
    insertion_code: str | None
    component_id: str
    provider_description: str | None
    provider_classification: str | None
    coordinate_atom_count: int
    observation_kind: str
    source_snapshot_id: str

    def __post_init__(self) -> None:
        if self.coordinate_atom_count < 1:
            raise ValueError("observed component requires coordinates")
        if self.observation_kind not in ("water", "ion", "other_component"):
            raise ValueError("unknown conservative observation type")
