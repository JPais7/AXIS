"""Explicit identity ingestion, frozen replay and project-scoped reads."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.domain.protein import GeneProteinMapping, MappingStatus
from axis.sources.uniprot import (
    IMPORTER_VERSION,
    ParsedProtein,
    UniProtAdapter,
    parse_record,
)
from axis.storage import EvidenceStore, RecordConflictError


class TargetIdentityService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def import_package(self, project: str, directory: Path | None = None) -> str:
        root = (
            directory
            if directory
            else resources.files("axis").joinpath("resources/targets/erap1/uniprot/v1")
        )
        manifest_raw = root.joinpath("manifest.json").read_bytes()
        expected = root.joinpath("manifest.sha256").read_text().strip()
        if hashlib.sha256(manifest_raw).hexdigest() != expected:
            raise ValueError("frozen manifest checksum mismatch")
        manifest = json.loads(manifest_raw)
        if manifest["importer_version"] != IMPORTER_VERSION:
            raise ValueError("unsupported identity importer version")
        if manifest["record_file"] != "record.json":
            raise ValueError("unsupported package resource path")
        raw = root.joinpath("record.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["raw_sha256"]:
            raise ValueError("frozen source checksum mismatch")
        parsed = parse_record(
            raw,
            manifest["accession"],
            datetime.fromisoformat(manifest["retrieved_at"]),
            expected_taxon=manifest["taxon_id"],
            provider_release=manifest.get("provider_release"),
            resource_path="axis/resources/targets/erap1/uniprot/v1/record.json"
            if directory is None
            else str(directory.resolve() / "record.json"),
        )
        return self.ingest(
            project,
            parsed,
            manifest["gene_namespace"],
            manifest["gene_identifier"],
            manifest["taxon_id"],
        )

    def import_live(self, project: str, accession: str, *, expected_taxon: int) -> str:
        pair = self.store.target_disease_pairs.get(
            self.store.projects.get(project).target_disease_pair
        )
        parsed = UniProtAdapter().retrieve(
            accession, datetime.now(UTC), expected_taxon=expected_taxon
        )
        return self.ingest(
            project,
            parsed,
            pair.target.namespace,
            pair.target.identifier,
            expected_taxon,
        )

    def ingest(
        self,
        project: str,
        parsed: ParsedProtein,
        gene_namespace: str,
        gene_identifier: str,
        taxon: int,
    ) -> str:
        pair = self.store.target_disease_pairs.get(
            self.store.projects.get(project).target_disease_pair
        )
        protein = parsed.protein
        if gene_namespace in ("HGNC", "HGNC-symbol") and taxon != 9606:
            raise ValueError("human HGNC gene namespace requires taxon 9606")
        # Current discovery entities lack taxon: require an explicit expected taxon
        # and provider-backed gene field, not display-label similarity.
        if (
            pair.target.kind.value != "gene"
            or pair.target.namespace != gene_namespace
            or pair.target.identifier != gene_identifier
            or protein.gene_symbol != gene_identifier
            or protein.taxon_id != taxon
        ):
            raise ValueError("project/gene/provider mapping mismatch")
        if protein.source_snapshot_id != parsed.snapshot.id or any(
            i.protein_identity_id != protein.id
            or i.source_snapshot_id != parsed.snapshot.id
            for i in parsed.isoforms
        ):
            raise ValueError("inconsistent parsed identity bundle")
        previous = self.store.targets.by_accession(
            protein.namespace, protein.primary_accession
        )
        # Conservative policy: reject changed immutable biological identity;
        # changed metadata can coexist in a new snapshot, never overwrite.
        for old in previous:
            if (old.sequence_checksum, old.sequence_version, old.taxon_id) != (
                protein.sequence_checksum,
                protein.sequence_version,
                protein.taxon_id,
            ):
                raise RecordConflictError(
                    "sequence/version/taxon conflict: import rejected"
                )
        mapping = GeneProteinMapping(
            f"mapping:{project}:{protein.id}",
            gene_identifier,
            gene_namespace,
            protein.id,
            taxon,
            "encodes",
            "UniProt",
            str(protein.record_version) if protein.record_version else None,
            parsed.snapshot.id,
            MappingStatus.VERIFIED,
            "UniProt primary gene field and expected taxon match project gene; "
            "identity mapping only, not therapeutic validation.",
            protein.created_at,
        )
        with self.store._transaction():
            self.store.targets.insert_snapshot(parsed.snapshot)
            self.store.targets.insert_protein(protein)
            for isoform in parsed.isoforms:
                self.store.targets.insert_isoform(isoform)
            self.store.targets.insert_mapping(mapping)
            self.store.targets.link(project, protein.id, mapping.id)
        return protein.id

    def projection(self, project: str, identifier: str) -> dict[str, Any]:
        protein = self.store.targets.require_member(project, identifier)
        return {
            "protein": asdict(protein),
            "isoforms": [asdict(i) for i in self.store.targets.isoforms(identifier)],
            "mappings": [
                asdict(m)
                for m in self.store.targets.mappings(identifier)
                if m.id.startswith(f"mapping:{project}:")
            ],
            "snapshot": asdict(self.store.targets.snapshot(protein.source_snapshot_id)),
            "boundary": "Imported identity is not evidence of therapeutic efficacy.",
            "structure_count": len(self.store.structures.list_ids(project, identifier)),
            "project_id": project,
            "chemical_count": self.store.pharmacology.collection(
                project, identifier, "compounds", 1, 0
            )["total"],
        }
