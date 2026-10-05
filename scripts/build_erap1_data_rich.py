"""Freeze a bounded, explicitly incomplete scientific integration from verified cache.

Run with PYTHONPATH=. python scripts/build_erap1_data_rich.py --cache EXTERNAL_CACHE.
Source PDFs, coordinates, HTML and raw-MS remain outside Git. Does not approve
curation, overwrite historical state, or manufacture a final DecisionState.
"""

import argparse
import csv
import io
import json
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import gemmi
import numpy as np

from axis.cellular.service import CellularPharmacologyService
from axis.decision import rules
from axis.decision.engine import analyze
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.evidence_integration import (
    CUTOFF,
    VERSION,
    allotype_summary,
    digest,
    eligible_date,
    learning_admission,
    normalize_chemical,
    normalize_pic50,
    source_assigned_stereo,
    supplement_summary,
    table_inventory,
)
from axis.learning.dataset import build_dataset, group_records
from axis.learning.eligibility import assess
from axis.pharmacology.service import PharmacologyService
from axis.sources.pdb import parse_mmcif
from axis.storage import EvidenceStore
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService
from axis.validation.core import summary
from scripts.acquire_erap1_data_rich import PACKAGE, PDBS, PXDS, ROOT, write

PROJECT = "AXIS-DD-ERAP1-CURATED-001"


def verified(cache: Path, name: str) -> bytes:
    raw = (cache / name).read_bytes()
    provenance = json.loads((cache / (name + ".provenance.json")).read_text())
    if provenance.get("status") != 200 or digest(raw) != provenance.get("sha256"):
        raise ValueError(f"source artifact failed integrity: {name}")
    return raw


def structures(cache: Path, store: EvidenceStore, protein: str) -> list[dict[str, Any]]:
    service = StructureIdentityService(store)
    results = []
    for pdb in PDBS:
        raw = verified(cache, pdb + ".cif")
        metadata = json.loads(verified(cache, pdb + ".entry.json"))
        if not eligible_date(metadata["rcsb_accession_info"]["initial_release_date"]):
            raise ValueError("post-cutoff structure")
        if not eligible_date(metadata["rcsb_accession_info"]["revision_date"]):
            raise ValueError("post-cutoff coordinates require historical revision")
        provenance = json.loads((cache / (pdb + ".cif.provenance.json")).read_text())
        parsed = parse_mmcif(raw, pdb)
        result: dict[str, Any] = {
            "pdb_id": pdb,
            "source_publication": metadata["rcsb_primary_citation"],
            "source_sha256": digest(raw),
            "release_date": metadata["rcsb_accession_info"]["initial_release_date"],
            "metadata": parsed.metadata,
            "epistemic_type": "axis_observation",
            "review_state": "pending_review",
            "boundary": (
                "Crystallographic construct geometry, not cellular occupancy or "
                "therapeutic efficacy"
            ),
        }
        try:
            sid = service.ingest(
                PROJECT,
                protein,
                raw,
                pdb,
                datetime.fromisoformat(provenance["retrieved_at"]),
                None,
            )
            projection = service.projection(PROJECT, protein, sid)
            mapping = service.mapping(PROJECT, protein, sid)
            result.update(
                mapping_status="source_anchored_sequence_verified",
                constructs=projection["constructs"],
                chains=projection["chains"],
                mapping_checksums=[
                    x["transformation"]["mapping_sha256"] for x in mapping["chains"]
                ],
            )
        except ValueError as error:
            # Do not turn a bad 916 -> 941 anchor into an inferred alignment.
            result.update(
                mapping_status="BLOCKED",
                mapping_error=str(error),
                deposited_segments=[x["segments"] for x in parsed.chains],
            )
        result["components"] = [
            c for c in parsed.components if c["component_id"] != "HOH"
        ]
        result["water_instances"] = sum(
            c["component_id"] == "HOH" for c in parsed.components
        )
        result["site_classification"] = {
            "epistemic_type": "source_assertion",
            "value": "regulatory/allosteric site",
            "scope": (
                "publication chemotype; individual ligand/source-label "
                "adjudication pending"
            ),
        }
        # Actual distances from source coordinates, without author/canonical equality.
        block = gemmi.cif.read_string(raw.decode()).sole_block()
        atoms = block.get_mmcif_category("_atom_site.")
        protein_atoms = []
        other: dict[tuple[str, str, str], list[list[float]]] = defaultdict(list)
        labels = {x["label_asym_id"] for x in parsed.chains}
        for i, element in enumerate(atoms["type_symbol"]):
            if element in {"H", "D"} or float(atoms["occupancy"][i] or 0) <= 0:
                continue
            xyz = [float(atoms[k][i]) for k in ("Cartn_x", "Cartn_y", "Cartn_z")]
            label, component, number = (
                str(atoms[k][i])
                for k in ("label_asym_id", "label_comp_id", "auth_seq_id")
            )
            if label in labels:
                protein_atoms.append((label, number, xyz))
            elif component != "HOH":
                other[(label, component, number)].append(xyz)
        coordinates = np.array([a[2] for a in protein_atoms])
        contacts = []
        for (label, component, number), xyz in sorted(other.items()):
            if len(xyz) < 5 or component in {"NAG", "BMA", "MAN"}:
                continue
            distances = np.sqrt(
                ((coordinates[:, None] - np.array(xyz)[None, :]) ** 2).sum(axis=2)
            ).min(axis=1)
            residues: dict[tuple[str, str], float] = {}
            for atom, distance in zip(protein_atoms, distances, strict=True):
                if distance <= 4:
                    key = (atom[0], atom[1])
                    residues[key] = min(
                        float(distance), residues.get(key, float("inf"))
                    )
            contacts.append(
                {
                    "component": component,
                    "label_chain": label,
                    "author_number": number,
                    "cutoff_angstrom": 4.0,
                    "contacts": [
                        {
                            "protein_label_chain": k[0],
                            "protein_author_residue": k[1],
                            "minimum_distance_angstrom": round(v, 6),
                        }
                        for k, v in sorted(residues.items())
                    ],
                    "numbering": (
                        "depositor author numbering; "
                        "never treated as canonical position"
                    ),
                }
            )
        result["computed_contacts"] = contacts
        results.append(result)
    return results


def chemistry(cache: Path) -> dict[str, Any]:
    compounds, measurements, candidate_records = [], [], []
    sources = [
        ("jm5c03071_si_002.csv", "10.1021/acs.jmedchem.5c03071"),
        ("jm6c00029_si_002.csv", "10.1021/acs.jmedchem.6c00029"),
    ]
    for filename, doi in sources:
        raw = verified(cache, "si/" + filename)
        for row_number, row in enumerate(
            csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))), 2
        ):
            if not row.get("SMILES"):
                continue
            compound = normalize_chemical(row, doi, f"{filename}:row:{row_number}")
            compound["input_sha256"] = digest(raw)
            if "6c00029" in doi and compound["source_label"] in {"1", "2", "19", "20"}:
                label = compound["source_label"]
                atoms = (10, 14) if label in {"1", "2"} else (17, 21)
                cip = "S" if label in {"1", "20"} else "R"
                compound["source_assigned_identity"] = {
                    "source": "jm6c00029_si_001.pdf",
                    "page": 12 if label in {"1", "2"} else 29 if label == "19" else 30,
                    "input_sha256": digest(verified(cache, "si/jm6c00029_si_001.pdf")),
                    "source_assertion": f"(3{cip},4{cip}) absolute stereochemistry",
                    "isomeric_smiles": source_assigned_stereo(
                        compound["original_smiles"], dict.fromkeys(atoms, cip)
                    ),
                    "transformation": (
                        "Explicit SI CIP assignments; "
                        "original relative CSV representation "
                        "retained separately"
                    ),
                    "review_state": "pending_review",
                }
            compounds.append(compound)
            for column, value in row.items():
                if "pIC50" not in column or not value:
                    continue
                biochemical = column == "ERAP1 pIC50"
                measurement = {
                    "id": compound["id"] + ":" + column,
                    "compound_id": compound["id"],
                    "source": doi,
                    "locator": compound["locator"] + ":column:" + column,
                    **normalize_pic50(value),
                    "assay": {
                        "target": "ERAP1",
                        "species": "human",
                        "matrix": "isolated enzyme"
                        if biochemical
                        else "HeLa antigen presentation",
                        "assay_type": "biochemical_activity"
                        if biochemical
                        else "cellular_activity",
                        "target_construct": None,
                        "substrate": None,
                        "duration": None,
                        "replicate_information": (
                            "Source summary mean; consult SI Table S2 (BRADSHAW) / "
                            "Supplementary Table 1 (Tinworth)"
                        ),
                        "direct_target_engagement": False,
                        "context_status": (
                            "NOT FULLY ADJUDICATED; do not borrow "
                            "protocol from a different "
                            "publication"
                        ),
                    },
                    "epistemic_type": "source_assertion",
                    "normalization_epistemic_type": "axis_observation",
                    "review_state": "pending_review",
                }
                measurement["learning_admission"] = learning_admission(
                    measurement["assay"]
                )
                measurements.append(measurement)
                # Numerical-policy diagnostic only. Not an admitted training dataset.
                candidate_records.append(
                    {
                        "id": measurement["id"],
                        "compound_ref": compound["id"],
                        "smiles": compound.get("source_assigned_identity", {}).get(
                            "isomeric_smiles", compound["original_smiles"]
                        ),
                        "operator": measurement["derived_operator"],
                        "value": measurement["derived_value"],
                        "unit": "nM",
                        "endpoint": "IC50",
                        "source": doi,
                        "date": "2026-04-13" if "5c03071" in doi else "2026-06-22",
                        "replicate_group": (
                            "published aggregate, not individual replicates"
                        ),
                        "context": {
                            "target": "ERAP1",
                            "taxon": 9606,
                            "assay_type": measurement["assay"]["assay_type"],
                            "format": doi + "|" + column + "|UNADJUDICATED_PROTOCOL",
                            "substrate": "UNADJUDICATED",
                        },
                    }
                )
    duplicates = defaultdict(list)
    for compound in compounds:
        duplicates[compound["canonical_cxsmiles"]].append(compound["id"])
    diagnostics = []
    for records in group_records(candidate_records).values():
        candidate = build_dataset(
            records,
            project_id=PROJECT,
            revision=2,
            label="Unadmitted v2 numerical diagnostic",
            provenance=(
                "Explicit pIC50 conversion; source assay methods remain unadjudicated"
            ),
        )
        diagnostics.append(
            {
                "dataset": candidate,
                "numerical_policy_assessment": assess(candidate),
                "scientific_admission": (
                    "REFUSED: unresolved exact assay protocol/context"
                ),
                "model_built": False,
            }
        )
    return {
        "version": "candidate-v2",
        "compounds": compounds,
        "measurements": measurements,
        "same_source_representation_groups": [
            v for v in duplicates.values() if len(v) > 1
        ],
        "learning": diagnostics,
        "historical_learning_unchanged": True,
        "pooling": "none across publications or assay columns",
        "model_status": (
            "MODEL NOT BUILT; source-context adjudication required before "
            "learning admission"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    cache = args.cache.resolve()
    if cache.is_relative_to(ROOT):
        raise SystemExit("external cache required")
    before = json.loads((PACKAGE / "before.json").read_text())
    artifacts = []
    for path in sorted(cache.rglob("*.provenance.json")):
        metadata = json.loads(path.read_text())
        if metadata.get("cache_path") == "PMC3393101.xml":
            continue
        if metadata.get("status") == 200:
            verified(cache, metadata["cache_path"])
        metadata["redistributed"] = False
        artifacts.append(metadata)
    write(PACKAGE / "source-artifacts.json", artifacts)
    studies = []
    for path in sorted(cache.glob("*.epmc.json")):
        result = json.loads(verified(cache, path.name))["resultList"]["result"]
        if len(result) != 1:
            raise ValueError(f"ambiguous publication: {path.name}")
        publication = result[0]
        pmcid = publication.get("pmcid")
        full = bool(pmcid and (cache / (pmcid + ".xml")).exists())
        if pmcid == "PMC9892207" and (cache / (pmcid + ".bioc.xml")).exists():
            full = verified(cache, pmcid + ".bioc.xml").lstrip().startswith(b"<?xml")
        if publication["doi"].lower() == "10.1002/eji.202350449":
            full = verified(cache, "temponeras2023-valid.pdf").startswith(b"%PDF")
        supplement = (
            "6c00029" in path.name or "5c03071" in path.name or "4c00401" in path.name
        )
        studies.append(
            {
                "doi": publication["doi"],
                "pmid": publication["id"],
                "pmcid": pmcid,
                "title": publication["title"],
                "first_publication_date": publication.get("firstPublicationDate"),
                "eligible_by_cutoff": eligible_date(
                    publication.get("firstPublicationDate")
                ),
                "accessibility": "FULL_TEXT_ACCESSIBLE"
                if full
                else "SUPPLEMENT_ACCESSIBLE"
                if supplement
                else "METADATA_ONLY",
                "action": "CONTEXTUALIZE" if full else "INSUFFICIENT_ACCESS",
                "review_state": "pending_review",
                "boundary": (
                    "Access classification is claim-specific; indexed metadata does "
                    "not imply full adjudication"
                ),
            }
        )
    write(PACKAGE / "study-index.json", studies)
    access = []
    for accession in PXDS:
        project = json.loads(verified(cache, accession + ".project.json"))
        files = json.loads(verified(cache, accession + ".files.json"))
        if not eligible_date(project["publicationDate"]):
            raise ValueError("post-cutoff dataset")
        access.append(
            {
                "accession": accession,
                "title": project["title"],
                "release_date": project["publicationDate"],
                "license": project.get("license"),
                "references": project.get("references"),
                "sample_processing": project.get("sampleProcessingProtocol"),
                "data_processing": project.get("dataProcessingProtocol"),
                "file_count": len(files),
                "inventory_complete": len(files) < 500,
                "raw_ms_reprocessing": "NOT PERFORMED",
                "files": [
                    {
                        "name": f["fileName"],
                        "bytes": f.get("fileSizeBytes"),
                        "provider_checksum": f.get("checksum"),
                        "release_date": f.get("publicationDate"),
                        "updated_date": f.get("updatedDate"),
                        "locations": f.get("publicFileLocations"),
                        "downloaded": (cache / accession / f["fileName"]).exists(),
                    }
                    for f in files
                ],
            }
        )
    write(PACKAGE / "data-access.json", access)
    samples = []
    # Transcribed from author key Sample IDs!A2:D13; hash anchors the original XLSX.
    rows = [
        ("20991", "Allotype 2", 1, [1, 2]),
        ("20992", "Allotype 10", 1, [1, 2]),
        ("20993", "Allotype 2", 2, [1, 2]),
        ("20994", "Allotype 10", 2, [2, 3]),
        ("20995", "Allotype 2", 3, [1, 2]),
        ("20996", "Allotype 10", 3, [1, 2]),
    ]
    for name, condition, biological, technical in rows:
        for i, run in enumerate(technical, 1):
            samples.append(
                {
                    "sample": f"{name}_{run}.raw",
                    "condition": condition,
                    "biological_replicate": biological,
                    "technical_replicate": i,
                }
            )
    datasets = {
        "PXD066752": {
            "samples": samples,
            "sample_key_sha256": digest(
                verified(cache, "PXD066752/key_ERAP1_allotypes.xlsx")
            ),
            "sample_key_locator": "Sample IDs!A2:D13",
            "cell_type": "A375 melanoma, not primary axSpA tissue",
            "hla_b27": False,
            "intervention": "ERAP1 allotypes 2 versus 10; not KO versus drug",
            "exposure": "IFN-gamma 20 ng/mL for 24h",
            "review_state": "pending_review",
        },
        "PXD054491": {
            "intervention": "WT versus chemical inhibitor versus KO",
            "condition_column_mapping": (
                "UNRESOLVED; raw sample numbers are not inferred conditions"
            ),
            "biological_replicates_per_condition": 2,
            "technical_replicates": 3,
        },
        "PXD054494": {
            "intervention": "WT versus chemical inhibitor versus KO",
            "condition_column_mapping": (
                "UNRESOLVED; raw sample numbers are not inferred conditions"
            ),
            "biological_replicates_per_condition": 2,
            "technical_replicates": 3,
        },
    }
    write(PACKAGE / "immunopeptidome-datasets.json", datasets)
    peptides = {}
    for accession, filename in [
        ("PXD054491", "Peptide_List_PartI.txt"),
        ("PXD054494", "Peptide_List_PartII.txt"),
        ("PXD066752", "report.pr_matrix.tsv"),
    ]:
        raw = verified(cache, accession + "/" + filename)
        output = PACKAGE / "inputs" / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            raw
        )  # Deliberately frozen CC0 processed input, never raw MS.
        peptides[accession] = (
            allotype_summary(raw, samples)
            if accession == "PXD066752"
            else table_inventory(raw, "PEP.StrippedSequence")
        )
    source_supplement = verified(cache, "processed/2025-supplement-peptides.json")
    (PACKAGE / "inputs/2025-supplement-peptides.json").write_bytes(source_supplement)
    source_supplement_data = json.loads(source_supplement)
    peptides["2025_supplement"] = supplement_summary(source_supplement_data)
    for accession, report in [
        ("PXD054491", "Report 1 blanks removed"),
        ("PXD054494", "Report 2 blanks removed"),
    ]:
        datasets[accession]["condition_column_mapping"] = source_supplement_data[
            "reports"
        ][report]["samples"]
        datasets[accession]["condition_mapping_source"] = "mmc2.xlsx:" + report
    write(PACKAGE / "immunopeptidome-datasets.json", datasets)
    with (
        tempfile.TemporaryDirectory(prefix="axis-data-rich-build-") as temp,
        EvidenceStore(Path(temp) / "audit.duckdb") as store,
    ):
        import_curated_erap1(store)
        protein = TargetIdentityService(store).import_package(PROJECT)
        StructureIdentityService(store).import_package(PROJECT, protein)
        PharmacologyService(store).import_package(PROJECT, protein)
        CellularPharmacologyService(store).import_package(PROJECT, protein)
        decision = DecisionService(store)
        decision.import_package(PROJECT, protein)
        baseline_inputs = decision.inputs(PROJECT, protein)
        baseline = analyze(baseline_inputs)
        mapped = structures(cache, store, protein)
        structural_inputs = decision.inputs(PROJECT, protein)
        structural_candidate = analyze(structural_inputs)
    write(
        PACKAGE / "decision-inputs.json",
        {"baseline": baseline_inputs, "structural_only": structural_inputs},
    )
    write(PACKAGE / "structure-index.json", mapped)
    write(PACKAGE / "chemical-datasets.json", chemistry(cache))
    write(
        PACKAGE / "computational-replications.json",
        {
            "algorithm": VERSION,
            "peptides": peptides,
            "source_conclusion_reproduced": {
                "PXD066752": {
                    "source": "10.1111/imm.70056 Figure 3A",
                    "source_assertion": {
                        "union": 2325,
                        "intersection": 2162,
                        "allotype_2_unique": 130,
                        "allotype_10_unique": 33,
                    },
                    "axis_observation": {
                        "union": peptides["PXD066752"]["union"],
                        "intersection": peptides["PXD066752"]["intersection"],
                        "unique": peptides["PXD066752"]["unique"],
                    },
                    "agreement": (
                        "EXACT for sequence-set counts, "
                        "not differential-expression/motif "
                        "conclusions"
                    ),
                }
            },
            "code_hashes": {
                str(p.relative_to(ROOT)): digest(p.read_bytes())
                for p in [
                    ROOT / "axis/evidence_integration.py",
                    ROOT / "axis/sources/pdb.py",
                    Path(__file__).resolve(),
                ]
            },
            "dependencies": before["dependencies"],
            "random_seed": None,
            "deterministic": True,
        },
    )
    write(
        PACKAGE / "decision-impact.json",
        {
            "status": "NOT READY FOR INDEPENDENT SCIENTIFIC REVIEW",
            "final_decision_state_created": False,
            "canonical_before": before["canonical_decision"],
            "isolated_baseline_summary": summary(baseline),
            "structural_only_candidate_summary": summary(structural_candidate),
            "scope": (
                "Existing engine executed on baseline and isolated structural "
                "additions only; not a completed evidence reassessment"
            ),
            "rules_fingerprint": rules.fingerprint(),
            "critical_uncertainty_classification": (
                "NOT ADJUDICATED for final integrated corpus"
            ),
            "next_experiment_classification": (
                "NOT ADJUDICATED for final integrated corpus"
            ),
            "material_blockers": [
                (
                    "2026 chemistry exact assay protocols/constructs/exposure and "
                    "Tinworth translational/engagement methods inaccessible in "
                    "publisher main text; SI alone does not justify full programme "
                    "reassessment"
                ),
            ],
            "resolved_access_questions": [
                (
                    "Tinworth SI explicitly assigns stereochemistry for labels 1/2 and "
                    "19/20; original CSV conflict and source-assigned alternatives "
                    "retained"
                ),
                (
                    "PXD054491/PXD054494 conditions recovered from Supplement Table A; "
                    "source-classified peptide sets counted without independent "
                    "differential statistics"
                ),
            ],
            "structural_limitation": (
                "All 12 structures mapped; 9TF6/9TFN require explicit deposited "
                "deletion records. Contacts use author numbering, not canonical "
                "numbering. Crystallographic geometry does not establish cellular "
                "occupancy."
            ),
            "historical_state_modified": False,
        },
    )
    checksums = {
        str(p.relative_to(PACKAGE)): digest(p.read_bytes())
        for p in sorted(PACKAGE.rglob("*"))
        if p.is_file() and p.name not in {"manifest.json", "manifest.sha256"}
    }
    write(
        PACKAGE / "manifest.json",
        {
            "package_version": "1",
            "algorithm": VERSION,
            "cutoff": CUTOFF,
            "baseline_main_sha": before["main_sha"],
            "review_state": "pending_review",
            "status": "NOT READY FOR INDEPENDENT SCIENTIFIC REVIEW",
            "checksums": checksums,
            "boundary": (
                "Incomplete candidate audit, not a final scientifically reassessed "
                "DecisionState"
            ),
        },
    )
    (PACKAGE / "manifest.sha256").write_text(
        digest((PACKAGE / "manifest.json").read_bytes()) + "\n"
    )
    print("Frozen partial audit:", PACKAGE)
    print(
        "PXD066752 sequence-set agreement:",
        peptides["PXD066752"]["union"],
        peptides["PXD066752"]["intersection"],
    )
    print("Mapped structures:", Counter(s["mapping_status"] for s in mapped))


if __name__ == "__main__":
    main()
