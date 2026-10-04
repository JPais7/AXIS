"""Retrospective validation service: seal, run at T, audit, reveal, assess, review.

The decision at the cutoff is produced by the ordinary Decision Engine over the
sealed window only. The future file is opened solely by ``reveal`` after the
decision, the leakage audit and the baselines are persisted.
"""

import hashlib
import os
import re
import subprocess
from datetime import UTC, datetime
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from axis.decision import rules
from axis.domain.validation import (
    BENCHMARK_KINDS,
    CONCLUSIONS,
    DIMENSIONS,
    INVALID_LABEL,
    SYNTHETIC_LABEL,
)
from axis.storage import EvidenceStore
from axis.validation import core, temporal
from axis.validation.package import BenchmarkSet, PackageError, load_set, sha256_file

RETRO_VERSION = "axis-retro-1"
REVIEWER_BLOCK = re.compile(
    r"\b(ai|axis|assistant|claude|gpt|llm|model)\b", re.IGNORECASE
)


def registry_root() -> Path:
    return Path(str(resources.files("axis"))) / "resources/benchmarks/retrospective"


def software_commit() -> str:
    if os.environ.get("AXIS_COMMIT"):
        return os.environ["AXIS_COMMIT"]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
            timeout=5,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        try:
            return f"installed-package:{metadata.version('axis-bio')}"
        except metadata.PackageNotFoundError:
            return "unknown"


def now() -> datetime:
    return datetime.now(UTC)


class BenchmarkError(ValueError):
    """A benchmark operation was refused (order, state or integrity)."""


class BenchmarkService:
    def __init__(self, store: EvidenceStore, root: Path | None = None) -> None:
        self.store = store
        self.root = root or registry_root()
        self.repo = store.benchmarks

    # -- registry ----------------------------------------------------------

    def package_paths(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(p.parent for p in self.root.glob("*/v*/manifest.json"))

    def load(self, set_id: str) -> BenchmarkSet:
        for path in self.package_paths():
            if path.parent.name == set_id:
                return load_set(path)
        raise BenchmarkError(f"unknown benchmark set {set_id!r}")

    def set_of(self, case_id: str) -> BenchmarkSet:
        case = self.repo.case(case_id, required=False)
        if case is not None:
            return self.load(case["set_id"])
        for path in self.package_paths():
            package = load_set(path)
            if case_id in package.manifest["cases"]:
                return package
        raise BenchmarkError(f"unknown benchmark case {case_id!r}")

    def register(self, set_id: str | None = None) -> list[str]:
        """Register (idempotently) and seal the cases of one or all sets."""
        sealed: list[str] = []
        for path in self.package_paths():
            if set_id and path.parent.name != set_id:
                continue
            package = load_set(path)
            stamp = now()
            with self.store._transaction():
                self.repo.register_set(
                    package.manifest, sha256_file(path / "manifest.json"), stamp
                )
                for case_id in package.manifest["cases"]:
                    self.repo.seal_case(package.protocol(case_id), stamp)
                    sealed.append(case_id)
        return sealed

    def list_cases(self) -> list[dict[str, Any]]:
        self.register()
        out = []
        for case in self.repo.cases():
            protocol = case["protocol"]
            out.append(
                {
                    "case_id": case["case_id"],
                    "set_id": case["set_id"],
                    "status": case["status"],
                    "benchmark_kind": protocol["benchmark_kind"],
                    "synthetic": protocol["synthetic"],
                    "label": SYNTHETIC_LABEL if protocol["synthetic"] else "",
                    "cutoff": protocol["cutoff"],
                    "case_type": protocol["case_type"],
                    "question": protocol["question"],
                }
            )
        return out

    # -- snapshot ----------------------------------------------------------

    def snapshot(self, case_id: str) -> dict[str, Any]:
        package = self.set_of(case_id)
        self.register(package.set_id)
        protocol = package.protocol(case_id)
        window_file = package.window(case_id)
        cutoff = temporal.TemporalCutoff.parse(
            protocol["cutoff_id"], protocol["cutoff"], protocol["cutoff_rationale"]
        )
        availability = package.availability()
        records = window_file["records"]
        fingerprint = temporal.snapshot_fingerprint(
            records, cutoff, package.availability_digest()
        )
        sources = window_file["record_sources"]
        used = sorted(set(sources.values()))
        payload = {
            "label": SYNTHETIC_LABEL if protocol["synthetic"] else "",
            "cutoff": cutoff.date.isoformat(),
            "cutoff_rationale": cutoff.rationale,
            "fingerprint": fingerprint,
            "availability_sha256": protocol["availability_sha256"],
            "records": {k: len(v) for k, v in records.items() if isinstance(v, list)},
            "record_ids": temporal.record_ids(records),
            "sources": [
                {
                    "source": s,
                    "title": availability[s]["title"],
                    "nominal_publication_date": availability[s][
                        "nominal_publication_date"
                    ],
                    "first_publicly_accessible_date": availability[s][
                        "first_publicly_accessible_date"
                    ],
                    "availability_kind": availability[s]["availability_kind"],
                }
                for s in used
            ],
            "future_records_withheld": "count only; identities sealed until reveal",
        }
        existing = [
            r
            for r in self.repo.rows("temporal_snapshots", case_id)
            if r["fingerprint"] == fingerprint
        ]
        if not existing:
            self.repo.add(
                "temporal_snapshots",
                f"{case_id}:snapshot:{fingerprint[:12]}",
                {
                    "case_id": case_id,
                    "cutoff": cutoff.date,
                    "fingerprint": fingerprint,
                    "created_at": now(),
                    "payload": payload,
                },
            )
        return payload

    # -- audit -------------------------------------------------------------

    def _audit(
        self,
        case_id: str,
        phase: str,
        outputs: list[Any],
        *,
        baseline_frozen: bool,
        future_opened: bool,
    ) -> dict[str, Any]:
        package = self.set_of(case_id)
        checks = {"protocol_checksum_mismatch": True, "window_checksum_mismatch": True}
        try:
            protocol = package.protocol(case_id)
        except PackageError:
            checks["protocol_checksum_mismatch"] = False
            return self._persist_audit(
                case_id,
                phase,
                {
                    "valid": False,
                    "label": INVALID_LABEL,
                    "findings": [
                        {
                            "category": "protocol_checksum_mismatch",
                            "subject": case_id,
                            "detail": "package integrity failure",
                        }
                    ],
                    "checked": {},
                },
            )
        try:
            window_file = package.window(case_id)
            template = package.template()
        except PackageError:
            return self._persist_audit(
                case_id,
                phase,
                {
                    "valid": False,
                    "label": INVALID_LABEL,
                    "findings": [
                        {
                            "category": "window_checksum_mismatch",
                            "subject": case_id,
                            "detail": "package integrity failure",
                        }
                    ],
                    "checked": {},
                },
            )
        stored = self.repo.case(case_id)
        assert stored is not None
        if stored["protocol_fingerprint"] != protocol["protocol_fingerprint"]:
            checks["protocol_checksum_mismatch"] = False
        if (
            sha256_file(package.path / f"cases/{case_id}/window.json")
            != protocol["window_sha256"]
        ):
            checks["window_checksum_mismatch"] = False
        # The future file is read here only to learn identities to look for in
        # the outputs; it is the audit, not the decision, that sees them, and
        # the read is not counted as an opening by the decision path.
        future_file = package._load(f"cases/{case_id}/future.json")
        future_ids = set(temporal.record_ids(future_file["records"]))
        future_sources = set(future_file["record_sources"].values())
        cutoff = temporal.TemporalCutoff.parse(
            protocol["cutoff_id"], protocol["cutoff"], protocol["cutoff_rationale"]
        )
        result = core.leakage_audit(
            availability=package.availability(),
            cutoff=cutoff,
            window_file=window_file,
            future_ids=future_ids,
            future_sources=future_sources,
            template=core.scrub_template(template["template"], window_file["records"])[
                0
            ],
            forbidden_tokens=template["forbidden_tokens"],
            outputs=outputs,
            checksums_ok=checks,
            future_opened_before_reveal=future_opened,
            baseline_frozen_before_reveal=baseline_frozen,
        )
        return self._persist_audit(case_id, phase, result)

    def _persist_audit(
        self, case_id: str, phase: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        count = len(self.repo.rows("leakage_audits", case_id)) + 1
        self.repo.add(
            "leakage_audits",
            f"{case_id}:audit:{count}",
            {
                "case_id": case_id,
                "phase": phase,
                "valid": result["valid"],
                "created_at": now(),
                "payload": result,
            },
        )
        if not result["valid"]:
            self.repo.set_status(case_id, "invalid", now())
        return result

    def leakage_audit(self, case_id: str) -> dict[str, Any]:
        """Stand-alone audit of the stored cutoff decision (or of the package)."""
        self.register()
        runs = [
            r
            for r in self.repo.rows("benchmark_runs", case_id)
            if r["phase"] == "cutoff"
        ]
        outputs = [runs[-1]["payload"]["analysis"]] if runs else []
        frozen = bool(self.repo.rows("benchmark_baselines", case_id))
        return self._audit(
            case_id,
            "standalone",
            outputs,
            baseline_frozen=frozen or not runs,
            future_opened=False,
        )

    # -- run at the cutoff -------------------------------------------------

    def run(self, case_id: str, mode: str | None = None) -> dict[str, Any]:
        package = self.set_of(case_id)
        self.register(package.set_id)
        case = self.repo.case(case_id)
        assert case is not None
        if case["status"] == "invalid":
            raise BenchmarkError(f"{INVALID_LABEL}: case {case_id} is invalid")
        protocol = package.protocol(case_id)
        mode = mode or protocol["review_mode"]
        window_file = package.window(case_id)
        window = window_file["records"]
        template, scrubbed = core.scrub_template(package.template()["template"], window)
        snapshot = self.snapshot(case_id)
        analysis = core.decide(template, window, mode)
        state = core.summary(analysis)
        validity = core.decision_validity(analysis, window)
        claims = core.overstated_claims(analysis)
        baseline = core.naive_baseline(window)
        stamp = now()
        run_no = (
            len(
                [
                    r
                    for r in self.repo.rows("benchmark_runs", case_id)
                    if r["phase"] == "cutoff"
                ]
            )
            + 1
        )
        current = rules.fingerprint()
        revision = None
        if current != protocol["rules_fingerprint"]:
            revision = {
                "status": "post_benchmark_rule_revision",
                "sealed_fingerprint": protocol["rules_fingerprint"],
                "current_fingerprint": current,
                "note": (
                    "The rules changed after this protocol was sealed; the result "
                    "describes the current rules, not the ones that were sealed."
                ),
            }
            self.repo.add(
                "benchmark_rule_notes",
                f"{case_id}:rulenote:{run_no}",
                {
                    "case_id": case_id,
                    "kind": "post_benchmark_rule_revision",
                    "created_at": stamp,
                    "payload": revision,
                },
            )
        run_id = f"{case_id}:run:{run_no}"
        payload = {
            "label": SYNTHETIC_LABEL if protocol["synthetic"] else "",
            "snapshot_fingerprint": snapshot["fingerprint"],
            "analysis": analysis,
            "state": state,
            "decision_validity": validity,
            "overstated_claims": claims,
            "rule_revision": revision,
            "template_references_removed": scrubbed,
            "retro_version": RETRO_VERSION,
            "deterministic": True,
            "llm_used": False,
            "network_used": False,
        }
        with self.store._transaction():
            self.repo.add(
                "benchmark_runs",
                run_id,
                {
                    "case_id": case_id,
                    "phase": "cutoff",
                    "rules_fingerprint": current,
                    "software_commit": software_commit(),
                    "review_mode": mode,
                    "created_at": stamp,
                    "payload": payload,
                },
            )
            self._freeze_baseline(
                case_id, "internal-least-evidence", "run-1", baseline, stamp
            )
            self.repo.set_status(case_id, "executed", stamp)
        audit = self._audit(
            case_id,
            "pre_reveal",
            [analysis],
            baseline_frozen=True,
            future_opened=case_id in package.opened_future,
        )
        return {
            "run_id": run_id,
            "state": state,
            "audit": audit,
            "valid": audit["valid"],
            "label": None if audit["valid"] else INVALID_LABEL,
            "rule_revision": revision,
        }

    # -- baselines ---------------------------------------------------------

    def _freeze_baseline(
        self,
        case_id: str,
        kind: str,
        label: str,
        payload: dict[str, Any],
        stamp: datetime,
    ) -> None:
        self.repo.add(
            "benchmark_baselines",
            f"{case_id}:baseline:{kind}:{label}",
            {
                "case_id": case_id,
                "baseline_kind": kind,
                "run_label": label,
                "sha256": temporal.digest(payload),
                "frozen_at": stamp,
                "payload": payload,
            },
        )

    def import_baseline(self, case_id: str, document: dict[str, Any]) -> list[str]:
        """Freeze externally produced baseline outputs; only before the reveal."""
        case = self.repo.case(case_id)
        assert case is not None
        if case["status"] in {"revealed", "reviewed"}:
            raise BenchmarkError(
                "baselines must be frozen before the future evidence is revealed"
            )
        if case["status"] != "executed":
            raise BenchmarkError(
                "run the case at its cutoff before importing baselines"
            )
        name = str(document.get("baseline", "")).strip()
        if not name:
            raise BenchmarkError("baseline file needs a 'baseline' name")
        labels = []
        for run in document.get("runs", []):
            edge = run.get("recommended_edge")
            if edge not in core.EDGES:
                raise BenchmarkError(f"baseline run edge {edge!r} is not a known edge")
            payload = {
                "baseline": name,
                "model": run.get("model", ""),
                "stochastic": bool(run.get("stochastic", False)),
                "recommended_edge": edge,
                "supported_edges": list(run.get("supported_edges", [])),
                "free_text": run.get("free_text", ""),
                "produced_with_access_to_future_evidence": False,
                "source": "external, supplied by the investigator",
            }
            self._freeze_baseline(
                case_id, f"external:{name}", run["label"], payload, now()
            )
            labels.append(run["label"])
        return labels

    # -- reveal ------------------------------------------------------------

    def reveal(self, case_id: str) -> dict[str, Any]:
        package = self.set_of(case_id)
        case = self.repo.case(case_id)
        assert case is not None
        if case["status"] == "invalid":
            raise BenchmarkError(f"{INVALID_LABEL}: refusing to reveal {case_id}")
        if case["status"] in {"revealed", "reviewed"}:
            raise BenchmarkError("the future evidence was already revealed")
        if case["status"] != "executed":
            raise BenchmarkError("run the case at its cutoff before the reveal")
        runs = [
            r
            for r in self.repo.rows("benchmark_runs", case_id)
            if r["phase"] == "cutoff"
        ]
        audits = self.repo.rows("leakage_audits", case_id)
        if not audits or not audits[-1]["payload"]["valid"]:
            raise BenchmarkError(f"{INVALID_LABEL}: no valid pre-reveal audit")
        baselines = self.repo.rows("benchmark_baselines", case_id)
        if not baselines:
            raise BenchmarkError("baselines must be frozen before the reveal")
        protocol = package.protocol(case_id)
        cut_run = runs[-1]
        mode = cut_run["review_mode"]
        window_file = package.window(case_id)
        window = window_file["records"]
        template = package.template()["template"]  # scrubbed per evidence set below
        state_t = cut_run["payload"]["state"]
        # ---- the only place the future file is opened ----
        future_file = package.read_future(case_id)
        future = future_file["records"]
        fsources = future_file["record_sources"]
        availability = package.availability()
        merged = temporal.merge(window, future)
        analysis_t1 = core.decide(template, merged, mode)
        state_t1 = core.summary(analysis_t1)
        diff = core.state_diff(state_t, state_t1)
        relevance: dict[str, dict[str, Any]] = {}
        for source in sorted(set(fsources.values())):
            subset = core.subset_by_source(future, fsources, source)
            item = core.relevance_of_source(template, window, subset, state_t, mode)
            item["title"] = availability[source]["title"]
            item["first_publicly_accessible_date"] = availability[source][
                "first_publicly_accessible_date"
            ]
            relevance[source] = item
        valid = bool(audits[-1]["payload"]["valid"])
        conclusion = core.conclusion_of(state_t, state_t1, relevance, valid)
        calibration = core.uncertainty_calibration(state_t, state_t1, relevance)
        rec = core.recommendation_relevance(state_t, relevance)
        baseline_comparisons = []
        for row in baselines:
            if row["baseline_kind"].startswith("internal"):
                baseline_comparisons.append(
                    {
                        "baseline": row["baseline_kind"],
                        "run": row["run_label"],
                        "frozen_at": row["frozen_at"],
                        "sha256": row["sha256"],
                        **core.compare_to_baseline(state_t, row["payload"], relevance),
                    }
                )
            else:
                baseline_comparisons.append(
                    {
                        "baseline": row["baseline_kind"],
                        "run": row["run_label"],
                        "frozen_at": row["frozen_at"],
                        "sha256": row["sha256"],
                        "stochastic": row["payload"]["stochastic"],
                        **core.compare_to_baseline(state_t, row["payload"], relevance),
                    }
                )
        matrix = {
            "temporal_integrity": {"result": "valid" if valid else "invalid"},
            "decision_validity_at_cutoff": {
                "result": cut_run["payload"]["decision_validity"]["result"]
            },
            "uncertainty_calibration": {"result": calibration["result"]},
            "recommendation_relevance": {"result": rec["result"]},
            "future_evidence_relevance": {
                "result": sorted({v["relevance"] for v in relevance.values()})
            },
            "evidence_update_behavior": {
                "result": f"decision_changed:{diff['decision_changed']}",
                "reviewed": "pending_human_review",
            },
            "overstated_claims": {
                "result": cut_run["payload"]["overstated_claims"]["result"]
            },
            "baseline_comparison": {
                "result": sorted({b["result"] for b in baseline_comparisons}),
                "runs": len(baseline_comparisons),
            },
        }
        assert tuple(matrix) == DIMENSIONS
        robustness = core.leave_one_source_out(
            template, window, window_file["record_sources"], state_t, mode
        )
        post_audit = self._audit(
            case_id,
            "post_reveal",
            [cut_run["payload"]["analysis"]],
            baseline_frozen=True,
            future_opened=False,
        )
        stamp = now()
        run_id = (
            f"{case_id}:reveal:{len(self.repo.rows('benchmark_runs', case_id)) + 1}"
        )
        payload = {
            "label": SYNTHETIC_LABEL if protocol["synthetic"] else "",
            "future_sources": [
                {
                    "source": s,
                    "title": availability[s]["title"],
                    "nominal_publication_date": availability[s][
                        "nominal_publication_date"
                    ],
                    "first_publicly_accessible_date": availability[s][
                        "first_publicly_accessible_date"
                    ],
                }
                for s in sorted(set(fsources.values()))
            ],
            "state_t1": state_t1,
            "diff": diff,
            "retro_version": RETRO_VERSION,
            "post_reveal_audit": post_audit,
        }
        assessment = {
            "provenance": {
                "produced_by": "AXIS deterministic retrospective rules "
                + RETRO_VERSION,
                "decision_rules_fingerprint": cut_run["rules_fingerprint"],
                "software_commit": software_commit(),
                "protocol_fingerprint": protocol["protocol_fingerprint"],
                "rule_revision": cut_run["payload"]["rule_revision"],
                "human_review": "pending",
                "benchmark_kind": protocol["benchmark_kind"],
                "synthetic": protocol["synthetic"],
            },
            "conclusion": conclusion,
            "relevance": relevance,
            "uncertainty_calibration": calibration,
            "recommendation_relevance": rec,
            "matrix": matrix,
            "baseline_comparison": baseline_comparisons,
            "leave_one_source_out": robustness,
            "limits": [
                "Retrospective: this cannot establish clinical efficacy or "
                "prospective validity.",
                "One case; no aggregate performance is computed.",
                "The decision template was authored after the cutoff and is audited, "
                "not proven free of hindsight.",
            ],
        }
        with self.store._transaction():
            self.repo.add(
                "benchmark_runs",
                run_id,
                {
                    "case_id": case_id,
                    "phase": "reveal",
                    "rules_fingerprint": rules.fingerprint(),
                    "software_commit": software_commit(),
                    "review_mode": mode,
                    "created_at": stamp,
                    "payload": payload,
                },
            )
            self.repo.add(
                "retrospective_assessments",
                f"{case_id}:assessment:{run_id.rsplit(':', 1)[-1]}",
                {
                    "case_id": case_id,
                    "run_id": run_id,
                    "conclusion": conclusion["conclusion"],
                    "created_at": stamp,
                    "payload": assessment,
                },
            )
            if post_audit["valid"]:
                self.repo.set_status(case_id, "revealed", stamp)
        if not post_audit["valid"]:
            assessment["conclusion"] = {
                "conclusion": "invalid_due_to_leakage",
                "label": INVALID_LABEL,
                "basis": [f["category"] for f in post_audit["findings"]],
            }
        return {"run_id": run_id, **payload, "assessment": assessment}

    # -- blind review ------------------------------------------------------

    def blind_packet(self, case_id: str) -> dict[str, Any]:
        case = self.repo.case(case_id)
        assert case is not None
        existing = self.repo.rows("benchmark_blind_packets", case_id)
        if existing:
            return dict(existing[-1]["packet"])
        if case["status"] not in {"revealed", "reviewed"}:
            raise BenchmarkError("a blind packet is built after the reveal")
        protocol = case["protocol"]
        runs = {r["phase"]: r for r in self.repo.rows("benchmark_runs", case_id)}
        state_t = runs["cutoff"]["payload"]["state"]
        baseline = next(b for b in self.repo.rows("benchmark_baselines", case_id))[
            "payload"
        ]
        assessment = self.repo.rows("retrospective_assessments", case_id)[-1]["payload"]
        a_is_axis = (
            int(
                hashlib.sha256(
                    (protocol["protocol_fingerprint"] + "|blind").encode()
                ).hexdigest(),
                16,
            )
            % 2
            == 0
        )
        axis_view = {
            "next_question": state_t["recommendation_question"]
            or state_t["no_experiment_message"],
            "open_evidence_areas": sorted(
                u["category"]
                for u in state_t["uncertainties"].values()
                if u["status"] == "open"
            ),
        }
        base_view = {
            "next_question": f"Collect evidence on the {baseline['recommended_edge']} "
            "step.",
            "open_evidence_areas": [baseline["recommended_edge"]],
        }
        options = {
            "A": axis_view if a_is_axis else base_view,
            "B": base_view if a_is_axis else axis_view,
        }
        mapping = {
            "A": "axis" if a_is_axis else "baseline",
            "B": "baseline" if a_is_axis else "axis",
        }
        packet = {
            "case_id": case_id,
            "label": SYNTHETIC_LABEL if protocol["synthetic"] else "",
            "cutoff": protocol["cutoff"],
            "question": protocol["question"],
            "options": options,
            "later_evidence": [
                {
                    "source": s["source"],
                    "title": s["title"],
                    "available_from": s["first_publicly_accessible_date"],
                    "what_it_addressed": assessment["relevance"][s["source"]][
                        "relevance"
                    ],
                }
                for s in self.repo.rows("benchmark_runs", case_id)[-1]["payload"][
                    "future_sources"
                ]
            ],
            "instructions": (
                "Options A and B are unlabelled. Judge which better pointed at what "
                "later evidence addressed. Do not infer which is the software."
            ),
        }
        self.repo.add(
            "benchmark_blind_packets",
            f"{case_id}:blind:1",
            {
                "case_id": case_id,
                "mapping_sha256": temporal.digest(mapping),
                "created_at": now(),
                "unblinded_at": None,
                "packet": packet,
                "sealed_mapping": mapping,
            },
        )
        return packet

    def review(
        self,
        case_id: str,
        reviewer: str,
        *,
        dimensions: dict[str, dict[str, str]],
        preference: str,
        conclusion_opinion: str,
        rationale: str,
    ) -> dict[str, Any]:
        case = self.repo.case(case_id)
        assert case is not None
        if case["status"] not in {"revealed", "reviewed"}:
            raise BenchmarkError("only a revealed, valid case can be reviewed")
        if not reviewer.strip() or REVIEWER_BLOCK.search(reviewer):
            raise BenchmarkError("AI cannot review its own validation")
        if preference not in {"A", "B", "neither", "cannot_judge"}:
            raise BenchmarkError("preference must be A, B, neither or cannot_judge")
        if conclusion_opinion not in CONCLUSIONS:
            raise BenchmarkError(f"conclusion must be one of {CONCLUSIONS}")
        unknown = sorted(set(dimensions) - set(DIMENSIONS))
        if unknown:
            raise BenchmarkError(f"unknown dimensions {unknown}")
        if not rationale.strip():
            raise BenchmarkError("a review needs a rationale")
        self.blind_packet(case_id)
        count = len(self.repo.rows("benchmark_reviews", case_id)) + 1
        stamp = now()
        payload = {
            "reviewer": reviewer,
            "reviewer_kind": "investigator",
            "dimensions": dimensions,
            "preference": preference,
            "conclusion_opinion": conclusion_opinion,
            "rationale": rationale,
            "blind": True,
        }
        self.repo.add(
            "benchmark_reviews",
            f"{case_id}:review:{count}",
            {
                "case_id": case_id,
                "reviewer": reviewer,
                "reviewed_at": stamp,
                "payload": payload,
            },
        )
        self.repo.set_status(case_id, "reviewed", stamp)
        return {"id": f"{case_id}:review:{count}", **payload}

    def unblind(self, case_id: str) -> dict[str, str]:
        if not self.repo.rows("benchmark_reviews", case_id):
            raise BenchmarkError("unblinding requires at least one submitted review")
        packet = self.repo.rows("benchmark_blind_packets", case_id)[-1]
        self.repo.unblind(packet["id"], now())
        return dict(packet["sealed_mapping"])

    # -- views -------------------------------------------------------------

    def show(self, case_id: str) -> dict[str, Any]:
        self.register()
        case = self.repo.case(case_id)
        if case is None:
            raise BenchmarkError(f"unknown benchmark case {case_id!r}")
        runs = self.repo.rows("benchmark_runs", case_id)
        assessments = self.repo.rows("retrospective_assessments", case_id)
        revealed = case["status"] in {"revealed", "reviewed"}
        reveal_run = next((r for r in reversed(runs) if r["phase"] == "reveal"), None)
        packet = self.repo.rows("benchmark_blind_packets", case_id)
        unblinded = bool(packet and packet[-1]["unblinded_at"])
        return {
            "case_id": case_id,
            "set_id": case["set_id"],
            "status": case["status"],
            "protocol": case["protocol"],
            "label": INVALID_LABEL
            if case["status"] == "invalid"
            else (SYNTHETIC_LABEL if case["protocol"]["synthetic"] else ""),
            "snapshots": [
                r["payload"] for r in self.repo.rows("temporal_snapshots", case_id)
            ],
            "cutoff_run": next(
                (
                    {k: v for k, v in r["payload"].items() if k != "analysis"}
                    | {
                        "run_id": r["id"],
                        "rules_fingerprint": r["rules_fingerprint"],
                        "software_commit": r["software_commit"],
                        "created_at": r["created_at"],
                    }
                    for r in reversed(runs)
                    if r["phase"] == "cutoff"
                ),
                None,
            ),
            "audits": [
                {"phase": a["phase"], "valid": a["valid"], **a["payload"]}
                for a in self.repo.rows("leakage_audits", case_id)
            ],
            "baselines": [
                {
                    "kind": b["baseline_kind"],
                    "run": b["run_label"],
                    "frozen_at": b["frozen_at"],
                    "sha256": b["sha256"],
                    "payload": b["payload"],
                }
                for b in self.repo.rows("benchmark_baselines", case_id)
            ],
            "reveal": reveal_run["payload"] if reveal_run and revealed else None,
            "assessment": assessments[-1]["payload"]
            if assessments and revealed
            else None,
            "reviews": [
                {"id": r["id"], **r["payload"]}
                for r in self.repo.rows("benchmark_reviews", case_id)
            ],
            "blind_packet_mapping": packet[-1]["sealed_mapping"]
            if packet and unblinded
            else None,
            "rule_notes": [
                r["payload"] for r in self.repo.rows("benchmark_rule_notes", case_id)
            ],
        }

    def report(self, set_id: str | None = None) -> str:
        self.register()
        cases = [c for c in self.repo.cases() if not set_id or c["set_id"] == set_id]
        lines = ["# AXIS retrospective validation report", ""]
        kinds = sorted({c["protocol"]["benchmark_kind"] for c in cases})
        lines += [
            f"Benchmark kinds in this report: {', '.join(kinds) or 'none'}.",
            "",
            "A retrospective benchmark cannot establish clinical efficacy or "
            "prospective validity. No aggregate score is computed; each case is "
            "reported on its own dimensions.",
            "",
        ]
        for case in cases:
            view = self.show(case["case_id"])
            protocol = view["protocol"]
            lines += [
                f"## {case['case_id']} — {view['status']}",
                "",
                f"- kind: {protocol['benchmark_kind']}"
                + (f" ({SYNTHETIC_LABEL})" if protocol["synthetic"] else ""),
                f"- cutoff: {protocol['cutoff']} — {protocol['cutoff_rationale']}",
                f"- question: {protocol['question']}",
                f"- selection: {protocol['selection_rationale']}",
                f"- protocol fingerprint: `{protocol['protocol_fingerprint']}`",
            ]
            run = view["cutoff_run"]
            if run:
                state = run["state"]
                lines += [
                    f"- rules: `{run['rules_fingerprint']}`; software "
                    f"`{run['software_commit']}`",
                    f"- decision at T: critical uncertainty "
                    f"`{state['critical_uncertainty_id']}`; recommended "
                    f"`{state['recommended_experiment_id']}`",
                ]
                if run.get("rule_revision"):
                    lines.append("- **post-benchmark rule revision recorded**")
            for audit in view["audits"][-1:]:
                lines.append(
                    f"- leakage audit ({audit['phase']}): "
                    + ("valid" if audit["valid"] else f"**{INVALID_LABEL}**")
                )
            if view["assessment"]:
                a = view["assessment"]
                lines += ["", f"**Conclusion: {a['conclusion']['conclusion']}**", ""]
                lines += ["| dimension | result |", "|---|---|"]
                for dim, value in a["matrix"].items():
                    lines.append(f"| {dim} | {value['result']} |")
                lines += ["", "Future evidence, source by source:", ""]
                for source, rel in a["relevance"].items():
                    lines.append(
                        f"- {source} ({rel['first_publicly_accessible_date']}): "
                        f"{rel['relevance']}"
                    )
            lines.append("")
        lines += ["## Failure analysis", ""]
        flagged = False
        for case in cases:
            view = self.show(case["case_id"])
            a = view["assessment"]
            if view["status"] == "invalid":
                flagged = True
                lines.append(f"- {case['case_id']}: {INVALID_LABEL}")
            elif a:
                notes = [
                    f"{d}={v['result']}"
                    for d, v in a["matrix"].items()
                    if str(v["result"]).startswith(("invalid", "not_", "overstate"))
                    or v["result"]
                    in (
                        "future_did_not_test_the_question",
                        "future_tested_a_different_open_question",
                    )
                ]
                if a["conclusion"]["conclusion"] not in (
                    "supported_by_future_evidence",
                ):
                    notes.append(f"conclusion={a['conclusion']['conclusion']}")
                if notes:
                    flagged = True
                    lines.append(f"- {case['case_id']}: " + "; ".join(notes))
        if not flagged:
            lines.append("- none flagged by the rules (see human review).")
        lines += [
            "",
            "## Limits",
            "",
            "- Case selection is not random; see the set's selection note.",
            "- Cases drawn from the dataset the rules were developed on are "
            "development benchmarks, not independent validation.",
            "- Whether AXIS adds value over a literature-aware language-model "
            "baseline is **not demonstrated** unless such baseline runs were "
            "imported before the reveal.",
        ]
        return "\n".join(lines) + "\n"


def kinds() -> tuple[str, ...]:
    return BENCHMARK_KINDS
