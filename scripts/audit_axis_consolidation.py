"""Inventory the verified Git reference and compare frozen scientific semantics.

Read-only against historical resources; audit outputs are ordinary release records.
No network, scientific acquisition, model training or rule alteration.
"""

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "84ecc56e74747bdee12ecdf15b9a80bc760798f4"
AUDIT = ROOT / "docs/consolidation/2026"
CASE = ROOT / "axis/resources/evidence-integration/erap1-data-rich/2026"
TERMS = re.compile(
    r"ERAP1|ERAP2|HLA-B27|BRADSHAW|Tinworth|Maben|Hap2|YTAFTIPSI|EAAGIGILTV|"
    r"EAST-1|GRWD0715|10\.\d{4,9}/\S+|\b[0-9][A-Z0-9]{3}\b"
)
LOCAL = re.compile(r"/Users/[^\s\"']+|/home/[^\s\"']+|[A-Z]:\\Users\\[^\s\"']+")
SECRET = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|"
    r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{30,}|-----BEGIN .*PRIVATE KEY-----"
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    indent = None if path.name == "repository-inventory.json" else 2
    path.write_text(json.dumps(value, indent=indent, sort_keys=True) + "\n")


def private_path_projection(value: Any) -> Any:
    """Bind historical local provenance without re-publishing private paths."""
    if isinstance(value, str) and value.startswith(("/Users/", "/home/")):
        return "local-path-sha256:" + sha(value.encode())
    if isinstance(value, list):
        return [private_path_projection(v) for v in value]
    if isinstance(value, dict):
        return {k: private_path_projection(v) for k, v in value.items()}
    return value


def classify(name: str) -> tuple[str, str]:
    if name in {
        "axis/decision/service.py",
        "axis/learning/dataset.py",
        "axis/computational/service.py",
        "axis/pharmacology/service.py",
        "axis/cellular/service.py",
    }:
        return (
            "GENERALIZE",
            "serialization/case configuration; preserve scientific outputs",
        )
    if name.startswith("docs/") and (
        "implementation-report" in name
        or name
        in {
            "docs/erap1-data-rich-final-scientific-closure-2026.md",
            "docs/erap1-targeted-assay-methods-unblock-2026.md",
        }
    ):
        return (
            "ARCHIVE",
            "historical narrative; logical archive only, stable links preserved",
        )
    if name.startswith("scripts/") and any(
        token in name
        for token in (
            "ddx24_word",
            "ddx24_pilot_documents",
            "review_word",
            "reviewer1",
            "second_search",
            "screening_consensus",
        )
    ):
        return (
            "ARCHIVE",
            "one-off case utility; retained history, outside active release path",
        )
    return (
        "KEEP",
        "runtime/tests/config/docs or required provenance/reproduction",
    )


def inventory() -> dict[str, Any]:
    names = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", REFERENCE], cwd=ROOT, text=True
    ).splitlines()
    rows, occurrences, local_paths, secrets = [], [], [], []
    duplicate: dict[str, list[str]] = defaultdict(list)
    total = resource = 0
    for name in names:
        raw = subprocess.check_output(["git", "show", f"{REFERENCE}:{name}"], cwd=ROOT)
        category, reason = classify(name)
        total += len(raw)
        resource += len(raw) if name.startswith("axis/resources/") else 0
        h = sha(raw)
        duplicate[h].append(name)
        row = {
            "path": name,
            "bytes": len(raw),
            "sha256": h,
            "category": category,
            "reason": reason,
        }
        if name.startswith("scripts/"):
            row["script_role"] = (
                "one-off historical utility"
                if category == "ARCHIVE"
                else "reproducibility utility"
                if any(
                    t in name
                    for t in (
                        "erap1",
                        "assay",
                        "bradshaw",
                        "verify_",
                        "build_",
                        "audit_",
                    )
                )
                else "permanent pipeline/development utility"
            )
        if name.startswith("tests/"):
            row["test_taxonomy"] = (
                "scientific regression/reproducibility"
                if any(
                    t in name
                    for t in (
                        "erap1",
                        "evidence_integration",
                        "prospective",
                        "temporal",
                    )
                )
                else "domain/integration"
                if any(
                    t in name
                    for t in ("decision", "learning", "results", "cellular", "storage")
                )
                else "unit/behavioral"
            )
        rows.append(row)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        occurrence_class = (
            "LEGITIMATE_CASE_TEST"
            if name.startswith("tests/")
            else "DOCUMENTATION"
            if name.endswith(".md") or name.startswith(("docs/", "reports/"))
            else "LEGITIMATE_CASE_DATA"
        )
        for i, line in enumerate(text.splitlines(), 1):
            matches = [m.group() for m in TERMS.finditer(line)]
            if matches:
                is_leak = (
                    name == "axis/pharmacology/service.py" and i in {134, 137, 150}
                ) or (name == "axis/cellular/service.py" and i in {241, 242, 316})
                occurrences.append(
                    {
                        "path": name,
                        "line": i,
                        "terms": matches,
                        "classification": "GENERIC_CODE_LEAK"
                        if is_leak
                        else occurrence_class,
                    }
                )
            if LOCAL.search(line):
                local_paths.append(
                    {
                        "path": name,
                        "line": i,
                        "action": "retain historical provenance; no new local default",
                    }
                )
            if SECRET.search(line):
                expired_source_url = (
                    name
                    == CASE.relative_to(ROOT).as_posix() + "/v1/source-artifacts.json"
                    and '"resolved_url"' in line
                    and "X-Amz-Date=20261005T181432Z" in line
                    and "X-Amz-Expires=10" in line
                    and all(m.group().startswith("AKIA") for m in SECRET.finditer(line))
                )
                secrets.append(
                    {
                        "path": name,
                        "line": i,
                        "disposition": "expired URL; identifier, not secret key"
                        if expired_source_url
                        else "UNRESOLVED",
                        "action": "retain provenance; value not printed",
                    }
                )
    if any(s["disposition"] == "UNRESOLVED" for s in secrets):
        raise ValueError(
            "possible credentials detected; promotion requires investigation"
        )
    result = {
        "scientific_reference_sha": REFERENCE,
        "reference_label": "ERAP1_DATA_RICH_SCIENTIFIC_REFERENCE_2026",
        "main_sha": "d491ebe47ee0c40dfaa3823a44a9decd1afae29d",
        "merge_base": "d491ebe47ee0c40dfaa3823a44a9decd1afae29d",
        "integration_branch": "codex/erap1-data-rich-evidence-integration-2026",
        "consolidation_branch": "codex/axis-consolidation-post-erap1-2026",
        "reference_ahead": 4,
        "reference_behind": 0,
        "starting_tree": "clean",
        "classification_counts": dict(Counter(r["category"] for r in rows)),
        "tracked_files": len(rows),
        "tracked_bytes": total,
        "runtime_resource_bytes": resource,
        "largest_files": sorted(rows, key=lambda r: r["bytes"], reverse=True)[:20],
        "files": rows,
        "case_occurrences": occurrences,
        "local_path_occurrences": local_paths,
        "credential_pattern_findings": secrets,
        "duplicate_groups": [v for v in duplicate.values() if len(v) > 1],
        "deletion_candidates": [],
        "physical_archives": [],
        "protected_history": "all resources/commercial/benchmarks stay byte-identical",
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        grouped[occurrence.pop("path")].append(occurrence)
    result["case_occurrences"] = dict(grouped)
    result["case_classification_reasons"] = {
        "GENERIC_CODE_LEAK": "extract case-specific service configuration",
        "LEGITIMATE_CASE_DATA": "case package, import guard or source-linked data",
        "LEGITIMATE_CASE_TEST": "source/case fixture or regression assertion",
        "DOCUMENTATION": "scientific narrative, historical report or provenance",
    }
    save(AUDIT / "repository-inventory.json", result)
    return result


def material() -> dict[str, Any]:
    from scripts.reassess_erap1_bradshaw import OUTPUT, read, replay

    proof = replay()
    state = read(OUTPUT / "decision-state-v2.json")
    reassess = read(OUTPUT / "decision-reassessment.json")
    learn = read(OUTPUT / "learning-eligibility.json")
    result = {
        "reference_sha": REFERENCE,
        "classification": reassess["classification"],
        "critical_uncertainty": state["critical_uncertainty_id"],
        "recommended_experiment": state["recommended_experiment_id"],
        "evidence": state["evidence"],
        "uncertainties": state["uncertainties"],
        "causal_diff": read(OUTPUT / "causal-decision-diff.json"),
        "assay_comparability": read(OUTPUT / "assay-comparability.json"),
        "allotype_substrate": read(OUTPUT / "allotype-substrate-context.json"),
        "maben_engagement": reassess["historical_Maben_engagement"],
        "learning": learn,
        "claims": read(OUTPUT / "integrated-claim-delta.json"),
        "sources": read(OUTPUT / "source-provenance.json"),
        "replay": proof,
        "protected_hashes": {
            p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
            for directory in (
                ROOT / "axis/resources",
                ROOT / "reports/commercial/erap1-axspa/v1",
                ROOT / "axis/resources/prospective",
                ROOT / "axis/resources/benchmarks",
                ROOT / "reports/prospective",
                ROOT / "benchmarks",
            )
            for p in directory.rglob("*")
            if p.is_file()
        },
    }
    return private_path_projection(result)


def capture() -> None:
    if (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        != REFERENCE
    ):
        raise ValueError("golden capture requires exact scientific reference HEAD")
    if (AUDIT / "golden-reference.json").exists():
        raise ValueError("golden reference already exists")
    inventory()
    save(AUDIT / "golden-reference.json", material())


def compare() -> dict[str, Any]:
    baseline = json.loads((AUDIT / "golden-reference.json").read_text())
    actual = material()
    new_resources = sorted(
        set(actual["protected_hashes"]) - set(baseline["protected_hashes"])
    )
    if any(not p.startswith("axis/resources/cases/") for p in new_resources):
        raise ValueError("unexpected new scientific resource; STOP promotion")
    actual["protected_hashes"] = {
        p: actual["protected_hashes"].get(p) for p in baseline["protected_hashes"]
    }
    from axis.assay_context import CuratedComparison, ScopedLimitation

    for row in actual["assay_comparability"]["comparisons"]:
        CuratedComparison(
            row["families"],
            row["status"],
            row["inference"],
            "bradshaw-main-v3/assay-comparability.json",
            row.get("condition"),
        )
    for row in read_json_limitations():
        ScopedLimitation(
            tuple(row["fields"]),
            row["affected_inference"],
            row["blocks_current_decision"],
            row["reason"],
        )
    keys = sorted(set(baseline) | set(actual))
    changes = [k for k in keys if baseline.get(k) != actual.get(k)]
    result = {
        "reference_sha": REFERENCE,
        "scientific_equivalence": "PASS" if not changes else "FAIL",
        "classification": "BYTE_IDENTICAL" if not changes else "SCIENTIFIC_CHANGE",
        "changed_dimensions": changes,
        "checked_dimensions": keys,
        "new_configuration_resources": new_resources,
    }
    if changes:
        raise ValueError("SCIENTIFIC_CHANGE; STOP promotion: " + ",".join(changes))
    return result


def read_json_limitations() -> list[dict[str, Any]]:
    return json.loads(
        (CASE / "bradshaw-main-v3/localized-uncertainty.json").read_text()
    )["remaining"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    if args.capture:
        capture()
        print("Reference inventory and pre-refactor golden semantics captured")
    else:
        print(json.dumps(compare(), indent=2))
