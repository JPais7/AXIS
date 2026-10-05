"""Bounded BRADSHAW primary-method delta and existing-engine reassessment.

Never rewrites parents, approves claims, changes rules or trains a model.
First freeze needs legitimately supplied PDFs; replay needs only frozen facts.
"""

import argparse
import csv
import io
import json
import subprocess
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from axis.cellular.service import CellularPharmacologyService
from axis.decision import engine, rules
from axis.decision.evidence import load_records
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.domain.cellular import (
    BiologicalContext,
    CellularAssessment,
    CellularExperiment,
    ExperimentalReadout,
)
from axis.domain.decision import DecisionState
from axis.evidence_integration import (
    CUTOFF,
    digest,
    eligible_date,
    learning_admission,
)
from axis.learning.dataset import build_dataset, group_records
from axis.learning.eligibility import assess, policy_fingerprint
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService
from scripts.adjudicate_erap1_assay_methods import (
    BASE,
    BRAD,
    FINAL,
    LIDDLE,
    PARENT,
    VERIFIED,
    field,
    stage_a,
)
from scripts.adjudicate_erap1_assay_methods import (
    OUTPUT as METHODS,
)
from scripts.adjudicate_erap1_assay_methods import (
    matrix as parent_matrix,
)
from scripts.adjudicate_erap1_assay_methods import (
    replay as parent_replay,
)
from scripts.close_erap1_data_rich import ROOT, envelope, read, roundtrip, write

OUTPUT = BASE.parent / "bradshaw-main-v3"
PROJECT = "AXIS-DD-ERAP1-CURATED-001"
ALGORITHM = "erap1-bradshaw-main-reassessment-1"
SNAPSHOT = ROOT / "reports/commercial/erap1-axspa/v1/state-snapshot.json"
NOW = datetime.fromisoformat("2026-10-05T23:59:59+00:00")
PARENTS = {"v1": BASE, "closure-v1": PARENT, "assay-methods-v2": METHODS}

# Visual transcription of primary tables, NOT values read from the prompt.
# Page 9 Table2 compound28 conflicts with SI/CSV (5.3 vs5.4), retained below.
MAIN_TABLES = {
    6: [
        (9, 8.6, 7.4),
        (10, 8.1, 7),
        (11, 7.6, 6.8),
        (12, 7.9, 6.3),
        (13, 8.7, None),
        (14, 7.2, 5.1),
        (15, 7.3, 6.8),
        (16, 6.2, None),
    ],
    9: [
        (21, 9, 7.5),
        (22, 7.4, 5.3),
        (23, 8.7, 7.8),
        (24, 8.6, 7.5),
        (25, 8.1, 6.6),
        (26, 8, 7.2),
        (27, 8.4, 7.2),
        (28, 6.8, 5.3),
        (29, 6.4, 5.2),
        (30, 5.9, 4.7),
    ],
    12: [
        (33, 8.6, 6.6),
        (34, 7.5, 6.3),
        (35, 7.5, 6.5),
        (36, 7.9, 7.5),
        (37, 6.3, None),
    ],
    14: [(40, 7.9, 7.3), (41, 7.8, 6.6), (42, 7.9, 7.2), (43, 8, 6.5), (44, 8, 6.6)],
    16: [(21, 9, 7.5), (40, 7.9, 7.3)],
}
EXTRA_TESTS = {
    (21, "enzyme"): {
        "operator": ">",
        "pIC50": 9.29,
        "n": 1,
        "locator": "main PDF p9 Table2 footnote(a)",
    },
    (28, "cell"): {
        "operator": "<",
        "pIC50": 4.3,
        "n": 4,
        "locator": "main PDF p9 Table2 footnote(c)",
    },
    (33, "cell"): {
        "operator": "<",
        "pIC50": 4.3,
        "n": 5,
        "locator": "main PDF p12 Table4 footnote(a)",
    },
    (44, "cell"): {
        "operator": "<",
        "pIC50": 4.3,
        "n": 1,
        "locator": "main PDF p14 Table6 footnote(c)",
    },
}


def hashes(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): digest(p.read_bytes())
        for p in folder.rglob("*")
        if p.is_file()
    }


def extract(pdf_python: str, path: Path) -> list[str]:
    code = (
        "import json,sys;from pypdf import PdfReader;"
        "print(json.dumps([p.extract_text() for p in PdfReader(sys.argv[1]).pages]))"
    )
    return json.loads(subprocess.check_output([pdf_python, "-c", code, str(path)]))


def ingest(pdf_python: str, main: Path, si: Path, csv_path: Path) -> dict[str, Any]:
    pages = extract(pdf_python, main)
    if len(pages) != 28 or not main.read_bytes().startswith(b"%PDF-"):
        raise ValueError("not the complete BRADSHAW article")
    first = " ".join(pages[0].split())
    required = [
        "Automated Molecular Design in BRADSHAW",
        "Robert P. Law",
        BRAD,
        "Published: April 13, 2026",
        "8869",
        "8896",
    ]
    if not all(t in first for t in required):
        raise ValueError("article identity/date mismatch")
    facts = {
        "purified_hap2": (4, "purified ERAP1 Hap2"),
        "rapidfire": (4, "Rapidfire mass"),
        "product": (4, "8-mer TAFTIPSI"),
        "endpoint_definition": (5, "Hap2 biochemical"),
        "main_methods": (17, "ERAP1 Enzymatic Activity"),
        "cell_endpoint": (17, "Cellular Antigen Presentation Assay"),
        "duration": (17, "40 h"),
        "cell_controls": (17, "50 μM FAC"),
        "allotype_panel": (16, "allotypes 1−10"),
        "ref22": (27, "Targeting the Regulatory Site"),
        "ref8": (26, "Common Allotypes"),
    }
    checks = []
    for name, (page, token) in facts.items():
        if token not in " ".join(pages[page - 1].split()):
            raise ValueError("primary source verification failed: " + name)
        checks.append(
            {
                "fact": name,
                "page": page,
                "verified": True,
                "page_text_sha256": digest(pages[page - 1].encode()),
            }
        )
    text = extract(pdf_python, si)[59]
    if "Table S2" not in text or "Standard Deviation" not in text:
        raise ValueError("SI potency table missing")
    stats = {}
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) < 4 or not tokens[0].isdigit() or tokens[1] != "=":
            continue
        cpd = tokens.pop(0)
        entries = {}
        for kind in ("enzyme", "cell"):
            if not tokens:
                break
            if tokens.pop(0) != "=":
                raise ValueError("unexpected SI operator")
            mean, n = float(tokens.pop(0)), int(tokens.pop(0))
            sd = float(tokens.pop(0)) if tokens and tokens[0] != "=" else None
            entries[kind] = {
                "operator": "=",
                "mean": mean,
                "n_in_mean": n,
                "sd_pIC50": sd,
                "locator": "SI S60 TableS2 row:" + cpd,
            }
        stats[cpd] = entries
    if len(stats) != 39:
        raise ValueError(f"unexpected SI row count {len(stats)}")
    chemistry = read(BASE / "chemical-datasets.json")
    source_compounds = [c for c in chemistry["compounds"] if c["source"] == BRAD]
    raw_rows = [
        r
        for r in csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8-sig")))
        if r.get("Paper Number") and r.get("SMILES")
    ]
    if [c["source_row"] for c in source_compounds] != raw_rows:
        raise ValueError("CSV differs from historical chemical records")
    source = {
        "filename": main.name,
        "local_path": str(main.resolve()),
        "sha256": digest(main.read_bytes()),
        "bytes": main.stat().st_size,
        "doi": BRAD,
        "authors": "Law et al.",
        "title": (
            "Automated Molecular Design in BRADSHAW, Applied to the "
            "Optimization of ERAP1 Inhibitors"
        ),
        "journal": "Journal of Medicinal Chemistry",
        "year": 2026,
        "volume": 69,
        "pages": "8869-8896",
        "publication_date": "2026-04-13",
        "access_date": CUTOFF,
        "access_provenance": "PDF footer: UNIV LUSOFONA 02800 user on 05 October 2026",
        "eligible": eligible_date("2026-04-13"),
        "redistributed": False,
        "source_class": "peer_reviewed_primary_research",
        "review_state": "pending_review",
        "si_sha256": digest(si.read_bytes()),
        "csv_sha256": digest(csv_path.read_bytes()),
        "publication_package": BRAD,
        "independent_study_count": 1,
        "verification": checks,
    }
    if "UNIV LUSOFONA 02800 user on 05 October 2026" not in first:
        raise ValueError("access provenance not verified")
    for c in source_compounds:
        if c["input_sha256"] != source["csv_sha256"]:
            raise ValueError("CSV checksum differs")
    if source["si_sha256"] not in json.dumps(read(BASE / "source-artifacts.json")):
        raise ValueError("SI not linked to historical source inventory")
    return {
        "main_source": source,
        "si_statistics": stats,
        "main_table_values": MAIN_TABLES,
        "additional_censored_tests": [
            {"compound": c, "family": k, **v} for (c, k), v in EXTRA_TESTS.items()
        ],
    }


def matrix() -> list[dict[str, Any]]:
    rows = parent_matrix()
    for row in rows[:2]:
        kind = "enzyme" if row["id"].endswith("enzyme") else "cell"
        row.update(
            version_scope="final main + SI + CSV; explicit ref22 inheritance",
            final_context_adjudicated=True,
            completeness="PARTIALLY_ADJUDICATED",
        )
        for name, value in row["fields"].items():
            if value["state"] not in VERIFIED:
                row["fields"][name] = field(
                    source=BRAD,
                    locator=(
                        "main PDF p17; explicit ref22 checked; field not established"
                    ),
                )

        def direct(value: str, locator: str = "main PDF p17 (8885)") -> dict[str, Any]:
            return field(value, source=BRAD, locator=locator)

        def inherit(value: str) -> dict[str, Any]:
            return field(
                value,
                source=LIDDLE,
                locator="Liddle PDF p8 (H)",
                state="INHERITED_VERIFIED",
                chain=[BRAD + ":p17:ref22", LIDDLE],
            )

        row["fields"].update(
            {
                "target": direct("ERAP1"),
                "species": direct(
                    "human ERAP1"
                    if kind == "enzyme"
                    else "human HeLa; mouse H-2Kb/beta2m reporter"
                ),
                "construct": inherit("full-length ERAP1; C-terminal 6His retained")
                if kind == "enzyme"
                else direct("endogenous HeLa ERAP1; BacMam reporter"),
                "substrate": direct(
                    "YTAFTIPSI -> TAFTIPSI", "main PDF p4 (8872); p17 ref22"
                )
                if kind == "enzyme"
                else direct("ER-targeted LEQLESIINFEKL -> SIINFEKL presentation"),
                "allotype": direct("Hap2 / Allotype2", "main PDF p4,p5 Figure4,p17")
                if kind == "enzyme"
                else field(source=BRAD),
                "incubation duration": inherit("60 min")
                if kind == "enzyme"
                else direct("40 h"),
                "readout": direct(
                    "RapidFire MS; TAFTIPSI product", "main PDF p4 (8872)"
                )
                if kind == "enzyme"
                else direct(
                    "25.D1.16 APC; Intellicyt iQue Screener Plus flow cytometry"
                ),
                "endpoint": direct(
                    "Hap2/YTAFTIPSI biochemical pIC50", "main PDF p5 Figure4"
                )
                if kind == "enzyme"
                else direct("HeLa antigen-presentation pIC50; NOT occupancy"),
                "replicates": direct(
                    (
                        "SI S60 row-specific N in mean; main Tables1,2,4,6 "
                        "exceptions supersede generic n>=2"
                    ),
                    "SI S60; main PDF pp6,9,12,14",
                ),
                "error metric": direct(
                    "SI S60 pIC50 SD; absent for n=1; not IC50 SD", "SI S60 TableS2"
                ),
                "fitting": inherit("four-parameter dose response; slope and asymptotes")
                if kind == "enzyme"
                else direct("four-parameter variable slope"),
            }
        )
        if kind == "enzyme":
            for name, value in {
                "enzyme concentration": "1 nM",
                "substrate concentration": "5 uM",
                "buffer": "50 mM HEPES; 100 mM NaCl; 0.002% Tween20; 0.005% BSA",
                "pH": "7.0",
            }.items():
                row["fields"][name] = inherit(value)
        else:
            row["cell_context"] = {
                "ERAP1_allotype": "NOT_CONFIRMED",
                "ERAP2": "NOT_CONFIRMED",
                "endogenous_HLA": "NOT_CONFIRMED",
                "genotype": "NOT_CONFIRMED",
                "control1": "LEQLESIINFEKL + DMSO",
                "control2": "LEQLESIINFEKL + control ERAP1 inhibitor50uM FAC",
                "control_compound_identity": (
                    "NOT_CONFIRMED; do not borrow Tinworth compound6"
                ),
                "normalization": "100-100*(compound-control2)/(control1-control2)",
                "viability": (
                    "95% establishes 0.5% DMSO tolerance, not viability at "
                    "every exposure"
                ),
                "instrument_change": "iQue vs Liddle Cyan; main takes precedence",
            }
    return rows


def numerical(seed: dict[str, Any]) -> list[dict[str, Any]]:
    chemistry = read(BASE / "chemical-datasets.json")
    compounds = {c["id"]: c for c in chemistry["compounds"]}
    out = []
    for old in chemistry["measurements"]:
        if old["source"] != BRAD:
            continue
        cpd = int(old["compound_id"].split(":")[-1])
        kind = "enzyme" if old["id"].endswith(":ERAP1 pIC50") else "cell"
        stats = seed["si_statistics"].get(str(cpd), {}).get(kind)
        main_values = [
            {"page": int(page), "value": triple[1 if kind == "enzyme" else 2]}
            for page, triples in seed["main_table_values"].items()
            for triple in triples
            if triple[0] == cpd
        ]
        disagreements = []
        if stats and (
            stats["mean"] != old["source_value"]
            or stats["operator"] != old["source_operator"]
        ):
            disagreements.append("SI/CSV summary conflict")
        if any(v["value"] != old["source_value"] for v in main_values):
            disagreements.append("main/CSV summary conflict")
        extra = EXTRA_TESTS.get((cpd, kind))
        if extra:
            disagreements.append(
                "additional censored tests; mean is not complete replicate distribution"
            )
        if stats and stats["n_in_mean"] < 2:
            disagreements.append("single exact occasion; not replicated")
        out.append(
            {
                "parent_measurement_id": old["id"],
                "compound_id": old["compound_id"],
                "original_smiles": compounds[old["compound_id"]]["original_smiles"],
                "family": kind,
                "csv": old,
                "si_statistics": stats,
                "main_values": main_values,
                "additional_test": extra,
                "measurement_status": "CONDITIONAL"
                if disagreements or stats is None
                else "CONSISTENT",
                "limitations": disagreements
                + (
                    ["compound-specific N/SD not reported in SI"]
                    if stats is None
                    else []
                ),
                "fit_admission": not disagreements
                and stats is not None
                and stats["n_in_mean"] >= 2,
                "review_state": "pending_review",
            }
        )
    return out


def allotypes() -> dict[str, Any]:
    return {
        "source": BRAD,
        "locator": "main PDF p8 Results; p16 Figure16; p17 Methods",
        "compound": BRAD + ":compound:40",
        "allotypes": list(range(1, 11)),
        "substrates": {
            "YTAFTIPSI": {
                "product": "TAFTIPSI",
                "enzyme_nM": [1, 1, 1, 1, 2, 2, 2, 2, 2, 10],
                "censored_below_pIC50_4": [4, 6, 7, 8, 9, 10],
            },
            "EAAGIGILTV": {
                "product": "AGIGILTV",
                "enzyme_nM": [5, 2.5, 6, 7.5, 10, 10, 12, 7.5, 7.5, 30],
            },
        },
        "graph_values_digitized": False,
        "pooling": False,
        "source_conclusion": (
            "Potency/maximum response depend on allotype and "
            "substrate; series not progressed to preclinical "
            "candidate development due to context dependence and "
            "potency/exposure limitations"
        ),
        "clinical_efficacy": False,
        "review_state": "pending_review",
    }


def learning(seed: dict[str, Any]) -> dict[str, Any]:
    rows = numerical(seed)
    records = []
    for r in rows:
        if not r["fit_admission"]:
            continue
        m = r["csv"]
        kind = r["family"]
        records.append(
            {
                "id": m["id"],
                "compound_ref": m["compound_id"],
                "smiles": r["original_smiles"],
                "value": m["derived_value"],
                "operator": m["derived_operator"],
                "unit": "nM",
                "endpoint": "IC50",
                "source": BRAD,
                "date": "2026-04-13",
                "replicate_group": "published mean; individual replicates unavailable",
                "context": {
                    "target": "ERAP1",
                    "taxon": 9606,
                    "assay_type": "biochemical_activity"
                    if kind == "enzyme"
                    else "cellular_activity",
                    "format": BRAD + ":" + kind,
                    "substrate": "Hap2:YTAFTIPSI"
                    if kind == "enzyme"
                    else "HeLa:LEQLESIINFEKL:H-2Kb:pharmacological_control",
                },
            }
        )
    admitted = []
    for rs in group_records(records).values():
        d = build_dataset(
            rs,
            project_id=PROJECT,
            revision=3,
            label="BRADSHAW source-context adjudicated; conservative fitting subset",
            provenance=(
                "Main+SI+CSV; conflicts/singletons/missingN excluded, "
                "never invented replicates"
            ),
        )
        admitted.append({"dataset": d, "assessment": assess(d)})
    contexts = {r["id"]: r for r in matrix()[:2]}
    admission = {}
    for name, row in contexts.items():
        f = row["fields"]
        admission[name] = learning_admission(
            {
                "protocol_locator": f["construct"]["chain"],
                "target_construct": f["construct"]["value"],
                "substrate": f["substrate"]["value"],
                "duration": f["incubation duration"]["value"],
            }
        )
    return {
        "source_context_admission": admission,
        "datasets": admitted,
        "policy_fingerprint": policy_fingerprint(),
        "model_built": False,
        "excluded_ids": [
            r["parent_measurement_id"] for r in rows if not r["fit_admission"]
        ],
        "replicate_policy": (
            "require explicit N>=2, consistent primary summaries "
            "and no mixed exact/censored occasions"
        ),
        "temporal_split": (
            "NOT_ESTABLISHED: publication date is not measurement "
            "date; primary iteration labels incomplete"
        ),
        "leakage": "scaffold-aware split required; no train/test performance claimed",
        "applicability_domain": (
            "restricted to this chemical series and endpoint; no "
            "axSpA or cross-programme prediction"
        ),
        "identity": (
            "source CXSMILES/stereo retained; tested salt/form not "
            "confirmed; no tautomer/salt merging"
        ),
        "historical_model_status": "MODEL NOT BUILT; immutable",
        "Tinworth_separate_policy_rerun": [
            {
                "dataset_id": d["dataset"]["id"],
                "assessment": assess(d["dataset"]),
                "context": "methods-v2 explicit inheritance; retained distinct schemes",
                "admission": "SAR_ONLY; duplicate structure/small-size failures remain",
            }
            for d in read(BASE / "chemical-datasets.json")["learning"]
            if FINAL in d["dataset"]["id"]
        ],
        "new_status": "MODEL_ELIGIBLE_WITH_CONDITIONS"
        if all(d["assessment"]["conclusion"] != "not_eligible" for d in admitted)
        else "SAR_ONLY",
    }


def comparisons() -> dict[str, Any]:
    return {
        "review_state": "pending_review",
        "existing_rules_changed": False,
        "comparisons": [
            {
                "families": "BRADSHAW internal biochemical",
                "status": "COMPARABLE",
                "inference": (
                    "within-source Hap2/YTAFTIPSI SAR, not transferable "
                    "absolute potency"
                ),
                "condition": (
                    "preserve exclusions/replicate uncertainty and tested-form limits"
                ),
            },
            {
                "families": "BRADSHAW biochemical vs cellular",
                "status": "NOT_COMPARABLE",
                "inference": (
                    "paired descriptive endpoints only; never pool; "
                    "functional phenotype not occupancy"
                ),
            },
            {
                "families": "BRADSHAW vs Tinworth biochemical",
                "status": "PARTIALLY_COMPARABLE",
                "inference": (
                    "explicit common Liddle inheritance establishes method "
                    "family, not numeric interchangeability"
                ),
                "condition": (
                    "temperature/preincubation/dose range/form unknown; "
                    "distinct compounds/publications; no selectivity ratio"
                ),
            },
            {
                "families": "BRADSHAW vs historical Maben",
                "status": "NOT_COMPARABLE",
                "inference": (
                    "different source assay/substrate/preparation; no "
                    "pooling or engagement transfer"
                ),
            },
            {
                "families": "BRADSHAW allotype/substrate panel",
                "status": "NOT_COMPARABLE",
                "inference": (
                    "context-specific characterization, not one pooled "
                    "training endpoint"
                ),
            },
        ],
        "numeric_selectivity_rule": (
            "axis.pharmacology.selectivity.compare; unchanged; "
            "parent selectivity replay retains null ratios/bounds"
        ),
        "qualitative_categories": (
            "curated inference, not falsely presented as a generic "
            "numeric comparability engine"
        ),
    }


def scoped_experiment(
    records: dict[str, Any],
    key: str,
    source: str,
    text: str,
    *,
    compound: str | None = None,
    modality: str = "small_molecule",
    cell: str | None = None,
    mhc: str | None = None,
    hla: str | None = None,
    edge: str = "hla",
    duration: str | None = None,
    controls: tuple[str, ...] = (),
    locator: str,
    claim_id: str | None = None,
) -> None:
    identifier = "brad-v3:" + key
    exp = CellularExperiment(
        identifier,
        key,
        "source-perturbation:" + key,
        BiologicalContext(cell_line=cell, hla_allele=hla, mhc_allele=mhc),
        source,
        locator,
        controls,
        compound_id=compound,
        reported_perturbagen=key,
        modality=modality,
        duration=duration,
        limitation=(
            "Source-context curation pending expert review; no "
            "occupancy, matched chemical-genetic dependency or "
            "axSpA efficacy inferred"
        ),
    )
    ro = ExperimentalReadout(
        identifier + ":readout",
        identifier,
        text,
        text,
        "changed",
        "HLA_molecular" if edge == "hla" else "disease_phenotype",
        locator,
        claim_id=claim_id or "brad-v3:claim:" + key,
    )
    a = CellularAssessment(
        identifier + ":" + edge,
        identifier,
        edge,
        "supported",
        (
            "Source-reported endpoint only; scoped "
            "perturbation/context, not clinical benefit"
        ),
        supporting_readout_ids=(ro.id,),
    )
    records["experiments"].append(asdict(exp))
    records["readouts"].append(asdict(ro))
    records["assessments"].append(asdict(a))


def prepare_records(
    store: EvidenceStore, protein: str, seed: dict[str, Any]
) -> dict[str, Any]:
    records = load_records(store, PROJECT, protein)
    old_structure_ids = read(BASE / "decision-inputs.json")["structural_only"][
        "evidence"
    ]["structure_ids"]
    records["structure_ids"] = old_structure_ids
    chemical = read(BASE / "chemical-datasets.json")
    records["compounds"] = sorted(
        set(records["compounds"]) | {c["id"] for c in chemical["compounds"]}
    )
    for m in chemical["measurements"]:
        if not m["id"].endswith(":ERAP1 pIC50"):
            continue
        records["biochemical_measurements"].append(
            {
                "id": "measurement:" + m["id"],
                "compound_id": m["compound_id"],
                "value": m["derived_value"],
                "endpoint": "IC50",
                "operator": m["derived_operator"],
                "source": m["source"],
                "locator": m["locator"],
                "context": "Hap2/YTAFTIPSI",
                "direct_cellular_engagement": False,
                "review_state": "pending_review",
            }
        )
    for c in (21, 40):
        scoped_experiment(
            records,
            "bradshaw-" + str(c),
            BRAD,
            "SIINFEKL antigen presentation inhibited in HeLa; pIC50 "
            + str(7.5 if c == 21 else 7.3),
            compound=BRAD + ":compound:" + str(c),
            cell="HeLa",
            mhc="H-2Kb/beta2m",
            duration="40 h",
            controls=("DMSO", "50uM FAC control inhibitor", "GFP", "Zombie Violet"),
            locator="main p16 Table8,p17; SI S60; CSV compound:" + str(c),
        )
    for control, value in (("KK", 7.25), ("compound6", 7.05)):
        scoped_experiment(
            records,
            "tinworth-21-" + control,
            FINAL,
            "HeLa antigen presentation inhibition pIC50 "
            + str(value)
            + "; normalization "
            + control,
            compound=FINAL + ":compound:21",
            cell="HeLa",
            mhc="H-2Kb/beta2m",
            duration="40 h",
            controls=(control, "GFP", "Zombie Violet"),
            locator="final SI S5; preprint p15 Methods; assay-methods-v2",
        )
    scoped_experiment(
        records,
        "tinworth-CT26",
        FINAL,
        (
            "Compound21 modifies CT26 MHC-I peptide repertoire; "
            "three biological replicates, LFQ; not compound-in-KO "
            "rescue"
        ),
        compound=FINAL + ":compound:21",
        cell="CT26",
        mhc="H-2Kd/H-2Dd",
        duration="30 days",
        controls=("vehicle WT", "ERAP1 KO separate comparator"),
        locator="preprint p15,p16; final SI; methods-v2 CT26 row",
    )
    scoped_experiment(
        records,
        "tinworth-CIA",
        FINAL,
        "Source reports mouse CIA pathology/immune PD; not axSpA clinical efficacy",
        compound=FINAL + ":compound:21",
        edge="disease",
        duration="D18-D36",
        controls=("vehicle", "Enbrel"),
        locator="final SI; preprint pp12-14,17",
    )
    # Frozen integrated claims remain auditable; never auto-promoted to engagement.
    claims = read(PARENT / "integrated-claims.json")["claims"]
    for key in (
        "temponeras-mode",
        "2025-b3p-design",
        "allotype2025-design",
        "tran-arthritis",
        "hry-presentation",
    ):
        claim = next(
            c for c in claims if c["domain_claim"]["identifier"].endswith(":" + key)
        )
        scoped_experiment(
            records,
            key,
            claim["domain_claim"]["provenance"]["source_identifier"],
            claim["domain_claim"]["predicate"],
            modality="variant_expression"
            if key == "allotype2025-design"
            else "knockout"
            if key == "tran-arthritis"
            else "small_molecule",
            cell="A375"
            if key in {"temponeras-mode", "2025-b3p-design", "allotype2025-design"}
            else "HeLa"
            if key == "hry-presentation"
            else None,
            hla="HLA-B27" if key == "tran-arthritis" else None,
            edge="disease" if key == "tran-arthritis" else "hla",
            locator=claim["source_locator"],
            claim_id=claim["domain_claim"]["identifier"],
        )
    for target in ("ERAP2", "LNPEP"):
        records["selectivity"].append(
            {
                "id": "methods:tin21:" + target,
                "comparability_status": "Not directly comparable",
            }
        )
    records["source_context_registry"] = {
        "main": seed["main_source"],
        "matrix_sha256": digest(json.dumps(matrix(), sort_keys=True).encode()),
        "numerical_sha256": digest(
            json.dumps(numerical(seed), sort_keys=True).encode()
        ),
        "allotypes": allotypes(),
        "integrated_claim_ids": [c["domain_claim"]["identifier"] for c in claims],
        "non_engine_context": (
            "allotype substrate results, population associations, "
            "PD/PK, source caveats retained; no new rule interprets "
            "these as direct engagement"
        ),
        "excluded_engagement_upgrade": [
            "FOCIS abstract",
            "sponsor healthy-volunteer statement",
            "mouse PK-estimated TE",
        ],
    }
    return records


class WindowDecisionService(DecisionService):
    """Use the existing explicit-record window API, not a new decision rule."""

    window: dict[str, Any] | None = None

    def inputs(
        self,
        project: str,
        protein: str,
        mode: str = "exploratory",
        overrides: dict[str, str] | None = None,
        records: dict[str, Any] | None = None,
    ) -> engine.Inputs:
        return super().inputs(project, protein, mode, overrides, records or self.window)


def reassessment(seed: dict[str, Any]) -> dict[str, Any]:
    if not stage_a(matrix())["stage_b_permitted"]:
        raise ValueError("Stage A does not permit a DecisionState")
    canonical = read(SNAPSHOT)["decision"]
    baseline = read(BASE / "before.json")
    if digest(SNAPSHOT.read_bytes()) != baseline["canonical_snapshot_sha256"]:
        raise ValueError("canonical historical state changed")
    with (
        tempfile.TemporaryDirectory(prefix="axis-bradshaw-v3-") as temp,
        EvidenceStore(Path(temp) / "audit.duckdb") as store,
    ):
        import_curated_erap1(store)
        protein = TargetIdentityService(store).import_package(PROJECT)
        StructureIdentityService(store).import_package(PROJECT, protein)
        PharmacologyService(store).import_package(PROJECT, protein)
        CellularPharmacologyService(store).import_package(PROJECT, protein)
        service = WindowDecisionService(store)
        service.import_package(PROJECT, protein)
        # Seed the actual immutable canonical payload, never synthesize a BEFORE.
        state = DecisionState(
            canonical["id"],
            PROJECT,
            protein,
            canonical["version"],
            canonical["hypothesis_id"],
            canonical["hypothesis_revision"],
            datetime.fromisoformat(canonical["created_at"]),
            canonical["created_by"],
            canonical["evidence_digest"],
            canonical["rules_version"],
            canonical["rationale"],
            canonical["critical_uncertainty_id"],
            canonical["recommended_experiment_id"],
            canonical["supersedes_id"],
        )
        store.decisions.add_state(state, canonical)
        original_inputs = service.inputs(PROJECT, protein)
        original = engine.analyze(original_inputs)
        for key in ("critical_uncertainty_id", "recommended_experiment_id"):
            if original[key] != canonical[key]:
                raise ValueError("canonical framing cannot be reproduced")
        if rules.fingerprint() != baseline["rules_fingerprint"]:
            raise ValueError("decision rules changed")
        service.window = prepare_records(store, protein, seed)
        inputs = service.inputs(PROJECT, protein)
        claims = claim_delta(service.window, seed)
        roundtrip(claims)
        after = service.build(
            PROJECT,
            protein,
            created_at=NOW,
            trigger=(
                "BRADSHAW main article explicit assay-chain "
                "adjudication; cutoff2026-10-05"
            ),
        )
        if after["version"] != 2 or after["supersedes_id"] != canonical["id"]:
            raise ValueError("invalid historical causal linkage")
        # Source-context metadata is not silently treated as rule-consumed evidence.
        return {
            "before": canonical,
            "after": after,
            "inputs": inputs,
            "records": service.window,
            "claim_delta": claims,
            "review_mode": "exploratory",
            "context_registry_in_engine_digest": False,
            "source_package_link": (
                "manifest.json binds all sources, normalized records and state"
            ),
            "classification": "DECISION STABLE"
            if all(
                after[k] == canonical[k]
                for k in ("critical_uncertainty_id", "recommended_experiment_id")
            )
            else "DECISION CHANGED",
            "rules_fingerprint": rules.fingerprint(),
            "rules_changed": False,
            "historical_Maben_engagement": (
                "UNRESOLVED; no compound-specific cellular occupancy added"
            ),
            "question_advancement": "QUESTION_PARTIALLY_ADVANCED",
            "corrector_hypothesis": "PLAUSIBLE_BUT_INSUFFICIENT",
        }


def claim_delta(records: dict[str, Any], seed: dict[str, Any]) -> list[dict[str, Any]]:
    experiments = {e["id"]: e for e in records["experiments"]}
    main = seed["main_source"]
    main_artifact = {
        "retrieved_at": CUTOFF + "T00:00:00+00:00",
        "url": "https://doi.org/" + BRAD,
        "sha256": main["sha256"],
        "cache_path": main["local_path"],
    }
    preprint = next(
        s
        for s in read(METHODS / "source-artifacts.json")
        if s["artifact"] == "targeted/tin-preprint.pdf"
    )
    tin_artifact = preprint | {"cache_path": preprint["artifact"]}
    out = []
    for ro in records["readouts"]:
        if not (ro.get("claim_id") or "").startswith("brad-v3:claim:"):
            continue
        exp = experiments[ro["experiment_id"]]
        tin = exp["source_id"] == FINAL
        spec = {
            "id": ro["claim_id"],
            "source": exp["source_id"],
            "text": ro["qualitative_result"],
            "kind": "source_assertion",
            "context": {
                "cell_type": exp["context"]["cell_line"],
                "assay": "antigen presentation"
                if "HeLa" in (exp["context"]["cell_line"] or "")
                else "source-specific mouse model",
                "endpoint": ro["endpoint"],
            },
            "source_class": "preprint_methods_with_final_SI_concordance"
            if tin
            else "peer_reviewed_primary_research",
            "locator": ro["locator"],
            "polarity": "supports",
            "scope": (
                "compound/context specific endpoint; not direct cellular occupancy"
            ),
            "limitations": [exp["limitation"], "pending independent scientific review"],
        }
        claim = envelope(spec, tin_artifact if tin else main_artifact)
        claim["decision_input_admission"] = (
            "Exploratory source-scoped readout; not auto-approved"
        )
        if tin:
            claim["source_version_chain"] = [
                preprint["publication_version"],
                FINAL + ":SI; same publication programme not replication",
            ]
        else:
            claim["retrieval_timestamp_precision"] = (
                "date-only footer; midnight is serialization "
                "convention, not recorded access time"
            )
        out.append(claim)
    return out


def causal(result: dict[str, Any], learn: dict[str, Any]) -> dict[str, Any]:
    before, after = result["before"], result["after"]
    items = {}
    for label, key in (
        ("Critical uncertainty", "critical_uncertainty_id"),
        ("Next experiment", "recommended_experiment_id"),
    ):
        items[label] = {
            "status": "STABLE" if before[key] == after[key] else "CHANGED",
            "before": before[key],
            "after": after[key],
            "cause": (
                "new Hap2 biochemical and reporter/peptide evidence -> "
                "pharmacology/phenotype claims, not direct occupancy -> "
                "DECISION-GAP-001/002, DECISION-CRIT-001 -> actual "
                "engine output"
            ),
            "stable_reason": (
                "programme tractability cannot resolve historical Maben "
                "compound-specific engagement"
            ),
        }
    for name, status, explanation in (
        (
            "Therapeutic strategy",
            "STABLE",
            (
                "Strategy identifiers unchanged; tractability is not "
                "evidence of axSpA clinical benefit"
            ),
        ),
        (
            "Structural tractability",
            "CHANGED",
            (
                "12 source-mapped structures added since canonical "
                "BEFORE -> regulatory-site structure claims -> "
                "DECISION-STRUCT-001 -> design context only, not "
                "engagement"
            ),
        ),
        (
            "Chemical tractability",
            "CHANGED",
            (
                "BRADSHAW/Tinworth source-normalized Hap2 measurements "
                "-> biochemical edge supported -> DECISION-GAP-001; "
                "expands chemical coverage, not disease efficacy"
            ),
        ),
        (
            "Cellular pharmacology",
            "CHANGED",
            (
                "HeLa/CT26 source readouts -> hla edge/phenotype "
                "references -> DECISION-GAP-001/DEP-001; does not "
                "become direct engagement"
            ),
        ),
        (
            "Historical Maben engagement",
            "STABLE",
            "No Maben compound occupancy measurement; later compounds cannot supply it",
        ),
        (
            "Chemical Learning status",
            "CHANGED",
            (
                "main ref22 -> admissible single-context conservative "
                "subsets -> existing learning_admission/eligibility "
                "policy -> "
            )
            + learn["new_status"]
            + "; no model trained",
        ),
    ):
        items[name] = {
            "status": status,
            "cause": explanation,
            "classification_scope": (
                "evidence coverage/admission change, not a new decision "
                "rule or clinical recommendation"
            ),
        }
    return {
        "from": before["id"],
        "to": after["id"],
        "classification": result["classification"],
        "items": items,
        "engine_diff": after["diff"],
        "review_state": "pending_review",
        "no_opaque_score": True,
    }


def acceptance() -> dict[str, str]:
    return {
        name: "PASS WITH CONDITIONS"
        if name
        in {
            "BRADSHAW assay completeness",
            "Cross-programme comparability",
            "Numerical integrity",
            "Chemical identity",
            "Chemical Learning eligibility",
            "External-review readiness",
        }
        else "PASS"
        for name in (
            "Source authenticity",
            "Provenance integrity",
            "BRADSHAW assay identity",
            "BRADSHAW assay completeness",
            "BRADSHAW internal comparability",
            "Cross-programme comparability",
            "Numerical integrity",
            "Chemical identity",
            "Allotype/substrate context",
            "Cellular endpoint integrity",
            "Chemical Learning eligibility",
            "Epistemic integrity",
            "Decision causality",
            "Offline reproducibility",
            "External-review readiness",
        )
    }


def build(seed: dict[str, Any]) -> dict[str, Any]:
    if not seed["main_source"]["eligible"] or not eligible_date(
        seed["main_source"]["publication_date"]
    ):
        raise ValueError("ineligible source")
    rows = matrix()
    learn = learning(seed)
    decision = reassessment(seed)
    return {
        "source-provenance.json": seed,
        "assay-method-matrix.json": rows,
        "stage-a.json": stage_a(rows),
        "numerical-reconciliation.json": numerical(seed),
        "allotype-substrate-context.json": allotypes(),
        "assay-comparability.json": comparisons(),
        "learning-eligibility.json": learn,
        "decision-reassessment.json": decision,
        "decision-state-v2.json": decision["after"],
        "integrated-claim-delta.json": decision["claim_delta"],
        "causal-decision-diff.json": causal(decision, learn),
        "localized-uncertainty.json": {
            "old_blocker": "RESOLVED: main explicit potency-method chain",
            "remaining": [
                {
                    "fields": [
                        "temperature",
                        "preincubation",
                        "concentration range",
                        "tested salt/form",
                    ],
                    "affected_inference": (
                        "cross-programme quantitative interchangeability; exact "
                        "replication of experiments"
                    ),
                    "blocks_current_decision": False,
                    "reason": (
                        "not required to establish source internal "
                        "Hap2/YTAFTIPSI activity; no ratio/pooled potency "
                        "admitted"
                    ),
                },
                {
                    "fields": [
                        "HeLa ERAP1 allotype",
                        "ERAP2",
                        "endogenous HLA",
                        "control inhibitor identity",
                    ],
                    "affected_inference": (
                        "human allotype/HLA-B27 translation; matching control chemistry"
                    ),
                    "blocks_current_decision": False,
                    "reason": (
                        "current question remains compound-specific engagement; "
                        "no HLA-B27 efficacy or control-identity transfer "
                        "asserted"
                    ),
                },
                {
                    "fields": [
                        "main/SI discrepancy compound28",
                        "additional censored occasions21/28/33/44",
                        "missingN",
                        "singleton22/28",
                    ],
                    "affected_inference": (
                        "exact predictive fitting and replicate distribution"
                    ),
                    "blocks_current_decision": False,
                    "reason": (
                        "excluded from fitting subset; qualitative tool "
                        "compound40 evidence remains supported"
                    ),
                },
            ],
        },
        "acceptance-matrix.json": acceptance(),
    }


def verify(root: Path = OUTPUT) -> dict[str, Any]:
    manifest = read(root / "manifest.json")
    if (
        digest((root / "manifest.json").read_bytes())
        != (root / "manifest.sha256").read_text().strip()
    ):
        raise ValueError("manifest checksum mismatch")
    if manifest["algorithm"] != ALGORITHM or manifest["cutoff"] != CUTOFF:
        raise ValueError("algorithm/cutoff mismatch")
    if manifest["code_sha256"] != digest(Path(__file__).read_bytes()):
        raise ValueError("replay code changed")
    names = {p.name for p in root.glob("*.json") if p.name != "manifest.json"}
    if names != set(manifest["files"]):
        raise ValueError("unmanifested/missing file")
    for name, sha in manifest["files"].items():
        if Path(name).name != name or digest((root / name).read_bytes()) != sha:
            raise ValueError("file checksum mismatch")
    for name, folder in PARENTS.items():
        if hashes(folder) != manifest["parents"][name]:
            raise ValueError("historical package changed")
    if rules.fingerprint() != manifest["rules_fingerprint"]:
        raise ValueError("decision rules changed")
    return manifest


def replay(root: Path = OUTPUT) -> dict[str, Any]:
    verify(root)
    parent_replay()
    actual = build(read(root / "source-provenance.json"))
    for name, value in actual.items():
        if json.loads(json.dumps(value, default=str)) != read(root / name):
            raise ValueError("semantic replay differs: " + name)
    return {
        "status": "OFFLINE BRADSHAW REASSESSMENT REPLAY PASSED",
        "stage_a": actual["stage-a.json"]["stage"],
        "decision": actual["decision-reassessment.json"]["classification"],
        "decision_state": actual["decision-state-v2.json"]["id"],
        "historical_packages_unchanged": True,
    }


def freeze(seed: dict[str, Any]) -> None:
    if OUTPUT.exists():
        raise ValueError("new package already exists; use replay")
    parent_replay()
    payloads = build(seed)
    OUTPUT.mkdir()
    for name, value in payloads.items():
        write(OUTPUT / name, value)
    manifest = {
        "algorithm": ALGORITHM,
        "cutoff": CUTOFF,
        "starting_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "code_sha256": digest(Path(__file__).read_bytes()),
        "rules_fingerprint": rules.fingerprint(),
        "parents": {name: hashes(folder) for name, folder in PARENTS.items()},
        "files": {name: digest((OUTPUT / name).read_bytes()) for name in payloads},
        "review_state": "pending_review",
        "raw_sources_redistributed": False,
        "canonical_snapshot_sha256": digest(SNAPSHOT.read_bytes()),
        "execution_timestamp": NOW.isoformat(),
        "timestamp_policy": (
            "deterministic cutoff snapshot, not claimed wall-clock time"
        ),
        "boundary": (
            "Source context delta + exploratory existing-engine "
            "DecisionState v2; no human approval or model training"
        ),
    }
    write(OUTPUT / "manifest.json", manifest)
    (OUTPUT / "manifest.sha256").write_text(
        digest((OUTPUT / "manifest.json").read_bytes()) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--pdf-python")
    parser.add_argument("--main", type=Path)
    parser.add_argument("--si", type=Path)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    if args.replay:
        print(json.dumps(replay(), indent=2))
    elif all((args.pdf_python, args.main, args.si, args.csv)):
        freeze(ingest(args.pdf_python, args.main, args.si, args.csv))
        print(json.dumps(replay(), indent=2))
    else:
        parser.error("choose --replay or provide --pdf-python --main --si --csv")
