"""Small, pure audit computations for the bounded ERAP1 evidence integration.

No network, review approval, model training or production-state mutation.
Processed-table summaries are not raw-MS reprocessing or experimental results.
"""

import csv
import hashlib
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date
from itertools import product
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

VERSION = "erap1-data-rich-audit-1"
CUTOFF = "2026-10-05"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def eligible_date(value: str | None, cutoff: str = CUTOFF) -> bool:
    """Unknown dates are not eligible; access/release dates are not interchangeable."""
    if value is None:
        return False
    return date.fromisoformat(value[:10]) <= date.fromisoformat(cutoff)


def normalize_chemical(
    row: dict[str, str], source: str, locator: str
) -> dict[str, Any]:
    """Preserve enhanced stereo and labels; never merge by standard InChI alone."""
    original = row["SMILES"]
    mol = Chem.MolFromSmiles(original)
    if mol is None:
        raise ValueError(f"invalid source SMILES at {locator}")
    label = row.get("Compound_ID") or row.get("Paper Number")
    if not label:
        raise ValueError("source compound label required")
    return {
        "id": f"{source}:compound:{label}",
        "source": source,
        "source_label": label,
        "locator": locator,
        "source_row": row,
        "original_smiles": original,
        "isomeric_smiles": Chem.MolToSmiles(mol, isomericSmiles=True),
        "canonical_cxsmiles": Chem.MolToCXSmiles(mol),
        "enhanced_stereo_groups": [
            {"type": str(g.GetGroupType()), "atoms": [a.GetIdx() for a in g.GetAtoms()]}
            for g in mol.GetStereoGroups()
        ],
        "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
        "exact_molecular_mass": rdMolDescriptors.CalcExactMolWt(mol),
        "formal_charge": Chem.GetFormalCharge(mol),
        "chemical_form": "source representation; no salt stripping or tautomer merging",
        "epistemic_type": "axis_observation",
        "review_state": "pending_review",
    }


def normalize_pic50(value: str) -> dict[str, Any]:
    """Explicit log-endpoint transformation with reversed inequality, not pooling."""
    value = value.strip()
    operator = next((op for op in ("<=", ">=", "<", ">") if value.startswith(op)), "=")
    number = float(value.removeprefix(operator) if operator != "=" else value)
    if not math.isfinite(number):
        raise ValueError("finite pIC50 required")
    return {
        "source_endpoint": "pIC50",
        "source_operator": operator,
        "source_value": number,
        "source_unit": "-log10(IC50/M)",
        "derived_endpoint": "IC50",
        "derived_operator": {"=": "=", "<": ">", ">": "<", "<=": ">=", ">=": "<="}[
            operator
        ],
        "derived_value": 10 ** (9 - number),
        "derived_unit": "nM",
        "transformation": "IC50[nM] = 10**(9-pIC50); inequality reverses",
    }


def source_assigned_stereo(smiles: str, cips: dict[int, str]) -> str:
    """Apply explicit source CIP assignments, retaining the original separately.

    Unknown/relative stereo is never resolved without source assignments.
    Atom indices refer to the preserved source SMILES, not canonical atom order.
    """
    mol = Chem.MolFromSmiles(smiles.split("|")[0].strip())
    if mol is None or not cips or any(v not in {"R", "S"} for v in cips.values()):
        raise ValueError("valid source structure and explicit CIP assignments required")
    positions = list(cips)
    if any(p < 0 or p >= mol.GetNumAtoms() for p in positions):
        raise ValueError("source stereo atom outside molecule")
    candidates = set()
    for flips in product((False, True), repeat=len(positions)):
        candidate = Chem.Mol(mol)
        for position, flip in zip(positions, flips, strict=True):
            if flip:
                candidate.GetAtomWithIdx(position).InvertChirality()
        Chem.AssignStereochemistry(candidate, cleanIt=True, force=True)
        if all(
            candidate.GetAtomWithIdx(p).HasProp("_CIPCode")
            and candidate.GetAtomWithIdx(p).GetProp("_CIPCode") == cip
            for p, cip in cips.items()
        ):
            candidates.add(Chem.MolToSmiles(candidate, isomericSmiles=True))
    if len(candidates) != 1:
        raise ValueError("source stereo assignment not uniquely represented")
    return candidates.pop()


def learning_admission(assay: dict[str, Any]) -> dict[str, Any]:
    """Scientific context admission precedes generic numerical model eligibility."""
    missing = [
        name
        for name in ("protocol_locator", "target_construct", "substrate", "duration")
        if not assay.get(name)
    ]
    return {
        "admitted": not missing,
        "reason": "source protocol adjudicated"
        if not missing
        else "Unresolved exact source assay fields: " + ", ".join(missing),
    }


def supplement_summary(data: dict[str, Any]) -> dict[str, Any]:
    reports = data["reports"]
    union = set().union(*(set(r["sequences"]) for r in reports.values()))
    classifications = data["classifications"]
    keys = sorted(classifications)
    if len(keys) != 2:
        raise ValueError("two distinct perturbation comparisons required")
    up = [set(classifications[k]["upregulated_or_unique"]) for k in keys]
    return {
        "epistemic_type": "axis_observation",
        "source": data["source"],
        "unique_sequences_8_16": len(union),
        "classification_counts": {
            k: {g: len(v) for g, v in groups.items()}
            for k, groups in classifications.items()
        },
        "upregulated_or_unique_overlap": {
            "conditions": keys,
            "intersection": len(up[0] & up[1]),
            "union": len(up[0] | up[1]),
            "jaccard": len(up[0] & up[1]) / len(up[0] | up[1]),
        },
        "classification_union": {
            k: len(set().union(*(set(v) for v in groups.values())))
            for k, groups in classifications.items()
        },
        "scope": (
            "Counts of source-classified processed sequences; source q-values "
            "not independently recomputed"
        ),
        "raw_ms_reprocessing": "NOT PERFORMED",
        "review_state": "pending_review",
    }


def table_inventory(raw: bytes, sequence_column: str) -> dict[str, Any]:
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t"))
    if not rows or sequence_column not in rows[0]:
        raise ValueError("expected peptide sequence column missing")
    sequences = {r[sequence_column] for r in rows if r[sequence_column]}
    return {
        "input_sha256": digest(raw),
        "rows": len(rows),
        "unique_sequences": len(sequences),
        "length_distribution": dict(sorted(Counter(map(len, sequences)).items())),
        "epistemic_type": "axis_observation",
        "scope": (
            "all sequences in supplied processed export; not "
            "condition-specific detections"
        ),
    }


def allotype_summary(raw: bytes, samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse precursors to sequence and technical runs within biological samples.

    Detection means finite positive intensity in any run, not statistical enrichment.
    No missing-value imputation, p-values, HLA assignments or motif predictions.
    """
    rows = list(csv.DictReader(io.StringIO(raw.decode()), delimiter="\t"))
    if not rows or "Stripped.Sequence" not in rows[0]:
        raise ValueError("DIA-NN sequence column missing")
    columns: dict[str, str] = {}
    sample_ids = {s["sample"] for s in samples}
    if len(sample_ids) != len(samples):
        raise ValueError("duplicate sample identifiers")
    for column in rows[0]:
        name = column.replace("\\", "/").rsplit("/", 1)[-1]
        if name in sample_ids:
            if name in columns:
                raise ValueError("ambiguous sample column")
            columns[name] = column
    if set(columns) != sample_ids:
        raise ValueError("sample key does not match matrix columns exactly")
    per_run: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        sequence = row["Stripped.Sequence"]
        if not 8 <= len(sequence) <= 14:
            continue
        for name, column in columns.items():
            text = row[column]
            number = float(text) if text and text != "NA" else math.nan
            if math.isfinite(number) and number > 0:
                per_run[(sequence, name)] += number
    biological: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for sample in samples:
        for (sequence, run), number in per_run.items():
            if run == sample["sample"]:
                biological[
                    (sequence, sample["condition"], str(sample["biological_replicate"]))
                ].append(number)
    per_condition: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (sequence, condition, _), values in biological.items():
        per_condition[(sequence, condition)].append(statistics.mean(values))
    conditions = sorted({s["condition"] for s in samples})
    if len(conditions) != 2:
        raise ValueError("exactly two allotype conditions required")
    sets = {
        c: {p for p, condition in per_condition if condition == c} for c in conditions
    }
    first, second = conditions
    union = sets[first] | sets[second]
    common = sets[first] & sets[second]
    directions: Counter[str] = Counter()
    for sequence in sorted(common):
        difference = math.log2(
            statistics.mean(per_condition[(sequence, first)])
            / statistics.mean(per_condition[(sequence, second)])
        )
        directions[
            "first_higher"
            if difference > 0
            else "second_higher"
            if difference < 0
            else "equal"
        ] += 1
    return {
        "input_sha256": digest(raw),
        "algorithm": VERSION,
        "parameters": {
            "length": [8, 14],
            "precursors": "sum per sequence/run",
            "technical_replicates": "mean observed runs per biological replicate",
            "biological_replicates": "mean observed biological values",
            "missing": "not imputed; conditional on observed values",
        },
        "raw_ms_reprocessing": "NOT PERFORMED",
        "epistemic_type": "axis_observation",
        "conditions": conditions,
        "biological_replicates": {
            c: len({s["biological_replicate"] for s in samples if s["condition"] == c})
            for c in conditions
        },
        "union": len(union),
        "intersection": len(common),
        "jaccard": len(common) / len(union) if union else None,
        "unique": {c: len(sets[c] - common) for c in conditions},
        "length_distribution": {
            c: dict(sorted(Counter(map(len, sets[c])).items())) for c in conditions
        },
        "descriptive_abundance_direction": dict(sorted(directions.items())),
        "statistical_differential_expression": (
            "NOT PERFORMED; no technical-run pseudoreplication"
        ),
        "hla_assignment_and_motifs": (
            "NOT PERFORMED; raw matrix contains no source HLA assignment"
        ),
        "review_state": "pending_review",
    }


def verify_package(root: Path) -> dict[str, Any]:
    raw = root.joinpath("manifest.json").read_bytes()
    if digest(raw) != root.joinpath("manifest.sha256").read_text().strip():
        raise ValueError("integration manifest checksum mismatch")
    manifest: dict[str, Any] = json.loads(raw)
    if manifest["cutoff"] != CUTOFF or manifest["algorithm"] != VERSION:
        raise ValueError("unsupported integration version/cutoff")
    for name, expected in manifest["checksums"].items():
        path = root / name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(
            root.resolve()
        ):
            raise ValueError("unsafe manifest resource path")
        if digest(path.read_bytes()) != expected:
            raise ValueError(f"integration resource checksum mismatch: {name}")
    return manifest


def replay(root: Path) -> dict[str, Any]:
    """Replay frozen processed tables offline; no web or production-state writes."""
    verify_package(root)
    inputs = json.loads(root.joinpath("immunopeptidome-datasets.json").read_text())
    observations = {
        "PXD054491": table_inventory(
            root.joinpath("inputs/Peptide_List_PartI.txt").read_bytes(),
            "PEP.StrippedSequence",
        ),
        "PXD054494": table_inventory(
            root.joinpath("inputs/Peptide_List_PartII.txt").read_bytes(),
            "PEP.StrippedSequence",
        ),
        "PXD066752": allotype_summary(
            root.joinpath("inputs/report.pr_matrix.tsv").read_bytes(),
            inputs["PXD066752"]["samples"],
        ),
        "2025_supplement": supplement_summary(
            json.loads(
                root.joinpath("inputs/2025-supplement-peptides.json").read_text()
            )
        ),
    }
    expected = json.loads(root.joinpath("computational-replications.json").read_text())
    if json.loads(json.dumps(observations)) != expected["peptides"]:
        raise ValueError("processed-table replay differs from frozen observations")
    from axis.decision import engine, rules
    from axis.validation.core import summary

    inputs = json.loads(root.joinpath("decision-inputs.json").read_text())
    decision = json.loads(root.joinpath("decision-impact.json").read_text())
    if rules.fingerprint() != decision["rules_fingerprint"]:
        raise ValueError("decision rules differ from frozen audit")
    for name, key in (
        ("baseline", "isolated_baseline_summary"),
        ("structural_only", "structural_only_candidate_summary"),
    ):
        if summary(engine.analyze(inputs[name])) != decision[key]:
            raise ValueError("isolated decision replay differs from frozen audit")
    return {
        "status": "OFFLINE PROCESSED-TABLE AND ISOLATED ENGINE REPLAY PASSED",
        "decision_reassessment": (
            "WITHHELD pending material source/context adjudication"
        ),
        "observations": observations,
    }
