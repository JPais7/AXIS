"""Immutable identity infrastructure, not disease evidence."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from axis.domain.models import _require_aware_datetime, _require_text


def normalize_sequence(sequence: str) -> str:
    """Remove whitespace and uppercase; reject headers, gaps and punctuation."""
    value = "".join(sequence.split()).upper()
    if not value or re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYBXZJUO]+", value) is None:
        raise ValueError("invalid amino-acid sequence (FASTA headers not accepted)")
    return value


def sequence_checksum(sequence: str) -> str:
    return hashlib.sha256(normalize_sequence(sequence).encode("ascii")).hexdigest()


def _sequence(sequence: str, length: int, checksum: str) -> None:
    if sequence != normalize_sequence(sequence):
        raise ValueError("stored sequence must be normalized")
    if length != len(sequence) or checksum != sequence_checksum(sequence):
        raise ValueError("sequence length/checksum mismatch")


class MappingStatus(StrEnum):
    VERIFIED = "verified"
    PROVISIONAL = "provisional"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SourceSnapshot:
    id: str
    provider: str
    provider_record_id: str
    retrieval_timestamp: datetime
    request_url: str
    raw_content_checksum: str
    content_type: str
    importer_version: str
    provider_release: str | None = None
    local_resource_path: str | None = None
    metadata_json: str = "{}"

    def __post_init__(self) -> None:
        for key in (
            "id",
            "provider",
            "provider_record_id",
            "request_url",
            "content_type",
            "importer_version",
        ):
            _require_text(getattr(self, key), key)
        if re.fullmatch(r"[a-f0-9]{64}", self.raw_content_checksum) is None:
            raise ValueError("snapshot requires SHA-256")
        _require_aware_datetime(self.retrieval_timestamp, "retrieval_timestamp")


@dataclass(frozen=True)
class ProteinIdentity:
    id: str
    namespace: str
    primary_accession: str
    entry_name: str
    recommended_name: str | None
    gene_symbol: str | None
    organism_name: str
    taxon_id: int
    sequence: str
    sequence_length: int
    sequence_checksum: str
    sequence_version: int | None
    record_version: int | None
    reviewed_status: str
    source_snapshot_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        for key in (
            "id",
            "namespace",
            "primary_accession",
            "entry_name",
            "organism_name",
            "reviewed_status",
            "source_snapshot_id",
        ):
            _require_text(getattr(self, key), key)
        if self.taxon_id < 1:
            raise ValueError("taxon must be positive")
        for version in (self.sequence_version, self.record_version):
            if version is not None and version < 1:
                raise ValueError("versions must be positive or unknown")
        _sequence(self.sequence, self.sequence_length, self.sequence_checksum)
        _require_aware_datetime(self.created_at, "created_at")


@dataclass(frozen=True)
class ProteinIsoform:
    id: str
    protein_identity_id: str
    namespace: str
    accession: str
    isoform_name: str | None
    sequence: str | None
    sequence_length: int | None
    sequence_checksum: str | None
    sequence_version: int | None
    canonical: bool
    source_snapshot_id: str

    def __post_init__(self) -> None:
        for key in (
            "id",
            "protein_identity_id",
            "namespace",
            "accession",
            "source_snapshot_id",
        ):
            _require_text(getattr(self, key), key)
        if self.sequence is None:
            if any(
                x is not None
                for x in (
                    self.sequence_length,
                    self.sequence_checksum,
                    self.sequence_version,
                )
            ):
                raise ValueError("unknown sequence must have unknown integrity fields")
        else:
            if self.sequence_length is None or self.sequence_checksum is None:
                raise ValueError("sequence requires integrity fields")
            _sequence(self.sequence, self.sequence_length, self.sequence_checksum)
        if self.sequence_version is not None and self.sequence_version < 1:
            raise ValueError("invalid isoform sequence version")


@dataclass(frozen=True)
class GeneProteinMapping:
    id: str
    gene_entity_id: str
    gene_namespace: str
    protein_identity_id: str
    taxon_id: int
    mapping_type: str
    source: str
    source_version: str | None
    source_snapshot_id: str
    status: MappingStatus
    notes: str
    created_at: datetime

    def __post_init__(self) -> None:
        for key in (
            "id",
            "gene_entity_id",
            "gene_namespace",
            "protein_identity_id",
            "mapping_type",
            "source",
            "source_snapshot_id",
            "notes",
        ):
            _require_text(getattr(self, key), key)
        if self.taxon_id < 1 or not isinstance(self.status, MappingStatus):
            raise ValueError("invalid taxon or mapping status")
        _require_aware_datetime(self.created_at, "created_at")
