"""Generate frozen views from explicitly curated inputs, never classify literature."""

import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "axis/resources/evidence-addendum/erap1-axspa/2020-2026/v1"


def write(name, value):
    (PACKAGE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main():
    studies = json.loads((PACKAGE / "curation.json").read_text())
    discovered = json.loads((PACKAGE / "discovery-metadata.json").read_text())
    metadata = {r["id"]: r for r in discovered}
    claims, impacts, accesses = [], [], []
    cache_root = Path(tempfile.gettempdir())
    for study in studies:
        record = metadata.get(study.get("pmid"), {})
        if record.get("doi") and record["doi"] != study.get("doi"):
            raise ValueError("DOI mismatch: " + study["id"])
        study["title"] = record.get("title", study["id"])
        study["first_publication_date"] = record.get("firstPublicationDate")
        source_access = None
        if study.get("pmcid"):
            for path in sorted(cache_root.glob("axis-addendum-read-*/access.json")):
                access = json.loads(path.read_text())
                if access["pmcid"] == study["pmcid"]:
                    source_access = {k: v for k, v in access.items() if k != "cache"}
                    xml = ET.parse(path.parent / (study["pmcid"] + ".xml"))
                    title = xml.find(".//article-title")
                    if title is not None:
                        study["title"] = " ".join(title.itertext())
                    doi_values = [
                        a.text
                        for a in xml.findall(".//article-id")
                        if a.get("pub-id-type") == "doi"
                    ]
                    if study["doi"] not in doi_values:
                        raise ValueError("XML DOI mismatch: " + study["id"])
                    if study["action"] == "INTEGRATE" and not access["body_present"]:
                        raise ValueError("No inspected body: " + study["id"])
                    break
        if study["action"] == "INTEGRATE" and source_access is None:
            raise ValueError("No inspected source: " + study["id"])
        accesses.append(
            {
                "study_id": study["id"],
                "accessibility": study["accessibility"],
                "methods_sufficient": study["methods_sufficient"],
                "source_access": source_access,
                "access_date": "2026-10-05",
                "review_status": "pending_review",
            }
        )
        for number, (locator, text, direction) in enumerate(study["findings"], 1):
            claims.append(
                {
                    "id": f"addendum:claim:{study['id']}:{number}",
                    "study_id": study["id"],
                    "claim_text": text,
                    "source_locator": {
                        "url": "https://doi.org/" + study["doi"],
                        "pmcid": study.get("pmcid"),
                        "section": locator,
                    },
                    "experiment_id": "addendum:experiment:" + study["id"],
                    "experimental_context": study["context"],
                    "entities": ["ERAP1", study["id"]],
                    "layers": study["layers"],
                    "direction": direction,
                    "epistemic_kind": "source_assertion",
                    "review_status": "pending_review",
                    "clinical_efficacy": False,
                    "direct_cellular_engagement": False,
                    "chemical_genetic_dependency": False,
                    "therapeutic_direction_established": False,
                }
            )
        if study["action"] == "INTEGRATE":
            impacts.append(
                {
                    "id": "addendum:impact:" + study["id"],
                    "study_id": study["id"],
                    "claim_ids": [
                        c["id"] for c in claims if c["study_id"] == study["id"]
                    ],
                    "affected_evidence_layer": study["layers"],
                    "affected_hypothesis": "ERAP1 modulation in HLA-B27/AS biology",
                    "affected_explanation": [
                        "explanation:on_target",
                        "explanation:context",
                        "explanation:indirect",
                        "explanation:off_target",
                    ],
                    "affected_uncertainty": [
                        "uncertainty:target_engagement",
                        "uncertainty:genetic_context",
                        "uncertainty:mechanistic_bridge",
                    ],
                    "affected_intervention_strategy": (
                        "genotype/context-dependent ERAP1 modulation; "
                        "direction unresolved"
                    ),
                    "affected_experiment": "decision:exp:chemical-genetic-engagement",
                    "impact_direction": study["impact_direction"],
                    "materiality": study["materiality"],
                    "rationale": study["impact_rationale"],
                    "epistemic_kind": "axis_inference",
                    "review_status": "pending_review",
                }
            )
    write("candidate-studies.json", studies)
    write("accessibility.json", accesses)
    write("included-studies.json", [s for s in studies if s["action"] == "INTEGRATE"])
    write(
        "contextualized-studies.json",
        [s for s in studies if s["action"] == "CONTEXTUALIZE"],
    )
    write(
        "inaccessible-studies.json",
        [s for s in studies if s["action"] == "INSUFFICIENT_ACCESS"],
    )
    write("claims.json", claims)
    write("impact-assessments.json", impacts)
    baseline = ROOT / "reports/commercial/erap1-axspa/v1/state-snapshot.json"
    state = json.loads(baseline.read_text())
    write(
        "baseline.json",
        {
            "commit": "d491ebe47ee0c40dfaa3823a44a9decd1afae29d",
            "snapshot_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            "decision_digest": state["decision"]["evidence_digest"],
            "critical": state["decision"]["critical_uncertainty_id"],
            "recommended": "decision:exp:chemical-genetic-engagement",
            "learning": "MODEL NOT BUILT",
            "historical_refresh_commit": "a3cbb37a5681a057dfe1c86c7e8686553d95c4b2",
        },
    )
    context = json.loads((PACKAGE / "context-access.json").read_text())
    structures = []
    for row in context:
        if "/entry/" not in row["url"]:
            continue
        pdb = row["url"].rsplit("/", 1)[-1]
        entry = row["response"]
        polymer = next(
            r["response"] for r in context if r["url"].endswith("/" + pdb + "/1")
        )
        structures.append(
            {
                "pdb_id": pdb,
                "study_id": "cyclohexyl-2024",
                "release_date": entry["rcsb_accession_info"]["initial_release_date"],
                "method": entry["exptl"][0]["method"],
                "resolution_angstrom": entry["rcsb_entry_info"]["resolution_combined"][
                    0
                ],
                "construct_length": polymer["entity_poly"][
                    "rcsb_sample_sequence_length"
                ],
                "chains": polymer["entity_poly"]["pdbx_strand_id"],
                "sequence_mapping": polymer["rcsb_polymer_entity_align"],
                "sequence_conflicts": polymer["entity_poly"]["rcsb_conflict_count"],
                "mutations": (
                    "Depositor mutation count zero; five reference conflicts "
                    "and engineered linker/tag. Full allotype reconciliation "
                    "not performed."
                ),
                "conformation": "not independently classified from coordinates",
                "ligand": entry["struct"]["title"],
                "metal": (
                    "ZN deposited; binding site attribution from paper, "
                    "not occupancy in cells"
                ),
                "binding_site": "paper-reported allosteric regulatory site",
                "missing_residues": {
                    "unmodeled_polymer_count": entry["rcsb_entry_info"][
                        "deposited_unmodeled_polymer_monomer_count"
                    ],
                    "per_chain_ranges": "not evaluated",
                },
                "limitations": (
                    "Metadata/source-level structural curation, not a validated "
                    "coordinate/docking or druggability assessment."
                ),
            }
        )
    write("structures.json", structures)
    counts = Counter(s["action"] for s in studies)
    write(
        "summary.json",
        {
            "discovery_records": len(discovered),
            "selected_candidates": len(studies),
            "selection_actions": dict(counts),
            "source_assertions": len(claims),
            "impact_assessments": len(impacts),
            "structures": len(structures),
            "new_learning_measurements": 0,
            "coverage": (
                "Not comprehensive; discovery records not all "
                "scientifically screened"
            ),
            "layers": dict(
                Counter(
                    layer
                    for s in studies
                    if s["action"] == "INTEGRATE"
                    for layer in s["layers"]
                )
            ),
        },
    )
    table = [
        "# Bounded addendum: selected-study table",
        "",
        "Discovery retrieval is not complete scientific screening. INTEGRATE means "
        "inclusion in this versioned addendum, not expert approval or canonical "
        "Evidence Store import.",
        "",
        "| Study | Year | Layer | Primary? | Full text/access | Methods sufficient? "
        "| Disease relevance | Decision relevance/action | Rationale |",
        "|---|---:|---|---|---|---|---|---|---|",
    ]
    for study in studies:
        values = [
            f"[{study['id']}](https://doi.org/{study['doi']})"
            if study.get("doi")
            else "[EAST1](https://clinicaltrials.gov/study/NCT07047703)",
            str(study["year"]),
            ", ".join(study["layers"]),
            str(study.get("primary", True)),
            study["accessibility"],
            str(study["methods_sufficient"]),
            study["disease_relevance"],
            study.get("materiality", "not adjudicated") + "; " + study["action"],
            study["rationale"],
        ]
        table.append("| " + " | ".join(v.replace("|", "/") for v in values) + " |")
    (PACKAGE / "study-selection.md").write_text("\n".join(table) + "\n")
    entries = []
    for path in sorted(PACKAGE.iterdir()):
        if path.name in {"manifest.json", "manifest.sha256"}:
            continue
        data = path.read_bytes()
        entries.append(
            {
                "path": path.name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    write(
        "manifest.json",
        {
            "schema_version": 1,
            "frozen": True,
            "review_status": "pending_review",
            "files": entries,
        },
    )
    digest = hashlib.sha256((PACKAGE / "manifest.json").read_bytes()).hexdigest()
    (PACKAGE / "manifest.sha256").write_text(digest + "  manifest.json\n")
    print(json.dumps(json.loads((PACKAGE / "summary.json").read_text()), indent=2))


if __name__ == "__main__":
    main()
