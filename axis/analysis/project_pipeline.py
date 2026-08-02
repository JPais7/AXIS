"""Resumable, guarded orchestration of the AXIS discovery project."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from axis.analysis.article_finalization import ArticleFinalizer
from axis.analysis.cd8_cross_cohort import Cd8CrossCohortAnalyzer
from axis.analysis.cd8_evidence_review import Cd8EvidenceReviewer
from axis.analysis.cell_composition import CellCompositionDiagnostic
from axis.analysis.confounding_freeze import ConfoundingFreezeBuilder
from axis.analysis.ddx24_validation import Ddx24ValidationPlanner
from axis.analysis.emtab10948_review import Emtab10948Reviewer
from axis.analysis.emtab12805_review import Emtab12805Reviewer
from axis.analysis.gene_evidence import GeneEvidenceBuilder
from axis.analysis.gse232131_sample_audit import Gse232131SampleAuditor
from axis.analysis.gse288581_validation import Gse288581Validator
from axis.analysis.gse299639_review import Gse299639Reviewer
from axis.analysis.hierarchical_evidence import HierarchicalEvidenceAnalyzer
from axis.analysis.improvement_audit import ImprovementAuditor
from axis.analysis.publication_package import PublicationPackager
from axis.analysis.publication_readiness import PublicationReadinessBuilder
from axis.analysis.secondary_single_cell_review import (
    SecondarySingleCellReviewer,
)
from axis.analysis.single_cell_reference_expansion import (
    SingleCellReferenceExpander,
)
from axis.analysis.single_cell_robustness import SingleCellRobustnessAnalyzer
from axis.analysis.study_quarantine import StudyQuarantineBuilder
from axis.analysis.target_deep_dive import TargetDeepDiveBuilder
from axis.analysis.target_meta_analysis import TargetMetaAnalyzer
from axis.analysis.validation_cohort_selection import ValidationCohortSelector


@dataclass(frozen=True)
class ProjectStage:
    order: int
    name: str
    status: str
    message: str
    artifacts: tuple[str, ...]


@dataclass(frozen=True)
class ProjectPipelineRun:
    completed: int
    blocked: int
    failed: int
    status_path: Path
    table_path: Path
    report_path: Path
    lock_path: Path


class AxisProjectPipeline:
    """Audit upstream evidence and rebuild safe, deterministic downstream work."""

    DISCOVERY_STUDIES = ("GSE25101", "GSE18781", "GSE73754")

    def run(
        self,
        *,
        workspace: str | Path = Path("."),
        output_root: str | Path = Path("data/project"),
        accept_input_changes: bool = False,
    ) -> ProjectPipelineRun:
        root = Path(workspace)
        output = root / output_root
        output.mkdir(parents=True, exist_ok=True)
        lock_path = output / "discovery-input-lock.json"
        current_lock = self._input_lock(root)
        self._guard_lock(
            lock_path,
            current_lock,
            accept_input_changes=accept_input_changes,
        )

        stages: list[ProjectStage] = []
        blocked = False
        definitions = self._definitions(root)
        for order, (name, message, artifacts, action) in enumerate(definitions, 1):
            missing = tuple(str(path) for path in artifacts if not path.exists())
            if blocked:
                stages.append(
                    ProjectStage(
                        order,
                        name,
                        "blocked",
                        "Blocked by an earlier incomplete or failed stage.",
                        tuple(str(path) for path in artifacts),
                    )
                )
                continue
            if missing:
                stages.append(
                    ProjectStage(
                        order,
                        name,
                        "blocked",
                        f"Missing required artifacts: {'; '.join(missing)}",
                        tuple(str(path) for path in artifacts),
                    )
                )
                blocked = True
                continue
            try:
                if action is not None:
                    action()
                stages.append(
                    ProjectStage(
                        order,
                        name,
                        "completed",
                        message,
                        tuple(str(path) for path in artifacts),
                    )
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                stages.append(
                    ProjectStage(
                        order,
                        name,
                        "failed",
                        f"{type(error).__name__}: {error}",
                        tuple(str(path) for path in artifacts),
                    )
                )
                blocked = True

        return self._write_outputs(output, lock_path, stages, current_lock)

    def status(
        self,
        *,
        workspace: str | Path = Path("."),
        output_root: str | Path = Path("data/project"),
    ) -> ProjectPipelineRun:
        root = Path(workspace)
        output = root / output_root
        output.mkdir(parents=True, exist_ok=True)
        lock_path = output / "discovery-input-lock.json"
        stages = []
        blocked = False
        for order, (name, message, artifacts, _) in enumerate(
            self._definitions(root), 1
        ):
            missing = tuple(str(path) for path in artifacts if not path.exists())
            if missing or blocked:
                status = "blocked"
                detail = (
                    f"Missing required artifacts: {'; '.join(missing)}"
                    if missing
                    else "Blocked by an earlier incomplete stage."
                )
                blocked = True
            else:
                status = "completed"
                detail = message
            stages.append(
                ProjectStage(
                    order,
                    name,
                    status,
                    detail,
                    tuple(str(path) for path in artifacts),
                )
            )
        return self._write_outputs(
            output, lock_path, stages, self._input_lock(root)
        )

    def _definitions(
        self, root: Path
    ) -> tuple[
        tuple[str, str, tuple[Path, ...], Callable[[], object] | None], ...
    ]:
        prepared = tuple(
            root
            / "data"
            / "geo"
            / accession
            / "prepared"
            / f"{accession}_series_matrix"
            for accession in self.DISCOVERY_STUDIES
        )
        gene_results = tuple(path / "gene-level-results.tsv" for path in prepared)
        eligibility = tuple(path / "study-eligibility.json" for path in prepared)
        preparations = tuple(path / "preparation.json" for path in prepared)
        qc = tuple(path / "qc" / "qc-report.json" for path in prepared)
        matrices = tuple(path / "case-matrix.tsv.gz" for path in prepared) + tuple(
            path / "control-matrix.tsv.gz" for path in prepared
        )

        gene_root = root / "data" / "analysis" / "gene-evidence"
        deep_root = gene_root / "deep-dive"
        decisions = deep_root / "decisions"
        return (
            (
                "study_search",
                "Study catalogue is available for eligibility review.",
                (root / "data" / "catalog" / "study-catalog.tsv",),
                None,
            ),
            (
                "eligibility",
                "Frozen discovery studies have explicit eligibility decisions.",
                eligibility,
                lambda: self._validate_eligibility(eligibility),
            ),
            (
                "download",
                "Local case and control expression matrices are available.",
                matrices,
                None,
            ),
            (
                "preparation",
                "All discovery matrices have preparation manifests.",
                preparations,
                None,
            ),
            (
                "quality_control",
                "All discovery studies have quality-control reports.",
                qc,
                None,
            ),
            (
                "expression_analysis",
                "Gene-level results are available for every discovery study.",
                gene_results,
                None,
            ),
            (
                "study_comparison",
                "Direction concordance is available across the frozen studies.",
                (
                    root
                    / "data"
                    / "analysis"
                    / "three-study-concordance"
                    / "direction-concordance.tsv",
                ),
                None,
            ),
            (
                "directional_synthesis",
                (
                    "Combined directional evidence is available; raw effects "
                    "are not pooled because platform-compatible standard errors "
                    "are unavailable."
                ),
                (
                    root
                    / "data"
                    / "analysis"
                    / "three-study-concordance"
                    / "direction-concordance-analysis.json",
                ),
                lambda: self._validate_synthesis(root),
            ),
            (
                "target_meta_analysis",
                "Random-effects estimates and forest plots were rebuilt.",
                gene_results,
                lambda: self._build_target_meta_analysis(root),
            ),
            (
                "cell_composition_diagnostic",
                "Cell-lineage marker-score sensitivity was rebuilt.",
                (
                    root / "data/geo/platforms/GPL6947/GPL6947.annot.gz",
                    root / "data/geo/platforms/GPL570/GPL570.annot.gz",
                    root / "data/geo/platforms/GPL10558/GPL10558.annot.gz",
                ),
                lambda: self._build_cell_composition(root),
            ),
            (
                "external_and_single_cell_validation",
                "Independent bulk and single-cell validation tables are present.",
                (
                    root
                    / "data"
                    / "analysis"
                    / "external-validation"
                    / "GSE181364-candidate-validation.tsv",
                    root
                    / "data"
                    / "single-cell"
                    / "GSE194315"
                    / "transcriptome"
                    / "integrated-candidates.tsv",
                ),
                None,
            ),
            (
                "incremental_study_quarantine",
                "New studies were isolated in a manual validation queue.",
                (
                    root / "data/catalog/study-catalog.tsv",
                    root
                    / (
                        "data/catalog/cross-repository/"
                        "cross-repository-catalog.tsv"
                    ),
                ),
                lambda: self._build_quarantine(root),
            ),
            (
                "validation_cohort_selection",
                (
                    "Independent bulk and single-cell candidates were ranked "
                    "for manual review."
                ),
                (
                    root
                    / (
                        "data/catalog/incremental-quarantine/"
                        "study-review-queue.tsv"
                    ),
                    root
                    / "data/catalog/cohort-selection/cohort-evaluation.tsv",
                    root
                    / "data/catalog/sample-proposals/study-validation.tsv",
                    root
                    / (
                        "data/catalog/participant-expansion/"
                        "participant-cohorts.tsv"
                    ),
                ),
                lambda: self._select_validation_cohorts(root),
            ),
            (
                "gse299639_validation_review",
                (
                    "GSE299639 was frozen as exploratory directional support "
                    "with unresolved treatment and count-data gates."
                ),
                (
                    root
                    / (
                        "data/geo/GSE299639/supplementary/"
                        "GSE299639_genes_TPM.anno.txt.gz"
                    ),
                    root
                    / (
                        "data/geo/GSE299639/prepared/rnaseq-normalized/"
                        "gene-level-results.tsv"
                    ),
                    root
                    / (
                        "data/geo/GSE299639/prepared/"
                        "rnaseq-normalized-without-AS-M1/"
                        "gene-level-results.tsv"
                    ),
                ),
                lambda: self._review_gse299639(root),
            ),
            (
                "emtab12805_single_cell_review",
                (
                    "E-MTAB-12805 and GSE232131 were collapsed to one "
                    "mechanistic cohort with reference-use gates."
                ),
                (
                    root
                    / (
                        "data/catalog/cross-repository/"
                        "cross-repository-catalog.tsv"
                    ),
                ),
                lambda: self._review_emtab12805(root),
            ),
            (
                "gse232131_sample_audit",
                (
                    "GSE232131 donor pooling, conditions and file inventory "
                    "were audited before any large matrix download."
                ),
                (
                    root
                    / "data/geo/GSE232131/GSE232131_series_matrix.txt.gz",
                ),
                lambda: self._audit_gse232131_samples(root),
            ),
            (
                "emtab10948_single_cell_review",
                (
                    "E-MTAB-10948 was restricted to paired blood-synovial "
                    "Treg mechanism analysis."
                ),
                (
                    root
                    / (
                        "data/catalog/cross-repository/sample-audit/"
                        "E-MTAB-10948/study-audit.json"
                    ),
                    root
                    / (
                        "data/catalog/cross-repository/sample-audit/"
                        "E-MTAB-10948/E-MTAB-10948.sdrf.txt"
                    ),
                ),
                lambda: self._review_emtab10948(root),
            ),
            (
                "gse194315_reference_expansion",
                (
                    "DDX24 and ADA were tested across every adequately "
                    "replicated GSE194315 PBMC cell type."
                ),
                (
                    root
                    / (
                        "data/single-cell/GSE194315/"
                        "GSE194315_PBMC-01-07_processed_data_files.tar.gz"
                    ),
                    root
                    / "data/single-cell/GSE194315/cell-metadata.tsv.gz",
                    root
                    / (
                        "data/single-cell/GSE194315/plan/"
                        "cell-type-design.tsv"
                    ),
                ),
                lambda: self._expand_single_cell_reference(root),
            ),
            (
                "gse194315_robustness",
                (
                    "Available batch covariates, participant influence and "
                    "lineage consistency were tested."
                ),
                (
                    root
                    / (
                        "data/single-cell/GSE194315/reference-expansion/"
                        "pseudobulk/targeted-pseudobulk.tsv"
                    ),
                    root
                    / "data/single-cell/GSE194315/cell-metadata.tsv.gz",
                ),
                lambda: self._analyze_single_cell_robustness(root),
            ),
            (
                "secondary_single_cell_selection",
                (
                    "GSE288581 and GSE277117 were audited; GSE288581 was "
                    "selected for targeted CD8 validation."
                ),
                (
                    root
                    / (
                        "data/geo/GSE277117/"
                        "GSE277117-GPL21697_series_matrix.txt.gz"
                    ),
                    root
                    / (
                        "data/geo/GSE277117/"
                        "GSE277117-GPL28038_series_matrix.txt.gz"
                    ),
                    root
                    / "data/geo/GSE288581/GSE288581_series_matrix.txt.gz",
                ),
                lambda: self._review_secondary_single_cell(root),
            ),
            (
                "gse288581_target_validation",
                (
                    "DDX24 and ADA were tested by donor in an independent "
                    "CD8-memory case-control cohort."
                ),
                (
                    root
                    / "data/geo/GSE288581/GSE288581_series_matrix.txt.gz",
                ),
                lambda: self._validate_gse288581(root),
            ),
            (
                "cd8_cross_cohort_synthesis",
                (
                    "Independent donor-level CD8 effects were combined, with "
                    "CD8 cell-state sensitivity analysis."
                ),
                (
                    root
                    / (
                        "data/analysis/single-cell-validation/CD8-cross-cohort/"
                        "cross-cohort-summary.tsv"
                    ),
                    root
                    / (
                        "data/analysis/single-cell-validation/CD8-cross-cohort/"
                        "cd8-state-sensitivity.tsv"
                    ),
                ),
                lambda: self._synthesize_cd8(root),
            ),
            (
                "cd8_evidence_review",
                (
                    "Third-cohort eligibility and systematic-review "
                    "publication readiness were formally audited."
                ),
                (
                    root
                    / (
                        "data/analysis/single-cell-validation/"
                        "CD8-evidence-review/candidate-cohort-registry.tsv"
                    ),
                    root
                    / (
                        "data/analysis/single-cell-validation/"
                        "CD8-evidence-review/publication-readiness.json"
                    ),
                ),
                lambda: Cd8EvidenceReviewer().review(
                    output_root=root
                    / (
                        "data/analysis/single-cell-validation/"
                        "CD8-evidence-review"
                    )
                ),
            ),
            (
                "hierarchical_multimodal_synthesis",
                (
                    "CD8, microarray and whole-blood sequencing evidence was "
                    "synthesized in separate compatible strata."
                ),
                (
                    root
                    / (
                        "data/analysis/hierarchical-target-evidence/"
                        "hierarchical-synthesis.tsv"
                    ),
                    root
                    / (
                        "data/analysis/hierarchical-target-evidence/"
                        "context-summary.tsv"
                    ),
                ),
                lambda: self._synthesize_hierarchical(root),
            ),
            (
                "ddx24_confounding_and_evidence_freeze",
                (
                    "Available confounders were audited and confirmation, "
                    "refutation and safety criteria were frozen."
                ),
                (
                    root
                    / "data/analysis/ddx24-evidence-freeze/confounding-audit.tsv",
                    root
                    / (
                        "data/analysis/ddx24-evidence-freeze/"
                        "confirmation-refutation-criteria.tsv"
                    ),
                    root
                    / "data/analysis/ddx24-evidence-freeze/evidence-freeze.json",
                ),
                lambda: self._freeze_ddx24(root),
            ),
            (
                "ddx24_manuscript_and_rt_qpcr_protocol",
                (
                    "A data-bound manuscript draft and prospective RT-qPCR "
                    "falsification protocol were generated."
                ),
                (
                    root
                    / "data/publication/ddx24-study/manuscript-draft.md",
                    root
                    / (
                        "data/publication/ddx24-study/"
                        "rt-qpcr-operational-protocol.md"
                    ),
                    root
                    / (
                        "data/publication/ddx24-study/"
                        "manuscript-completion-checklist.tsv"
                    ),
                ),
                lambda: self._prepare_ddx24_publication(root),
            ),
            (
                "ddx24_article_finalization",
                (
                    "Publication figures, verified references and an "
                    "independent-review form were generated."
                ),
                (
                    root
                    / (
                        "data/publication/ddx24-study/figures/"
                        "figure-1-cohort-effects.png"
                    ),
                    root
                    / (
                        "data/publication/ddx24-study/figures/"
                        "figure-2-context-concordance.png"
                    ),
                    root / "data/publication/ddx24-study/references.bib",
                ),
                lambda: ArticleFinalizer().finalize(
                    cohort_path=root
                    / (
                        "data/analysis/hierarchical-target-evidence/"
                        "cohort-evidence.tsv"
                    ),
                    context_path=root
                    / (
                        "data/analysis/hierarchical-target-evidence/"
                        "context-summary.tsv"
                    ),
                    output_root=root / "data/publication/ddx24-study",
                ),
            ),
            (
                "genetics_mechanism_pharmacology",
                "Genetic and target-intelligence evidence is locally cached.",
                (
                    deep_root / "genetics" / "as-genetic-evidence.tsv",
                    deep_root / "target-intelligence.tsv",
                    deep_root / "dossiers" / "DDX24.json",
                    deep_root / "dossiers" / "ADA.json",
                ),
                None,
            ),
            (
                "gene_ranking",
                "Conservative cross-platform gene evidence was rebuilt.",
                (
                    root
                    / "data"
                    / "analysis"
                    / "concordance"
                    / "exploratory-shortlist.tsv",
                    root
                    / "data"
                    / "analysis"
                    / "karow"
                    / "candidate-validation.tsv",
                ),
                lambda: self._build_gene_evidence(root),
            ),
            (
                "target_decisions",
                "DDX24 and ADA decision dossiers were rebuilt.",
                (gene_root / "gene-evidence-master.tsv",),
                lambda: self._build_deep_dive(root),
            ),
            (
                "article_outputs",
                "Decision tables and the preregistered DDX24 plan were rebuilt.",
                (decisions / "target-decisions.tsv",),
                lambda: self._build_article_outputs(root),
            ),
            (
                "self_improvement_audit",
                "Evidence weaknesses were converted into a prioritized backlog.",
                (
                    root
                    / (
                        "data/analysis/target-meta-analysis/"
                        "target-meta-analysis.tsv"
                    ),
                    root
                    / (
                        "data/analysis/cell-composition-diagnostic/"
                        "target-composition-adjustment.tsv"
                    ),
                    root
                    / (
                        "data/catalog/incremental-quarantine/"
                        "study-review-queue.tsv"
                    ),
                ),
                lambda: self._build_improvement_audit(root),
            ),
            (
                "publication_package",
                "A checksum-bound computational manuscript package was rebuilt.",
                (
                    deep_root
                    / "ddx24-validation"
                    / "ddx24-preregistered-plan.json",
                ),
                lambda: self._build_publication_package(root),
            ),
        )

    @staticmethod
    def _validate_eligibility(paths: tuple[Path, ...]) -> None:
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("decision") != "approved":
                raise ValueError(f"discovery study is not approved: {path}")

    def _validate_synthesis(self, root: Path) -> None:
        path = (
            root
            / "data"
            / "analysis"
            / "three-study-concordance"
            / "direction-concordance-analysis.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        if tuple(payload.get("studies", ())) != self.DISCOVERY_STUDIES:
            raise ValueError("directional synthesis does not match frozen studies")
        if payload.get("publication_eligible") is not False:
            raise ValueError("exploratory synthesis must not be publication eligible")

    @staticmethod
    def _build_gene_evidence(root: Path) -> object:
        return GeneEvidenceBuilder().build(
            shortlist_path=root
            / "data/analysis/concordance/exploratory-shortlist.tsv",
            single_cell_path=root
            / (
                "data/single-cell/GSE194315/transcriptome/"
                "integrated-candidates.tsv"
            ),
            causal_review_path=root
            / (
                "data/single-cell/GSE194315/candidate-review/"
                "candidate-causal-review.tsv"
            ),
            karow_signature_path=root
            / "data/analysis/karow/published-signatures.tsv",
            genetics_path=root
            / (
                "data/single-cell/GSE194315/candidate-review/genetics/"
                "as-genetic-evidence.tsv"
            ),
            intelligence_path=root
            / (
                "data/single-cell/GSE194315/candidate-review/intelligence/"
                "target-intelligence.tsv"
            ),
            output_root=root / "data/analysis/gene-evidence",
        )

    def _build_target_meta_analysis(self, root: Path) -> object:
        studies = {
            accession: (
                root
                / "data"
                / "geo"
                / accession
                / "prepared"
                / f"{accession}_series_matrix"
            )
            for accession in self.DISCOVERY_STUDIES
        }
        return TargetMetaAnalyzer().analyze(
            studies=studies,
            output_root=root / "data/analysis/target-meta-analysis",
        )

    def _build_cell_composition(self, root: Path) -> object:
        studies = {
            accession: (
                root
                / "data"
                / "geo"
                / accession
                / "prepared"
                / f"{accession}_series_matrix"
            )
            for accession in self.DISCOVERY_STUDIES
        }
        platforms = {
            "GSE25101": root
            / "data/geo/platforms/GPL6947/GPL6947.annot.gz",
            "GSE18781": root
            / "data/geo/platforms/GPL570/GPL570.annot.gz",
            "GSE73754": root
            / "data/geo/platforms/GPL10558/GPL10558.annot.gz",
        }
        return CellCompositionDiagnostic().analyze(
            studies=studies,
            platform_annotations=platforms,
            output_root=root / "data/analysis/cell-composition-diagnostic",
        )

    @staticmethod
    def _build_quarantine(root: Path) -> object:
        return StudyQuarantineBuilder().build(
            geo_catalog_path=root / "data/catalog/study-catalog.tsv",
            cross_repository_path=root
            / "data/catalog/cross-repository/cross-repository-catalog.tsv",
            output_root=root / "data/catalog/incremental-quarantine",
        )

    @staticmethod
    def _select_validation_cohorts(root: Path) -> object:
        return ValidationCohortSelector().select(
            quarantine_path=root
            / "data/catalog/incremental-quarantine/study-review-queue.tsv",
            cohort_evaluation_path=root
            / "data/catalog/cohort-selection/cohort-evaluation.tsv",
            sample_validation_path=root
            / "data/catalog/sample-proposals/study-validation.tsv",
            participant_cohorts_path=root
            / "data/catalog/participant-expansion/participant-cohorts.tsv",
            output_root=root / "data/catalog/validation-cohort-selection",
        )

    @staticmethod
    def _review_gse299639(root: Path) -> object:
        prepared = root / "data/geo/GSE299639/prepared"
        return Gse299639Reviewer().review(
            abundance_path=root
            / (
                "data/geo/GSE299639/supplementary/"
                "GSE299639_genes_TPM.anno.txt.gz"
            ),
            full_results_path=prepared
            / "rnaseq-normalized/gene-level-results.tsv",
            sensitivity_results_path=prepared
            / "rnaseq-normalized-without-AS-M1/gene-level-results.tsv",
            qc_path=prepared / "rnaseq-normalized/qc/qc-report.json",
            sensitivity_summary_path=prepared
            / "rnaseq-normalized/outlier-sensitivity.json",
            output_root=root
            / "data/analysis/external-validation/GSE299639",
        )

    @staticmethod
    def _review_emtab12805(root: Path) -> object:
        return Emtab12805Reviewer().review(
            output_root=root
            / "data/analysis/single-cell-validation/E-MTAB-12805"
        )

    @staticmethod
    def _audit_gse232131_samples(root: Path) -> object:
        return Gse232131SampleAuditor().audit(
            matrix_path=root
            / "data/geo/GSE232131/GSE232131_series_matrix.txt.gz",
            output_root=root
            / (
                "data/analysis/single-cell-validation/E-MTAB-12805/"
                "sample-audit"
            ),
        )

    @staticmethod
    def _review_emtab10948(root: Path) -> object:
        source = (
            root
            / "data/catalog/cross-repository/sample-audit/E-MTAB-10948"
        )
        return Emtab10948Reviewer().review(
            study_audit_path=source / "study-audit.json",
            sdrf_path=source / "E-MTAB-10948.sdrf.txt",
            output_root=root
            / "data/analysis/single-cell-validation/E-MTAB-10948",
        )

    @staticmethod
    def _expand_single_cell_reference(root: Path) -> object:
        single_cell = root / "data/single-cell/GSE194315"
        return SingleCellReferenceExpander().expand(
            archive_path=single_cell
            / "GSE194315_PBMC-01-07_processed_data_files.tar.gz",
            metadata_path=single_cell / "cell-metadata.tsv.gz",
            cell_type_design_path=single_cell
            / "plan/cell-type-design.tsv",
            output_root=single_cell / "reference-expansion",
        )

    @staticmethod
    def _analyze_single_cell_robustness(root: Path) -> object:
        single_cell = root / "data/single-cell/GSE194315"
        return SingleCellRobustnessAnalyzer().analyze(
            pseudobulk_path=single_cell
            / (
                "reference-expansion/pseudobulk/"
                "targeted-pseudobulk.tsv"
            ),
            metadata_path=single_cell / "cell-metadata.tsv.gz",
            reference_results_path=single_cell
            / (
                "reference-expansion/"
                "target-cell-type-validation.tsv"
            ),
            output_root=single_cell / "robustness",
        )

    @staticmethod
    def _review_secondary_single_cell(root: Path) -> object:
        return SecondarySingleCellReviewer().review(
            gse277117_matrices=(
                root
                / (
                    "data/geo/GSE277117/"
                    "GSE277117-GPL21697_series_matrix.txt.gz"
                ),
                root
                / (
                    "data/geo/GSE277117/"
                    "GSE277117-GPL28038_series_matrix.txt.gz"
                ),
            ),
            gse288581_matrix=root
            / "data/geo/GSE288581/GSE288581_series_matrix.txt.gz",
            output_root=root
            / "data/analysis/single-cell-validation/secondary-cohorts",
        )

    @staticmethod
    def _validate_gse288581(root: Path) -> object:
        with Gse288581Validator() as validator:
            return validator.validate(
                series_matrix_path=root
                / "data/geo/GSE288581/GSE288581_series_matrix.txt.gz",
                output_root=root
                / "data/analysis/single-cell-validation/GSE288581",
            )

    @staticmethod
    def _synthesize_cd8(root: Path) -> object:
        return Cd8CrossCohortAnalyzer().analyze(
            gse194315_path=root
            / "data/single-cell/GSE194315/robustness/batch-adjusted-targets.tsv",
            gse288581_path=root
            / (
                "data/analysis/single-cell-validation/GSE288581/"
                "target-validation.tsv"
            ),
            output_root=root
            / "data/analysis/single-cell-validation/CD8-cross-cohort",
        )

    @staticmethod
    def _synthesize_hierarchical(root: Path) -> object:
        return HierarchicalEvidenceAnalyzer().analyze(
            cd8_effects_path=root
            / (
                "data/analysis/single-cell-validation/CD8-cross-cohort/"
                "cohort-effects.tsv"
            ),
            cd8_summary_path=root
            / (
                "data/analysis/single-cell-validation/CD8-cross-cohort/"
                "cross-cohort-summary.tsv"
            ),
            microarray_effects_path=root
            / "data/analysis/target-meta-analysis/study-effects.tsv",
            microarray_summary_path=root
            / "data/analysis/target-meta-analysis/target-meta-analysis.tsv",
            gse181364_path=root
            / (
                "data/analysis/external-validation/"
                "GSE181364-candidate-validation.tsv"
            ),
            gse299639_path=root
            / "data/analysis/external-validation/GSE299639/target-validation.tsv",
            output_root=root / "data/analysis/hierarchical-target-evidence",
        )

    @staticmethod
    def _freeze_ddx24(root: Path) -> object:
        return ConfoundingFreezeBuilder().build(
            covariates_path=root
            / "data/single-cell/GSE194315/robustness/covariate-availability.tsv",
            batch_adjusted_path=root
            / "data/single-cell/GSE194315/robustness/batch-adjusted-targets.tsv",
            leave_one_out_path=root
            / "data/single-cell/GSE194315/robustness/leave-one-out-stability.tsv",
            hierarchical_path=root
            / (
                "data/analysis/hierarchical-target-evidence/"
                "hierarchical-synthesis.tsv"
            ),
            context_path=root
            / "data/analysis/hierarchical-target-evidence/context-summary.tsv",
            gse288581_sensitivity_path=root
            / (
                "data/analysis/single-cell-validation/GSE288581/"
                "leave-one-donor-out.tsv"
            ),
            output_root=root / "data/analysis/ddx24-evidence-freeze",
        )

    @staticmethod
    def _prepare_ddx24_publication(root: Path) -> object:
        return PublicationReadinessBuilder().build(
            hierarchical_path=root
            / (
                "data/analysis/hierarchical-target-evidence/"
                "hierarchical-synthesis.tsv"
            ),
            context_path=root
            / "data/analysis/hierarchical-target-evidence/context-summary.tsv",
            decision_path=root
            / "data/analysis/ddx24-evidence-freeze/decision-summary.json",
            criteria_path=root
            / (
                "data/analysis/ddx24-evidence-freeze/"
                "confirmation-refutation-criteria.tsv"
            ),
            output_root=root / "data/publication/ddx24-study",
        )

    @staticmethod
    def _build_deep_dive(root: Path) -> object:
        deep = root / "data/analysis/gene-evidence/deep-dive"
        return TargetDeepDiveBuilder().build(
            master_path=root
            / "data/analysis/gene-evidence/gene-evidence-master.tsv",
            three_study_path=root
            / (
                "data/analysis/three-study-concordance/"
                "direction-concordance.tsv"
            ),
            external_validation_path=root
            / (
                "data/analysis/external-validation/"
                "GSE181364-candidate-validation.tsv"
            ),
            single_cell_path=root
            / (
                "data/single-cell/GSE194315/transcriptome/"
                "integrated-candidates.tsv"
            ),
            karow_path=root / "data/analysis/karow/candidate-validation.tsv",
            genetics_path=deep / "genetics/as-genetic-evidence.tsv",
            intelligence_path=deep / "target-intelligence.tsv",
            dossier_directory=deep / "dossiers",
            meta_analysis_path=root
            / "data/analysis/target-meta-analysis/target-meta-analysis.tsv",
            composition_path=root
            / (
                "data/analysis/cell-composition-diagnostic/"
                "target-composition-adjustment.tsv"
            ),
            reference_expansion_path=root
            / (
                "data/single-cell/GSE194315/reference-expansion/"
                "target-cell-type-validation.tsv"
            ),
            output_root=deep / "decisions",
        )

    @staticmethod
    def _build_article_outputs(root: Path) -> object:
        deep = root / "data/analysis/gene-evidence/deep-dive"
        return Ddx24ValidationPlanner().build(
            decisions_path=deep / "decisions/target-decisions.tsv",
            output_root=deep / "ddx24-validation",
        )

    @staticmethod
    def _build_improvement_audit(root: Path) -> object:
        return ImprovementAuditor().audit(
            meta_analysis_path=root
            / "data/analysis/target-meta-analysis/target-meta-analysis.tsv",
            composition_path=root
            / (
                "data/analysis/cell-composition-diagnostic/"
                "target-composition-adjustment.tsv"
            ),
            quarantine_path=root
            / "data/catalog/incremental-quarantine/study-review-queue.tsv",
            output_root=root / "data/project/improvement",
        )

    @staticmethod
    def _build_publication_package(root: Path) -> object:
        artifacts = {
            "discovery_lock": root / "data/project/discovery-input-lock.json",
            "meta_analysis": root
            / "data/analysis/target-meta-analysis/target-meta-analysis.tsv",
            "leave_one_out": root
            / "data/analysis/target-meta-analysis/leave-one-study-out.tsv",
            "ddx24_forest_plot": root
            / "data/analysis/target-meta-analysis/ddx24-forest-plot.png",
            "ada_forest_plot": root
            / "data/analysis/target-meta-analysis/ada-forest-plot.png",
            "composition": root
            / (
                "data/analysis/cell-composition-diagnostic/"
                "target-composition-adjustment.tsv"
            ),
            "external_validation": root
            / (
                "data/analysis/external-validation/"
                "GSE181364-candidate-validation.tsv"
            ),
            "gse299639_review": root
            / (
                "data/analysis/external-validation/GSE299639/"
                "eligibility-review.json"
            ),
            "gse299639_targets": root
            / (
                "data/analysis/external-validation/GSE299639/"
                "target-validation.tsv"
            ),
            "emtab12805_review": root
            / (
                "data/analysis/single-cell-validation/E-MTAB-12805/"
                "eligibility-review.json"
            ),
            "emtab12805_overlap": root
            / (
                "data/analysis/single-cell-validation/E-MTAB-12805/"
                "repository-overlap.tsv"
            ),
            "gse232131_sample_audit": root
            / (
                "data/analysis/single-cell-validation/E-MTAB-12805/"
                "sample-audit/sample-audit.json"
            ),
            "gse232131_sample_sheet": root
            / (
                "data/analysis/single-cell-validation/E-MTAB-12805/"
                "sample-audit/library-donor-condition.tsv"
            ),
            "emtab10948_review": root
            / (
                "data/analysis/single-cell-validation/E-MTAB-10948/"
                "eligibility-review.json"
            ),
            "emtab10948_sample_sheet": root
            / (
                "data/analysis/single-cell-validation/E-MTAB-10948/"
                "participant-tissue-sheet.tsv"
            ),
            "gse194315_reference_expansion": root
            / (
                "data/single-cell/GSE194315/reference-expansion/"
                "target-cell-type-validation.tsv"
            ),
            "gse194315_robustness": root
            / (
                "data/single-cell/GSE194315/robustness/"
                "robustness-analysis.json"
            ),
            "gse194315_batch_adjusted": root
            / (
                "data/single-cell/GSE194315/robustness/"
                "batch-adjusted-targets.tsv"
            ),
            "gse194315_leave_one_out": root
            / (
                "data/single-cell/GSE194315/robustness/"
                "leave-one-out-stability.tsv"
            ),
            "secondary_single_cell_review": root
            / (
                "data/analysis/single-cell-validation/secondary-cohorts/"
                "secondary-cohort-review.json"
            ),
            "secondary_single_cell_decisions": root
            / (
                "data/analysis/single-cell-validation/secondary-cohorts/"
                "candidate-decisions.tsv"
            ),
            "gse288581_validation": root
            / (
                "data/analysis/single-cell-validation/GSE288581/"
                "target-validation.tsv"
            ),
            "gse288581_sensitivity": root
            / (
                "data/analysis/single-cell-validation/GSE288581/"
                "leave-one-donor-out.tsv"
            ),
            "cd8_cross_cohort_summary": root
            / (
                "data/analysis/single-cell-validation/CD8-cross-cohort/"
                "cross-cohort-summary.tsv"
            ),
            "cd8_cross_cohort_sensitivity": root
            / (
                "data/analysis/single-cell-validation/CD8-cross-cohort/"
                "cd8-state-sensitivity.tsv"
            ),
            "cd8_candidate_registry": root
            / (
                "data/analysis/single-cell-validation/CD8-evidence-review/"
                "candidate-cohort-registry.tsv"
            ),
            "cd8_review_readiness": root
            / (
                "data/analysis/single-cell-validation/CD8-evidence-review/"
                "publication-readiness.json"
            ),
            "cd8_literature_search_log": root
            / (
                "data/analysis/single-cell-validation/CD8-evidence-review/"
                "literature-search-log.tsv"
            ),
            "hierarchical_target_synthesis": root
            / (
                "data/analysis/hierarchical-target-evidence/"
                "hierarchical-synthesis.tsv"
            ),
            "hierarchical_context_summary": root
            / "data/analysis/hierarchical-target-evidence/context-summary.tsv",
            "ddx24_confounding_audit": root
            / "data/analysis/ddx24-evidence-freeze/confounding-audit.tsv",
            "ddx24_confirmation_criteria": root
            / (
                "data/analysis/ddx24-evidence-freeze/"
                "confirmation-refutation-criteria.tsv"
            ),
            "ddx24_evidence_freeze": root
            / "data/analysis/ddx24-evidence-freeze/evidence-freeze.json",
            "ddx24_manuscript_draft": root
            / "data/publication/ddx24-study/manuscript-draft.md",
            "ddx24_rt_qpcr_protocol": root
            / "data/publication/ddx24-study/rt-qpcr-operational-protocol.md",
            "ddx24_figure_cohorts": root
            / (
                "data/publication/ddx24-study/figures/"
                "figure-1-cohort-effects.png"
            ),
            "ddx24_figure_contexts": root
            / (
                "data/publication/ddx24-study/figures/"
                "figure-2-context-concordance.png"
            ),
            "ddx24_references": root
            / "data/publication/ddx24-study/references.bib",
            "single_cell": root
            / (
                "data/single-cell/GSE194315/transcriptome/"
                "integrated-candidates.tsv"
            ),
            "target_decisions": root
            / (
                "data/analysis/gene-evidence/deep-dive/decisions/"
                "target-decisions.tsv"
            ),
            "laboratory_plan": root
            / (
                "data/analysis/gene-evidence/deep-dive/ddx24-validation/"
                "ddx24-preregistered-plan.json"
            ),
        }
        return PublicationPackager().build(
            artifacts=artifacts,
            meta_analysis_path=artifacts["meta_analysis"],
            composition_path=artifacts["composition"],
            output_root=root / "data/publication",
        )

    def _input_lock(self, root: Path) -> dict[str, object]:
        inputs = {}
        for accession in self.DISCOVERY_STUDIES:
            path = (
                root
                / "data"
                / "geo"
                / accession
                / "prepared"
                / f"{accession}_series_matrix"
                / "gene-level-results.tsv"
            )
            inputs[accession] = {
                "path": str(path),
                "sha256": self._sha256(path) if path.exists() else None,
            }
        return {
            "schema_version": 1,
            "discovery_studies": list(self.DISCOVERY_STUDIES),
            "inputs": inputs,
        }

    @staticmethod
    def _guard_lock(
        path: Path,
        current: dict[str, object],
        *,
        accept_input_changes: bool,
    ) -> None:
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            if previous != current and not accept_input_changes:
                raise ValueError(
                    "frozen discovery inputs changed; review them and rerun with "
                    "--accept-input-changes to create a new lock"
                )
        if not path.exists() or accept_input_changes:
            path.write_text(
                json.dumps(current, indent=2) + "\n",
                encoding="utf-8",
            )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_outputs(
        output: Path,
        lock_path: Path,
        stages: list[ProjectStage],
        current_lock: dict[str, object],
    ) -> ProjectPipelineRun:
        completed = sum(stage.status == "completed" for stage in stages)
        blocked = sum(stage.status == "blocked" for stage in stages)
        failed = sum(stage.status == "failed" for stage in stages)
        status_path = output / "project-status.json"
        table_path = output / "project-stages.tsv"
        report_path = output / "project-report.md"
        status_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "status": (
                        "completed"
                        if completed == len(stages)
                        else "attention_required"
                    ),
                    "completed": completed,
                    "blocked": blocked,
                    "failed": failed,
                    "input_lock": current_lock,
                    "stages": [asdict(stage) for stage in stages],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        with table_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=("order", "name", "status", "message", "artifacts"),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            for stage in stages:
                row = asdict(stage)
                row["artifacts"] = "|".join(stage.artifacts)
                writer.writerow(row)
        overall = "completed" if not blocked and not failed else "attention required"
        lines = [
            "# AXIS automated project report",
            "",
            f"Overall status: **{overall}**",
            "",
            f"- Completed stages: {completed}/{len(stages)}",
            f"- Blocked stages: {blocked}",
            f"- Failed stages: {failed}",
            "",
            "## Pipeline",
            "",
        ]
        lines.extend(
            f"{stage.order}. **{stage.name} - {stage.status}**: {stage.message}"
            for stage in stages
        )
        lines.extend(
            [
                "",
                "## Scientific guardrails",
                "",
                "- Discovery cohorts are frozen by checksum.",
                "- Missing evidence blocks downstream execution.",
                "- Directional synthesis is exploratory, not causal evidence.",
                "- External validation remains separate from discovery.",
                "- Laboratory outputs remain marked as planned until imported.",
                "",
            ]
        )
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return ProjectPipelineRun(
            completed=completed,
            blocked=blocked,
            failed=failed,
            status_path=status_path,
            table_path=table_path,
            report_path=report_path,
            lock_path=lock_path,
        )
