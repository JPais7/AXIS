"""Build the frozen SYNTHETIC chemical-learning fixture (offline, deterministic).

SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE. The designed relationship is
documented in the output: log10(IC50 nM) = scaffold offset - 1.0 * lipophilic
substituent constant + noise. Nothing here says anything about a real target.

    poetry run python scripts/build_learning_fixtures.py
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

OUT = (
    Path(__file__).resolve().parents[1]
    / "axis/resources/chemical-learning/synthetic-generic/v1"
)
LABEL = "SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE"
SCAFFOLDS = {
    "A": ("c1ccc({R})cc1C(=O)NC", "c1ccccc1C(=O)NC", 3.00),
    "B": ("c1ccc({R})cc1C(=O)Nc1ccccn1", "c1ccccc1C(=O)Nc1ccccn1", 2.85),
    "C": ("c1ccc2cc({R})ccc2c1", "c1ccc2ccccc2c1", 3.15),
    "D": ("c1ccc({R})cc1S(=O)(=O)N1CCCC1", "c1ccccc1S(=O)(=O)N1CCCC1", 2.95),
    "E": ("c1ccc({R})cc1Oc1ccccc1", "c1ccccc1Oc1ccccc1", 3.05),
    "F": ("c1ccc({R})cc1C1CCNCC1", "c1ccccc1C1CCNCC1", 2.90),
}
SUBSTITUENTS = {
    "H": ("", 0.0),
    "F": ("F", 0.14),
    "Cl": ("Cl", 0.71),
    "Br": ("Br", 0.86),
    "Me": ("C", 0.56),
    "OMe": ("OC", -0.02),
    "CF3": ("C(F)(F)F", 0.88),
    "NO2": ("[N+](=O)[O-]", -0.28),
    "OH": ("O", -0.67),
}
CONTEXT = {
    "target": "SYN-TARGET-A",
    "taxon": 0,
    "assay_type": "biochemical_activity",
    "format": "recombinant enzyme",
    "substrate": "SYN-SUBSTRATE-1",
    "system": LABEL,
}


def record(rid, ref, smiles, value, unit, op, date, context=None, group=None):
    return {
        "id": rid,
        "compound_ref": ref,
        "smiles": smiles,
        "operator": op,
        "value": value,
        "unit": unit,
        "endpoint": "IC50",
        "context": context or CONTEXT,
        "source": f"synthetic-source-{date[:4]}",
        "date": date,
        "replicate_group": group,
        "synthetic": True,
        "label": LABEL,
    }


def main() -> None:
    rng = np.random.RandomState(2026)
    records, compounds = [], []
    n = 0
    for s_name, (template, plain, base) in sorted(SCAFFOLDS.items()):
        for r_name, (prefix, _sigma) in sorted(SUBSTITUENTS.items()):
            if rng.rand() < 0.07:
                continue  # missing combination: not every analogue was made
            n += 1
            ref = f"synthetic:cmpd-{s_name}-{r_name}"
            smiles = template.format(R=prefix) if prefix else plain
            mol = Chem.MolFromSmiles(smiles)
            logp, tpsa = Descriptors.MolLogP(mol), rdMolDescriptors.CalcTPSA(mol)
            log_ic50 = (
                3.0
                + 0.0 * base
                - 0.45 * (logp - 2.0)
                + 0.006 * (tpsa - 40)
                + rng.normal(0, 0.1)
            )
            ic50 = 10**log_ic50
            compounds.append((ref, smiles, ic50, ""))
    order = rng.permutation(len(compounds))
    compounds = [
        (
            ref,
            smiles,
            ic50,
            f"{2018 + (int(rank) * 5) // len(compounds)}-{1 + int(rank) % 12:02d}-15",
        )
        for (ref, smiles, ic50, _), rank in zip(compounds, order, strict=True)
    ]
    records = []
    threshold = float(np.percentile([c[2] for c in compounds], 90))
    for i, (ref, smiles, ic50, date) in enumerate(compounds):
        if ic50 > threshold:
            records.append(
                record(
                    f"m:{ref}:1",
                    ref,
                    smiles,
                    round(threshold / 1000, 3),
                    "µM",
                    ">",
                    date,
                )
            )
        elif i % 9 == 0:
            for k, jitter in enumerate((0.95, 1.05, 1.0), start=1):
                records.append(
                    record(
                        f"m:{ref}:{k}",
                        ref,
                        smiles,
                        round(ic50 * jitter / 1000, 4),
                        "µM",
                        "=",
                        date,
                        group=ref,
                    )
                )
        else:
            records.append(
                record(f"m:{ref}:1", ref, smiles, round(ic50, 3), "nM", "=", date)
            )
    # one contradictory compound: two exact values an order of magnitude apart
    ref, smiles, ic50, date = compounds[7]
    records = [r for r in records if r["compound_ref"] != ref]
    records += [
        record(f"m:{ref}:a", ref, smiles, round(ic50, 3), "nM", "=", date),
        record(f"m:{ref}:b", ref, smiles, round(ic50 * 12, 3), "nM", "=", date),
    ]
    # a second assay with a different substrate: must never be pooled
    other = {**CONTEXT, "substrate": "SYN-SUBSTRATE-2"}
    for ref, smiles, ic50, date in compounds[:5]:
        records.append(
            record(
                f"m2:{ref}",
                ref,
                smiles,
                round(ic50 * 3.1, 3),
                "nM",
                "=",
                date,
                context=other,
            )
        )
    # a no-signal control: same structures, labels permuted
    perm = {**CONTEXT, "substrate": "SYN-PERMUTED-LABELS"}
    values = rng.permutation([c[2] for c in compounds])
    for (ref, smiles, _, date), v in zip(compounds, values, strict=True):
        records.append(
            record(
                f"mp:{ref}",
                ref,
                smiles,
                round(float(v), 3),
                "nM",
                "=",
                date,
                context=perm,
            )
        )
    records.sort(key=lambda r: r["id"])
    OUT.mkdir(parents=True, exist_ok=True)
    body = {
        "label": LABEL,
        "designed_relationship": "log10(IC50 nM) = 3.0 - 0.45*(Crippen logP - 2) + 0.006*(TPSA - 40) + N(0, 0.1), computed with RDKit; the permuted-labels context shares structures but not labels",
        "project_id": "SYNTHETIC-LEARNING-PROJECT",
        "records": records,
    }
    (OUT / "measurements.json").write_text(
        json.dumps(body, indent=1, sort_keys=True) + "\n"
    )
    files = {
        "measurements.json": hashlib.sha256(
            (OUT / "measurements.json").read_bytes()
        ).hexdigest()
    }
    (OUT / "README.md").write_text(
        f"{LABEL}. Invented chemistry for exercising dataset, SAR, model, prediction and update logic.\n"
    )
    files["README.md"] = hashlib.sha256((OUT / "README.md").read_bytes()).hexdigest()
    manifest = {"set_id": "synthetic-generic", "synthetic": True, "files": files}
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    (OUT / "manifest.sha256").write_text(
        hashlib.sha256((OUT / "manifest.json").read_bytes()).hexdigest() + "\n"
    )
    print(len(records), "records;", len(compounds), "compounds")


if __name__ == "__main__":
    main()
