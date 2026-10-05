"""Bounded primary-source acquisition; bulk artifacts never enter the checkout.

--cache must point outside the repository. Existing artifacts are never replaced.
Metadata/public artifacts only: no raw-MS downloads, authentication or paywalls.
"""

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "axis/resources/evidence-integration/erap1-data-rich/2026/v1"
BASE = "d491ebe47ee0c40dfaa3823a44a9decd1afae29d"
PXDS = (
    "PXD005502",
    "PXD008500",
    "PXD054491",
    "PXD054494",
    "PXD060572",
    "PXD060575",
    "PXD066752",
)
PDBS = (
    "9GJN",
    "9GJS",
    "9GK6",
    "9GKE",
    "9TD3",
    "9TD5",
    "9TD4",
    "9TD7",
    "9TF3",
    "9TF4",
    "9TF6",
    "9TFN",
)
DOIS = (
    "10.1021/acsmedchemlett.4c00401",
    "10.1021/acs.jmedchem.5c03071",
    "10.1021/acs.jmedchem.6c00029",
    "10.1002/eji.202350449",
    "10.1016/j.jbc.2021.100443",
    "10.3390/cells11152427",
    "10.1002/art.42327",
    "10.3389/fimmu.2024.1415964",
    "10.1074/mcp.m116.066241",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def before() -> None:
    path = PACKAGE / "before.json"
    if path.exists():
        return
    state_path = ROOT / "reports/commercial/erap1-axspa/v1/state-snapshot.json"
    snapshot = json.loads(state_path.read_text())
    from axis.decision import rules
    from axis.validation.core import summary

    state = snapshot["decision"]
    write(
        path,
        {
            "recorded_at": datetime.now(UTC).isoformat(),
            "main_sha": BASE,
            "main_clean_before_task": True,
            "axis_version": "0.2.1.dev0",
            "recent_addendum_on_main": False,
            "east1_on_main": False,
            "east1_branch_head": "2e985b1bb2922b8bd970a24759755772d3107d09",
            "canonical_project": state["project_id"],
            "canonical_protein": state["protein_id"],
            "canonical_decision": {
                k: state[k]
                for k in (
                    "id",
                    "evidence_digest",
                    "critical_uncertainty_id",
                    "recommended_experiment_id",
                    "rules_version",
                    "review_mode",
                )
            },
            "canonical_snapshot_sha256": sha(state_path.read_bytes()),
            "decision_summary": summary(state),
            "position": state["position"],
            "evidence": state["evidence"],
            "learning": snapshot["learning"],
            "learning_eligibility": snapshot["eligibility"],
            "structure": {
                k: snapshot["structure"][k]
                for k in ("structure", "boundary", "constructs", "components")
            },
            "source_layers": {
                "discovery": json.loads(
                    (
                        ROOT / "axis/resources/discovery/erap1-axspa/v1/manifest.json"
                    ).read_text()
                )["assessments"],
                "cellular": snapshot["cellular"],
                "selectivity": snapshot["selectivity"],
            },
            "resource_manifests": {
                str(p.relative_to(ROOT)): {
                    "sha256": sha(p.read_bytes()),
                    "version": json.loads(p.read_text()).get(
                        "package_version", json.loads(p.read_text()).get("version")
                    ),
                }
                for p in (ROOT / "axis/resources").rglob("manifest.json")
            },
            "schemas": {
                str(p.relative_to(ROOT)): sha(p.read_bytes())
                for p in [
                    ROOT / "axis/domain/structure.py",
                    ROOT / "axis/domain/pharmacology.py",
                    ROOT / "axis/domain/cellular.py",
                    ROOT / "axis/domain/decision.py",
                    ROOT / "axis/storage/migrations/013_chemical_learning.sql",
                ]
            },
            "rules_fingerprint": rules.fingerprint(),
            "python": sys.version,
            "dependencies": {
                n: importlib.metadata.version(n)
                for n in (
                    "pytest",
                    "mypy",
                    "ruff",
                    "rdkit",
                    "gemmi",
                    "numpy",
                    "scipy",
                    "duckdb",
                    "httpx",
                )
            },
            "boundary": (
                "Read-only BEFORE export from frozen canonical main snapshot; no "
                "scientific state overwritten."
            ),
        },
    )


def fetch(cache: Path, name: str, url: str, post: Any = None) -> dict[str, Any]:
    path = cache / name
    meta = cache / (name + ".provenance.json")
    if path.exists() and meta.exists():
        return json.loads(meta.read_text())
    now = datetime.now(UTC).isoformat()
    req = urllib.request.Request(
        url,
        data=json.dumps(post).encode() if post is not None else None,
        headers={
            "User-Agent": "AXIS-bounded-scientific-acquisition/1",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            raw = response.read(30_000_001)
            if len(raw) > 30_000_000:
                raise ValueError(
                    "bounded acquisition size limit; download separately if justified"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            result = {
                "url": url,
                "resolved_url": response.url,
                "retrieved_at": now,
                "cache_path": name,
                "sha256": sha(raw),
                "bytes": len(raw),
                "status": response.status,
                "content_type": response.headers.get("Content-Type"),
                "request_body": post,
            }
    except Exception as error:
        result = {
            "url": url,
            "retrieved_at": now,
            "cache_path": name,
            "status": "FAILED",
            "error": str(error),
            "request_body": post,
        }
    write(meta, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    cache = args.cache.resolve()
    if cache.is_relative_to(ROOT) or not cache.exists():
        raise SystemExit("Existing external/local cache directory required")
    if (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        != BASE
    ):
        raise SystemExit("Acquire from the audited clean-main baseline")
    before()
    jobs = []
    for doi in DOIS:
        query = urllib.parse.urlencode(
            {"query": "DOI:" + doi, "format": "json", "resultType": "core"}
        )
        jobs.append(
            (
                doi.split("/")[1] + ".epmc.json",
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + query,
                None,
            )
        )
    for accession in PXDS:
        jobs.extend(
            [
                (
                    accession + ".project.json",
                    "https://www.ebi.ac.uk/pride/ws/archive/v2/projects/" + accession,
                    None,
                ),
                (
                    accession + ".files.json",
                    "https://www.ebi.ac.uk/pride/ws/archive/v2/projects/"
                    + accession
                    + "/files?pageSize=500",
                    None,
                ),
            ]
        )
    for pdb in PDBS:
        jobs.append(
            (
                pdb + ".entry.json",
                "https://data.rcsb.org/rest/v1/core/entry/" + pdb,
                None,
            )
        )
    for doi in DOIS[:3]:
        jobs.append(
            (
                doi.split("/")[1] + ".figshare-search.json",
                "https://api.figshare.com/v2/articles/search",
                {"resource_doi": doi},
            )
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda j: fetch(cache, *j), jobs))
    write(cache / "acquisition-index.json", results)
    for item in results:
        print(item["cache_path"], item["status"], item.get("bytes", item.get("error")))


if __name__ == "__main__":
    main()
