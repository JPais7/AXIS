"""Official mmCIF acquisition and parsing through Gemmi, without interpretation."""

import re
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

import gemmi
import httpx

from axis.domain.protein import normalize_sequence

IMPORTER_VERSION = "1"


def validate_pdb_id(identifier: str) -> None:
    if re.fullmatch(r"[1-9][A-Z0-9]{3}", identifier) is None:
        raise ValueError("invalid uppercase four-character PDB identifier")


@dataclass(frozen=True)
class ParsedPDB:
    identifier: str
    metadata: dict[str, Any]
    chains: tuple[dict[str, Any], ...]
    components: tuple[dict[str, Any], ...]


def parse_mmcif(raw: bytes, identifier: str) -> ParsedPDB:
    validate_pdb_id(identifier)
    try:
        block = gemmi.cif.read_string(raw.decode()).sole_block()

        def rows(category: str) -> list[dict[str, Any]]:
            values = block.get_mmcif_category(category)
            if not values:
                return []
            return [
                {
                    k: (v[i] if v[i] not in (False, None, "?", ".") else None)
                    for k, v in values.items()
                }
                for i in range(len(next(iter(values.values()))))
            ]

        def scalar(tag: str) -> str | None:
            value = block.find_value(tag)
            return (
                gemmi.cif.as_string(value)
                if value and value not in ("?", ".")
                else None
            )

        if scalar("_entry.id") != identifier:
            raise ValueError("PDB identity mismatch")
        method = scalar("_exptl.method")
        if not method or method.upper() in ("THEORETICAL MODEL", "AB INITIO MODEL"):
            raise ValueError("experimental structural method required")
        atoms = rows("_atom_site.")
        if not atoms:
            raise ValueError("no structural coordinates")
        models = {str(a.get("pdbx_PDB_model_num") or "1") for a in atoms}
        if models != {"1"}:
            raise ValueError("multi-model ensembles not supported in this slice")
        refs = {r["id"]: r for r in rows("_struct_ref.")}
        sources = {r["entity_id"]: r for r in rows("_entity_src_gen.")}
        polymers = {r["entity_id"]: r for r in rows("_entity_poly.")}
        scheme = rows("_pdbx_poly_seq_scheme.")
        differences = rows("_struct_ref_seq_dif.")
        ref_sequences = rows("_struct_ref_seq.")
        chains = []
        protein_labels = set()
        for asym in rows("_struct_asym."):
            entity, label = asym["entity_id"], asym["id"]
            poly = polymers.get(entity)
            if not poly or poly["type"] != "polypeptide(L)":
                continue
            chain_scheme = [r for r in scheme if r["asym_id"] == label]
            auths = {r["pdb_strand_id"] for r in chain_scheme}
            if len(auths) != 1:
                raise ValueError("ambiguous author chain identity")
            auth = next(iter(auths))
            ref_rows = [
                r
                for r in ref_sequences
                if auth in (r["pdbx_strand_id"] or "").split(",")
            ]
            if not ref_rows:
                raise ValueError("protein chain lacks authoritative cross-reference")
            ref = refs[ref_rows[0]["ref_id"]]
            if ref.get("entity_id") != entity:
                raise ValueError("cross-reference entity does not match polymer")
            if any(refs[r["ref_id"]] != ref for r in ref_rows):
                raise ValueError(
                    "multiple protein references require explicit resolution"
                )
            source = sources.get(entity, {})
            if source.get("pdbx_gene_src_ncbi_taxonomy_id") is None:
                raise ValueError("source protein taxon not reported")
            positions = {
                int(a["label_seq_id"])
                for a in atoms
                if a["label_asym_id"] == label
                and a.get("label_seq_id")
                and float(a.get("occupancy") or 0) > 0
            }
            numbering = {
                int(r["seq_id"]): (r.get("pdb_seq_num"), r.get("pdb_ins_code"))
                for r in chain_scheme
            }
            scheme_components = {int(r["seq_id"]): r["mon_id"] for r in chain_scheme}
            atom_numbering: dict[int, tuple[str | None, str | None]] = {}
            # Represented residues use atom author numbering and insertion codes.
            for a in atoms:
                if a["label_asym_id"] == label and a.get("label_seq_id"):
                    key = int(a["label_seq_id"])
                    value = (a.get("auth_seq_id"), a.get("pdbx_PDB_ins_code"))
                    if key in positions:
                        if a["label_comp_id"] != scheme_components.get(key):
                            raise ValueError(
                                "atom residue disagrees with polymer scheme"
                            )
                        if key in atom_numbering and atom_numbering[key] != value:
                            raise ValueError(
                                "conflicting atom author residue numbering"
                            )
                        atom_numbering[key] = value
                        numbering[key] = value
            chain_diffs = {
                int(r["seq_num"]): r["details"]
                for r in differences
                if r["pdbx_pdb_strand_id"] == auth
            }
            chains.append(
                {
                    "label_asym_id": label,
                    "auth_asym_id": auth,
                    "entity_id": entity,
                    "sequence": normalize_sequence(
                        poly["pdbx_seq_one_letter_code_can"]
                    ),
                    "polymer_type": poly["type"],
                    "accession": ref["pdbx_db_accession"],
                    "namespace": ref["db_name"],
                    "taxon": int(source["pdbx_gene_src_ncbi_taxonomy_id"]),
                    "expression_system": source.get("pdbx_host_org_scientific_name"),
                    "segments": [
                        (
                            int(r["seq_align_beg"]),
                            int(r["seq_align_end"]),
                            int(r["db_align_beg"]),
                            int(r["db_align_end"]),
                        )
                        for r in ref_rows
                    ],
                    "numbering": numbering,
                    "coordinates": positions,
                    "differences": chain_diffs,
                }
            )
            protein_labels.add(label)
        if not chains:
            raise ValueError("no protein chain with supported source mapping")
        chem = {r["id"]: r for r in rows("_chem_comp.")}
        groups: dict[tuple[str, str, str, str | None, str], int] = {}
        for a in atoms:
            if (
                a["label_asym_id"] in protein_labels
                or float(a.get("occupancy") or 0) <= 0
            ):
                continue
            component_key = (
                a["label_asym_id"],
                a["auth_asym_id"],
                a["auth_seq_id"],
                a.get("pdbx_PDB_ins_code"),
                a["label_comp_id"],
            )
            groups[component_key] = groups.get(component_key, 0) + 1
        components = []
        for (label, auth, number, code, component), count in sorted(
            groups.items(), key=str
        ):
            info = chem.get(component, {})
            components.append(
                {
                    "label_asym_id": label,
                    "auth_asym_id": auth,
                    "author_residue_number": number,
                    "insertion_code": code,
                    "component_id": component,
                    "provider_description": info.get("name"),
                    "provider_classification": info.get("type"),
                    "coordinate_atom_count": count,
                    "observation_kind": "water"
                    if component == "HOH"
                    else "ion"
                    if "ION" in str(info.get("name", "")).upper() and count == 1
                    else "other_component",
                }
            )
        revisions = rows("_pdbx_audit_revision_history.")
        revision = revisions[-1] if revisions else {}
        resolution = scalar("_refine.ls_d_res_high") or scalar(
            "_em_3d_reconstruction.resolution"
        )
        return ParsedPDB(
            identifier,
            {
                "title": scalar("_struct.title") or "Not reported",
                "experimental_method": method,
                "resolution": float(resolution) if resolution else None,
                "deposition_date": scalar(
                    "_pdbx_database_status.recvd_initial_deposition_date"
                ),
                "release_date": revisions[0]["revision_date"] if revisions else None,
                "revision": f"{revision['major_revision']}.{revision['minor_revision']}"
                if revision
                else None,
                "revision_date": revision.get("revision_date"),
                "experimental_conditions": rows("_exptl_crystal_grow."),
                "parser": f"Gemmi {version('gemmi')}",
            },
            tuple(chains),
            tuple(components),
        )
    except (RuntimeError, KeyError, TypeError, UnicodeError) as error:
        raise ValueError("malformed or unsupported structural mmCIF") from error


class PDBAdapter:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client

    def retrieve(self, identifier: str) -> bytes:
        validate_pdb_id(identifier)
        url = f"https://files.rcsb.org/download/{identifier}.cif"
        if self.client is None:
            with httpx.Client(timeout=60, follow_redirects=False) as client:
                response = client.get(url)
        else:
            response = self.client.get(url)
        response.raise_for_status()
        return response.content
