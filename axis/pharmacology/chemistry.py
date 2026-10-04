"""Isolated RDKit identity/2D boundary; no salt stripping or stereo guessing."""

import hashlib
from typing import Any

from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D


def resolve_structure(smiles: str) -> dict[str, Any]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("invalid source SMILES")
    isomeric = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False)
    drawer = rdMolDraw2D.MolDraw2DSVG(360, 240)
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
    drawer.FinishDrawing()
    svg = str(drawer.GetDrawingText())
    return {
        "original_smiles": smiles,
        "canonical_smiles": canonical,
        "isomeric_smiles": isomeric,
        "canonical_inchi": Chem.MolToInchi(mol),  # type: ignore[no-untyped-call]
        "inchi_key": Chem.MolToInchiKey(mol),  # type: ignore[no-untyped-call]
        "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
        "molecular_weight": float(Descriptors.MolWt(mol)),  # type: ignore[attr-defined]
        "formal_charge": int(Chem.GetFormalCharge(mol)),
        "depiction_svg": svg,
        "transformation": {
            "software": "RDKit",
            "version": rdBase.rdkitVersion,
            "method": "canonical SMILES, InChI, 2D depiction v1",
            "parameters": {
                "isomericSmiles": True,
                "salt_stripping": False,
                "tautomer_normalization": False,
                "stereo_assignment": False,
            },
            "input": smiles,
            "output": isomeric,
            "sha256": hashlib.sha256(isomeric.encode()).hexdigest(),
            "depiction_sha256": hashlib.sha256(svg.encode()).hexdigest(),
            "stereochemistry_features": [
                {"type": str(s.type), "specified": str(s.specified)}
                for s in Chem.FindPotentialStereo(mol)
            ],
        },
    }
