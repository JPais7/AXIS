"""Reproducible publication manifest and conservative manuscript scaffold."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class PublicationPackageRun:
    artifacts: int
    manifest_path: Path
    outline_path: Path
    checklist_path: Path


class PublicationPackager:
    """Bind article claims to exact local results and explicit limitations."""

    def build(
        self,
        *,
        artifacts: Mapping[str, str | Path],
        meta_analysis_path: str | Path,
        composition_path: str | Path,
        output_root: str | Path = Path("data/publication"),
    ) -> PublicationPackageRun:
        resolved = {name: Path(path) for name, path in artifacts.items()}
        missing = [str(path) for path in resolved.values() if not path.exists()]
        if missing:
            raise ValueError(f"publication artifacts are missing: {missing}")
        meta = self._indexed(Path(meta_analysis_path))
        composition = self._rows(Path(composition_path))
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        manifest_path = destination / "reproducibility-manifest.json"
        outline_path = destination / "manuscript-outline.md"
        checklist_path = destination / "reporting-checklist.tsv"
        manifest_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "package_status": "computational_draft_not_peer_reviewed",
                    "artifacts": {
                        name: {
                            "path": str(path),
                            "sha256": self._sha256(path),
                            "bytes": path.stat().st_size,
                        }
                        for name, path in resolved.items()
                    },
                    "claim_policy": {
                        "DDX24": "exploratory_composition_sensitive_hypothesis",
                        "ADA": "associated_but_systemic_inhibition_deprioritised",
                        "drug_discovery": "not_established",
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        outline_path.write_text(
            self._outline(meta, composition, resolved),
            encoding="utf-8",
        )
        checklist = self._checklist(resolved)
        with checklist_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=tuple(checklist[0]),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(checklist)
        return PublicationPackageRun(
            artifacts=len(resolved),
            manifest_path=manifest_path,
            outline_path=outline_path,
            checklist_path=checklist_path,
        )

    @staticmethod
    def _outline(
        meta: dict[str, dict[str, str]],
        composition: list[dict[str, str]],
        artifacts: dict[str, Path],
    ) -> str:
        ddx = meta["DDX24"]
        ada = meta["ADA"]
        ddx_sensitive = sum(
            row.get("gene_symbol") == "DDX24"
            and bool(row.get("effect_retained_percent"))
            and float(row["effect_retained_percent"]) < 50
            for row in composition
        )
        return "\n".join(
            [
                "# Manuscript outline - computational draft",
                "",
                "## Working title",
                "",
                (
                    "Cross-cohort transcriptomic assessment identifies "
                    "composition-sensitive DDX24 and ADA signals in axial "
                    "spondyloarthritis"
                ),
                "",
                "## Permitted central claim",
                "",
                (
                    "Three discovery cohorts show directionally concordant "
                    "expression, but random-effects and composition diagnostics "
                    "substantially limit therapeutic interpretation."
                ),
                "",
                "## Results that must be reported",
                "",
                (
                    f"- DDX24 random-effects estimate: {ddx['pooled_effect']}; "
                    f"95% CI {ddx['ci_low']} to {ddx['ci_high']}; "
                    f"p={ddx['p_value']}; I2={ddx['i_squared_percent']}%."
                ),
                (
                    f"- ADA random-effects estimate: {ada['pooled_effect']}; "
                    f"95% CI {ada['ci_low']} to {ada['ci_high']}; "
                    f"p={ada['p_value']}; I2={ada['i_squared_percent']}%."
                ),
                (
                    f"- DDX24 retained less than 50% of its unadjusted effect "
                    f"in {ddx_sensitive} marker-score-adjusted studies."
                ),
                "- External validation direction conflicts must be reported.",
                "- Single-cell evidence must remain separate from bulk discovery.",
                "- No disease-specific causal genetic evidence was identified.",
                "",
                "## Required sections",
                "",
                "1. Preregistered eligibility and frozen discovery cohorts.",
                "2. Study-specific normalization, QC and differential models.",
                "3. Random-effects target meta-analysis and sensitivity analysis.",
                "4. Cell-composition confounding diagnostic.",
                "5. Independent bulk and single-cell validation.",
                "6. Genetics, tractability and therapeutic-direction assessment.",
                "7. Limitations and falsification experiments.",
                "",
                "## Prohibited claims",
                "",
                "- DDX24 causes axial spondyloarthritis.",
                "- DDX24 is a validated therapeutic target.",
                "- ADA inhibition is supported as an axSpA treatment.",
                "- Marker scores are measured cell proportions.",
                "- The laboratory experiment has been executed.",
                "",
                "## Bound artifacts",
                "",
                *[f"- {name}: `{path}`" for name, path in artifacts.items()],
                "",
            ]
        )

    @staticmethod
    def _checklist(
        artifacts: dict[str, Path],
    ) -> list[dict[str, object]]:
        return [
            {
                "item": "frozen_discovery_cohorts",
                "status": "complete",
                "evidence": artifacts["discovery_lock"],
            },
            {
                "item": "random_effects_and_heterogeneity",
                "status": "complete",
                "evidence": artifacts["meta_analysis"],
            },
            {
                "item": "leave_one_study_out",
                "status": "complete",
                "evidence": artifacts["leave_one_out"],
            },
            {
                "item": "cell_composition_sensitivity",
                "status": "diagnostic_only",
                "evidence": artifacts["composition"],
            },
            {
                "item": "validated_reference_deconvolution",
                "status": "missing",
                "evidence": "",
            },
            {
                "item": "independent_functional_validation",
                "status": "planned_not_executed",
                "evidence": artifacts["laboratory_plan"],
            },
        ]

    @staticmethod
    def _rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @classmethod
    def _indexed(cls, path: Path) -> dict[str, dict[str, str]]:
        return {row["gene_symbol"]: row for row in cls._rows(path)}

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
