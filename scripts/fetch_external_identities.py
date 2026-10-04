"""Freeze external chemical-identity verification for researcher-supplied compounds.

Network is used only here (online acquisition). The frozen JSON it writes is what
campaigns replay offline. Identity verification says "this structure is that named
compound"; it says nothing about ERAP1 pharmacology.

    poetry run python scripts/fetch_external_identities.py <output.json>
"""

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from rdkit import Chem

NAMES = {
    "compound:supplied:bestatin": ("bestatin", "CC(C)C[C@H](NC(=O)[C@@H](O)[C@H](N)Cc1ccccc1)C(=O)O"),
    "compound:supplied:captopril": ("captopril", "C[C@H](CS)C(=O)N1CCC[C@H]1C(=O)O"),
    "compound:supplied:vorinostat": ("vorinostat", "ONC(=O)CCCCCCC(=O)Nc1ccccc1"),
}
PROPS = "Title,MolecularFormula,MolecularWeight,IsomericSMILES,InChIKey"


def main() -> None:
    entries = {}
    for ref, (name, smiles) in NAMES.items():
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            f"{urllib.parse.quote(name)}/property/{PROPS}/JSON"
        )
        raw = urllib.request.urlopen(url, timeout=30).read()
        first = json.loads(raw)["PropertyTable"]["Properties"][0]
        ours = Chem.MolFromSmiles(smiles)
        our_key = Chem.MolToInchiKey(ours)
        entries[ref] = {
            "name": name,
            "campaign_smiles": smiles,
            "campaign_inchikey": our_key,
            "provider": "PubChem PUG REST",
            "provider_record": f"CID {first['CID']}",
            "provider_title": first.get("Title"),
            "provider_formula": first.get("MolecularFormula"),
            "provider_inchikey": first.get("InChIKey"),
            "provider_isomeric_smiles": first.get("IsomericSMILES") or first.get("SMILES"),
            "request_url": url,
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "identity_check": "match" if first.get("InChIKey") == our_key else "MISMATCH",
        }
    out = {
        "resource": "external-compound-identity",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "provider_release": "PubChem live service; no release identifier is exposed by PUG REST",
        "scope": "Verifies chemical identity only. It is not evidence of ERAP1 binding, inhibition, selectivity or cellular activity.",
        "entries": entries,
    }
    Path(sys.argv[1]).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    for ref, e in entries.items():
        print(ref, e["provider_record"], e["identity_check"])


if __name__ == "__main__":
    main()
