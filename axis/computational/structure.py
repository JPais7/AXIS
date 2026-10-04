"""Explicit structure preparation and site definition (never overwrites a source)."""

import hashlib
from importlib import metadata
from pathlib import Path
from typing import Any

import gemmi

from axis.computational.chem import digest

PREPARATION = "axis-structure-prep-1"
SITE_METHOD = "axis-metal-shell-1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_structure(
    cif: Path,
    *,
    source_structure_id: str,
    chain: str,
    retain_metals: tuple[str, ...] = ("ZN",),
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Select one chain; record every removed/retained component and every non-step."""
    source_sha = sha256_file(cif)
    if expected_sha256 and expected_sha256 != source_sha:
        raise ValueError("source structure checksum differs from the frozen record")
    structure = gemmi.read_structure(str(cif))
    structure.setup_entities()
    model = structure[0]
    chains = [c.name for c in model]
    if chain not in chains:
        raise ValueError(f"chain {chain!r} is not in {source_structure_id}")
    removed: dict[str, int] = {}
    retained: dict[str, int] = {}
    resolved = 0
    for c in model:
        for residue in c:
            kind = residue.name
            if c.name != chain:
                removed[f"chain {c.name}:{kind}"] = (
                    removed.get(f"chain {c.name}:{kind}", 0) + 1
                )
            elif residue.het_flag != "H":
                resolved += 1
            elif kind in retain_metals:
                retained[kind] = retained.get(kind, 0) + 1
            else:
                removed[kind] = removed.get(kind, 0) + 1
    prepared = gemmi.Structure()
    prepared.cell = structure.cell
    prepared.spacegroup_hm = structure.spacegroup_hm
    new_model = gemmi.Model(1)
    new_chain = gemmi.Chain(chain)
    for residue in model[chain]:
        if residue.het_flag != "H" or residue.name in retain_metals:
            new_chain.add_residue(residue)
    new_model.add_chain(new_chain)
    prepared.add_model(new_model)
    text = prepared.make_pdb_string()
    sequence = max((len(e.full_sequence) for e in structure.entities), default=0)
    record: dict[str, Any] = {
        "source_structure_id": source_structure_id,
        "source_sha256": source_sha,
        "chain": chain,
        "chains_in_source": chains,
        "tool": "gemmi",
        "tool_version": metadata.version("gemmi"),
        "preparation": PREPARATION,
        "parameters": {"chain": chain, "retain_metals": list(retain_metals)},
        "removed_components": dict(sorted(removed.items())),
        "retained_components": dict(sorted(retained.items())),
        "resolved_polymer_residues": resolved,
        "entity_sequence_length": sequence,
        "missing_residues_note": (
            "longest entity length minus resolved residues is an upper bound"
        ),
        "added_atoms": "none",
        "hydrogens": "not added",
        "protonation": "not assigned",
        "waters": "removed",
        "metals": f"retained: {', '.join(retain_metals)}; coordination not modelled",
        "output_format": "PDB text (regenerated deterministically; not stored in Git)",
        "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "limitations": [
            "single crystallographic state; not shown to be disease-relevant",
            "no ligand bound in the source: validation by redocking is impossible",
            "water, glycans and other chains removed",
        ],
    }
    record["id"] = (
        f"prepared-structure:{source_structure_id}:{chain}:{digest(record)[:12]}"
    )
    return record


def define_site(
    cif: Path, *, chain: str, around: str, radius: float, site_id: str
) -> dict[str, Any]:
    """Residues within ``radius`` Å of a named component: a boundary AXIS chose."""
    structure = gemmi.read_structure(str(cif))
    model = structure[0]
    centre = None
    for residue in model[chain]:
        if residue.name == around:
            centre = residue[0].pos
            break
    if centre is None:
        return {
            "id": site_id,
            "status": "failed",
            "failure": f"{around} not found in chain {chain}",
        }
    search = gemmi.NeighborSearch(model, structure.cell, max(radius, 5.0)).populate()
    found: dict[tuple[int, str], float] = {}
    for mark in search.find_atoms(centre, "\0", radius=radius):
        cra = mark.to_cra(model)
        if cra.chain.name != chain or cra.residue.name in ("HOH", around):
            continue
        d = cra.atom.pos.dist(centre)
        key = (int(cra.residue.seqid.num or 0), cra.residue.name)
        found[key] = min(d, found.get(key, 99.0))
    residues = [
        {"auth_seq_id": n, "residue": name, "min_distance_to_centre": round(d, 2)}
        for (n, name), d in sorted(found.items())
    ]
    return {
        "id": site_id,
        "status": "defined",
        "site_type": "known_catalytic_site",
        "type_note": (
            "Centred on the observed metal ion. The catalytic role of the metal is "
            "literature knowledge and is not re-derived here; the radius is an AXIS "
            "choice, not a measured binding-site boundary."
        ),
        "method": SITE_METHOD,
        "centre_component": around,
        "radius_angstrom": radius,
        "chain": chain,
        "residues": residues,
        "known_ligands": [],
        "confidence_category": "position observed; boundary defined by AXIS",
        "druggability": "not assessed (a defined region is not a druggable pocket)",
    }
