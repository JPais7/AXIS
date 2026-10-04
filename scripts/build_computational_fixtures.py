"""Build the frozen computational-discovery packages (offline, bounded, checksummed).

    poetry run python scripts/build_computational_fixtures.py

* erap1/v1            — the ERAP1 campaign (real indexed chemistry + a small
                        researcher-supplied exploration set, review pending)
* synthetic-generic/v1 — SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE
"""

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "axis/resources/computational-discovery"
SYN = "SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE"
RANGES = {
    "molecular_weight": [150.0, 600.0],
    "crippen_logp": [None, 5.0],
    "tpsa": [None, 140.0],
    "hbd": [None, 5],
    "hba": [None, 10],
    "rotatable_bonds": [None, 10],
}
ASSAYS = [
    "biochemical ERAP1 peptidase assay (construct and substrate to be fixed with the assay provider)",
    "orthogonal counterscreen for assay interference and aggregation",
]


def write(directory: Path, plan: dict[str, Any], synthetic: bool, note: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "campaign-plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n"
    )
    files = {
        "campaign-plan.json": hashlib.sha256(
            (directory / "campaign-plan.json").read_bytes()
        ).hexdigest()
    }
    (directory / "README.md").write_text(note)
    files["README.md"] = hashlib.sha256(
        (directory / "README.md").read_bytes()
    ).hexdigest()
    manifest = {
        "set_id": plan["campaign_id"],
        "synthetic": synthetic,
        "files": files,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    (directory / "manifest.sha256").write_text(
        hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest() + "\n"
    )


def erap1() -> dict[str, Any]:
    pharm = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "axis/resources/pharmacology/erap1/v1/compounds.json"
        ).read_text()
    )
    members: list[dict[str, Any]] = [
        {
            "ref": c["id"],
            "name": c["preferred_name"],
            "smiles": c["original_smiles"],
            "origin": "indexed_experimental",
            "compound_identity": c["id"],
            "input_stereochemistry": c["stereochemistry_status"],
            "hypothesis_ids": [],
            "inclusion_rationale": "Experimentally characterised chemistry already indexed by AXIS (Phase 3.3); reference chemistry, not a candidate.",
        }
        for c in pharm
    ]
    supplied = [
        (
            "compound:supplied:bestatin",
            "Bestatin",
            "CC(C)C[C@H](NC(=O)[C@@H](O)[C@H](N)Cc1ccccc1)C(=O)O",
        ),
        (
            "compound:supplied:captopril",
            "Captopril",
            "C[C@@H](CS)C(=O)N1CCC[C@H]1C(=O)O",
        ),
        ("compound:supplied:vorinostat", "Vorinostat", "ONC(=O)CCCCCCC(=O)Nc1ccccc1"),
    ]
    for ref, name, smiles in supplied:
        members.append(
            {
                "ref": ref,
                "name": name,
                "smiles": smiles,
                "origin": "researcher_supplied",
                "compound_identity": None,
                "input_stereochemistry": None,
                "hypothesis_ids": ["hypothesis:erap1:zinc-binding-chemotype"],
                "inclusion_rationale": "Known drug carrying a metal-binding group (hydroxamate, thiol or alpha-hydroxy-beta-amino amide), supplied as a researcher hypothesis to explore the catalytic-metal region. Structure typed by hand and NOT verified against ChEMBL/PubChem; AXIS indexes no ERAP1 evidence for it.",
            }
        )
    return {
        "campaign_id": "campaign:erap1:bounded-chemistry-v1",
        "title": "ERAP1 bounded chemical-hypothesis campaign",
        "project_id": "AXIS-DD-ERAP1-CURATED-001",
        "target_label": "ERAP1",
        "protein_id": "UniProt Q9NZ08",
        "question": "Given the currently indexed ERAP1 structural and chemical evidence, which molecules in this bounded chemical space justify experimental testing of specific ERAP1 binding/modulation hypotheses, and which hypotheses remain untested by it?",
        "intervention_strategy": "pharmacological modulation of ERAP1 (working formulation; direction of benefit not assumed)",
        "decision_link": {
            "note": "chemical matter is needed to address the engagement/dependency uncertainties of the current decision state",
            "requires": "decision package imported for the project",
        },
        "structure": {
            "resource": "resources/structures/erap1/3qnf/v1/structure.cif",
            "source_structure_id": "PDB:3QNF",
            "source_sha256": "04b29d420769a6ce405c85d90e6888289de20381e17e64c1a31c3e4f835b8f75",
            "chain": "A",
            "construct": "as deposited in 3QNF (see structure package)",
            "structural_state": "open state as deposited; not shown to be the disease-relevant conformation",
            "canonical_mapping": "UniProt Q9NZ08 via the AXIS structure-identity package",
            "ligands_cofactors": "ZN retained; NAG and water removed; no drug-like ligand bound",
        },
        "site": {
            "id": "site:erap1:3qnf:A:zinc-shell-8A",
            "around": "ZN",
            "radius": 8.0,
        },
        "hypotheses": [
            {
                "id": "hypothesis:erap1:zinc-binding-chemotype",
                "revision": 1,
                "statement": "A molecule carrying a metal-binding group that reaches the catalytic zinc region may inhibit ERAP1 catalytic trimming.",
                "strategy": "inhibit",
                "desired_effect": "reduce catalytic trimming in a biochemical assay",
                "structural_state": "open state (3QNF chain A)",
                "site_id": "site:erap1:3qnf:A:zinc-shell-8A",
                "rationale": "Aminopeptidases are zinc metalloenzymes; chemotypes with metal-binding groups are the generic way to engage such a site.",
                "supporting_chemistry": [],
                "contradicting_chemistry": [],
                "constraints": [
                    "standard docking cannot represent metal coordination",
                    "proximity is not chelation",
                ],
                "uncertainties": [
                    "whether the site is therapeutically relevant",
                    "ERAP1 versus ERAP2/IRAP selectivity",
                    "no ERAP1 evidence indexed for these compounds",
                ],
                "falsification": [
                    "No measurable activity in the biochemical ERAP1 assay at adequate concentration",
                    "Activity disappears under the orthogonal counterscreen (assay artefact)",
                    "A direct-engagement experiment contradicts the proposed binding mechanism",
                ],
                "epistemic_status": "researcher_hypothesis",
            },
            {
                "id": "hypothesis:erap1:maben-series-analog",
                "revision": 1,
                "statement": "A scaffold related to an indexed experimentally characterised series may preserve ERAP1 modulation while changing selectivity.",
                "strategy": "modulate",
                "desired_effect": "retain biochemical modulation of the indexed series",
                "structural_state": "not specified",
                "site_id": None,
                "rationale": "Analog follow-up of indexed chemistry is the lowest-risk way to use known SAR.",
                "supporting_chemistry": [
                    "compound:maben-1",
                    "compound:maben-2",
                    "compound:maben-3",
                ],
                "contradicting_chemistry": [],
                "constraints": ["no observed SAR is indexed beyond three compounds"],
                "uncertainties": ["whether any analog exists in this bounded space"],
                "falsification": [
                    "Analog inactive in the same biochemical assay as the parent"
                ],
                "epistemic_status": "ai_suggestion",
            },
        ],
        "space": {
            "source": "indexed AXIS ERAP1 pharmacology package (3 compounds) plus 3 researcher-supplied molecules",
            "source_version": "axis-erap1-pharmacology v1; supplied set frozen 2026-10",
            "retrieval_date": "no live retrieval; offline fixture",
            "selection_criteria": "all indexed ERAP1 compounds; metal-binding-group exploration set chosen by the researcher",
            "filters": "none applied",
            "size_before_filtering": 6,
            "identity_policy": "indexed compounds keep their CompoundIdentity; supplied compounds are campaign-local and unverified",
            "deduplication": "by reference id",
            "members": members,
        },
        "methods": ["descriptors", "similarity", "clustering", "scaffolds", "docking"],
        "constraints": {
            "descriptor_ranges": RANGES,
            "exploit_threshold": 0.4,
            "cluster_threshold": 0.7,
            "require_structure": True,
            "require_structural_compatibility": False,
            "structural_compatibility_reason": "docking is not validated for this site, so it cannot be a selection requirement",
            "panel": {"exploitation": 3, "exploration": 3, "per_cluster": 1},
        },
        "assay_options": ASSAYS,
    }


def synthetic() -> dict[str, Any]:
    def member(
        i: int, smiles: str, origin: str, evidence: str | None = None, hyp: bool = True
    ) -> dict[str, Any]:
        return {
            "ref": f"synthetic:cmpd-{i}",
            "name": f"{SYN} compound {i}",
            "smiles": smiles,
            "origin": origin,
            "compound_identity": None,
            "input_stereochemistry": None,
            "hypothesis_ids": ["hypothesis:synthetic:h1"] if hyp else [],
            "fixture_evidence": evidence,
            "inclusion_rationale": SYN,
        }

    members = [
        member(
            1,
            "CC(=O)Nc1ccc(O)cc1",
            "known",
            "SYNTHETIC reference activity record",
            hyp=False,
        ),
        member(2, "CC(=O)Nc1ccc(OC)cc1", "supplied"),
        member(3, "CC(=O)Nc1ccc(OCC)cc1", "supplied"),
        member(4, "c1ccc2ccccc2c1", "supplied"),
        member(5, "OC(=O)c1ccccc1", "supplied"),
        member(6, "CCCCCCCCCCCC(=O)O", "supplied"),
        member(7, "not-a-smiles", "supplied"),
    ]
    return {
        "campaign_id": "campaign:synthetic:generic-v1",
        "title": f"{SYN} — generic campaign",
        "project_id": "SYNTHETIC-PROJECT",
        "target_label": "SYN-TARGET-A",
        "protein_id": None,
        "question": f"{SYN}: which compounds of this invented space would be prioritized for testing?",
        "intervention_strategy": "synthetic strategy",
        "decision_link": None,
        "structure": None,
        "site": None,
        "hypotheses": [
            {
                "id": "hypothesis:synthetic:h1",
                "revision": 1,
                "statement": f"{SYN}: an invented hypothesis.",
                "strategy": "synthetic",
                "desired_effect": "synthetic",
                "structural_state": "none",
                "site_id": None,
                "rationale": SYN,
                "supporting_chemistry": [],
                "contradicting_chemistry": [],
                "constraints": [],
                "uncertainties": [SYN],
                "falsification": ["synthetic falsification condition"],
                "epistemic_status": "researcher_hypothesis",
            }
        ],
        "space": {
            "source": SYN,
            "source_version": "n/a",
            "retrieval_date": "n/a",
            "selection_criteria": SYN,
            "filters": "none",
            "identity_policy": "synthetic",
            "deduplication": "by reference id",
            "members": members,
        },
        "methods": ["descriptors", "similarity", "clustering", "scaffolds"],
        "constraints": {
            "descriptor_ranges": RANGES,
            "exploit_threshold": 0.5,
            "cluster_threshold": 0.7,
            "require_structure": False,
            "require_structural_compatibility": False,
            "panel": {"exploitation": 2, "exploration": 2, "per_cluster": 1},
        },
        "assay_options": ["synthetic assay"],
    }


def main() -> None:
    write(
        ROOT / "erap1/v1",
        erap1(),
        False,
        "ERAP1 bounded computational campaign (Phase 3.8). Indexed chemistry: Maben 2020 compounds 1-3 "
        "(AXIS pharmacology v1). Three exploration molecules are researcher-supplied and unverified; "
        "no live retrieval was used. Computational prioritization only; requires experimental validation.\n",
    )
    write(
        ROOT / "synthetic-generic/v1",
        synthetic(),
        True,
        f"{SYN}. Invented compounds exercising target independence, failure handling and ordering.\n",
    )
    print("built", ROOT)


if __name__ == "__main__":
    main()
