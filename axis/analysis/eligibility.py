"""Human-reviewed study eligibility gates for cross-study inference."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class StudyEligibility:
    accession: str
    matrix: str
    decision: str
    rationale: str
    species: str
    tissue: str
    phenotype: str
    allowed_roles: tuple[str, ...]
    assessed_at: str
    gene_results_checksum: str
    design_path: str | None
    qc_report_path: str
    case_samples: int
    control_samples: int
    outlier_samples: tuple[str, ...]
    minimum_sample_correlation: float
    unmodeled_covariates: tuple[str, ...]


class StudyAssessor:
    VALID_DECISIONS = {"approved", "review", "excluded"}
    VALID_ROLES = {
        "discovery",
        "external_validation",
        "mechanistic",
        "treatment_response",
    }

    def assess(
        self,
        accession: str,
        *,
        decision: str,
        rationale: str,
        species: str,
        tissue: str,
        phenotype: str,
        allowed_roles: tuple[str, ...],
        data_root: str | Path = Path("data/geo"),
    ) -> tuple[Path, ...]:
        accession = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        if decision not in self.VALID_DECISIONS:
            raise ValueError("decision must be approved, review, or excluded")
        for name, value in (
            ("rationale", rationale),
            ("species", species),
            ("tissue", tissue),
            ("phenotype", phenotype),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        normalized_roles = tuple(
            dict.fromkeys(role.strip().lower() for role in allowed_roles)
        )
        invalid_roles = set(normalized_roles) - self.VALID_ROLES
        if invalid_roles:
            raise ValueError(f"invalid eligibility roles: {sorted(invalid_roles)}")
        if decision == "approved" and not normalized_roles:
            raise ValueError("approved studies require at least one allowed role")
        prepared_root = Path(data_root) / accession / "prepared"
        gene_paths = tuple(sorted(prepared_root.glob("*/gene-level-results.tsv")))
        if not gene_paths:
            raise GeoApiError(
                f"no gene-level results found for {accession}; analyze it first"
            )
        outputs: list[Path] = []
        for gene_path in gene_paths:
            directory = gene_path.parent
            qc_path = directory / "qc" / "qc-report.json"
            if not qc_path.exists():
                raise GeoApiError(
                    f"QC report is missing for {directory.name}; "
                    f"run 'axis qc {accession}' first"
                )
            qc = json.loads(qc_path.read_text(encoding="utf-8"))
            design_path = directory / "experimental-design.json"
            analysis_path = directory / "differential-analysis.json"
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            method = analysis.get("method", {})
            unmodeled = (
                tuple(method.get("declared_but_unmodeled_covariates", ()))
                if isinstance(method, dict)
                else ()
            )
            checksum = hashlib.sha256(gene_path.read_bytes()).hexdigest()
            eligibility = StudyEligibility(
                accession=accession,
                matrix=directory.name,
                decision=decision,
                rationale=rationale.strip(),
                species=species.strip(),
                tissue=tissue.strip(),
                phenotype=phenotype.strip(),
                allowed_roles=normalized_roles,
                assessed_at=datetime.now(UTC).isoformat(),
                gene_results_checksum=f"sha256:{checksum}",
                design_path=str(design_path) if design_path.exists() else None,
                qc_report_path=str(qc_path),
                case_samples=int(qc["case_samples"]),
                control_samples=int(qc["control_samples"]),
                outlier_samples=tuple(qc["outlier_samples"]),
                minimum_sample_correlation=float(qc["minimum_sample_correlation"]),
                unmodeled_covariates=unmodeled,
            )
            output = directory / "study-eligibility.json"
            output.write_text(
                json.dumps(asdict(eligibility), indent=2) + "\n",
                encoding="utf-8",
            )
            outputs.append(output)
        return tuple(outputs)


def verify_study_eligibility(
    gene_path: Path,
    *,
    required_role: str | None = None,
) -> dict[str, object]:
    """Require a current approved eligibility manifest for one result file."""
    path = gene_path.with_name("study-eligibility.json")
    if not path.exists():
        raise GeoApiError(
            f"eligibility manifest is missing for {gene_path.parent.name}; "
            "run 'axis assess ...' first"
        )
    payload = cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )
    if payload.get("decision") != "approved":
        raise GeoApiError(
            f"study {payload.get('accession')} is not approved "
            f"(decision={payload.get('decision')})"
        )
    if required_role is not None:
        roles = payload.get("allowed_roles", ())
        if not isinstance(roles, list) or required_role not in roles:
            raise GeoApiError(
                f"study {payload.get('accession')} is not approved for "
                f"role {required_role!r}"
            )
    checksum = "sha256:" + hashlib.sha256(gene_path.read_bytes()).hexdigest()
    if payload.get("gene_results_checksum") != checksum:
        raise GeoApiError(
            f"eligibility for {payload.get('accession')} is stale; "
            "results changed after assessment"
        )
    return payload
