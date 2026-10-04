"""Reproducible structural ingestion and persisted read projections."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.domain.protein import SourceSnapshot, sequence_checksum
from axis.domain.structure import (
    ChainInstance,
    ExperimentalStructure,
    ObservedStructureComponent,
    ProteinConstruct,
    ResidueStatus,
)
from axis.sources.pdb import IMPORTER_VERSION, PDBAdapter, parse_mmcif
from axis.storage import EvidenceStore
from axis.structures.mapping import coverage, map_residues, mapping_checksum


class StructureIdentityService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def import_package(
        self, project: str, protein: str, directory: Path | None = None
    ) -> str:
        root = (
            directory
            if directory
            else resources.files("axis").joinpath("resources/structures/erap1/3qnf/v1")
        )
        raw_manifest = root.joinpath("manifest.json").read_bytes()
        if (
            hashlib.sha256(raw_manifest).hexdigest()
            != root.joinpath("manifest.sha256").read_text().strip()
        ):
            raise ValueError("structural package manifest checksum mismatch")
        manifest = json.loads(raw_manifest)
        if manifest["importer_version"] != IMPORTER_VERSION:
            raise ValueError("unsupported structure importer version")
        if (
            manifest["mapping_algorithm"] != "provider-segment-projection"
            or manifest["mapping_version"] != "1"
        ):
            raise ValueError("unsupported frozen mapping transformation")
        raw = root.joinpath("structure.cif").read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["raw_sha256"]:
            raise ValueError("frozen mmCIF checksum mismatch")
        p = self.store.targets.require_member(project, protein)
        if p.sequence_checksum != manifest["canonical_sequence_sha256"]:
            raise ValueError("structure package is pinned to a different sequence")
        return self.ingest(
            project,
            protein,
            raw,
            manifest["pdb_id"],
            datetime.fromisoformat(manifest["retrieved_at"]),
            str(directory / "structure.cif")
            if directory
            else "axis/resources/structures/erap1/3qnf/v1/structure.cif",
        )

    def import_live(self, project: str, protein: str, pdb_id: str) -> str:
        self.store.targets.require_member(project, protein)
        raw = PDBAdapter().retrieve(pdb_id)
        return self.ingest(project, protein, raw, pdb_id, datetime.now(UTC), None)

    def ingest(
        self,
        project: str,
        protein: str,
        raw: bytes,
        pdb_id: str,
        retrieved_at: datetime,
        resource: str | None,
    ) -> str:
        p = self.store.targets.require_member(project, protein)
        parsed = parse_mmcif(raw, pdb_id)
        digest = hashlib.sha256(raw).hexdigest()
        # Stable raw snapshot identity; imports against different protein snapshots
        # have distinct structural identity and mapping objects.
        snapshot_id = f"pdb:{pdb_id}:{digest}:{retrieved_at.isoformat()}"
        protein_digest = hashlib.sha256(protein.encode()).hexdigest()[:16]
        sid = f"structure:{snapshot_id}:{protein_digest}"
        snapshot = SourceSnapshot(
            snapshot_id,
            "wwPDB/RCSB",
            pdb_id,
            retrieved_at,
            f"https://files.rcsb.org/download/{pdb_id}.cif",
            digest,
            "chemical/x-mmcif",
            IMPORTER_VERSION,
            parsed.metadata["revision"],
            resource,
            json.dumps(parsed.metadata, sort_keys=True),
        )
        metadata = parsed.metadata
        structure = ExperimentalStructure(
            sid,
            "wwPDB/RCSB",
            pdb_id,
            metadata["title"],
            metadata["experimental_method"],
            metadata["resolution"],
            metadata["deposition_date"],
            metadata["release_date"],
            metadata["revision"],
            metadata["revision_date"],
            "experimental",
            snapshot_id,
            digest,
        )
        bundles = []
        for c in parsed.chains:
            if (
                c["accession"] != p.primary_accession
                or p.namespace != "uniprot"
                or c["namespace"] != "UNP"
                or c["taxon"] != p.taxon_id
            ):
                raise ValueError(
                    "chain source identity/taxon disagrees with pinned protein"
                )
            cid = f"{sid}:chain:{c['label_asym_id']}"
            rows = map_residues(
                p.sequence,
                c["sequence"],
                cid,
                c["segments"],
                c["numbering"],
                c["coordinates"],
                c["differences"],
            )
            mapped = [
                r.canonical_position
                for r in rows
                if r.canonical_position and r.construct_position
            ]
            construct_id = f"{sid}:construct:{c['entity_id']}"
            tags = tuple(
                f"{position}:{detail}"
                for position, detail in sorted(c["differences"].items())
                if detail and "tag" in detail.lower()
            )
            canonical_isoform = self.store.targets.canonical_isoform(protein)
            construct = ProteinConstruct(
                construct_id,
                protein,
                canonical_isoform.id
                if canonical_isoform
                and canonical_isoform.sequence_checksum == p.sequence_checksum
                else None,
                f"Deposited entity {c['entity_id']}",
                min(mapped),
                max(mapped),
                c["sequence"],
                sequence_checksum(c["sequence"]),
                c["expression_system"],
                True if tags else None,
                tuple(
                    f"{r.canonical_identity}{r.canonical_position}"
                    f"{r.residue_identity}: {r.status}"
                    for r in rows
                    if r.canonical_position
                    and r.construct_position
                    and r.residue_identity != r.canonical_identity
                ),
                tuple(
                    r.canonical_position
                    for r in rows
                    if r.status == ResidueStatus.DELETION and r.canonical_position
                ),
                tuple(
                    r.construct_position
                    for r in rows
                    if r.status == ResidueStatus.INSERTION and r.construct_position
                ),
                tags,
                None,
                "Deposited entity sequence; coordinate absence does not establish "
                "physical truncation. Isoform relation is AXIS sequence-checksum "
                "inference, not a provider isoform claim.",
                snapshot_id,
            )
            chain = ChainInstance(
                cid,
                sid,
                construct_id,
                c["label_asym_id"],
                c["auth_asym_id"],
                c["entity_id"],
                c["sequence"],
                sequence_checksum(c["sequence"]),
                c["polymer_type"],
                protein,
                "source_anchored_sequence_verified",
            )
            transformation = {
                "algorithm": "provider-segment-projection",
                "version": "1",
                "software": "AXIS StructureIdentityService",
                "importer_version": IMPORTER_VERSION,
                "parser": parsed.metadata["parser"],
                "protein_identity_id": protein,
                "parameters": {"identity_threshold": 0.95, "segments": c["segments"]},
                "source": "mmCIF _struct_ref_seq + _pdbx_poly_seq_scheme + _atom_site",
                "canonical_input_sha256": p.sequence_checksum,
                "construct_input_sha256": chain.sequence_checksum,
                "mapping_sha256": mapping_checksum(rows),
                "coverage": coverage(rows, len(p.sequence)),
                "epistemic_type": (
                    "AXIS-computed projection of provider anchors; "
                    "no sequence alignment"
                ),
            }
            bundles.append((construct, chain, rows, transformation))
        components = [
            ObservedStructureComponent(
                structure_id=sid, source_snapshot_id=snapshot_id, **c
            )
            for c in parsed.components
        ]
        with self.store._transaction():
            self.store.targets.insert_snapshot(snapshot)
            self.store.structures.insert_structure(structure, raw)
            for construct, chain, rows, transformation in bundles:
                self.store.structures.insert_construct(construct)
                self.store.structures.insert_chain(chain)
                self.store.structures.insert_mapping(
                    chain.id, [asdict(r) for r in rows], transformation
                )
            self.store.structures.insert_components(
                sid, [asdict(c) for c in components]
            )
            self.store.structures.link(project, protein, sid)
        return sid

    def projection(self, project: str, protein: str, identifier: str) -> dict[str, Any]:
        self.store.structures.require_member(project, protein, identifier)
        structure = self.store.structures.structure(identifier)
        constructs = self.store.structures.constructs(identifier)
        chains = self.store.structures.chains(identifier)
        return {
            "structure": structure,
            "constructs": constructs,
            "identity_graph": {
                "nodes": (
                    [{"id": protein, "kind": "ProteinIdentity"}]
                    + [{"id": c["id"], "kind": "ProteinConstruct"} for c in constructs]
                    + [{"id": identifier, "kind": "ExperimentalStructure"}]
                    + [{"id": c["id"], "kind": "ChainInstance"} for c in chains]
                    + [
                        {
                            "id": structure["source_snapshot_id"],
                            "kind": "SourceSnapshot",
                        }
                    ]
                ),
                "edges": (
                    [
                        {
                            "source": protein,
                            "target": c["id"],
                            "relation": "represented_by",
                        }
                        for c in constructs
                    ]
                    + [
                        {
                            "source": c["id"],
                            "target": identifier,
                            "relation": "observed_in",
                        }
                        for c in constructs
                    ]
                    + [
                        {
                            "source": identifier,
                            "target": c["id"],
                            "relation": "contains",
                        }
                        for c in chains
                    ]
                    + [
                        {
                            "source": c["id"],
                            "target": protein,
                            "relation": "maps_to",
                        }
                        for c in chains
                    ]
                    + [
                        {
                            "source": identifier,
                            "target": structure["source_snapshot_id"],
                            "relation": "sourced_from",
                        }
                    ]
                ),
                "scope": "structural identity only; no therapeutic-effect edges",
            },
            "chains": [
                {
                    **chain,
                    "coverage": self.store.structures.mapping(chain["id"])[
                        "transformation"
                    ]["coverage"],
                }
                for chain in chains
            ],
            "components": self.store.structures.components(identifier),
            "snapshot": asdict(
                self.store.targets.snapshot(structure["source_snapshot_id"])
            ),
            "boundary": (
                "This experimental structure alone does not establish druggability, "
                "therapeutic efficacy or disease relevance."
            ),
        }

    def mapping(self, project: str, protein: str, identifier: str) -> dict[str, Any]:
        self.store.structures.require_member(project, protein, identifier)
        return {
            "chains": [
                {"chain": c, **self.store.structures.mapping(c["id"])}
                for c in self.store.structures.chains(identifier)
            ]
        }
