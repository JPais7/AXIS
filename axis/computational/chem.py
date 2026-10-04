# mypy: disable-error-code="no-untyped-call,attr-defined,arg-type"
"""Deterministic RDKit operations with explicit, recorded preparation choices.

Nothing here strips salts, assigns stereochemistry, normalises tautomers or picks a
protonation state. Each of those is reported as "not performed" in the record.
"""

import hashlib
import json
from typing import Any

from rdkit import Chem, DataStructs, rdBase
from rdkit.Chem import (
    AllChem,
    Descriptors,
    Lipinski,
    rdFingerprintGenerator,
    rdMolDescriptors,
)
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.ML.Cluster import Butina

FINGERPRINT = {"type": "morgan", "radius": 2, "n_bits": 2048, "chirality": False}
METRIC = "tanimoto"
CONFORMER = {"method": "ETKDGv3", "seed": 20260101, "hydrogens": "added for 3D only"}
DESCRIPTORS = (
    "molecular_weight",
    "crippen_logp",
    "tpsa",
    "hbd",
    "hba",
    "rotatable_bonds",
    "formal_charge",
    "ring_count",
    "fraction_csp3",
    "heavy_atoms",
)


def rdkit_version() -> str:
    return str(rdBase.rdkitVersion)


def digest(value: object) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def parse(smiles: str) -> Chem.Mol | None:
    return Chem.MolFromSmiles(smiles)


def stereo_status(mol: Chem.Mol) -> dict[str, Any]:
    centers = Chem.FindMolChiralCenters(
        mol, includeUnassigned=True, useLegacyImplementation=False
    )
    unassigned = [i for i, tag in centers if tag == "?"]
    return {
        "stereocentres": len(centers),
        "unassigned": len(unassigned),
        "status": (
            "not_applicable"
            if not centers
            else "unspecified"
            if unassigned
            else "specified_in_input"
        ),
    }


def prepare_compound(
    ref: str,
    smiles: str,
    *,
    compound_identity: str | None,
    input_stereo: str | None,
    identity_provenance: str = "researcher_supplied",
    external_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A computational representation linked to, never replacing, the identity."""
    mol = parse(smiles)
    base: dict[str, Any] = {
        "compound_ref": ref,
        "compound_identity": compound_identity,
        "identity_provenance": identity_provenance,
        "external_identity": external_identity
        or {"status": "unverified", "note": "no external database mapping recorded"},
        "input_smiles": smiles,
        "tool": "RDKit",
        "tool_version": rdkit_version(),
        "operations_performed": [],
        "operations_not_performed": [
            "salt stripping",
            "stereochemistry assignment",
            "tautomer normalisation",
            "protonation-state assignment",
            "charge neutralisation",
        ],
    }
    if mol is None:
        return {
            **base,
            "status": "failed",
            "failure": "RDKit could not parse the input",
        }
    fragments = len(Chem.GetMolFrags(mol))
    stereo = stereo_status(mol)
    result: dict[str, Any] = {
        **base,
        "status": "prepared",
        "canonical_smiles": Chem.MolToSmiles(mol, isomericSmiles=False),
        "isomeric_smiles": Chem.MolToSmiles(mol),
        "inchi_key": Chem.MolToInchiKey(mol),
        "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
        "molecular_weight": round(Descriptors.MolWt(mol), 3),
        "fragments": fragments,
        "stereochemistry": {**stereo, "input_claim": input_stereo},
        "protonation_state": "as written in the input; not assigned",
        "tautomer_state": "as written in the input; not normalised",
        "warnings": (["multiple fragments retained as given"] if fragments > 1 else [])
        + (
            ["stereocentres unspecified; none was chosen"]
            if stereo["status"] == "unspecified"
            else []
        ),
    }
    result["operations_performed"].append("canonical SMILES (RDKit)")
    result["depiction_svg"] = depiction(mol)
    conformer = _conformer(mol)
    result["conformer"] = conformer
    if conformer["status"] == "generated":
        result["operations_performed"].append(
            f"3D conformer {CONFORMER['method']} seed {CONFORMER['seed']} "
            "(hydrogens added in 3D only)"
        )
    result["output_sha256"] = digest(
        {k: v for k, v in result.items() if k != "conformer"}
        | {"mol": conformer.get("molblock_sha256")}
    )
    return result


def depiction(mol: Chem.Mol) -> str:
    drawer = rdMolDraw2D.MolDraw2DSVG(260, 180)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return str(drawer.GetDrawingText())


def _conformer(mol: Chem.Mol) -> dict[str, Any]:
    work = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = CONFORMER["seed"]
    if AllChem.EmbedMolecule(work, params) != 0:
        return {"status": "failed", "failure": "embedding failed", **CONFORMER}
    block = Chem.MolToMolBlock(work)
    return {
        "status": "generated",
        **CONFORMER,
        "molblock_sha256": hashlib.sha256(block.encode()).hexdigest(),
        "note": "coordinates are not bit-reproducible across RDKit builds",
    }


def descriptors(smiles: str) -> dict[str, Any]:
    mol = parse(smiles)
    if mol is None:
        return {}
    return {
        "molecular_weight": round(Descriptors.MolWt(mol), 3),
        "crippen_logp": round(Descriptors.MolLogP(mol), 3),
        "tpsa": round(rdMolDescriptors.CalcTPSA(mol), 3),
        "hbd": Lipinski.NumHDonors(mol),
        "hba": Lipinski.NumHAcceptors(mol),
        "rotatable_bonds": Lipinski.NumRotatableBonds(mol),
        "formal_charge": Chem.GetFormalCharge(mol),
        "ring_count": rdMolDescriptors.CalcNumRings(mol),
        "fraction_csp3": round(rdMolDescriptors.CalcFractionCSP3(mol), 3),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
    }


def descriptor_flags(
    values: dict[str, Any], ranges: dict[str, list[float | None]]
) -> list[dict[str, Any]]:
    """Descriptive position against campaign-defined ranges; never a rejection."""
    flags = []
    for name, (low, high) in sorted(ranges.items()):
        value = values.get(name)
        if value is None:
            continue
        if (low is not None and value < low) or (high is not None and value > high):
            flags.append({"descriptor": name, "value": value, "range": [low, high]})
    return flags


def fingerprint(smiles: str) -> Any:
    mol = parse(smiles)
    if mol is None:
        return None
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=FINGERPRINT["radius"], fpSize=FINGERPRINT["n_bits"]
    )
    return generator.GetFingerprint(mol)


def similarity(a: str, b: str) -> float | None:
    fa, fb = fingerprint(a), fingerprint(b)
    if fa is None or fb is None:
        return None
    return round(float(DataStructs.TanimotoSimilarity(fa, fb)), 4)


def scaffold(smiles: str) -> str:
    mol = parse(smiles)
    if mol is None:
        return ""
    return str(Chem.MolToSmiles(MurckoScaffold.GetScaffoldForMol(mol)))


def cluster(members: dict[str, str], threshold: float) -> dict[str, Any]:
    """Butina clustering, deterministic: members are processed in sorted id order."""
    ids = sorted(members)
    fps = [fingerprint(members[i]) for i in ids]
    usable = [(i, f) for i, f in zip(ids, fps, strict=True) if f is not None]
    distances: list[float] = []
    for n in range(1, len(usable)):
        sims = DataStructs.BulkTanimotoSimilarity(
            usable[n][1], [f for _, f in usable[:n]]
        )
        distances.extend(1.0 - s for s in sims)
    groups = Butina.ClusterData(
        distances, len(usable), threshold, isDistData=True, reordering=True
    )
    clusters = []
    for group in groups:
        names = sorted(usable[g][0] for g in group)
        clusters.append({"representative": usable[group[0]][0], "members": names})
    clusters.sort(key=lambda c: c["members"][0])
    return {
        "algorithm": "Butina",
        "fingerprint": FINGERPRINT,
        "distance": f"1 - {METRIC}",
        "distance_threshold": threshold,
        "representative_rule": (
            "cluster centroid chosen by RDKit Butina (ties by input order; ids sorted)"
        ),
        "seed": None,
        "clusters": clusters,
        "unparsed": sorted(set(ids) - {i for i, _ in usable}),
    }
