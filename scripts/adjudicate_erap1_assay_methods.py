"""Freeze/replay a bounded assay-method delta; never replace historical artifacts.

No acquisition, model training, rule changes or DecisionState creation. Sources
are checked in an external cache on first freeze; replay needs only the repo.
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from axis.domain.pharmacology import Assay, BioactivityMeasurement
from axis.evidence_integration import CUTOFF, digest, eligible_date, verify_package
from axis.pharmacology.selectivity import compare
from scripts.close_erap1_data_rich import BASE, read, replay_closure, write
from scripts.close_erap1_data_rich import OUTPUT as PARENT

OUTPUT = BASE.parent / "assay-methods-v2"
ALGORITHM = "erap1-targeted-assay-methods-2"
TIN = "10.1101/2025.11.17.686761:v1"
FINAL = "10.1021/acs.jmedchem.6c00029"
BRAD = "10.1021/acs.jmedchem.5c03071"
LIDDLE = "10.1021/acs.jmedchem.9b02123"
HRY = "10.1021/acsmedchemlett.4c00401"
COLS = (
    "target",
    "species",
    "construct",
    "allotype",
    "substrate",
    "enzyme concentration",
    "substrate concentration",
    "buffer",
    "pH",
    "cofactors",
    "temperature",
    "preincubation",
    "incubation duration",
    "readout",
    "endpoint",
    "concentration range",
    "replicates",
    "error metric",
    "fitting",
)
CRITICAL = ("target", "construct", "substrate", "incubation duration", "readout")
VERIFIED = {"VERIFIED", "INHERITED_VERIFIED", "MODIFIED_VERIFIED"}
SOURCES = {
    "targeted/tin-api.json": ("2025-11-17", "official metadata", "bioRxiv API"),
    "targeted/tin-preprint.pdf": ("2025-11-17", "preprint", TIN),
    "targeted/tin-jats.xml": ("2025-11-17", "preprint", TIN),
    "targeted/tin-preprint-si.pdf": ("2025-11-17", "preprint SI", TIN),
    "targeted/liddle-main.pdf": ("2020-02-28", "author-hosted manuscript", LIDDLE),
    "targeted/giastas2019.xml": (
        "2019-02-13",
        "PMC full text",
        "10.1021/acsmedchemlett.9b00002",
    ),
    "targeted/ml9b00002_si_001.pdf": (
        "2019-02-13",
        "official SI",
        "10.1021/acsmedchemlett.9b00002",
    ),
    "targeted/brad-openalex.json": ("2026-04-13", "metadata only", BRAD),
}


def field(
    value: str | None = None,
    *,
    source: str = TIN,
    locator: str = "p15 Methods",
    state: str | None = None,
    chain: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "state": state or ("VERIFIED" if value else "NOT_CONFIRMED"),
        "source_version": source,
        "source_locator": locator,
        "accessibility": "LEGITIMATELY_ACCESSIBLE",
        "chain": chain or [source],
    }


def inherited(value: str, locator: str = "Liddle PDF p8 (H)") -> dict[str, Any]:
    return field(
        value,
        source=LIDDLE,
        locator=locator,
        state="INHERITED_VERIFIED",
        chain=[TIN + ":p15:ref31", LIDDLE],
    )


def matrix() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(
        identifier: str,
        values: dict[str, Any],
        *,
        material: bool = False,
        version: str = TIN,
        scope: str = "preprint only",
    ) -> dict[str, Any]:
        row = {
            "id": identifier,
            "source_version": version,
            "decision_material_potency": material,
            "version_scope": scope,
            "final_context_adjudicated": version == TIN,
            "review_state": "pending_review",
            "fields": {k: field(source=version) for k in COLS},
            "direct_cellular_engagement": False,
            "completeness": "PARTIALLY_ADJUDICATED",
        }
        row["fields"].update(values)
        rows.append(row)
        return row

    for kind in ("enzyme", "cell"):
        b = add(
            "bradshaw-2026-" + kind,
            {},
            material=True,
            version=BRAD,
            scope="final SI; main methods inaccessible",
        )
        b["completeness"] = "INSUFFICIENT_METHOD_INFORMATION"
        for k, v in {
            "target": "ERAP1",
            "endpoint": "ERAP1 pIC50"
            if kind == "enzyme"
            else "HeLa antigen presentation pIC50",
            "replicates": "per-compound N in mean, S60 Table S2; not all CSV rows",
            "error metric": "per-compound SD where reported, S60 Table S2",
        }.items():
            b["fields"][k] = field(v, source=BRAD, locator="SI S60 Table S2")
        for k in COLS:
            if b["fields"][k]["value"] is None:
                b["fields"][k].update(
                    accessibility="SI inspected; main methods inaccessible",
                    source_locator="SI S1-S75; no explicit potency-method chain",
                )
        b["excluded_inheritance"] = {
            "S3/ref1": "Hryczanek synthesis only; NOT an assay citation",
            "S56/ref9": "Giastas crystallography only; NOT a potency construct",
        }

    enzyme = {
        "target": field("human ERAP1", locator="p8 Table6; p15 Methods"),
        "species": field("human", locator="p8 Table6"),
        "construct": inherited("full-length ERAP1; C-terminal 6His retained"),
        "allotype": inherited("common haplotype 2"),
        "substrate": inherited("YTAFTIPSI -> TAFTIPSI"),
        "enzyme concentration": inherited("1 nM"),
        "substrate concentration": inherited("5 uM"),
        "buffer": inherited("50 mM HEPES; 100 mM NaCl; 0.002% Tween20; 0.005% BSA"),
        "pH": inherited("7.0"),
        "incubation duration": inherited("60 min"),
        "readout": inherited(
            "RapidFire C18; Sciex4000 Q-trap; product/internal standard"
        ),
        "endpoint": field("pIC50; 4-parameter inhibition concentration response"),
        "replicates": field(
            "n>=3 unless specified; final SI per-row N takes precedence"
        ),
        "error metric": field(
            "final SI S5 Table1 SD where given",
            source=FINAL,
            locator="S5 Supplementary Table1",
        ),
        "fitting": inherited("four-parameter dose response; slope and asymptotes"),
    }
    e = add("tinworth-human-enzyme", enzyme, material=True)
    e["preparation"] = {
        "expression": "Hi5/baculovirus inherited via Liddle p9 -> Giastas SI pp1-2",
        "purification": "Ni-NTA/SEC; Liddle retains 6His, unlike Giastas TEV removal",
        "residue_range": "full-length; not the deleted crystal construct",
        "mutations": "Hap2; mechanism mutants not default potency construct",
        "chain": [
            TIN + ":p15:ref31",
            LIDDLE + ":pp8-9:ref34",
            "10.1021/acsmedchemlett.9b00002:SI:pp1-2",
        ],
        "state": "INHERITED_VERIFIED",
    }
    for scheme in ("KK", "compound6"):
        cell = {
            "target": field("endogenous HeLa ERAP1"),
            "species": field("human HeLa; mouse H-2Kb/beta2m reporter"),
            "construct": inherited(
                "endogenous HeLa ERAP1; BacMam reporter, not purified enzyme"
            ),
            "substrate": inherited(
                "ER-targeted LEQLESIINFEKL precursor; SIINFEKL presentation"
            ),
            "incubation duration": inherited("40 h"),
            "readout": inherited(
                "25.D1.16 APC flow cytometry; GFP transduction; Zombie Violet"
            ),
            "endpoint": field("antigen-presentation pIC50; NOT occupancy"),
            "replicates": field(
                "n>=3 unless specified; final SI N in mean/total separate"
            ),
            "error metric": field(
                "final SI per-row SD where reported",
                source=FINAL,
                locator="S5 Supplementary Table1",
            ),
            "fitting": inherited(
                "four-parameter variable-slope concentration response"
            ),
        }
        c = add("tinworth-cell-" + scheme, cell, material=True)
        c["cell_context"] = {
            "ERAP1_allotype": "NOT_CONFIRMED",
            "endogenous_HLA": "NOT_CONFIRMED",
            "ERAP2": "NOT_CONFIRMED",
            "genotype": "NOT_CONFIRMED",
            "viability": "Zombie Violet; 95% threshold establishes 0.5% DMSO tolerance",
            "limit": "not proof of viability at every compound/exposure",
            "control": "KKSIINFEKL BacMam"
            if scheme == "KK"
            else "50 uM FAC pharmacological inhibitor; final SI identifies compound6",
            "control_chain": [TIN + ":p15:ref31"]
            if scheme == "KK"
            else [TIN + ":p15:ref38", HRY + ":SI:S34", FINAL + ":SI:S5"],
            "control_state": "INHERITED_VERIFIED"
            if scheme == "KK"
            else "MODIFIED_VERIFIED",
            "flow_instrument": "Cyan for Liddle; iQue for Hry modified method",
            "compound21_pIC50": 7.25 if scheme == "KK" else 7.05,
            "unbound_pIC50": None if scheme == "KK" else 7.26,
        }

    for substrate in ("YTAFTIPSI", "EAAGIGILTV"):
        m = add(
            "tinworth-mouse-" + substrate,
            {
                "target": field("mouse ERAAP", locator="p10 Table7"),
                "species": field("mouse", locator="p10 Table7"),
                "substrate": field(substrate, locator="p10 Table7"),
                "endpoint": field("pIC50 and maximum asymptote", locator="p10 Table7"),
                "incubation duration": inherited(
                    "60 min; source states identical method"
                ),
                "readout": inherited("RapidFire peptide-cleavage MS"),
            },
        )
        m["limits"] = [
            "p15 says YFATIPSI (8 letters), Table7 says YTAFTIPSI; retain conflict",
            "mouse construct/concentrations not copied from human assay",
        ]
        if substrate == "YTAFTIPSI":
            m["fields"]["substrate"]["state"] = "CONFLICTING"

    for target, substrate in (("ERAP2", "Arg-AMC"), ("LNPEP", "Leu-AMC")):
        add(
            "tinworth-counter-" + target,
            {
                "target": field(target, locator="p8 Table6; p15 Methods"),
                "substrate": inherited(substrate, "Liddle p3 Figure1 legend"),
                "readout": inherited("fluorogenic hydrolysis", "Liddle p3 Figure1"),
                "endpoint": field("biochemical pIC50", locator="p8 Table6"),
            },
        )
    add(
        "tinworth-other-counterscreens",
        {
            "target": field("heterogeneous liability panel", locator="preprint SI p7"),
            "endpoint": field(
                "pIC50/pEC50/pXC50, target-specific", locator="preprint SI p7"
            ),
            "readout": field(
                "various formats; no unified protocol", locator="preprint SI p7"
            ),
        },
    )
    im = add(
        "tinworth-CT26-immunopeptidome",
        {
            "target": field("mouse ERAAP / MHC-I peptidome", locator="pp10,16"),
            "species": field("Mus musculus CT26", locator="pp10,16"),
            "construct": field(
                "WT / ERAAP KO; exact KO preparation not confirmed", locator="pp10,16"
            ),
            "concentration range": field(
                "compound21 1 uM total; estimated 0.61 uM unbound", locator="p10"
            ),
            "incubation duration": field("30 days", locator="p10"),
            "readout": field(
                "H2-Kd/Dd IP; Exploris480; FragPipe22; IonQuant LFQ", locator="p16"
            ),
            "replicates": field(
                "3 biological replicates per WT/KO/inhibitor condition", locator="p16"
            ),
            "fitting": field(
                "VSN; LIMMA; BH-adjusted p<0.05 and fold change>=1.5", locator="p16"
            ),
            "endpoint": field(
                "relative peptide abundance; NOT occupancy", locator="p16"
            ),
        },
    )
    im["MS_details"] = {
        "IP": "2mg antibody/400uL beads;4C;150/400mM NaCl,Tris pH8;0.1M acetic acid",
        "LC": "50cm x100um C18,55C; 120min 2-40% ACN; 0.1% FA,3.5% DMSO",
        "search": "SwissProt mouse 2018-01-11; nonspecific 7-25aa; +/-20ppm",
        "FDR": "ion-level 1%; no invented PSM/peptide FDR from default workflow",
        "filter": "only peptides quantified across all conditions",
        "KO_dependency": "KO phenocopy not compound-in-KO rescue or direct occupancy",
    }
    cia = add(
        "tinworth-CIA",
        {
            "target": field(
                "inflammatory autoimmune mouse model; not axSpA", locator="p17"
            ),
            "species": field("70 male DBA/1OlaHsd mice,6-7 weeks", locator="p17"),
            "concentration range": field(
                "GSK235 30/90/270mg/kg oral BID; Enbrel10mg/kg IP alternate days",
                locator="p17",
            ),
            "incubation duration": field(
                "D18-D36; collagen0.2mg D0 and D21 in100uL FCA", locator="p17"
            ),
            "readout": field(
                "blinded daily paw scores; histology; IgG; IL12p40/IL6; MHC flow",
                locator="p17",
            ),
            "endpoint": field(
                "CIA pathology/immune PD; not axSpA efficacy", locator="pp12-14,17"
            ),
            "fitting": field(
                "one-way ANOVA treatment fixed effect; contrasts; BH correction",
                locator="preprint SI p6",
            ),
        },
    )
    cia["limits"] = [
        "group sizes/allocation/randomization not resolved from methods",
        "PK Results p9 D18/26/35 conflicts with Methods p17 D18/19/27/35/36",
        "TE estimated from unbound PK and enzyme inhibition, not occupancy",
    ]
    add(
        "tinworth-CT26-tumour",
        {
            "species": field("female BALB/c 6-8 weeks", locator="p17"),
            "concentration range": field(
                "GSK235 30/90/270mg/kg oral BID", locator="pp12,17"
            ),
            "incubation duration": field(
                "day1 inoculation/treatment to day17", locator="pp12,17"
            ),
            "readout": field(
                "tumour volume/body weight; prophylactic design", locator="p12"
            ),
            "replicates": field(None, locator="p17; no resolved per-group n"),
        },
    )
    add(
        "tinworth-oral-PK",
        {
            "species": field("female BALB/c", locator="pp8,16-17"),
            "concentration range": field(
                "compounds19/21 10mg/kg oral in1% methylcellulose", locator="pp8,16-17"
            ),
            "incubation duration": field("sampling up to24h", locator="pp16-17"),
            "readout": field(
                "whole-blood LCMSMS; WinNonlin noncompartmental", locator="p17"
            ),
            "replicates": field("n=3", locator="p8 Table5"),
        },
    )
    add(
        "tinworth-hepatocytes",
        {
            "species": field(
                "human; compounds19/21", locator="preprint SI pp4,6; final SI S5"
            ),
            "buffer": field("Williams Medium E", locator="preprint SI p6"),
            "temperature": field("37C,5% CO2,200rpm", locator="preprint SI p6"),
            "concentration range": field(
                "0.5uM;0.5million cells/mL", locator="preprint SI p6"
            ),
            "incubation duration": field("0-240min sampling", locator="preprint SI p6"),
            "readout": field("compound depletion by LCMSMS", locator="preprint SI p6"),
            "endpoint": field(
                "CLint scaled; unbound separately; NOT clinical PK",
                locator="preprint SI pp4,6",
            ),
            "fitting": field(
                "log analyte/internal-standard slope", locator="preprint SI p6"
            ),
        },
    )
    return rows


def stage_a(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required = {
        "bradshaw-2026-enzyme",
        "bradshaw-2026-cell",
        "tinworth-human-enzyme",
        "tinworth-cell-KK",
        "tinworth-cell-compound6",
    }
    identifiers = [row["id"] for row in rows]
    if len(identifiers) != len(set(identifiers)) or not required.issubset(identifiers):
        raise ValueError("missing/duplicate decision-material assay families")
    failures = []
    recovered = False
    for row in rows:
        if not row["decision_material_potency"]:
            continue
        missing = [
            k
            for k in CRITICAL
            if row["fields"][k]["state"] not in VERIFIED
            or row["fields"][k]["value"] is None
        ]
        recovered |= any(
            row["fields"][k]["value"] is not None for k in CRITICAL if k != "target"
        )
        if missing or not row["final_context_adjudicated"]:
            failures.append(
                {
                    "assay": row["id"],
                    "missing": missing,
                    "final_context_adjudicated": row["final_context_adjudicated"],
                }
            )
    stage = "A1" if not failures else ("A2" if recovered else "A3")
    return {
        "stage": stage,
        "blocker_resolved": not failures,
        "failures": failures,
        "stage_b_permitted": not failures,
        "policy": "Explicit protocol chain; adjudicated version fallback; no guesses",
    }


def selectivity() -> dict[str, Any]:
    out = {}
    for target, substrate, potency in (
        ("ERAP2", "Arg-AMC", 4.02),
        ("LNPEP", "Leu-AMC", 4.28),
    ):
        common = dict(
            assay_type="biochemical_activity",
            source_snapshot_id=TIN,
            locator="p8 Table6 / p15 ref31",
            biological_system="isolated enzyme",
        )
        a = Assay(
            id="methods:ERAP1",
            name="YTAFTIPSI",
            target_gene="ERAP1",
            source_assay_identifier="ERAP1",
            substrate="YTAFTIPSI",
            **common,
        )
        b = Assay(
            id="methods:" + target,
            name=substrate,
            target_gene=target,
            source_assay_identifier=target,
            substrate=substrate,
            **common,
        )
        measurements = []
        for assay, p in ((a, 8.45), (b, potency)):
            value = 10 ** (9 - p)
            measurements.append(
                BioactivityMeasurement(
                    id="methods:21:" + assay.target_gene,
                    compound_id=FINAL + ":compound:21",
                    assay_id=assay.id,
                    endpoint="IC50",
                    relation_operator="=",
                    original_value=str(value),
                    original_unit="nM",
                    value=value,
                    source_snapshot_id=TIN,
                    source_record_id="21:" + assay.target_gene,
                    locator="p8 Table6",
                )
            )
        out[target] = {
            "source_pIC50": [8.45, potency],
            "assays": [asdict(a), asdict(b)],
            "measurements": [asdict(m) for m in measurements],
            "result": compare(*measurements, a, b),
        }
    return out


def verify(root: Path = OUTPUT) -> dict[str, Any]:
    m = read(root / "manifest.json")
    if (
        digest((root / "manifest.json").read_bytes())
        != (root / "manifest.sha256").read_text().strip()
    ):
        raise ValueError("methods manifest mismatch")
    if m["algorithm"] != ALGORITHM or m["cutoff"] != CUTOFF:
        raise ValueError("methods algorithm/cutoff mismatch")
    actual_files = {p.name for p in root.glob("*.json") if p.name != "manifest.json"}
    if actual_files != set(m["files"]):
        raise ValueError("unmanifested/missing methods file")
    for name, sha in m["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or digest(path.read_bytes()) != sha:
            raise ValueError("methods file checksum mismatch: " + name)
    if digest(Path(__file__).read_bytes()) != m["code_sha256"]:
        raise ValueError("methods replay code changed")
    for package, hashes in m["parents"].items():
        parent = BASE if package == "v1" else PARENT
        actual = {
            p.relative_to(parent).as_posix(): digest(p.read_bytes())
            for p in parent.rglob("*")
            if p.is_file()
        }
        if actual != hashes:
            raise ValueError("historical parent changed")
    return m


def replay(root: Path = OUTPUT) -> dict[str, Any]:
    verify(root)
    verify_package(BASE)
    historical = replay_closure()
    rows = read(root / "assay-method-matrix.json")
    if rows != matrix():
        raise ValueError("curated method matrix differs")
    if stage_a(rows) != read(root / "stage-a.json"):
        raise ValueError("Stage A differs")
    if json.loads(json.dumps(selectivity())) != read(root / "selectivity.json"):
        raise ValueError("existing selectivity rules differ")
    if any(x["review_state"] != "pending_review" for x in rows):
        raise ValueError("AI cannot approve curation")
    for source in read(root / "source-artifacts.json"):
        if not eligible_date(source["public_available_date"]):
            raise ValueError("source beyond cutoff")
    relationship = read(root / "version-provenance.json")
    if relationship["relationship"]["independent_replication"]:
        raise ValueError("preprint/final cannot be independent replication")
    measurements = read(BASE / "chemical-datasets.json")["measurements"]
    version_values = relationship["preprint_summary_pIC50"]
    for key, token in (("biochemical_1_to_21", "ERAP1"), ("HeLa_1_to_21", "HeLa")):
        final_values = {
            int(m["compound_id"].split(":")[-1]): m["source_value"]
            for m in measurements
            if m["source"] == FINAL and token in m["id"]
        }
        expected = {i: v for i, v in enumerate(version_values[key], 1) if v is not None}
        if expected != final_values:
            raise ValueError("preprint/final endpoint summaries differ")
    refusal = read(root / "decision-refusal.json")
    if refusal["after"] is not None or refusal["candidate_created"]:
        raise ValueError("blocked Stage A cannot contain DecisionState")
    parents = {
        c["domain_claim"]["identifier"]: c
        for c in read(PARENT / "integrated-claims.json")["claims"]
    }
    for delta in read(root / "claim-provenance-delta.json"):
        parent = parents[delta["parent_claim_id"]]
        if (
            delta["parent_envelope_sha256"]
            != digest(json.dumps(parent, sort_keys=True).encode())
            or delta["review_state"] != "pending_review"
        ):
            raise ValueError("claim provenance delta differs")
    return {
        "status": "OFFLINE TARGETED METHODS REPLAY PASSED",
        "stage": stage_a(rows)["stage"],
        "historical_claim_roundtrips": historical["existing_claim_roundtrips"],
        "decision_created": False,
    }


def freeze(cache: Path) -> None:
    if (OUTPUT / "manifest.json").exists():
        raise ValueError("frozen delta already exists; use --replay")
    if cache.resolve().is_relative_to(BASE.parents[5]):
        raise ValueError("original source cache must remain outside repository")
    for name in (
        "version-provenance.json",
        "assay-comparability.json",
        "acceptance-matrix.json",
        "bounded-source-search.json",
    ):
        if not (OUTPUT / name).is_file():
            raise ValueError("explicit curated input required: " + name)
    verify_package(BASE)
    replay_closure()
    sources = []
    for name, (date, kind, version) in SOURCES.items():
        meta = read(cache / (name + ".provenance.json"))
        if (
            meta["status"] != 200
            or digest((cache / name).read_bytes()) != meta["sha256"]
        ):
            raise ValueError("invalid primary artifact: " + name)
        if name.endswith(".pdf") and not (cache / name).read_bytes().startswith(
            b"%PDF-"
        ):
            raise ValueError("source is not a PDF: " + name)
        sources.append(
            {
                k: meta[k]
                for k in ("url", "retrieved_at", "sha256", "bytes", "content_type")
            }
            | {
                "artifact": name,
                "publication_date": date,
                "public_available_date": (
                    meta["retrieved_at"][:10]
                    if kind == "author-hosted manuscript"
                    else date
                ),
                "hosting_public_date": None,
                "source_type": kind,
                "publication_version": version,
                "accessibility": "LEGITIMATELY_ACCESSIBLE",
                "redistributed": False,
            }
        )
    OUTPUT.mkdir(exist_ok=True)
    write(OUTPUT / "source-artifacts.json", sources)
    rows = matrix()
    gate = stage_a(rows)
    if gate["stage_b_permitted"]:
        raise ValueError(
            "Stage A resolved: separate actual-engine reassessment required"
        )
    write(OUTPUT / "assay-method-matrix.json", rows)
    write(OUTPUT / "stage-a.json", gate)
    write(OUTPUT / "selectivity.json", selectivity())
    write(
        OUTPUT / "decision-refusal.json",
        {
            "before": read(BASE / "before.json")["canonical_decision"],
            "after": None,
            "candidate_created": False,
            "critical_uncertainty_changed": None,
            "next_experiment_changed": None,
            "therapeutic_strategy_changed": None,
            "stage": gate["stage"],
            "reason": "BRADSHAW potency-method chain missing",
            "historical_Maben_engagement": "UNRESOLVED; no new occupancy evidence",
            "learning": "MODEL NOT BUILT; new eligibility not run before normalization",
            "question_advancement": "no new integrated assessment",
            "corrector_hypothesis": "historical PLAUSIBLE BUT INSUFFICIENT",
        },
    )
    claims = read(PARENT / "integrated-claims.json")["claims"]
    delta = []
    for c in claims:
        identifier = c["domain_claim"]["identifier"]
        if identifier in {
            "closure:claim:tinworth-controls",
            "closure:claim:tinworth-dmpk",
            "closure:claim:tinworth-cia",
        }:
            delta.append(
                {
                    "parent_claim_id": identifier,
                    "parent_envelope_sha256": digest(
                        json.dumps(c, sort_keys=True).encode()
                    ),
                    "review_state": "pending_review",
                    "immutable_claim_replaced": False,
                    "added_support": [
                        s for s in sources if "tin-preprint" in s["artifact"]
                    ],
                    "delta": "Preprint methods recovered; final SI controls numbers",
                    "admission": "source context only; no integrated engine admission",
                }
            )
    write(OUTPUT / "claim-provenance-delta.json", delta)
    write(
        OUTPUT / "manifest.json",
        {
            "algorithm": ALGORITHM,
            "cutoff": CUTOFF,
            "review_state": "pending_review",
            "code_sha256": digest(Path(__file__).read_bytes()),
            "parents": {
                name: {
                    p.relative_to(folder).as_posix(): digest(p.read_bytes())
                    for p in folder.rglob("*")
                    if p.is_file()
                }
                for name, folder in (("v1", BASE), ("closure-v1", PARENT))
            },
            "files": {
                p.name: digest(p.read_bytes())
                for p in OUTPUT.glob("*.json")
                if p.name != "manifest.json"
            },
            "boundary": "Method delta, NOT DecisionState v2; originals outside Git",
        },
    )
    (OUTPUT / "manifest.sha256").write_text(
        digest((OUTPUT / "manifest.json").read_bytes()) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.replay:
        print(json.dumps(replay(), indent=2))
    elif args.cache:
        freeze(args.cache)
        print(json.dumps(replay(), indent=2))
    else:
        parser.error("choose --replay or --cache for first freeze")
