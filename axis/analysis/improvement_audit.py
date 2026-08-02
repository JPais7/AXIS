"""Evidence-aware backlog generation for controlled AXIS self-improvement."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ImprovementAuditRun:
    findings: int
    critical: int
    backlog_path: Path
    report_path: Path


class ImprovementAuditor:
    """Convert quantitative weaknesses into a prioritized, reviewable backlog."""

    def audit(
        self,
        *,
        meta_analysis_path: str | Path,
        composition_path: str | Path,
        quarantine_path: str | Path,
        output_root: str | Path = Path("data/project/improvement"),
    ) -> ImprovementAuditRun:
        meta = self._indexed(Path(meta_analysis_path))
        composition = self._rows(Path(composition_path))
        quarantine = self._rows(Path(quarantine_path))
        findings: list[dict[str, object]] = []
        for gene, row in meta.items():
            heterogeneity = float(row["i_squared_percent"])
            p_value = float(row["p_value"])
            if heterogeneity >= 75:
                findings.append(
                    self._finding(
                        "critical",
                        gene,
                        "high_between_study_heterogeneity",
                        f"I_squared={heterogeneity:.1f}%",
                        "add_independent_cohorts_and_investigate_moderators",
                        "human_review",
                    )
                )
            if p_value > 0.05:
                findings.append(
                    self._finding(
                        "high",
                        gene,
                        "random_effect_not_significant",
                        f"p_value={p_value:.4g}",
                        "retain_as_exploratory_not_validated_target",
                        "automatic_guardrail",
                    )
                )
        for gene in meta:
            target_rows = [
                row for row in composition if row.get("gene_symbol") == gene
            ]
            retained = [
                float(row["effect_retained_percent"])
                for row in target_rows
                if row.get("effect_retained_percent")
            ]
            if retained and sum(value < 50 for value in retained) >= 2:
                findings.append(
                    self._finding(
                        "critical",
                        gene,
                        "composition_sensitive_signal",
                        (
                            f"{sum(value < 50 for value in retained)}/"
                            f"{len(retained)} studies retain <50% effect"
                        ),
                        "run_validated_reference_deconvolution",
                        "human_review",
                    )
                )
        if len(quarantine) < 2:
            findings.append(
                self._finding(
                    "high",
                    "PROJECT",
                    "insufficient_validation_candidates",
                    f"quarantined_candidates={len(quarantine)}",
                    "refresh_cross_repository_catalog",
                    "network_and_human_review",
                )
            )
        findings.append(
            self._finding(
                "medium",
                "PROJECT",
                "laboratory_validation_not_executed",
                "DDX24 plan is suspended pending reference deconvolution",
                "secure_clinical_and_laboratory_collaboration",
                "external_coordination",
            )
        )
        priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings.sort(
            key=lambda finding: (
                priority[str(finding["severity"])],
                str(finding["scope"]),
            )
        )
        for rank, finding in enumerate(findings, 1):
            finding["rank"] = rank
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        backlog_path = destination / "scientific-backlog.tsv"
        report_path = destination / "improvement-audit.json"
        self._write(backlog_path, findings)
        report_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "analysis_role": "controlled_self_improvement_audit",
                    "findings": findings,
                    "acceptance_policy": [
                        "One scientific change per review cycle.",
                        "All existing and new tests must pass.",
                        "Frozen discovery inputs cannot change silently.",
                        "Automated guardrails may downgrade but never promote claims.",
                        "Human approval is required for cohorts and interpretations.",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ImprovementAuditRun(
            findings=len(findings),
            critical=sum(row["severity"] == "critical" for row in findings),
            backlog_path=backlog_path,
            report_path=report_path,
        )

    @staticmethod
    def _finding(
        severity: str,
        scope: str,
        problem: str,
        evidence: str,
        next_action: str,
        authority: str,
    ) -> dict[str, object]:
        return {
            "rank": 0,
            "severity": severity,
            "scope": scope,
            "problem": problem,
            "evidence": evidence,
            "next_action": next_action,
            "required_authority": authority,
            "status": "open",
        }

    @staticmethod
    def _rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @classmethod
    def _indexed(cls, path: Path) -> dict[str, dict[str, str]]:
        return {row["gene_symbol"]: row for row in cls._rows(path)}

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=tuple(rows[0]),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
