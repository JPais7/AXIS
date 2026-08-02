"""Formal, auditable experimental-design manifests."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from axis.ingestion.geo import GSE_PATTERN, GeoApiError


@dataclass(frozen=True)
class ExperimentalDesign:
    accession: str
    assay: str
    data_type: str
    case_samples: int
    control_samples: int
    independence: str
    paired_by: str | None
    covariates: tuple[str, ...]
    recommended_method: str
    executable_method: str
    warnings: tuple[str, ...]


class DesignInspector:
    """Builds a design contract from prepared and analyzed study metadata."""

    VALID_INDEPENDENCE = {"independent", "repeated", "unknown"}

    def create(
        self,
        accession: str,
        *,
        independence: str,
        paired_by: str | None = None,
        covariates: tuple[str, ...] = (),
        data_root: str | Path = Path("data/geo"),
    ) -> tuple[Path, ...]:
        accession = accession.strip().upper()
        if not GSE_PATTERN.fullmatch(accession):
            raise ValueError(f"invalid GEO Series accession: {accession!r}")
        if independence not in self.VALID_INDEPENDENCE:
            raise ValueError("independence must be independent, repeated, or unknown")
        if paired_by is not None and independence == "independent":
            raise ValueError("paired_by is incompatible with independent samples")
        prepared_root = Path(data_root) / accession / "prepared"
        directories = (
            tuple(
                path
                for path in sorted(prepared_root.iterdir())
                if path.is_dir() and (path / "differential-analysis.json").exists()
            )
            if prepared_root.exists()
            else ()
        )
        if not directories:
            raise GeoApiError(
                f"no analyzed matrices found for {accession}; analyze it first"
            )
        paths: list[Path] = []
        for directory in directories:
            analysis = json.loads(
                (directory / "differential-analysis.json").read_text(encoding="utf-8")
            )
            design = self._design(
                accession,
                analysis=analysis,
                independence=independence,
                paired_by=paired_by,
                covariates=covariates,
            )
            path = directory / "experimental-design.json"
            path.write_text(
                json.dumps(asdict(design), indent=2) + "\n",
                encoding="utf-8",
            )
            paths.append(path)
        return tuple(paths)

    def _design(
        self,
        accession: str,
        *,
        analysis: dict[str, object],
        independence: str,
        paired_by: str | None,
        covariates: tuple[str, ...],
    ) -> ExperimentalDesign:
        data_type = str(analysis.get("data_type", "normalized microarray"))
        assay = "rna-seq" if "RNA-seq" in data_type else "microarray"
        case_value = analysis.get("case_samples", 0)
        control_value = analysis.get("control_samples", 0)
        case_samples = case_value if isinstance(case_value, int) else 0
        control_samples = control_value if isinstance(control_value, int) else 0
        warnings: list[str] = []
        if min(case_samples, control_samples) < 4:
            warnings.append("fewer than four samples in at least one group")
        if independence == "unknown":
            warnings.append("sample independence has not been established")
        if independence == "repeated" and paired_by is None:
            warnings.append("repeated samples require an explicit pairing variable")
        if not covariates:
            warnings.append("no covariates declared; review sex, age and batch")

        if assay == "microarray":
            recommended = (
                "limma with blocking/duplicateCorrelation"
                if independence == "repeated"
                else "limma empirical Bayes linear model"
            )
            method = analysis.get("method", {})
            selected = (
                str(method.get("selected", "")) if isinstance(method, dict) else ""
            )
            method_name = (
                str(method.get("name", "")) if isinstance(method, dict) else ""
            )
            if selected in {"linear-model", "moderated"} and method_name:
                executable = method_name
            else:
                executable = "Welch exploratory fallback"
        else:
            recommended = (
                "linear mixed model on normalized log abundance"
                if independence == "repeated"
                else "Welch test on normalized log abundance"
            )
            executable = "Welch test on log2(value + 1)"
            warnings.append(
                "normalized abundance is not a raw-count DESeq2/edgeR analysis"
            )
        if covariates:
            method = analysis.get("method", {})
            modeled = (
                {str(value) for value in method.get("modeled_covariates", [])}
                if isinstance(method, dict)
                else set()
            )
            unmodeled = tuple(
                covariate for covariate in covariates if covariate not in modeled
            )
            if unmodeled:
                warnings.append(
                    "the executable analysis does not model declared "
                    f"covariates: {', '.join(unmodeled)}"
                )
        return ExperimentalDesign(
            accession=accession,
            assay=assay,
            data_type=data_type,
            case_samples=case_samples,
            control_samples=control_samples,
            independence=independence,
            paired_by=paired_by,
            covariates=covariates,
            recommended_method=recommended,
            executable_method=executable,
            warnings=tuple(warnings),
        )
