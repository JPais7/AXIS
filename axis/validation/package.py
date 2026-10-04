"""Frozen, checksummed benchmark packages: sealed windows and sealed futures.

Layout of one benchmark set directory::

    manifest.json / manifest.sha256
    temporal-availability.json   dates per source (never invented)
    decision-template.json       explanations / candidates / hypothesis, no evidence
    cases/<case>/protocol.json   precommitted, fingerprinted before any run
    cases/<case>/window.json     evidence accessible at the cutoff
    cases/<case>/future.json     sealed; opened only by ``read_future`` at reveal

``BenchmarkSet.window`` can never return future evidence: the window file was
partitioned at build time and is re-verified against the availability table.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from axis.validation import temporal

SCHEMA = "axis-retrospective-benchmark-1"


class PackageError(ValueError):
    """The package is missing, altered or inconsistent; the case must not run."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def redact(
    template: dict[str, Any], redactions: list[dict[str, str]]
) -> dict[str, Any]:
    text = temporal.canonical(template)
    for item in redactions:
        text = text.replace(item["token"], item["replacement"])
    redacted: dict[str, Any] = json.loads(text)
    return redacted


def protocol_fingerprint(protocol: dict[str, Any]) -> str:
    body = {k: v for k, v in protocol.items() if k != "protocol_fingerprint"}
    return temporal.digest(body)


def build_set(
    out: Path,
    *,
    set_id: str,
    title: str,
    kind: str,
    synthetic: bool,
    records: dict[str, Any],
    record_sources: dict[str, str],
    availability_doc: dict[str, Any],
    template: dict[str, Any],
    redactions: list[dict[str, str]],
    cases: list[dict[str, Any]],
    rules_version: str,
    rules_fingerprint: str,
    selection_bias_note: str,
    forbidden_tokens: dict[str, list[str]],
    review_mode: str = "exploratory",
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    availability = availability_doc["sources"]
    write_json(out / "temporal-availability.json", availability_doc)
    write_json(
        out / "decision-template.json",
        {
            "template": redact(template, redactions),
            "redactions": redactions,
            "forbidden_tokens": forbidden_tokens,
        },
    )
    template_sha = sha256_file(out / "decision-template.json")
    entries: list[str] = ["temporal-availability.json", "decision-template.json"]
    for spec in cases:
        cutoff = temporal.TemporalCutoff.parse(
            spec["cutoff_id"], spec["cutoff"], spec["cutoff_rationale"]
        )
        horizon = date.fromisoformat(spec["horizon"]) if spec.get("horizon") else None
        excluded = frozenset(spec.get("excluded_sources", []))
        if excluded and not synthetic:
            raise PackageError(
                "excluding sources by design is allowed only in synthetic fixtures"
            )
        window, future, decisions = temporal.partition(
            records, record_sources, availability, cutoff, horizon, excluded
        )
        base = out / "cases" / spec["case_id"]
        write_json(
            base / "window.json",
            {
                "records": window,
                "record_sources": {
                    k: v
                    for k, v in record_sources.items()
                    if k in set(temporal.record_ids(window))
                },
                "decisions": [d for d in decisions if d["decision"] == "window"],
            },
        )
        write_json(
            base / "future.json",
            {
                "records": future,
                "record_sources": {
                    k: v
                    for k, v in record_sources.items()
                    if k in set(temporal.record_ids(future))
                },
                "decisions": [d for d in decisions if d["decision"] == "future"],
            },
        )
        protocol = {
            "schema": SCHEMA,
            "case_id": spec["case_id"],
            "set_id": set_id,
            "benchmark_kind": kind,
            "synthetic": synthetic,
            "label": spec.get("label", ""),
            "question": spec["question"],
            "cutoff_id": spec["cutoff_id"],
            "cutoff": spec["cutoff"],
            "cutoff_rationale": spec["cutoff_rationale"],
            "horizon": spec.get("horizon"),
            "excluded_sources_by_design": sorted(excluded),
            "excluded_undated_records": sum(
                d["decision"] == "undated" for d in decisions
            ),
            "excluded_beyond_horizon_records": sum(
                d["decision"] == "beyond_horizon" for d in decisions
            ),
            "case_type": spec["case_type"],
            "selection_rationale": spec["selection_rationale"],
            "review_mode": review_mode,
            "rules_version": rules_version,
            "rules_fingerprint": rules_fingerprint,
            "window_sha256": sha256_file(base / "window.json"),
            "future_sha256": sha256_file(base / "future.json"),
            "availability_sha256": sha256_file(out / "temporal-availability.json"),
            "template_sha256": template_sha,
            "dimensions_declared_before_run": list(spec["dimensions"]),
            "pre_declared_expectation": spec["expectation"],
        }
        protocol["protocol_fingerprint"] = protocol_fingerprint(protocol)
        write_json(base / "protocol.json", protocol)
        entries += [
            f"cases/{spec['case_id']}/{n}.json"
            for n in ("protocol", "window", "future")
        ]
    manifest = {
        "schema": SCHEMA,
        "set_id": set_id,
        "title": title,
        "benchmark_kind": kind,
        "synthetic": synthetic,
        "selection_bias_note": selection_bias_note,
        "cases": [c["case_id"] for c in cases],
        "files": {name: sha256_file(out / name) for name in sorted(entries)},
    }
    write_json(out / "manifest.json", manifest)
    (out / "manifest.sha256").write_text(sha256_file(out / "manifest.json") + "\n")


@dataclass
class BenchmarkSet:
    path: Path
    manifest: dict[str, Any]
    opened_future: list[str] = field(default_factory=list)

    @property
    def set_id(self) -> str:
        return str(self.manifest["set_id"])

    def _load(self, name: str) -> dict[str, Any]:
        path = self.path / name
        expected = self.manifest["files"].get(name)
        if expected is None or not path.is_file():
            raise PackageError(f"{name} is not part of the frozen package")
        if sha256_file(path) != expected:
            raise PackageError(f"{name} checksum mismatch; refusing to use it")
        loaded: dict[str, Any] = json.loads(path.read_text())
        return loaded

    def availability(self) -> dict[str, Any]:
        return dict(self._load("temporal-availability.json")["sources"])

    def availability_digest(self) -> str:
        return temporal.digest(self._load("temporal-availability.json"))

    def template(self) -> dict[str, Any]:
        return self._load("decision-template.json")

    def protocol(self, case_id: str) -> dict[str, Any]:
        protocol = self._load(f"cases/{case_id}/protocol.json")
        if protocol_fingerprint(protocol) != protocol["protocol_fingerprint"]:
            raise PackageError("protocol fingerprint mismatch")
        return protocol

    def window(self, case_id: str) -> dict[str, Any]:
        return self._load(f"cases/{case_id}/window.json")

    def read_future(self, case_id: str) -> dict[str, Any]:
        """The only door to future evidence; the opening is recorded and audited."""
        self.opened_future.append(case_id)
        return self._load(f"cases/{case_id}/future.json")


def load_set(path: Path) -> BenchmarkSet:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise PackageError(f"no benchmark manifest in {path}")
    checksum = (path / "manifest.sha256").read_text().strip()
    if sha256_file(manifest_path) != checksum:
        raise PackageError("manifest checksum mismatch; refusing to use the package")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != SCHEMA:
        raise PackageError("unsupported benchmark package schema")
    return BenchmarkSet(path, manifest)
