"""Daily command-line interface for the AXIS Evidence Store."""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from axis.analysis import (
    ArticleFinalizer,
    AxisDemoRunner,
    AxisProjectPipeline,
    Cd8CrossCohortAnalyzer,
    Cd8EvidenceReviewer,
    CellCompositionDiagnostic,
    CohortSelectionBuilder,
    ConfoundingFreezeBuilder,
    Ddx24ValidationPlanner,
    DemoBenchmarker,
    DesignInspector,
    DifferentialAnalyzer,
    DirectionConcordanceAnalyzer,
    Emtab10948Reviewer,
    Emtab12805Reviewer,
    ExpressionQualityControl,
    ExternalValidator,
    GeneEvidenceBuilder,
    Gse232131SampleAuditor,
    Gse288581Validator,
    Gse299639Reviewer,
    HierarchicalEvidenceAnalyzer,
    ImprovementAuditor,
    KarowSupplementAuditor,
    MirnaDifferentialAnalyzer,
    NormalizedRnaSeqAnalyzer,
    ProposedSampleSheetBuilder,
    PublicationPackager,
    PublicationReadinessBuilder,
    PublishedSupplementValidator,
    RankingPublisher,
    RecurrenceRanker,
    ReplicationAccessAuditor,
    SecondarySingleCellReviewer,
    SensitivityAnalyzer,
    ShortlistBuilder,
    SingleCellPlanBuilder,
    SingleCellPseudobulkAnalyzer,
    SingleCellReferenceExpander,
    SingleCellReplicationPlanner,
    SingleCellRobustnessAnalyzer,
    SingleCellTranscriptomeAnalyzer,
    SraReprocessingPlanner,
    StudyAssessor,
    StudyQuarantineBuilder,
    StudyReproducer,
    TargetDeepDiveBuilder,
    TargetMetaAnalyzer,
    TargetStabilityAnalyzer,
    ValidationCohortSelector,
    WorkflowComparisonPreparer,
    WorkflowComparisonSummarizer,
    write_sample_sheet_template,
)
from axis.domain import Study
from axis.ingestion import (
    BioStudiesCandidateAuditor,
    BioStudiesClient,
    CatalogTriageBuilder,
    CrossRepositoryCatalogBuilder,
    GeoApiError,
    GeoClient,
    GeoIngestionService,
    GeoMatrixDownloader,
    GeoMatrixPreparer,
    GeoPlatformDownloader,
    GeoSampleMetadataClient,
    GeoSupplementDownloader,
    MirnaCohortValidator,
    ParticipantExpansionBuilder,
    PmcSupplementDownloader,
    PrioritySampleAuditor,
    SraCandidateAuditor,
    SraClient,
    StudyCatalogBuilder,
)
from axis.storage import EvidenceStore, RecordNotFoundError
from axis.targets import (
    AtlasDownloadClient,
    CandidateReviewBuilder,
    CausalContextBuilder,
    EnsemblClient,
    FocusedTargetDossierBuilder,
    GeneticEvidenceBuilder,
    NucleomeContactBuilder,
    NucleomePlanBuilder,
    OpenTargetsClient,
    TargetIntelligenceBuilder,
    TherapeuticReadinessBuilder,
)

DEFAULT_DATABASE = Path("data/axis.duckdb")


@dataclass(frozen=True)
class CliSettings:
    database: Path


app = typer.Typer(
    name="axis",
    help="Local scientific discovery tools for axial spondyloarthritis.",
    no_args_is_help=True,
)
console = Console()
error_console = Console(stderr=True)


@app.callback()
def configure(
    context: typer.Context,
    database: Annotated[
        Path,
        typer.Option(
            "--database",
            "-d",
            envvar="AXIS_DATABASE",
            help="Path to the local DuckDB Evidence Store.",
            dir_okay=False,
        ),
    ] = DEFAULT_DATABASE,
) -> None:
    """Configure the local AXIS workspace."""
    context.obj = CliSettings(database=database.expanduser())


def _settings(context: typer.Context) -> CliSettings:
    settings = context.obj
    if not isinstance(settings, CliSettings):
        raise RuntimeError("CLI settings were not initialized")
    return settings


@app.command()
def search(
    context: typer.Context,
    query: Annotated[str, typer.Argument(help="GEO search expression.")],
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", min=1, max=200, help="Results to retrieve."),
    ] = 20,
    offset: Annotated[
        int,
        typer.Option("--offset", min=0, help="Result offset for pagination."),
    ] = 0,
    email: Annotated[
        str | None,
        typer.Option(
            "--email",
            envvar="NCBI_EMAIL",
            help="Contact email sent to NCBI.",
        ),
    ] = None,
) -> None:
    """Search GEO Series and save newly discovered study metadata."""
    settings = _settings(context)
    try:
        with (
            EvidenceStore(settings.database) as store,
            GeoClient(
                email=email,
                api_key=os.environ.get("NCBI_API_KEY"),
            ) as geo,
        ):
            page = GeoIngestionService(geo, store.studies).discover(
                query,
                limit=limit,
                offset=offset,
            )
    except GeoApiError as error:
        error_console.print(f"NCBI GEO request failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    console.print(
        _studies_table(page.studies, title=f"GEO results — {page.total} total")
    )
    console.print(
        f"Saved in {settings.database} · showing {len(page.studies)} "
        f"from offset {page.offset}"
    )


@app.command("build-study-catalog")
def build_study_catalog(
    maximum_per_query: Annotated[
        int,
        typer.Option(
            "--maximum-per-query",
            min=1,
            max=5000,
            help="Maximum number of GEO records collected for each query family.",
        ),
    ] = 500,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Directory where the catalog and review queue are written.",
        ),
    ] = Path("data/catalog"),
) -> None:
    """Build a deduplicated GEO metadata catalog before downloading expression data."""
    with GeoClient(
        email=os.getenv("NCBI_EMAIL"),
        api_key=os.getenv("NCBI_API_KEY"),
    ) as client:
        result = StudyCatalogBuilder().build(
            client,
            maximum_per_query=maximum_per_query,
            output_root=output,
        )

    typer.echo(
        f"Catalogued {result.unique_studies} unique studies from "
        f"{result.discovered_records} query matches."
    )
    typer.echo(f"Review queue: {result.download_candidates} studies.")
    typer.echo(f"Catalog: {result.output_path}")
    typer.echo(f"Queue: {result.queue_path}")
    typer.echo(
        "This stage uses metadata only; review relevance and design before downloading "
        "expression matrices."
    )


@app.command("build-cross-repository-catalog")
def build_cross_repository_catalog(
    geo_catalog: Annotated[
        Path,
        typer.Option(
            "--geo-catalog",
            exists=True,
            dir_okay=False,
            help="Existing GEO catalog used for overlap detection.",
        ),
    ] = Path("data/catalog/study-catalog.tsv"),
    maximum_per_query: Annotated[
        int,
        typer.Option("--maximum-per-query", min=1, max=5000),
    ] = 1000,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False),
    ] = Path("data/catalog/cross-repository"),
) -> None:
    """Discover ArrayExpress/BioStudies and SRA studies beyond GEO."""
    try:
        with (
            BioStudiesClient() as biostudies,
            SraClient(
                email=os.getenv("NCBI_EMAIL"),
                api_key=os.getenv("NCBI_API_KEY"),
            ) as sra,
        ):
            result = CrossRepositoryCatalogBuilder().build(
                biostudies,
                sra,
                geo_catalog_path=geo_catalog,
                output_root=output,
                maximum_per_query=maximum_per_query,
            )
    except (GeoApiError, OSError, ValueError) as error:
        error_console.print(
            f"Cross-repository discovery failed: {error}", style="bold red"
        )
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Catalogued {result.unique_records} unique repository records from "
        f"{result.records} query matches."
    )
    typer.echo(f"Candidates not matched to GEO: {result.new_candidates}.")
    typer.echo(f"Priority for metadata review: {result.priority_candidates}.")
    typer.echo(f"Catalog: {result.output_path}")
    typer.echo(f"New candidates: {result.new_path}")
    typer.echo(f"Priority queue: {result.priority_path}")
    typer.echo("Repository matches are not automatic scientific eligibility.")


@app.command("audit-biostudies-candidates")
def audit_biostudies_candidates(
    accessions: Annotated[
        list[str] | None,
        typer.Argument(
            help="ArrayExpress accessions to audit at participant level."
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False),
    ] = Path("data/catalog/cross-repository/sample-audit"),
) -> None:
    """Audit BioStudies SDRF metadata without counting technical files as people."""
    selected = tuple(accessions or ("E-MTAB-10948", "E-MTAB-12805"))
    try:
        with BioStudiesClient() as client:
            result = BioStudiesCandidateAuditor().audit(
                client,
                selected,
                output_root=output,
            )
    except (GeoApiError, OSError, ValueError) as error:
        error_console.print(
            f"BioStudies candidate audit failed: {error}", style="bold red"
        )
        raise typer.Exit(code=1) from error

    typer.echo(f"Audited {result.studies} BioStudies studies.")
    typer.echo(f"Participant-level results: {result.output_path}")
    typer.echo(
        "Technical files and sequencing lanes were collapsed into biological samples."
    )
    typer.echo("Review the recommended role before using a study for replication.")


@app.command("audit-sra-candidates")
def audit_sra_candidates(
    accessions: Annotated[
        list[str] | None,
        typer.Argument(help="SRA study accessions to audit."),
    ] = None,
    case_pattern: Annotated[
        str | None,
        typer.Option(
            "--case-pattern",
            help="Documented sample-name pattern for cases; never inferred.",
        ),
    ] = None,
    control_pattern: Annotated[
        str | None,
        typer.Option(
            "--control-pattern",
            help="Documented sample-name pattern for controls; never inferred.",
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False),
    ] = Path("data/catalog/cross-repository/sample-audit"),
) -> None:
    """Audit SRA runs as biological samples and independent participants."""
    selected = tuple(accessions or ("SRP517504",))
    try:
        with SraClient(
            email=os.getenv("NCBI_EMAIL"),
            api_key=os.getenv("NCBI_API_KEY"),
        ) as client:
            result = SraCandidateAuditor().audit(
                client,
                selected,
                output_root=output,
                case_pattern=case_pattern,
                control_pattern=control_pattern,
            )
    except (GeoApiError, OSError, ValueError, re.error) as error:
        error_console.print(f"SRA candidate audit failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    typer.echo(f"Audited {result.studies} SRA studies.")
    typer.echo(f"Participant-level results: {result.output_path}")
    typer.echo("Any sample-name mapping remains subject to manual confirmation.")


@app.command("audit-repository-priority")
def audit_repository_priority(
    queue: Annotated[
        Path,
        typer.Option(
            "--queue",
            exists=True,
            dir_okay=False,
            help="Cross-repository priority queue.",
        ),
    ] = Path("data/catalog/cross-repository/cross-repository-priority.tsv"),
    sra_case_pattern: Annotated[
        str | None,
        typer.Option("--sra-case-pattern"),
    ] = None,
    sra_control_pattern: Annotated[
        str | None,
        typer.Option("--sra-control-pattern"),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False),
    ] = Path("data/catalog/cross-repository/sample-audit"),
) -> None:
    """Audit every supported study in the cross-repository priority queue."""
    with queue.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    biostudies = tuple(
        row["accession"]
        for row in rows
        if row.get("source") == "BioStudies-ArrayExpress"
    )
    sra = tuple(
        row["accession"] for row in rows if row.get("source") == "NCBI-SRA"
    )
    try:
        if biostudies:
            with BioStudiesClient() as client:
                BioStudiesCandidateAuditor().audit(
                    client, biostudies, output_root=output
                )
        if sra:
            with SraClient(
                email=os.getenv("NCBI_EMAIL"),
                api_key=os.getenv("NCBI_API_KEY"),
            ) as client:
                SraCandidateAuditor().audit(
                    client,
                    sra,
                    output_root=output,
                    case_pattern=sra_case_pattern,
                    control_pattern=sra_control_pattern,
                )
    except (GeoApiError, OSError, ValueError, re.error) as error:
        error_console.print(
            f"Repository priority audit failed: {error}", style="bold red"
        )
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Audited priority queue: {len(biostudies)} BioStudies and "
        f"{len(sra)} SRA studies."
    )
    typer.echo(f"Results: {output}")
    typer.echo("No study was made automatically eligible for recurrence.")


@app.command("download-pmc-supplements")
def download_pmc_supplements(
    pmcid: Annotated[str, typer.Argument(help="PubMed Central identifier.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False),
    ] = Path("data/publications"),
) -> None:
    """Download small tabular supplements from an open PMC article package."""
    try:
        with PmcSupplementDownloader() as downloader:
            result = downloader.download(pmcid, output_root=output)
    except (GeoApiError, OSError, ValueError) as error:
        error_console.print(
            f"PMC supplement download failed: {error}", style="bold red"
        )
        raise typer.Exit(code=1) from error
    typer.echo(f"Downloaded {result.files} tabular supplements for {result.pmcid}.")
    typer.echo(f"Manifest: {result.manifest_path}")
    typer.echo("Inspect table meaning before using it as an expression matrix.")


@app.command("plan-sra-reprocessing")
def plan_sra_reprocessing(
    accession: Annotated[str, typer.Argument(help="SRA study accession.")],
    runinfo: Annotated[
        Path,
        typer.Option("--runinfo", exists=True, dir_okay=False),
    ],
    samples: Annotated[
        Path,
        typer.Option("--samples", exists=True, dir_okay=False),
    ],
    transcriptome_index: Annotated[
        Path | None,
        typer.Option(
            "--transcriptome-index",
            file_okay=False,
            help="Existing Salmon index; omitted indexes block execution.",
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False),
    ] = Path("data/raw-workflows"),
) -> None:
    """Plan a guarded SRA-to-Salmon workflow without downloading raw reads."""
    try:
        result = SraReprocessingPlanner().build(
            accession,
            runinfo,
            samples,
            transcriptome_index=transcriptome_index,
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(
            f"SRA workflow planning failed: {error}", style="bold red"
        )
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Planned {result.samples} samples; estimated working space "
        f"{result.estimated_working_gb:.1f} GB."
    )
    typer.echo(f"Status: {result.execution_status}")
    typer.echo(f"Missing tools: {result.missing_tools or 'none'}")
    typer.echo(f"Plan: {result.manifest_path}")
    typer.echo("No raw sequencing data were downloaded.")


@app.command("triage-study-catalog")
def triage_study_catalog(
    catalog: Annotated[
        Path,
        typer.Option(
            "--catalog",
            exists=True,
            dir_okay=False,
            help="Study catalog produced by build-study-catalog.",
        ),
    ] = Path("data/catalog/study-catalog.tsv"),
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Directory for triage results.",
        ),
    ] = Path("data/catalog"),
) -> None:
    """Prioritize direct-disease catalog matches for manual sample review."""
    try:
        result = CatalogTriageBuilder().build(catalog, output_root=output)
    except (OSError, ValueError) as error:
        error_console.print(f"Catalog triage failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    typer.echo(f"Triaged {result.candidates} direct-disease candidates.")
    typer.echo(
        f"Priority: {result.high_priority} high, "
        f"{result.medium_priority} medium, "
        f"{result.manual_review} manual relevance review."
    )
    typer.echo(f"Full triage: {result.output_path}")
    typer.echo(f"Priority queue: {result.priority_path}")
    typer.echo("No study was automatically approved; inspect GEO sample metadata next.")


@app.command("audit-priority-samples")
def audit_priority_samples(
    priority_queue: Annotated[
        Path,
        typer.Option(
            "--priority-queue",
            exists=True,
            dir_okay=False,
            help="Priority queue produced by triage-study-catalog.",
        ),
    ] = Path("data/catalog/direct-study-priority-queue.tsv"),
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Directory for study and sample audit files.",
        ),
    ] = Path("data/catalog/sample-audit"),
    maximum: Annotated[
        int | None,
        typer.Option(
            "--maximum",
            min=1,
            help="Optional number of priority studies to audit.",
        ),
    ] = None,
) -> None:
    """Stream GEO sample headers and suggest case/control study designs."""
    try:
        with GeoSampleMetadataClient() as client:
            result = PrioritySampleAuditor().build(
                client,
                priority_queue,
                output_root=output,
                maximum=maximum,
            )
    except (GeoApiError, OSError, ValueError) as error:
        error_console.print(f"Sample audit failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Audited {result.audited_studies} of {result.requested_studies} studies; "
        f"{result.failed_studies} lacked usable Series Matrix metadata."
    )
    typer.echo(f"Design review candidates: {result.design_review_candidates} studies.")
    typer.echo(f"Study audit: {result.study_path}")
    typer.echo(f"Design review queue: {result.design_queue_path}")
    typer.echo(f"Sample metadata: {result.sample_path}")
    typer.echo(
        "Suggested groups are not approvals; verify sample sheets before analysis."
    )


@app.command("collapse-participants")
def collapse_participants(
    sample_metadata: Annotated[
        Path,
        typer.Option("--sample-metadata", exists=True, dir_okay=False),
    ] = Path("data/catalog/participant-expansion/sample-metadata.tsv"),
    catalog: Annotated[
        Path,
        typer.Option("--catalog", exists=True, dir_okay=False),
    ] = Path("data/catalog/study-catalog.tsv"),
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False),
    ] = Path("data/catalog/participant-expansion"),
) -> None:
    """Collapse repeated GEO samples into independent participant cohorts."""
    try:
        result = ParticipantExpansionBuilder().build(
            sample_metadata,
            catalog,
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(
            f"Participant collapsing failed: {error}", style="bold red"
        )
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Resolved {result.participants} participants across {result.studies} studies."
    )
    typer.echo(f"Cohorts: {result.cohort_path}")
    typer.echo("Repeated samples were not counted as independent people.")


@app.command("build-proposed-sample-sheets")
def build_proposed_sample_sheets(
    design_queue: Annotated[
        Path,
        typer.Option(
            "--design-queue",
            exists=True,
            dir_okay=False,
            help="Design queue produced by audit-priority-samples.",
        ),
    ] = Path("data/catalog/sample-audit/design-review-queue.tsv"),
    sample_metadata: Annotated[
        Path,
        typer.Option(
            "--sample-metadata",
            exists=True,
            dir_okay=False,
            help="Sample metadata produced by audit-priority-samples.",
        ),
    ] = Path("data/catalog/sample-audit/sample-metadata.tsv"),
    catalog: Annotated[
        Path,
        typer.Option(
            "--catalog",
            exists=True,
            dir_okay=False,
            help="Full GEO study catalog.",
        ),
    ] = Path("data/catalog/study-catalog.tsv"),
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False),
    ] = Path("data/catalog/sample-proposals"),
) -> None:
    """Create editable sample proposals with disease and independence gates."""
    try:
        result = ProposedSampleSheetBuilder().build(
            design_queue_path=design_queue,
            sample_metadata_path=sample_metadata,
            catalog_path=catalog,
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"Sample proposal failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    typer.echo(f"Validated {result.studies} study designs.")
    typer.echo(f"axSpA design-review candidates: {result.axspa_candidates}.")
    typer.echo(
        f"Context-only exclusions: {result.related_disease_exclusions} related "
        f"disease, {result.non_expression_exclusions} non-expression."
    )
    typer.echo(f"Study validation: {result.output_path}")
    typer.echo(f"Editable proposals: {result.sheets_root}")
    typer.echo("No proposed sheet is approved until a reviewer signs it.")


@app.command("select-next-cohorts")
def select_next_cohorts(
    maximum: Annotated[
        int,
        typer.Option(
            "--maximum",
            min=1,
            max=20,
            help="Maximum number of independent cohorts to nominate.",
        ),
    ] = 5,
    validation: Annotated[
        Path,
        typer.Option("--validation", exists=True, dir_okay=False),
    ] = Path("data/catalog/sample-proposals/study-validation.tsv"),
    sample_metadata: Annotated[
        Path,
        typer.Option("--sample-metadata", exists=True, dir_okay=False),
    ] = Path("data/catalog/sample-audit/sample-metadata.tsv"),
    catalog: Annotated[
        Path,
        typer.Option("--catalog", exists=True, dir_okay=False),
    ] = Path("data/catalog/study-catalog.tsv"),
    geo_root: Annotated[
        Path,
        typer.Option("--geo-root", file_okay=False),
    ] = Path("data/geo"),
    output: Annotated[
        Path,
        typer.Option("--output", "-o", file_okay=False),
    ] = Path("data/catalog/cohort-selection"),
) -> None:
    """Nominate independent new cohorts after disease and modality gates."""
    try:
        result = CohortSelectionBuilder().build(
            validation_path=validation,
            sample_metadata_path=sample_metadata,
            catalog_path=catalog,
            geo_root=geo_root,
            output_root=output,
            maximum=maximum,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"Cohort selection failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Evaluated {result.evaluated} candidates; nominated "
        f"{result.selected} independent new cohorts."
    )
    typer.echo(
        f"Roles: {result.primary_replication} primary blood replication, "
        f"{result.mechanistic_context} mechanistic context."
    )
    typer.echo(f"Selection: {result.selection_path}")
    typer.echo(f"Full evaluation: {result.output_path}")
    typer.echo("Manual sample-sheet confirmation is still required.")


@app.command()
def download(
    accession: Annotated[
        str,
        typer.Argument(help="GEO Series accession (GSE...)."),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Root directory for downloaded GEO files.",
            file_okay=False,
        ),
    ] = Path("data/geo"),
) -> None:
    """Download processed GEO Series Matrix files and a checksum manifest."""
    try:
        with GeoMatrixDownloader() as downloader:
            result = downloader.download(accession, output_root=output)
    except (GeoApiError, ValueError) as error:
        error_console.print(f"GEO download failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    table = Table(title=f"Downloaded {result.accession}")
    table.add_column("File", style="bold cyan")
    table.add_column("Size", justify="right")
    table.add_column("SHA-256")
    for file in result.files:
        table.add_row(
            str(file.path),
            f"{file.size_bytes:,} bytes",
            file.checksum.removeprefix("sha256:"),
        )
    console.print(table)
    console.print(f"Manifest: {result.manifest_path}")


@app.command()
def prepare(
    accession: Annotated[
        str,
        typer.Argument(help="Downloaded GEO Series accession (GSE...)."),
    ],
    case_pattern: Annotated[
        str,
        typer.Option(
            "--case-pattern",
            help="Regular expression identifying case samples in GEO metadata.",
        ),
    ],
    control_pattern: Annotated[
        str,
        typer.Option(
            "--control-pattern",
            help="Regular expression identifying control samples in GEO metadata.",
        ),
    ],
    include_pattern: Annotated[
        str | None,
        typer.Option(
            "--include-pattern",
            help=("Regular expression samples must match to enter either group."),
        ),
    ] = None,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            help="Root directory containing downloaded GEO files.",
            file_okay=False,
        ),
    ] = Path("data/geo"),
) -> None:
    """Separate a downloaded matrix into auditable case/control tables."""
    try:
        result = GeoMatrixPreparer().prepare(
            accession,
            data_root=data_root,
            case_pattern=case_pattern,
            control_pattern=control_pattern,
            include_pattern=include_pattern,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"GEO preparation failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    table = Table(title=f"Prepared {result.accession}")
    table.add_column("Matrix", style="bold cyan")
    table.add_column("Cases", justify="right")
    table.add_column("Controls", justify="right")
    table.add_column("Unassigned", justify="right")
    table.add_column("Ambiguous", justify="right")
    table.add_column("Excluded", justify="right")
    table.add_column("Features", justify="right")
    for matrix in result.matrices:
        table.add_row(
            matrix.source_path.name,
            str(matrix.case_samples),
            str(matrix.control_samples),
            str(matrix.unassigned_samples),
            str(matrix.ambiguous_samples),
            str(matrix.excluded_samples),
            str(matrix.feature_rows),
        )
    console.print(table)
    for matrix in result.matrices:
        console.print(f"Prepared files: {matrix.output_directory}")
    if any(
        matrix.unassigned_samples or matrix.ambiguous_samples
        for matrix in result.matrices
    ):
        console.print(
            "Review sample-groups.tsv before analysis; unmatched or ambiguous "
            "samples were excluded.",
            style="bold yellow",
        )


@app.command()
def platform(
    accession: Annotated[
        str,
        typer.Argument(help="GEO platform accession (GPL...)."),
    ],
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            help="Root directory for GEO files.",
            file_okay=False,
        ),
    ] = Path("data/geo"),
) -> None:
    """Download an official GEO probe-to-gene annotation table."""
    try:
        with GeoPlatformDownloader() as downloader:
            result = downloader.download(accession, data_root=data_root)
    except (GeoApiError, ValueError) as error:
        error_console.print(f"GEO platform download failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(f"Downloaded {result.platform}: {result.path}")
    console.print(f"SHA-256: {result.checksum.removeprefix('sha256:')}")


@app.command("download-supplement")
def download_supplement(
    accession: Annotated[
        str,
        typer.Argument(help="GEO Series accession (GSE...)."),
    ],
    filename_pattern: Annotated[
        str,
        typer.Option(
            "--pattern",
            help="Regular expression selecting supplementary filenames.",
        ),
    ],
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            file_okay=False,
            help="Root directory containing GEO data.",
        ),
    ] = Path("data/geo"),
) -> None:
    """Download selected supplementary files declared by GEO."""
    try:
        with GeoSupplementDownloader() as downloader:
            results = downloader.download(
                accession,
                filename_pattern=filename_pattern,
                data_root=data_root,
            )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Supplementary download failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    for result in results:
        console.print(
            f"Downloaded {result.path} ({result.size_bytes:,} bytes, {result.checksum})"
        )


@app.command("validate-mirna-cohort")
def validate_mirna_cohort(
    accession: Annotated[str, typer.Argument(help="GEO Series accession.")],
    data_root: Annotated[
        Path,
        typer.Option("--data-root", file_okay=False, help="Root GEO data directory."),
    ] = Path("data/geo"),
) -> None:
    """Validate participant metadata and deposited microRNA matrices."""
    try:
        result = MirnaCohortValidator().validate(accession, data_root=data_root)
    except (GeoApiError, ValueError) as error:
        error_console.print(f"MicroRNA validation failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Validated {result.participants} participants and "
        f"{result.mirnas} microRNAs for {result.accession}."
    )
    console.print(
        f"Groups: {result.radiographic_axspa} r-axSpA, "
        f"{result.nonradiographic_axspa} nr-axSpA, "
        f"{result.healthy_controls} healthy controls."
    )
    console.print(f"Eligible for analysis: {result.eligible_for_analysis}")
    console.print(f"Report: {result.report_path}")


@app.command("analyze-mirna")
def analyze_mirna(
    accession: Annotated[str, typer.Argument(help="Validated GEO accession.")],
    data_root: Annotated[
        Path,
        typer.Option("--data-root", file_okay=False, help="Root GEO data directory."),
    ] = Path("data/geo"),
    alpha: Annotated[float, typer.Option("--alpha", min=0.000001, max=0.999999)] = 0.05,
    min_base_mean: Annotated[
        float, typer.Option("--min-base-mean", min=0.0)
    ] = 10.0,
) -> None:
    """Run three covariate-adjusted microRNA comparisons."""
    try:
        result = MirnaDifferentialAnalyzer().analyze(
            accession,
            data_root=data_root,
            alpha=alpha,
            min_base_mean=min_base_mean,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"MicroRNA analysis failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Analyzed {result.tested_mirnas} microRNAs across "
        f"{result.participants} participants."
    )
    for comparison in result.comparisons:
        console.print(
            f"{comparison.name}: {comparison.cases} cases, "
            f"{comparison.controls} controls, "
            f"{comparison.significant_mirnas} significant."
        )
    console.print(f"Summary: {result.summary_path}")
    console.print(f"Sensitivity: {result.sensitivity_path}")


@app.command("audit-karow-supplement")
def audit_karow_supplement(
    workbook: Annotated[Path, typer.Option("--workbook", exists=True)],
    candidates: Annotated[Path, typer.Option("--candidates", exists=True)] = Path(
        "data/analysis/concordance/exploratory-shortlist.tsv"
    ),
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/karow"
    ),
) -> None:
    """Audit Karow data access and validate candidates against published lists."""
    result = KarowSupplementAuditor().audit(
        workbook, candidates, output_root=output
    )
    console.print(
        f"Extracted {result.cohort1_features} cohort-1 features and "
        f"{result.cohort2_genes} cohort-2 genes."
    )
    console.print(
        f"Candidate support: {result.supported_candidates}; "
        f"conflicts: {result.conflicting_candidates}."
    )
    console.print(f"Access audit: {result.audit_path}")


@app.command("build-gene-evidence")
def build_gene_evidence(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/gene-evidence"
    ),
) -> None:
    """Build the conservative cross-platform gene evidence master table."""
    result = GeneEvidenceBuilder().build(
        shortlist_path="data/analysis/concordance/exploratory-shortlist.tsv",
        single_cell_path=(
            "data/single-cell/GSE194315/transcriptome/integrated-candidates.tsv"
        ),
        causal_review_path=(
            "data/single-cell/GSE194315/candidate-review/"
            "candidate-causal-review.tsv"
        ),
        karow_signature_path="data/analysis/karow/published-signatures.tsv",
        genetics_path=(
            "data/single-cell/GSE194315/candidate-review/genetics/"
            "as-genetic-evidence.tsv"
        ),
        intelligence_path=(
            "data/single-cell/GSE194315/candidate-review/intelligence/"
            "target-intelligence.tsv"
        ),
        output_root=output,
    )
    console.print(f"Integrated {result.genes} genes.")
    console.print(
        f"Groups: {result.pharmacological_priorities} pharmacological, "
        f"{result.experimental_priorities} experimental, "
        f"{result.secondary_hypotheses} secondary."
    )
    console.print(f"Master table: {result.master_path}")


@app.command("deep-dive-targets")
def deep_dive_targets(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/gene-evidence/deep-dive/decisions"
    ),
) -> None:
    """Resolve therapeutic readiness and falsification plans for DDX24 and ADA."""
    result = TargetDeepDiveBuilder().build(
        master_path="data/analysis/gene-evidence/gene-evidence-master.tsv",
        three_study_path=(
            "data/analysis/three-study-concordance/direction-concordance.tsv"
        ),
        external_validation_path=(
            "data/analysis/external-validation/"
            "GSE181364-candidate-validation.tsv"
        ),
        single_cell_path=(
            "data/single-cell/GSE194315/transcriptome/integrated-candidates.tsv"
        ),
        karow_path="data/analysis/karow/candidate-validation.tsv",
        genetics_path=(
            "data/analysis/gene-evidence/deep-dive/genetics/"
            "as-genetic-evidence.tsv"
        ),
        intelligence_path=(
            "data/analysis/gene-evidence/deep-dive/target-intelligence.tsv"
        ),
        dossier_directory=(
            "data/analysis/gene-evidence/deep-dive/dossiers"
        ),
        meta_analysis_path=(
            "data/analysis/target-meta-analysis/target-meta-analysis.tsv"
        ),
        composition_path=(
            "data/analysis/cell-composition-diagnostic/"
            "target-composition-adjustment.tsv"
        ),
        reference_expansion_path=(
            "data/single-cell/GSE194315/reference-expansion/"
            "target-cell-type-validation.tsv"
        ),
        output_root=output,
    )
    console.print(
        f"Deep-dived {result.targets} targets: {result.promoted} promoted, "
        f"{result.experimental_only} experimental, "
        f"{result.deprioritised} deprioritised."
    )
    console.print(f"Decisions: {result.decision_path}")


@app.command("plan-ddx24-validation")
def plan_ddx24_validation(
    donors_per_group: Annotated[
        int,
        typer.Option(
            "--donors-per-group",
            min=6,
            help="Independent axSpA and control donors per group.",
        ),
    ] = 6,
    technical_replicates: Annotated[
        int,
        typer.Option(
            "--technical-replicates",
            min=1,
            help="Technical replicates per donor and condition.",
        ),
    ] = 2,
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/gene-evidence/deep-dive/ddx24-validation"
    ),
) -> None:
    """Create the preregistered stage-one DDX24 validation package."""
    try:
        result = Ddx24ValidationPlanner().build(
            decisions_path=(
                "data/analysis/gene-evidence/deep-dive/decisions/"
                "target-decisions.tsv"
            ),
            output_root=output,
            donors_per_group=donors_per_group,
            technical_replicates=technical_replicates,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"DDX24 validation planning failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(
        f"Planned {result.experimental_units} experimental units across "
        f"{result.donors} independent donors."
    )
    console.print(f"Sample sheet: {result.sample_sheet_path}")
    console.print(f"Preregistered plan: {result.protocol_path}")


@app.command("project-run")
def project_run(
    accept_input_changes: Annotated[
        bool,
        typer.Option(
            "--accept-input-changes",
            help="Replace the frozen discovery-input lock after manual review.",
        ),
    ] = False,
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/project"
    ),
) -> None:
    """Run or resume the guarded AXIS discovery pipeline."""
    try:
        result = AxisProjectPipeline().run(
            output_root=output,
            accept_input_changes=accept_input_changes,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"Project pipeline stopped: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Project pipeline: {result.completed} completed, "
        f"{result.blocked} blocked, {result.failed} failed."
    )
    console.print(f"Report: {result.report_path}")


@app.command("project-status")
def project_status(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/project"
    ),
) -> None:
    """Inspect project readiness without rebuilding analyses."""
    result = AxisProjectPipeline().status(output_root=output)
    console.print(
        f"Project status: {result.completed} completed, "
        f"{result.blocked} blocked, {result.failed} failed."
    )
    console.print(f"Report: {result.report_path}")


@app.command("meta-analyze-targets")
def meta_analyze_targets(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/target-meta-analysis"
    ),
) -> None:
    """Run a guarded random-effects analysis for DDX24 and ADA."""
    studies = {
        accession: (
            Path("data/geo")
            / accession
            / "prepared"
            / f"{accession}_series_matrix"
        )
        for accession in ("GSE25101", "GSE18781", "GSE73754")
    }
    try:
        result = TargetMetaAnalyzer().analyze(
            studies=studies,
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"Target meta-analysis failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(
        f"Meta-analyzed {result.targets} targets across {result.studies} studies."
    )
    console.print(f"Results: {result.summary_path}")


@app.command("diagnose-cell-composition")
def diagnose_cell_composition(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/cell-composition-diagnostic"
    ),
) -> None:
    """Test whether blood-cell marker scores attenuate DDX24 and ADA."""
    accessions = ("GSE25101", "GSE18781", "GSE73754")
    studies = {
        accession: (
            Path("data/geo")
            / accession
            / "prepared"
            / f"{accession}_series_matrix"
        )
        for accession in accessions
    }
    platforms = {
        "GSE25101": Path("data/geo/platforms/GPL6947/GPL6947.annot.gz"),
        "GSE18781": Path("data/geo/platforms/GPL570/GPL570.annot.gz"),
        "GSE73754": Path("data/geo/platforms/GPL10558/GPL10558.annot.gz"),
    }
    try:
        result = CellCompositionDiagnostic().analyze(
            studies=studies,
            platform_annotations=platforms,
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"Cell-composition diagnostic failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(
        f"Diagnosed {result.targets} targets across {result.studies} studies."
    )
    console.print(f"Adjusted results: {result.adjustment_path}")


@app.command("refresh-study-quarantine")
def refresh_study_quarantine(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/catalog/incremental-quarantine"
    ),
) -> None:
    """Place new catalogued studies into a manual validation queue."""
    result = StudyQuarantineBuilder().build(
        geo_catalog_path="data/catalog/study-catalog.tsv",
        cross_repository_path=(
            "data/catalog/cross-repository/cross-repository-catalog.tsv"
        ),
        output_root=output,
    )
    console.print(
        f"Quarantined {result.candidates} candidates; "
        f"{result.direct_axspa} are axSpA-specific."
    )
    console.print(f"Review queue: {result.queue_path}")


@app.command("select-validation-cohorts")
def select_validation_cohorts(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/catalog/validation-cohort-selection"
    ),
) -> None:
    """Prioritize independent bulk and single-cell validation cohorts."""
    result = ValidationCohortSelector().select(
        quarantine_path=(
            "data/catalog/incremental-quarantine/study-review-queue.tsv"
        ),
        cohort_evaluation_path=(
            "data/catalog/cohort-selection/cohort-evaluation.tsv"
        ),
        sample_validation_path=(
            "data/catalog/sample-proposals/study-validation.tsv"
        ),
        participant_cohorts_path=(
            "data/catalog/participant-expansion/participant-cohorts.tsv"
        ),
        output_root=output,
    )
    console.print(
        f"Evaluated {result.evaluated} axSpA candidates; "
        f"{result.priority_review} require priority review."
    )
    console.print(
        f"Priorities: {result.bulk_candidates} bulk, "
        f"{result.single_cell_candidates} single-cell."
    )
    console.print(f"Review packet: {result.review_path}")


@app.command("review-gse299639")
def review_gse299639(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/external-validation/GSE299639"
    ),
) -> None:
    """Freeze the GSE299639 eligibility and target-validation review."""
    root = Path("data/geo/GSE299639/prepared")
    try:
        result = Gse299639Reviewer().review(
            abundance_path=(
                "data/geo/GSE299639/supplementary/"
                "GSE299639_genes_TPM.anno.txt.gz"
            ),
            full_results_path=root
            / "rnaseq-normalized/gene-level-results.tsv",
            sensitivity_results_path=root
            / "rnaseq-normalized-without-AS-M1/gene-level-results.tsv",
            qc_path=root / "rnaseq-normalized/qc/qc-report.json",
            sensitivity_summary_path=root
            / "rnaseq-normalized/outlier-sensitivity.json",
            output_root=output,
        )
    except (OSError, ValueError, KeyError) as error:
        error_console.print(f"GSE299639 review failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(
        f"Reviewed {result.samples} samples; decision: {result.decision}."
    )
    console.print(f"Target validation: {result.target_validation_path}")


@app.command("review-emtab12805")
def review_emtab12805(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/single-cell-validation/E-MTAB-12805"
    ),
) -> None:
    """Freeze allowed uses of the E-MTAB-12805/GSE232131 study."""
    result = Emtab12805Reviewer().review(output_root=output)
    console.print(
        f"Reviewed {result.accessions} linked accessions as one cohort; "
        f"decision: {result.decision}."
    )
    console.print(f"Eligibility review: {result.review_path}")


@app.command("review-emtab10948")
def review_emtab10948(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/single-cell-validation/E-MTAB-10948"
    ),
) -> None:
    """Freeze the paired-tissue role of E-MTAB-10948."""
    source = Path(
        "data/catalog/cross-repository/sample-audit/E-MTAB-10948"
    )
    try:
        result = Emtab10948Reviewer().review(
            study_audit_path=source / "study-audit.json",
            sdrf_path=source / "E-MTAB-10948.sdrf.txt",
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"E-MTAB-10948 review failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(
        f"Reviewed {result.biological_samples} paired samples from "
        f"{result.participants} AS participants; decision: {result.decision}."
    )
    console.print(f"Eligibility review: {result.review_path}")


@app.command("audit-gse232131-samples")
def audit_gse232131_samples(
    matrix: Annotated[Path, typer.Option("--matrix", exists=True)] = Path(
        "data/geo/GSE232131/GSE232131_series_matrix.txt.gz"
    ),
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/single-cell-validation/E-MTAB-12805/sample-audit"
    ),
) -> None:
    """Audit donors, conditions and processed files before a large download."""
    try:
        result = Gse232131SampleAuditor().audit(
            matrix_path=matrix,
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"GSE232131 sample audit failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(
        f"Audited {result.libraries} libraries from {result.donors} named "
        f"AS donors; decision: {result.decision}."
    )
    console.print(f"Sample sheet: {result.sample_sheet_path}")


@app.command("improve-inspect")
def improve_inspect(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/project/improvement"
    ),
) -> None:
    """Generate the evidence-aware AXIS self-improvement backlog."""
    result = ImprovementAuditor().audit(
        meta_analysis_path=(
            "data/analysis/target-meta-analysis/target-meta-analysis.tsv"
        ),
        composition_path=(
            "data/analysis/cell-composition-diagnostic/"
            "target-composition-adjustment.tsv"
        ),
        quarantine_path=(
            "data/catalog/incremental-quarantine/study-review-queue.tsv"
        ),
        output_root=output,
    )
    console.print(
        f"Improvement audit: {result.findings} findings, "
        f"{result.critical} critical."
    )
    console.print(f"Backlog: {result.backlog_path}")


@app.command("build-publication-package")
def build_publication_package(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/publication"
    ),
) -> None:
    """Build a claim-bound, reproducible computational manuscript package."""
    artifacts = {
        "discovery_lock": "data/project/discovery-input-lock.json",
        "meta_analysis": (
            "data/analysis/target-meta-analysis/target-meta-analysis.tsv"
        ),
        "leave_one_out": (
            "data/analysis/target-meta-analysis/leave-one-study-out.tsv"
        ),
        "ddx24_forest_plot": (
            "data/analysis/target-meta-analysis/ddx24-forest-plot.png"
        ),
        "ada_forest_plot": (
            "data/analysis/target-meta-analysis/ada-forest-plot.png"
        ),
        "composition": (
            "data/analysis/cell-composition-diagnostic/"
            "target-composition-adjustment.tsv"
        ),
        "external_validation": (
            "data/analysis/external-validation/"
            "GSE181364-candidate-validation.tsv"
        ),
        "gse299639_review": (
            "data/analysis/external-validation/GSE299639/"
            "eligibility-review.json"
        ),
        "gse299639_targets": (
            "data/analysis/external-validation/GSE299639/"
            "target-validation.tsv"
        ),
        "emtab12805_review": (
            "data/analysis/single-cell-validation/E-MTAB-12805/"
            "eligibility-review.json"
        ),
        "emtab12805_overlap": (
            "data/analysis/single-cell-validation/E-MTAB-12805/"
            "repository-overlap.tsv"
        ),
        "gse232131_sample_audit": (
            "data/analysis/single-cell-validation/E-MTAB-12805/"
            "sample-audit/sample-audit.json"
        ),
        "gse232131_sample_sheet": (
            "data/analysis/single-cell-validation/E-MTAB-12805/"
            "sample-audit/library-donor-condition.tsv"
        ),
        "emtab10948_review": (
            "data/analysis/single-cell-validation/E-MTAB-10948/"
            "eligibility-review.json"
        ),
        "emtab10948_sample_sheet": (
            "data/analysis/single-cell-validation/E-MTAB-10948/"
            "participant-tissue-sheet.tsv"
        ),
        "gse194315_reference_expansion": (
            "data/single-cell/GSE194315/reference-expansion/"
            "target-cell-type-validation.tsv"
        ),
        "gse194315_robustness": (
            "data/single-cell/GSE194315/robustness/"
            "robustness-analysis.json"
        ),
        "gse194315_batch_adjusted": (
            "data/single-cell/GSE194315/robustness/"
            "batch-adjusted-targets.tsv"
        ),
        "gse194315_leave_one_out": (
            "data/single-cell/GSE194315/robustness/"
            "leave-one-out-stability.tsv"
        ),
        "secondary_single_cell_review": (
            "data/analysis/single-cell-validation/secondary-cohorts/"
            "secondary-cohort-review.json"
        ),
        "secondary_single_cell_decisions": (
            "data/analysis/single-cell-validation/secondary-cohorts/"
            "candidate-decisions.tsv"
        ),
        "gse288581_validation": (
            "data/analysis/single-cell-validation/GSE288581/"
            "target-validation.tsv"
        ),
        "gse288581_sensitivity": (
            "data/analysis/single-cell-validation/GSE288581/"
            "leave-one-donor-out.tsv"
        ),
        "cd8_cross_cohort_summary": (
            "data/analysis/single-cell-validation/CD8-cross-cohort/"
            "cross-cohort-summary.tsv"
        ),
        "cd8_cross_cohort_sensitivity": (
            "data/analysis/single-cell-validation/CD8-cross-cohort/"
            "cd8-state-sensitivity.tsv"
        ),
        "cd8_candidate_registry": (
            "data/analysis/single-cell-validation/CD8-evidence-review/"
            "candidate-cohort-registry.tsv"
        ),
        "cd8_review_readiness": (
            "data/analysis/single-cell-validation/CD8-evidence-review/"
            "publication-readiness.json"
        ),
        "cd8_literature_search_log": (
            "data/analysis/single-cell-validation/CD8-evidence-review/"
            "literature-search-log.tsv"
        ),
        "hierarchical_target_synthesis": (
            "data/analysis/hierarchical-target-evidence/"
            "hierarchical-synthesis.tsv"
        ),
        "hierarchical_context_summary": (
            "data/analysis/hierarchical-target-evidence/context-summary.tsv"
        ),
        "ddx24_confounding_audit": (
            "data/analysis/ddx24-evidence-freeze/confounding-audit.tsv"
        ),
        "ddx24_confirmation_criteria": (
            "data/analysis/ddx24-evidence-freeze/"
            "confirmation-refutation-criteria.tsv"
        ),
        "ddx24_evidence_freeze": (
            "data/analysis/ddx24-evidence-freeze/evidence-freeze.json"
        ),
        "ddx24_manuscript_draft": (
            "data/publication/ddx24-study/manuscript-draft.md"
        ),
        "ddx24_rt_qpcr_protocol": (
            "data/publication/ddx24-study/rt-qpcr-operational-protocol.md"
        ),
        "ddx24_figure_cohorts": (
            "data/publication/ddx24-study/figures/"
            "figure-1-cohort-effects.png"
        ),
        "ddx24_figure_contexts": (
            "data/publication/ddx24-study/figures/"
            "figure-2-context-concordance.png"
        ),
        "ddx24_references": "data/publication/ddx24-study/references.bib",
        "single_cell": (
            "data/single-cell/GSE194315/transcriptome/"
            "integrated-candidates.tsv"
        ),
        "target_decisions": (
            "data/analysis/gene-evidence/deep-dive/decisions/"
            "target-decisions.tsv"
        ),
        "laboratory_plan": (
            "data/analysis/gene-evidence/deep-dive/ddx24-validation/"
            "ddx24-preregistered-plan.json"
        ),
    }
    try:
        result = PublicationPackager().build(
            artifacts=artifacts,
            meta_analysis_path=artifacts["meta_analysis"],
            composition_path=artifacts["composition"],
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"Publication package failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(f"Bound {result.artifacts} publication artifacts.")
    console.print(f"Manuscript outline: {result.outline_path}")


@app.command()
def analyze(
    accession: Annotated[
        str,
        typer.Argument(help="Prepared GEO Series accession (GSE...)."),
    ],
    platform_accession: Annotated[
        str,
        typer.Option(
            "--platform",
            help="GEO platform accession used to map probes to genes.",
        ),
    ],
    alpha: Annotated[
        float,
        typer.Option(
            "--alpha",
            min=0.000001,
            max=0.999999,
            help="Adjusted p-value threshold.",
        ),
    ] = 0.05,
    min_difference: Annotated[
        float,
        typer.Option(
            "--min-difference",
            min=0.0,
            help="Minimum absolute difference between group means.",
        ),
    ] = 0.0,
    method: Annotated[
        str,
        typer.Option(
            "--method",
            help="Statistical method: auto, moderated, or welch.",
        ),
    ] = "auto",
    sample_sheet: Annotated[
        Path | None,
        typer.Option(
            "--sample-sheet",
            exists=True,
            dir_okay=False,
            help="TSV with sample_id, group and optional covariate values.",
        ),
    ] = None,
    covariates: Annotated[
        list[str] | None,
        typer.Option(
            "--covariate",
            help="Sample-sheet covariate to model; repeat as needed.",
        ),
    ] = None,
    subject_column: Annotated[
        str | None,
        typer.Option(
            "--subject-column",
            help="Sample-sheet subject column for fixed blocking effects.",
        ),
    ] = None,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            help="Root directory containing prepared GEO files.",
            file_okay=False,
        ),
    ] = Path("data/geo"),
) -> None:
    """Run an exploratory probe-level differential expression analysis."""
    annotation_path = (
        data_root
        / "platforms"
        / platform_accession.upper()
        / f"{platform_accession.upper()}.annot.gz"
    )
    try:
        if not annotation_path.exists():
            console.print(f"Downloading annotation for {platform_accession.upper()}...")
            with GeoPlatformDownloader() as downloader:
                downloader.download(platform_accession, data_root=data_root)
        results = DifferentialAnalyzer().analyze(
            accession,
            platform=platform_accession,
            data_root=data_root,
            alpha=alpha,
            min_abs_difference=min_difference,
            method=method,
            sample_sheet=sample_sheet,
            covariates=tuple(covariates or ()),
            subject_column=subject_column,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Differential analysis failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    table = Table(title=f"Differential expression — {accession.upper()}")
    table.add_column("Matrix", style="bold cyan")
    table.add_column("Features", justify="right")
    table.add_column("Mapped", justify="right")
    table.add_column("Genes", justify="right")
    table.add_column("Significant genes", justify="right")
    for result in results:
        table.add_row(
            result.output_path.parent.name,
            str(result.features),
            str(result.mapped_features),
            str(result.genes),
            str(result.significant_genes),
        )
    console.print(table)
    for result in results:
        console.print(f"Results: {result.output_path}")
        console.print(f"Gene-level results: {result.gene_output_path}")
    console.print(
        "Exploratory result: review study design, time points and biological "
        "replication before interpretation.",
        style="bold yellow",
    )


@app.command("sample-sheet")
def sample_sheet_template(
    accession: Annotated[
        str,
        typer.Argument(help="Prepared GEO Series accession (GSE...)."),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            dir_okay=False,
            help="Destination TSV to create.",
        ),
    ],
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            file_okay=False,
            help="Root directory containing prepared GEO studies.",
        ),
    ] = Path("data/geo"),
) -> None:
    """Create an editable sample-sheet template from prepared groups."""
    matches = tuple(
        sorted((data_root / accession.upper() / "prepared").glob("*/sample-groups.tsv"))
    )
    if not matches:
        error_console.print(
            f"No prepared sample groups found for {accession.upper()}.",
            style="bold red",
        )
        raise typer.Exit(code=1)
    if len(matches) > 1:
        error_console.print(
            "Multiple prepared matrices found; choose one sample-groups.tsv manually.",
            style="bold red",
        )
        raise typer.Exit(code=1)
    path = write_sample_sheet_template(matches[0], output)
    console.print(f"Sample sheet template: {path}")
    console.print(
        "Fill requested covariate values before using --sample-sheet.",
        style="bold yellow",
    )


@app.command()
def qc(
    accession: Annotated[
        str,
        typer.Argument(help="Prepared GEO Series accession (GSE...)."),
    ],
    max_features: Annotated[
        int,
        typer.Option(
            "--max-features",
            min=2,
            help="Most variable features used for PCA.",
        ),
    ] = 5000,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            file_okay=False,
            help="Root directory containing prepared GEO studies.",
        ),
    ] = Path("data/geo"),
) -> None:
    """Generate expression QC metrics and diagnostic plots."""
    try:
        results = ExpressionQualityControl().run(
            accession,
            data_root=data_root,
            max_features=max_features,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Quality control failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    for result in results:
        console.print(
            f"QC {result.accession}: {result.samples} samples, "
            f"{result.features} features, "
            f"{len(result.outlier_samples)} candidate outliers."
        )
        console.print(f"Report: {result.report_path}")
        console.print(f"PCA: {result.pca_plot}")
        console.print(f"Distributions: {result.distribution_plot}")
        console.print(f"Correlations: {result.correlation_plot}")


@app.command()
def assess(
    accession: Annotated[
        str,
        typer.Argument(help="Analyzed and quality-controlled GEO Series."),
    ],
    decision: Annotated[
        str,
        typer.Option(
            "--decision",
            help="Eligibility decision: approved, review, or excluded.",
        ),
    ],
    rationale: Annotated[
        str,
        typer.Option(
            "--rationale",
            help="Required scientific justification for the decision.",
        ),
    ],
    species: Annotated[
        str,
        typer.Option(help="Verified species represented by the samples."),
    ],
    tissue: Annotated[
        str,
        typer.Option(help="Verified tissue or cell type."),
    ],
    phenotype: Annotated[
        str,
        typer.Option(help="Exact disease phenotype represented by the comparison."),
    ],
    roles: Annotated[
        list[str] | None,
        typer.Option(
            "--role",
            help=(
                "Allowed use: discovery, external_validation, mechanistic, "
                "or treatment_response; repeat as needed."
            ),
        ),
    ] = None,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            file_okay=False,
            help="Root directory containing analyzed GEO studies.",
        ),
    ] = Path("data/geo"),
) -> None:
    """Record a checksum-bound scientific eligibility decision."""
    try:
        paths = StudyAssessor().assess(
            accession,
            decision=decision,
            rationale=rationale,
            species=species,
            tissue=tissue,
            phenotype=phenotype,
            allowed_roles=tuple(roles or ()),
            data_root=data_root,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Study assessment failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    for path in paths:
        console.print(f"Eligibility: {path}")
    console.print(f"Decision recorded: {decision}")


@app.command()
def rank(
    studies: Annotated[
        list[str],
        typer.Argument(
            help="Two or more independently analyzed GEO Series accessions."
        ),
    ],
    alpha: Annotated[
        float,
        typer.Option(
            "--alpha",
            min=0.000001,
            max=0.999999,
            help="Per-study adjusted p-value threshold.",
        ),
    ] = 0.05,
    min_difference: Annotated[
        float,
        typer.Option(
            "--min-difference",
            min=0.0,
            help="Per-study minimum absolute mean difference.",
        ),
    ] = 0.0,
    min_recurrence: Annotated[
        int,
        typer.Option(
            "--min-recurrence",
            min=2,
            help="Minimum number of significant studies.",
        ),
    ] = 2,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            help="Root directory containing analyzed GEO studies.",
            file_okay=False,
        ),
    ] = Path("data/geo"),
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Directory for the cross-study ranking.",
            file_okay=False,
        ),
    ] = Path("data/analysis"),
) -> None:
    """Rank genes recurring across independent analyzed GEO studies."""
    try:
        result = RecurrenceRanker().rank(
            studies,
            data_root=data_root,
            output_root=output,
            alpha=alpha,
            min_abs_difference=min_difference,
            min_recurrence=min_recurrence,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Recurrence ranking failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Ranked {result.genes} genes across {len(result.studies)} studies; "
        f"{result.recurrent_genes} recurrent."
    )
    console.print(f"Results: {result.output_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Review species, tissue, assay, design and confounders before "
        "interpreting recurrence.",
        style="bold yellow",
    )


@app.command()
def sensitivity(
    studies: Annotated[
        list[str],
        typer.Argument(help="Two or more approved GEO Series accessions."),
    ],
    alphas: Annotated[
        list[float] | None,
        typer.Option(
            "--alpha",
            min=0.000001,
            max=0.999999,
            help="Adjusted p-value threshold; repeat for a custom grid.",
        ),
    ] = None,
    min_differences: Annotated[
        list[float] | None,
        typer.Option(
            "--min-difference",
            min=0.0,
            help="Absolute effect threshold; repeat for a custom grid.",
        ),
    ] = None,
    min_recurrences: Annotated[
        list[int] | None,
        typer.Option(
            "--min-recurrence",
            min=2,
            help="Required study count; repeat for a custom grid.",
        ),
    ] = None,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            file_okay=False,
            help="Root directory containing analyzed GEO studies.",
        ),
    ] = Path("data/geo"),
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Dedicated sensitivity-analysis directory.",
        ),
    ] = Path("data/analysis/sensitivity"),
) -> None:
    """Test recurrence robustness across a declared threshold grid."""
    try:
        result = SensitivityAnalyzer().run(
            studies,
            data_root=data_root,
            output_root=output,
            alphas=tuple(alphas) if alphas else (0.01, 0.05, 0.1),
            min_differences=(
                tuple(min_differences) if min_differences else (0.0, 0.25, 0.5)
            ),
            min_recurrences=(tuple(min_recurrences) if min_recurrences else (2,)),
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(
            f"Sensitivity analysis failed: {error}",
            style="bold red",
        )
        raise typer.Exit(code=1) from error
    console.print(
        f"Completed {result.scenarios} scenarios across "
        f"{len(result.studies)} studies; {result.stable_genes} genes stable "
        "across all scenarios."
    )
    console.print(f"Scenarios: {result.scenario_path}")
    console.print(f"Gene stability: {result.gene_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Sensitivity results are exploratory and cannot be published as "
        "primary claims.",
        style="bold yellow",
    )


@app.command()
def concordance(
    studies: Annotated[
        list[str],
        typer.Argument(help="Two or more approved GEO Series accessions."),
    ],
    minimum_studies: Annotated[
        int,
        typer.Option(
            "--minimum-studies",
            min=2,
            help="Minimum studies in which a gene must be available.",
        ),
    ] = 2,
    nominal_alpha: Annotated[
        float,
        typer.Option(
            "--nominal-alpha",
            min=0.000001,
            max=0.999999,
            help="Raw p-value used only to count supporting studies.",
        ),
    ] = 0.05,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            file_okay=False,
            help="Root directory containing analyzed GEO studies.",
        ),
    ] = Path("data/geo"),
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Dedicated direction-concordance directory.",
        ),
    ] = Path("data/analysis/concordance"),
) -> None:
    """Rank same-direction effects independently of significance cutoffs."""
    try:
        result = DirectionConcordanceAnalyzer().run(
            studies,
            data_root=data_root,
            output_root=output,
            minimum_studies=minimum_studies,
            nominal_alpha=nominal_alpha,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(
            f"Direction concordance failed: {error}",
            style="bold red",
        )
        raise typer.Exit(code=1) from error
    console.print(
        f"Ranked {result.genes} genes across {len(result.studies)} studies; "
        f"{result.concordant_genes} have concordant effect direction."
    )
    console.print(f"Results: {result.output_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Directional agreement is exploratory, not statistical recurrence, "
        "and cannot be published as a primary claim.",
        style="bold yellow",
    )


@app.command()
def shortlist(
    concordance_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            help="Direction-concordance TSV to filter.",
        ),
    ] = Path("data/analysis/concordance/direction-concordance.tsv"),
    minimum_nominal_studies: Annotated[
        int,
        typer.Option(
            "--minimum-nominal-studies",
            min=0,
            help="Minimum studies with a raw p-value below nominal alpha.",
        ),
    ] = 2,
    maximum_fdr: Annotated[
        float,
        typer.Option(
            "--maximum-fdr",
            min=0.000001,
            max=0.999999,
            help="Maximum Fisher combined adjusted p-value.",
        ),
    ] = 0.05,
    minimum_effect_percentile: Annotated[
        float,
        typer.Option(
            "--minimum-effect-percentile",
            min=0.0,
            max=1.0,
            help="Minimum mean within-study absolute-effect percentile.",
        ),
    ] = 0.8,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Output directory; defaults beside the source report.",
        ),
    ] = None,
) -> None:
    """Build an auditable hypothesis-generation candidate list."""
    try:
        result = ShortlistBuilder().build(
            concordance_path,
            output_root=output,
            minimum_nominal_studies=minimum_nominal_studies,
            maximum_combined_fdr=maximum_fdr,
            minimum_effect_percentile=minimum_effect_percentile,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(
            f"Shortlist creation failed: {error}",
            style="bold red",
        )
        raise typer.Exit(code=1) from error
    console.print(f"Selected {result.candidates} exploratory candidates.")
    console.print(f"Shortlist: {result.output_path}")
    console.print(f"Audit record: {result.summary_path}")
    console.print(
        "This shortlist generates hypotheses; it is not independent "
        "validation and cannot be published as a primary claim.",
        style="bold yellow",
    )


@app.command("validate-external")
def validate_external(
    validation_accession: Annotated[
        str,
        typer.Argument(help="Approved study not used during discovery."),
    ],
    shortlist_path: Annotated[
        Path,
        typer.Option(
            "--shortlist",
            exists=True,
            dir_okay=False,
            help="Frozen exploratory shortlist TSV.",
        ),
    ] = Path("data/analysis/concordance/exploratory-shortlist.tsv"),
    nominal_alpha: Annotated[
        float,
        typer.Option(
            "--nominal-alpha",
            min=0.000001,
            max=0.999999,
            help="Validation-study raw p-value threshold.",
        ),
    ] = 0.05,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            file_okay=False,
            help="Root directory containing analyzed GEO studies.",
        ),
    ] = Path("data/geo"),
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Dedicated external-validation directory.",
        ),
    ] = Path("data/analysis/external-validation"),
) -> None:
    """Test a frozen shortlist in one independent approved study."""
    try:
        result = ExternalValidator().validate(
            shortlist_path,
            validation_accession,
            data_root=data_root,
            output_root=output,
            nominal_alpha=nominal_alpha,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(
            f"External validation failed: {error}",
            style="bold red",
        )
        raise typer.Exit(code=1) from error
    console.print(
        f"Matched {result.matched_candidates}/{result.candidates} candidates; "
        f"{result.direction_validated} agree in direction and "
        f"{result.nominally_validated} have nominal directional support."
    )
    console.print(f"Candidate results: {result.output_path}")
    console.print(f"Validation report: {result.summary_path}")
    console.print(
        "This small-cohort validation remains exploratory and creates no "
        "primary claim.",
        style="bold yellow",
    )


@app.command("target-intelligence")
def target_intelligence(
    shortlist_path: Annotated[
        Path,
        typer.Option(
            "--shortlist",
            exists=True,
            dir_okay=False,
            help="Exploratory shortlist supplying gene symbols.",
        ),
    ] = Path("data/analysis/concordance/exploratory-shortlist.tsv"),
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            min=1,
            max=1000,
            help="Maximum shortlist genes to query.",
        ),
    ] = 100,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Target cache and dossier directory.",
        ),
    ] = Path("data/targets"),
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh",
            help="Ignore cached responses and query Open Targets again.",
        ),
    ] = False,
) -> None:
    """Build lightweight Open Targets dossiers for shortlist genes."""
    builder = TargetIntelligenceBuilder()
    try:
        genes = builder.genes_from_shortlist(shortlist_path, limit=limit)
        with OpenTargetsClient() as client:
            result = builder.build(
                genes,
                output_root=output,
                refresh=refresh,
                client=client,
            )
    except (GeoApiError, ValueError) as error:
        error_console.print(
            f"Target intelligence failed: {error}",
            style="bold red",
        )
        raise typer.Exit(code=1) from error
    console.print(
        f"Resolved {result.resolved_targets}/{result.requested_genes} targets."
    )
    console.print(f"Target table: {result.output_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(f"Individual dossiers: {result.dossier_directory}")
    console.print(
        "Evidence dimensions remain separate; no opaque aggregate target "
        "score or therapeutic claim was created.",
        style="bold yellow",
    )


@app.command("target-genetics")
def target_genetics(
    target_table: Annotated[
        Path,
        typer.Option(
            "--targets",
            exists=True,
            dir_okay=False,
            help="Target-intelligence TSV containing Ensembl identifiers.",
        ),
    ] = Path("data/targets/target-intelligence.tsv"),
    disease_id: Annotated[
        str,
        typer.Option(
            "--disease-id",
            help="Open Targets disease identifier.",
        ),
    ] = "MONDO_0005306",
    disease_name: Annotated[
        str,
        typer.Option(
            "--disease-name",
            help="Human-readable disease name recorded in provenance.",
        ),
    ] = "ankylosing spondylitis",
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Disease-specific genetic evidence directory.",
        ),
    ] = Path("data/targets/genetics"),
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh",
            help="Ignore cached genetic evidence and query again.",
        ),
    ] = False,
) -> None:
    """Import AS-specific human genetic evidence and modulation direction."""
    try:
        with OpenTargetsClient() as client:
            result = GeneticEvidenceBuilder().build(
                target_table,
                disease_id=disease_id,
                disease_name=disease_name,
                output_root=output,
                refresh=refresh,
                client=client,
            )
    except (GeoApiError, ValueError) as error:
        error_console.print(
            f"Target genetics failed: {error}",
            style="bold red",
        )
        raise typer.Exit(code=1) from error
    console.print(
        f"Genetic support found for {result.genetically_supported}/"
        f"{result.targets} targets; therapeutic direction resolved for "
        f"{result.direction_resolved}."
    )
    console.print(f"Genetic evidence: {result.output_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Missing or conflicting causal direction remains unknown; expression "
        "direction is never substituted for genetic direction.",
        style="bold yellow",
    )


@app.command("target-context")
def target_context(
    genetic_table: Annotated[
        Path,
        typer.Option(
            "--genetics",
            exists=True,
            dir_okay=False,
            help="Disease-specific genetic evidence TSV.",
        ),
    ] = Path("data/targets/genetics/as-genetic-evidence.tsv"),
    disease_id: Annotated[
        str,
        typer.Option(
            "--disease-id",
            help="Open Targets disease identifier.",
        ),
    ] = "MONDO_0005306",
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Fine-mapping and expression-context directory.",
        ),
    ] = Path("data/targets/context"),
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh",
            help="Ignore cached context responses and query again.",
        ),
    ] = False,
) -> None:
    """Deepen supported targets with fine-mapping and colocalisation."""
    try:
        with OpenTargetsClient() as client:
            result = CausalContextBuilder().build(
                genetic_table,
                disease_id=disease_id,
                output_root=output,
                refresh=refresh,
                client=client,
            )
    except (GeoApiError, ValueError) as error:
        error_console.print(
            f"Target context failed: {error}",
            style="bold red",
        )
        raise typer.Exit(code=1) from error
    console.print(
        f"Deepened {result.targets} targets; "
        f"{result.strong_locus_to_gene} have locus-to-gene score >= 0.5 and "
        f"{result.molecular_colocalisation} have strong molecular "
        "colocalisation."
    )
    console.print(f"Causal context: {result.output_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Baseline expression is contextual annotation, not disease-specific "
        "causality or therapeutic direction.",
        style="bold yellow",
    )


@app.command("target-readiness")
def target_readiness(
    genetics: Annotated[
        Path, typer.Option("--genetics", exists=True, dir_okay=False)
    ] = Path("data/targets/genetics/as-genetic-evidence.tsv"),
    causal_context: Annotated[
        Path, typer.Option("--context", exists=True, dir_okay=False)
    ] = Path("data/targets/context/as-causal-context.tsv"),
    discovery: Annotated[
        Path, typer.Option("--discovery", exists=True, dir_okay=False)
    ] = Path("data/analysis/three-study-concordance/direction-concordance.tsv"),
    validation: Annotated[
        Path, typer.Option("--validation", exists=True, dir_okay=False)
    ] = Path("data/analysis/external-validation/GSE181364-candidate-validation.tsv"),
    intelligence: Annotated[
        Path, typer.Option("--intelligence", exists=True, dir_okay=False)
    ] = Path("data/targets/target-intelligence.tsv"),
    nucleome: Annotated[
        Path | None,
        typer.Option(
            "--nucleome",
            exists=True,
            dir_okay=False,
            help="Optional reference single-cell 3D contact evidence.",
        ),
    ] = Path("data/targets/nucleome/atlas-contact-evidence.tsv"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/targets/readiness"
    ),
) -> None:
    """Integrate causal, expression, cell-context and drug evidence."""
    try:
        result = TherapeuticReadinessBuilder().build(
            genetics_path=genetics,
            context_path=causal_context,
            discovery_path=discovery,
            validation_path=validation,
            intelligence_path=intelligence,
            nucleome_path=nucleome,
            output_root=output,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(
            f"Target readiness failed: {error}",
            style="bold red",
        )
        raise typer.Exit(code=1) from error
    console.print(
        f"Integrated {result.targets} targets; "
        f"{result.mechanistic_priorities} are mechanistic priorities and "
        f"{result.direction_resolved} have a resolved therapeutic direction."
    )
    console.print(f"Readiness matrix: {result.output_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Known drugs show target-level clinical precedent across diseases, "
        "not efficacy in axial spondyloarthritis.",
        style="bold yellow",
    )


@app.command("nucleome-plan")
def nucleome_plan(
    causal_context: Annotated[
        Path, typer.Option("--context", exists=True, dir_okay=False)
    ] = Path("data/targets/context/as-causal-context.tsv"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/targets/nucleome"
    ),
    variant_flank: Annotated[int, typer.Option("--variant-flank", min=1)] = 250_000,
    promoter_flank: Annotated[int, typer.Option("--promoter-flank", min=1)] = 5_000,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Refresh cached gene coordinates.")
    ] = False,
) -> None:
    """Prepare focused 4D Nucleome queries for supported loci."""
    try:
        with httpx.Client(
            timeout=30.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "AXIS/0.1 nucleome-plan",
            },
        ) as http:
            result = NucleomePlanBuilder().build(
                causal_context,
                output_root=output,
                variant_flank=variant_flank,
                promoter_flank=promoter_flank,
                refresh=refresh,
                client=EnsemblClient(client=http),
            )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Nucleome plan failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Prepared {result.loci} locus queries across {result.targets} targets."
    )
    console.print(f"Query plan: {result.output_path}")
    console.print(f"BED regions: {result.regions_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Atlas contacts are healthy reference context, not disease-specific "
        "causality or therapeutic direction.",
        style="bold yellow",
    )


@app.command("nucleome-contacts")
def nucleome_contacts(
    plan: Annotated[Path, typer.Option("--plan", exists=True, dir_okay=False)] = Path(
        "data/targets/nucleome/atlas-query-plan.tsv"
    ),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/targets/nucleome"
    ),
    cells_per_group: Annotated[
        int,
        typer.Option(
            "--cells-per-group",
            min=1,
            max=25,
            help="Cells sampled per subtype and donor.",
        ),
    ] = 3,
    anchor_radius: Annotated[
        int,
        typer.Option(
            "--anchor-radius",
            min=1_000,
            max=100_000,
            help="Maximum distance from variant and promoter anchors.",
        ),
    ] = 25_000,
) -> None:
    """Scan selected annotated PBMC cells for planned 3D contacts."""
    try:
        with httpx.Client(
            timeout=120.0,
            follow_redirects=True,
            headers={"User-Agent": "AXIS/0.1 nucleome-contacts"},
        ) as http:
            result = NucleomeContactBuilder().build(
                plan,
                output_root=output,
                cells_per_subtype_donor=cells_per_group,
                anchor_radius=anchor_radius,
                client=AtlasDownloadClient(client=http),
            )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Nucleome scan failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Scanned {result.downloaded_cells} annotated cells across "
        f"{result.targets} targets; contacts were observed for "
        f"{result.targets_with_observed_contacts} targets."
    )
    console.print(f"Contact evidence: {result.output_path}")
    console.print(f"Cell manifest: {result.cell_manifest_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Not observed in this sparse sample does not mean biological absence.",
        style="bold yellow",
    )


@app.command("single-cell-plan")
def single_cell_plan(
    metadata: Annotated[
        Path, typer.Option("--metadata", exists=True, dir_okay=False)
    ] = Path("data/single-cell/GSE194315/cell-metadata.tsv.gz"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/single-cell/GSE194315/plan"
    ),
    minimum_cells: Annotated[int, typer.Option("--minimum-cells", min=1)] = 20,
    minimum_subjects: Annotated[int, typer.Option("--minimum-subjects", min=2)] = 5,
) -> None:
    """Plan a subject-aware AXI versus healthy single-cell analysis."""
    try:
        result = SingleCellPlanBuilder().build(
            metadata,
            output_root=output,
            minimum_cells_per_subject=minimum_cells,
            minimum_subjects_per_group=minimum_subjects,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Single-cell plan failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Planned {result.included_cells} cells from "
        f"{result.case_subjects} AXI and {result.control_subjects} healthy "
        f"subjects; {result.eligible_cell_types} cell types are eligible."
    )
    console.print(f"Cell-type design: {result.output_path}")
    console.print(f"Subject design: {result.subject_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Subjects, not individual cells, are the biological replicates.",
        style="bold yellow",
    )


@app.command("analyze-single-cell")
def analyze_single_cell(
    archive: Annotated[
        Path, typer.Option("--archive", exists=True, dir_okay=False)
    ] = Path(
        "data/single-cell/GSE194315/GSE194315_PBMC-01-07_processed_data_files.tar.gz"
    ),
    metadata: Annotated[
        Path, typer.Option("--metadata", exists=True, dir_okay=False)
    ] = Path("data/single-cell/GSE194315/cell-metadata.tsv.gz"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/single-cell/GSE194315/pseudobulk"
    ),
    minimum_cells: Annotated[int, typer.Option("--minimum-cells", min=1)] = 20,
) -> None:
    """Stream GSE194315 into subject-level targeted pseudobulk results."""
    try:
        result = SingleCellPseudobulkAnalyzer().analyze(
            archive,
            metadata,
            minimum_cells=minimum_cells,
            output_root=output,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Single-cell analysis failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Analyzed {result.runs} runs and {result.subjects} subjects; "
        f"created {result.comparisons} targeted cell-type comparisons."
    )
    console.print(f"Target results: {result.output_path}")
    console.print(f"Pseudobulk values: {result.pseudobulk_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Subjects, not cells, are tested as independent replicates.",
        style="bold yellow",
    )


@app.command("expand-single-cell-reference")
def expand_single_cell_reference(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/single-cell/GSE194315/reference-expansion"
    ),
) -> None:
    """Test DDX24 and ADA across every adequately replicated PBMC cell type."""
    try:
        result = SingleCellReferenceExpander().expand(
            archive_path=(
                "data/single-cell/GSE194315/"
                "GSE194315_PBMC-01-07_processed_data_files.tar.gz"
            ),
            metadata_path=(
                "data/single-cell/GSE194315/cell-metadata.tsv.gz"
            ),
            cell_type_design_path=(
                "data/single-cell/GSE194315/plan/cell-type-design.tsv"
            ),
            output_root=output,
        )
    except (OSError, ValueError, GeoApiError) as error:
        error_console.print(f"Single-cell reference expansion failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(
        f"Tested {result.targets} targets across {result.cell_types} "
        f"eligible cell types ({result.comparisons} comparisons)."
    )
    console.print(f"Results: {result.results_path}")


@app.command("analyze-single-cell-robustness")
def analyze_single_cell_robustness(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/single-cell/GSE194315/robustness"
    ),
) -> None:
    """Adjust available batches and run leave-one-subject-out checks."""
    result = SingleCellRobustnessAnalyzer().analyze(
        pseudobulk_path=(
            "data/single-cell/GSE194315/reference-expansion/"
            "pseudobulk/targeted-pseudobulk.tsv"
        ),
        metadata_path="data/single-cell/GSE194315/cell-metadata.tsv.gz",
        reference_results_path=(
            "data/single-cell/GSE194315/reference-expansion/"
            "target-cell-type-validation.tsv"
        ),
        output_root=output,
    )
    console.print(
        f"Completed {result.adjusted_tests} batch-adjusted tests and "
        f"{result.leave_one_out_tests} leave-one-subject-out tests."
    )
    console.print(f"Summary: {result.summary_path}")


@app.command("review-secondary-single-cell")
def review_secondary_single_cell(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/single-cell-validation/secondary-cohorts"
    ),
) -> None:
    """Select a second single-cell cohort from deposited GEO metadata."""
    result = SecondarySingleCellReviewer().review(
        gse277117_matrices=tuple(
            sorted(Path("data/geo/GSE277117").glob("*_series_matrix.txt.gz"))
        ),
        gse288581_matrix=(
            "data/geo/GSE288581/GSE288581_series_matrix.txt.gz"
        ),
        output_root=output,
    )
    console.print(
        f"Reviewed {result.candidates} candidates; selected "
        f"{result.selected_accession}."
    )
    console.print(f"Decisions: {result.review_path}")


@app.command("validate-gse288581")
def validate_gse288581(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/single-cell-validation/GSE288581"
    ),
) -> None:
    """Download only blood GEX matrices and validate DDX24/ADA by donor."""
    try:
        with Gse288581Validator() as validator:
            result = validator.validate(
                series_matrix_path=(
                    "data/geo/GSE288581/GSE288581_series_matrix.txt.gz"
                ),
                output_root=output,
            )
    except (OSError, ValueError, GeoApiError) as error:
        error_console.print(f"GSE288581 validation failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(
        f"Validated {result.targets} targets in {result.donors} donors; "
        f"downloaded {result.downloaded_files} files."
    )
    console.print(f"Results: {result.results_path}")


@app.command("synthesize-cd8-cohorts")
def synthesize_cd8_cohorts(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/single-cell-validation/CD8-cross-cohort"
    ),
) -> None:
    """Synthesize donor-level target effects across independent CD8 cohorts."""
    try:
        result = Cd8CrossCohortAnalyzer().analyze(
            gse194315_path=(
                "data/single-cell/GSE194315/robustness/"
                "batch-adjusted-targets.tsv"
            ),
            gse288581_path=(
                "data/analysis/single-cell-validation/GSE288581/"
                "target-validation.tsv"
            ),
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"CD8 cross-cohort synthesis failed: {error}")
        raise typer.Exit(code=1) from error
    console.print(
        f"Synthesized {result.targets} targets across "
        f"{result.cohorts} independent CD8 cohorts."
    )
    console.print(f"Results: {result.summary_path}")


@app.command("audit-cd8-evidence")
def audit_cd8_evidence(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/single-cell-validation/CD8-evidence-review"
    ),
) -> None:
    """Freeze third-cohort eligibility and systematic-review readiness."""
    result = Cd8EvidenceReviewer().review(output_root=output)
    console.print(
        f"Audited {result.candidates} candidate cohorts; "
        f"{result.eligible} are meta-analysis eligible."
    )
    console.print(f"Readiness: {result.readiness_path}")


@app.command("synthesize-hierarchical-evidence")
def synthesize_hierarchical_evidence(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/hierarchical-target-evidence"
    ),
) -> None:
    """Compare target evidence across CD8 and bulk blood assay strata."""
    result = HierarchicalEvidenceAnalyzer().analyze(
        cd8_effects_path=(
            "data/analysis/single-cell-validation/CD8-cross-cohort/"
            "cohort-effects.tsv"
        ),
        cd8_summary_path=(
            "data/analysis/single-cell-validation/CD8-cross-cohort/"
            "cross-cohort-summary.tsv"
        ),
        microarray_effects_path=(
            "data/analysis/target-meta-analysis/study-effects.tsv"
        ),
        microarray_summary_path=(
            "data/analysis/target-meta-analysis/target-meta-analysis.tsv"
        ),
        gse181364_path=(
            "data/analysis/external-validation/"
            "GSE181364-candidate-validation.tsv"
        ),
        gse299639_path=(
            "data/analysis/external-validation/GSE299639/target-validation.tsv"
        ),
        output_root=output,
    )
    console.print(
        f"Synthesized {result.cohorts} cohorts and "
        f"{result.participants} participants across assay contexts."
    )
    console.print(f"Results: {result.synthesis_path}")


@app.command("freeze-ddx24-evidence")
def freeze_ddx24_evidence(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/analysis/ddx24-evidence-freeze"
    ),
) -> None:
    """Audit final confounding and freeze DDX24 confirmation gates."""
    result = ConfoundingFreezeBuilder().build(
        covariates_path=(
            "data/single-cell/GSE194315/robustness/"
            "covariate-availability.tsv"
        ),
        batch_adjusted_path=(
            "data/single-cell/GSE194315/robustness/"
            "batch-adjusted-targets.tsv"
        ),
        leave_one_out_path=(
            "data/single-cell/GSE194315/robustness/"
            "leave-one-out-stability.tsv"
        ),
        hierarchical_path=(
            "data/analysis/hierarchical-target-evidence/"
            "hierarchical-synthesis.tsv"
        ),
        context_path=(
            "data/analysis/hierarchical-target-evidence/context-summary.tsv"
        ),
        gse288581_sensitivity_path=(
            "data/analysis/single-cell-validation/GSE288581/"
            "leave-one-donor-out.tsv"
        ),
        output_root=output,
    )
    console.print(
        f"Frozen {result.checks} confounding checks and "
        f"{result.criteria} decision criteria."
    )
    console.print(f"Decision: {result.decision_path}")


@app.command("prepare-ddx24-publication")
def prepare_ddx24_publication(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/publication/ddx24-study"
    ),
) -> None:
    """Build the DDX24 manuscript draft and prospective RT-qPCR protocol."""
    result = PublicationReadinessBuilder().build(
        hierarchical_path=(
            "data/analysis/hierarchical-target-evidence/"
            "hierarchical-synthesis.tsv"
        ),
        context_path=(
            "data/analysis/hierarchical-target-evidence/context-summary.tsv"
        ),
        decision_path=(
            "data/analysis/ddx24-evidence-freeze/decision-summary.json"
        ),
        criteria_path=(
            "data/analysis/ddx24-evidence-freeze/"
            "confirmation-refutation-criteria.tsv"
        ),
        output_root=output,
    )
    console.print(f"Manuscript: {result.manuscript_path}")
    console.print(f"RT-qPCR protocol: {result.protocol_path}")


@app.command("finalize-ddx24-article")
def finalize_ddx24_article(
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path(
        "data/publication/ddx24-study"
    ),
) -> None:
    """Generate final article figures, references and external-review form."""
    result = ArticleFinalizer().finalize(
        cohort_path=(
            "data/analysis/hierarchical-target-evidence/cohort-evidence.tsv"
        ),
        context_path=(
            "data/analysis/hierarchical-target-evidence/context-summary.tsv"
        ),
        output_root=output,
    )
    console.print(
        f"Generated {result.figures} figures and "
        f"{result.references} verified references."
    )
    console.print(f"External review form: {result.review_path}")


@app.command("reproduce")
def reproduce_study(
    study: Annotated[
        str,
        typer.Argument(help="Frozen study identifier, for example ddx24-study."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", file_okay=False, help="AXIS workspace root."),
    ] = Path("."),
    manifest: Annotated[
        Path | None,
        typer.Option(
            "--manifest",
            dir_okay=False,
            help=(
                "Optional manifest path; defaults to "
                "reproducibility/<study>/manifest.json."
            ),
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", file_okay=False),
    ] = Path("data/reproducibility"),
) -> None:
    """Rebuild and verify a frozen computational study without network access."""
    try:
        result = StudyReproducer().reproduce(
            study,
            workspace=workspace,
            manifest_path=manifest,
            output_root=output,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        error_console.print(f"Reproduction failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Reproduced {result.study}: "
        f"{result.passed}/{result.checks} checks passed."
    )
    console.print(f"Report: {result.report_path}")


@app.command("demo")
def run_demo(
    workspace: Annotated[
        Path,
        typer.Option("--workspace", file_okay=False, help="AXIS workspace root."),
    ] = Path("."),
    manifest: Annotated[
        Path,
        typer.Option("--manifest", dir_okay=False),
    ] = Path("examples/demo/manifest.json"),
    output: Annotated[
        Path,
        typer.Option("--output", file_okay=False),
    ] = Path("demo-output"),
) -> None:
    """Run the small offline synthetic AXIS demonstration."""
    try:
        result = AxisDemoRunner().run(
            workspace=workspace,
            manifest_path=manifest,
            output_root=output,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        error_console.print(f"Demo failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Synthetic demo passed: {result.passed}/{result.checks} checks."
    )
    console.print(f"Report: {result.report_path}")


@app.command("benchmark")
def run_benchmark(
    repetitions: Annotated[
        int,
        typer.Option("--repetitions", "-n", min=1, max=1000),
    ] = 10,
    warmups: Annotated[
        int,
        typer.Option("--warmups", min=0, max=100),
    ] = 1,
    workspace: Annotated[
        Path,
        typer.Option("--workspace", file_okay=False, help="AXIS workspace root."),
    ] = Path("."),
    manifest: Annotated[
        Path,
        typer.Option("--manifest", dir_okay=False),
    ] = Path("examples/demo/manifest.json"),
    output: Annotated[
        Path,
        typer.Option("--output", file_okay=False),
    ] = Path("benchmark-output"),
) -> None:
    """Benchmark repeated offline runs of the synthetic demonstration."""
    try:
        result = DemoBenchmarker().run(
            repetitions=repetitions,
            warmups=warmups,
            workspace=workspace,
            manifest_path=manifest,
            output_root=output,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        error_console.print(f"Benchmark failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Synthetic benchmark passed: {result.repetitions} measured runs "
        f"after {result.warmups} warmup runs."
    )
    console.print(f"Report: {result.report_path}")
    console.print(f"Runs: {result.runs_path}")


@app.command("prepare-workflow-comparison")
def prepare_workflow_comparison(
    output: Annotated[
        Path,
        typer.Option("--output", file_okay=False),
    ] = Path("workflow-comparison"),
) -> None:
    """Create the blinded, synthetic package used to compare analysis workflows."""
    try:
        result = WorkflowComparisonPreparer().prepare(output_root=output)
    except (OSError, ValueError) as error:
        error_console.print(f"Comparison preparation failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    console.print(f"Evaluator package: {result.output_root / 'evaluator-package'}")
    console.print(
        f"Coordinator reference: {result.output_root / 'coordinator-reference'}"
    )
    console.print(f"Manifest: {result.manifest_path}")


@app.command("summarize-workflow-comparison")
def summarize_workflow_comparison(
    assessments: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            dir_okay=False,
            help="Exactly two reviewer TSV files.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", file_okay=False),
    ] = Path("workflow-comparison-summary"),
    consensus: Annotated[
        Path | None,
        typer.Option("--consensus", exists=True, dir_okay=False),
    ] = None,
) -> None:
    """Summarize two independent workflow assessments without a weighted score."""
    try:
        result = WorkflowComparisonSummarizer().summarize(
            assessments,
            consensus_path=consensus,
            output_root=output,
        )
    except (OSError, ValueError) as error:
        error_console.print(f"Comparison summary failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error

    console.print(f"Report: {result.report_path}")
    console.print(f"Article table: {result.article_table_path}")
    console.print(f"Consensus template: {result.consensus_template_path}")
    console.print(f"Unresolved disagreements: {result.unresolved_disagreements}")


@app.command("analyze-single-cell-transcriptome")
def analyze_single_cell_transcriptome(
    archive: Annotated[
        Path, typer.Option("--archive", exists=True, dir_okay=False)
    ] = Path(
        "data/single-cell/GSE194315/GSE194315_PBMC-01-07_processed_data_files.tar.gz"
    ),
    metadata: Annotated[
        Path, typer.Option("--metadata", exists=True, dir_okay=False)
    ] = Path("data/single-cell/GSE194315/cell-metadata.tsv.gz"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/single-cell/GSE194315/transcriptome"
    ),
    minimum_cells: Annotated[int, typer.Option("--minimum-cells", min=1)] = 20,
    minimum_cpm: Annotated[float, typer.Option("--minimum-cpm", min=0.0)] = 1.0,
    minimum_group_fraction: Annotated[
        float,
        typer.Option("--minimum-group-fraction", min=0.01, max=1.0),
    ] = 0.2,
    bulk: Annotated[Path | None, typer.Option("--bulk", dir_okay=False)] = Path(
        "data/analysis/three-study-concordance/direction-concordance.tsv"
    ),
    readiness: Annotated[
        Path | None, typer.Option("--readiness", dir_okay=False)
    ] = Path("data/targets/readiness/therapeutic-readiness.tsv"),
) -> None:
    """Analyze all detected genes and predeclared immune pathways by subject."""
    try:
        result = SingleCellTranscriptomeAnalyzer().analyze(
            archive,
            metadata,
            minimum_cells=minimum_cells,
            minimum_cpm=minimum_cpm,
            minimum_group_fraction=minimum_group_fraction,
            bulk_path=bulk,
            readiness_path=readiness,
            output_root=output,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Transcriptome analysis failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Tested {result.genes_tested} gene/cell-type combinations and "
        f"{result.pathways_tested} pathway/cell-type combinations."
    )
    console.print(f"Differential genes: {result.differential_path}")
    console.print(f"Pathways: {result.pathway_path}")
    console.print(f"Integrated candidates: {result.candidate_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "The ranking is exploratory; AlphaFold is reserved for candidates "
        "that survive causal and replication review.",
        style="bold yellow",
    )


@app.command("review-single-cell-candidates")
def review_single_cell_candidates(
    candidates: Annotated[
        Path, typer.Option("--candidates", exists=True, dir_okay=False)
    ] = Path("data/single-cell/GSE194315/transcriptome/integrated-candidates.tsv"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/single-cell/GSE194315/candidate-review"
    ),
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Refresh Open Targets evidence.")
    ] = False,
) -> None:
    """Apply causal, safety and tractability gates to single-cell candidates."""
    reviewer = CandidateReviewBuilder()
    genes = reviewer.selected_genes(candidates)
    if not genes:
        error_console.print("No candidates passed transcriptomic triage.", style="red")
        raise typer.Exit(code=1)
    intelligence_root = output / "intelligence"
    genetics_root = output / "genetics"
    context_root = output / "context"
    try:
        with OpenTargetsClient() as client:
            intelligence = TargetIntelligenceBuilder().build(
                genes,
                output_root=intelligence_root,
                refresh=refresh,
                client=client,
            )
            genetics = GeneticEvidenceBuilder().build(
                intelligence.output_path,
                output_root=genetics_root,
                refresh=refresh,
                client=client,
            )
            context = CausalContextBuilder().build(
                genetics.output_path,
                output_root=context_root,
                refresh=refresh,
                client=client,
            )
        result = reviewer.build(
            candidates,
            intelligence_path=intelligence.output_path,
            genetics_path=genetics.output_path,
            context_path=context.output_path,
            output_root=output,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Candidate review failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Reviewed {result.candidates} candidates: {result.advance} advance "
        f"to perturbation and {result.evidence_generation} require more evidence."
    )
    console.print(f"Review: {result.output_path}")
    console.print(f"Decision rules: {result.summary_path}")
    console.print(
        "AlphaFold is enabled only after the causal and safety gates pass.",
        style="bold yellow",
    )


@app.command("plan-single-cell-replication")
def plan_single_cell_replication(
    candidates: Annotated[
        Path, typer.Option("--candidates", exists=True, dir_okay=False)
    ] = Path("data/single-cell/GSE194315/candidate-review/candidate-causal-review.tsv"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/single-cell/independent-replication"
    ),
) -> None:
    """Select independent cohorts without mixing discovery and validation."""
    try:
        result = SingleCellReplicationPlanner().build(candidates, output_root=output)
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Replication planning failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Reviewed {result.studies} cohorts; {result.eligible} meet the "
        "scientific criteria for direct replication."
    )
    console.print(f"Study eligibility: {result.output_path}")
    console.print(f"Candidate plan: {result.candidate_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Raw SRA reconstruction is intentionally not started automatically.",
        style="bold yellow",
    )


@app.command("audit-single-cell-publication-access")
def audit_single_cell_publication_access(
    article_xml: Annotated[
        Path, typer.Option("--article-xml", exists=True, dir_okay=False)
    ] = Path(".tmp/PMC11926545.xml"),
    supplements: Annotated[
        Path, typer.Option("--supplements", exists=True, dir_okay=False)
    ] = Path("C:/tmp/PMC11926545-supplementary.zip"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/single-cell/independent-replication/access-audit"
    ),
) -> None:
    """Verify that a publication exposes a distinct primary-data accession."""
    try:
        result = ReplicationAccessAuditor().audit(
            article_xml, supplements, output_root=output
        )
    except (OSError, ValueError) as error:
        error_console.print(f"Access audit failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Found {len(result.identifiers)} repository identifier(s); "
        f"primary access verified: {result.primary_accession_verified}."
    )
    console.print(f"Audit: {result.output_path}")
    if not result.primary_accession_verified:
        console.print(
            "The reported cohort cannot be downloaded reproducibly from the "
            "publication as currently archived.",
            style="bold yellow",
        )


@app.command("validate-published-single-cell")
def validate_published_single_cell(
    workbook: Annotated[
        Path, typer.Option("--workbook", exists=True, dir_okay=False)
    ] = Path(".tmp/PMC11926545-supplementary/DataSheet2.xlsx"),
    candidates: Annotated[
        Path, typer.Option("--candidates", exists=True, dir_okay=False)
    ] = Path("data/single-cell/GSE194315/candidate-review/candidate-causal-review.tsv"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/single-cell/independent-replication/published-validation"
    ),
) -> None:
    """Validate candidate directions in an independent published DE table."""
    try:
        result = PublishedSupplementValidator().validate(
            workbook, candidates, output_root=output
        )
    except (OSError, ValueError) as error:
        error_console.print(f"Published validation failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Reviewed {result.candidates} candidates: {result.supported} have "
        f"published directional support and {result.conflicts} conflict."
    )
    console.print(f"Candidate validation: {result.output_path}")
    console.print(f"Matched published rows: {result.evidence_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Published cell-level results are useful orthogonal evidence but do "
        "not replace donor-level pseudobulk replication.",
        style="bold yellow",
    )


@app.command("build-focused-target-dossier")
def build_focused_target_dossier(
    gene: Annotated[str, typer.Argument(help="Gene symbol to deepen.")] = "EWSR1",
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/targets/focused/EWSR1"
    ),
) -> None:
    """Build a falsifiable mechanistic dossier for a convergent candidate."""
    try:
        result = FocusedTargetDossierBuilder().build(
            gene,
            bulk_path=(
                "data/analysis/three-study-concordance/direction-concordance.tsv"
            ),
            single_cell_path=(
                "data/single-cell/GSE194315/transcriptome/cell-type-differential.tsv"
            ),
            published_path=(
                "data/single-cell/independent-replication/"
                "published-validation/published-candidate-validation.tsv"
            ),
            intelligence_path=(
                "data/single-cell/GSE194315/candidate-review/"
                "intelligence/target-intelligence.tsv"
            ),
            genetics_path=(
                "data/single-cell/GSE194315/candidate-review/"
                "genetics/as-genetic-evidence.tsv"
            ),
            dossier_directory=(
                "data/single-cell/GSE194315/candidate-review/intelligence/dossiers"
            ),
            output_root=output,
        )
    except (GeoApiError, OSError, ValueError, KeyError) as error:
        error_console.print(f"Focused dossier failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(f"{result.gene}: {result.decision}.")
    console.print(f"Evidence: {result.evidence_path}")
    console.print(f"Experiment: {result.experiment_path}")
    console.print(f"Dossier: {result.dossier_path}")
    console.print(
        "This nominates a perturbation experiment, not a drug or treatment.",
        style="bold yellow",
    )


@app.command("analyze-target-stability")
def analyze_target_stability(
    gene: Annotated[str, typer.Argument(help="Focused target gene.")] = "EWSR1",
    archive: Annotated[
        Path, typer.Option("--archive", exists=True, dir_okay=False)
    ] = Path(
        "data/single-cell/GSE194315/GSE194315_PBMC-01-07_processed_data_files.tar.gz"
    ),
    metadata: Annotated[
        Path, typer.Option("--metadata", exists=True, dir_okay=False)
    ] = Path("data/single-cell/GSE194315/cell-metadata.tsv.gz"),
    output: Annotated[Path, typer.Option("--output", "-o", file_okay=False)] = Path(
        "data/targets/focused/EWSR1/stability"
    ),
    bootstrap_iterations: Annotated[
        int, typer.Option("--bootstrap-iterations", min=100)
    ] = 5000,
) -> None:
    """Test confidence intervals and leave-one-donor-out target stability."""
    pseudobulk_root = output / "pseudobulk"
    try:
        aggregation = SingleCellPseudobulkAnalyzer().analyze(
            archive,
            metadata,
            target_genes=(gene.strip().upper(),),
            minimum_cells=20,
            output_root=pseudobulk_root,
        )
        result = TargetStabilityAnalyzer().analyze(
            aggregation.pseudobulk_path,
            gene=gene,
            bootstrap_iterations=bootstrap_iterations,
            output_root=output,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Target stability failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Analyzed {result.comparisons} cell-type effects; "
        f"{result.stable_comparisons} passed the donor-stability rule."
    )
    console.print(f"Stability: {result.output_path}")
    console.print(f"Leave-one-donor-out: {result.leave_one_out_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Stable association supports perturbation testing but does not prove "
        "causality or therapeutic direction.",
        style="bold yellow",
    )


@app.command()
def design(
    accession: Annotated[
        str,
        typer.Argument(help="Analyzed GEO Series accession (GSE...)."),
    ],
    independence: Annotated[
        str,
        typer.Option(
            "--independence",
            help="Sample structure: independent, repeated, or unknown.",
        ),
    ],
    paired_by: Annotated[
        str | None,
        typer.Option(
            "--paired-by",
            help="Variable linking paired or repeated samples.",
        ),
    ] = None,
    covariates: Annotated[
        list[str] | None,
        typer.Option(
            "--covariate",
            help="Declared covariate; repeat for multiple values.",
        ),
    ] = None,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            file_okay=False,
            help="Root directory containing analyzed GEO studies.",
        ),
    ] = Path("data/geo"),
) -> None:
    """Create a formal design contract and method recommendation."""
    try:
        paths = DesignInspector().create(
            accession,
            independence=independence,
            paired_by=paired_by,
            covariates=tuple(covariates or ()),
            data_root=data_root,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"Design creation failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        console.print(f"Design: {path}")
        console.print(f"Recommended method: {payload['recommended_method']}")
        for warning in payload["warnings"]:
            console.print(f"Warning: {warning}", style="bold yellow")


@app.command("publish-ranking")
def publish_ranking(
    context: typer.Context,
    ranking: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            help="Cross-study recurrence-ranking.tsv file.",
        ),
    ],
) -> None:
    """Publish recurrent genes as immutable Evidence Store claims."""
    settings = _settings(context)
    try:
        with EvidenceStore(settings.database) as store:
            result = RankingPublisher().publish(ranking, store=store)
    except (OSError, KeyError, ValueError) as error:
        error_console.print(f"Ranking publication failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Published {result.claims_added} claims from "
        f"{result.recurrent_rows} recurrent rows."
    )
    if not result.claims_added:
        console.print(
            "No claims were created because no row satisfies recurrence.",
            style="bold yellow",
        )


@app.command("analyze-rnaseq")
def analyze_rnaseq(
    accession: Annotated[
        str,
        typer.Argument(help="GEO Series accession (GSE...)."),
    ],
    input_path: Annotated[
        Path,
        typer.Option(
            "--input",
            exists=True,
            dir_okay=False,
            help="Normalized RNA-seq abundance table (.tsv or .gz).",
        ),
    ],
    case_columns: Annotated[
        str,
        typer.Option(
            "--case-columns",
            help="Regular expression matching case sample columns.",
        ),
    ],
    control_columns: Annotated[
        str,
        typer.Option(
            "--control-columns",
            help="Regular expression matching control sample columns.",
        ),
    ],
    gene_column: Annotated[
        str,
        typer.Option(help="Column containing gene symbols."),
    ] = "Gene",
    transcript_column: Annotated[
        str,
        typer.Option(help="Column containing transcript identifiers."),
    ] = "mRNA",
    exclude_columns: Annotated[
        str | None,
        typer.Option(
            "--exclude-columns",
            help="Optional regex excluding sample columns before analysis.",
        ),
    ] = None,
    analysis_label: Annotated[
        str | None,
        typer.Option(
            "--analysis-label",
            help="Safe label used for a separate sensitivity output directory.",
        ),
    ] = None,
    alpha: Annotated[
        float,
        typer.Option(
            "--alpha",
            min=0.000001,
            max=0.999999,
            help="Adjusted p-value threshold.",
        ),
    ] = 0.05,
    min_log2fc: Annotated[
        float,
        typer.Option(
            "--min-log2fc",
            min=0.0,
            help="Minimum absolute log2 fold change.",
        ),
    ] = 0.0,
    data_root: Annotated[
        Path,
        typer.Option(
            "--data-root",
            file_okay=False,
            help="Root directory containing GEO data.",
        ),
    ] = Path("data/geo"),
) -> None:
    """Analyze a normalized RNA-seq abundance table."""
    try:
        result = NormalizedRnaSeqAnalyzer().analyze(
            accession,
            input_path=input_path,
            case_pattern=case_columns,
            control_pattern=control_columns,
            data_root=data_root,
            gene_column=gene_column,
            transcript_column=transcript_column,
            exclude_column_pattern=exclude_columns,
            analysis_label=analysis_label,
            alpha=alpha,
            min_abs_log2_fold_change=min_log2fc,
        )
    except (GeoApiError, ValueError) as error:
        error_console.print(f"RNA-seq analysis failed: {error}", style="bold red")
        raise typer.Exit(code=1) from error
    console.print(
        f"Analyzed {result.transcripts} transcripts and {result.genes} genes; "
        f"{result.significant_genes} significant genes."
    )
    console.print(f"Transcript results: {result.transcript_output_path}")
    console.print(f"Gene-level results: {result.gene_output_path}")
    console.print(f"Method: {result.summary_path}")
    console.print(
        "Normalized-abundance workflow: use a raw-count model such as "
        "DESeq2/edgeR when integer counts are available.",
        style="bold yellow",
    )


@app.command("studies")
def list_studies(context: typer.Context) -> None:
    """List all studies currently stored locally."""
    settings = _settings(context)
    with EvidenceStore(settings.database) as store:
        studies = store.studies.list_all()
    if not studies:
        console.print("No studies stored. Run [bold]axis search QUERY[/bold] first.")
        return
    console.print(_studies_table(studies, title=f"Stored studies — {len(studies)}"))


@app.command()
def study(
    context: typer.Context,
    accession: Annotated[str, typer.Argument(help="GEO Series accession (GSE...).")],
) -> None:
    """Show one stored study with its provenance."""
    settings = _settings(context)
    try:
        with EvidenceStore(settings.database) as store:
            value = store.studies.get(accession.upper())
    except RecordNotFoundError as error:
        error_console.print(
            f"Study {accession.upper()} is not stored.",
            style="bold red",
        )
        raise typer.Exit(code=1) from error
    console.print(_study_panel(value))


@app.command()
def info(context: typer.Context) -> None:
    """Show the state of the local Evidence Store."""
    settings = _settings(context)
    with EvidenceStore(settings.database) as store:
        statistics = store.statistics()
    table = Table(title="AXIS Evidence Store", show_header=False)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    table.add_row("Database", str(settings.database))
    table.add_row("Schema version", str(statistics.schema_version))
    table.add_row("Studies", str(statistics.studies))
    table.add_row("Claims", str(statistics.claims))
    table.add_row("Hypotheses", str(statistics.hypotheses))
    console.print(table)


def _studies_table(studies: tuple[Study, ...], *, title: str) -> Table:
    table = Table(title=title)
    table.add_column("Accession", style="bold cyan", no_wrap=True)
    table.add_column("Organism", no_wrap=True)
    table.add_column("Samples", justify="right")
    table.add_column("Type")
    table.add_column("Title", overflow="fold")
    for value in studies:
        table.add_row(
            Text(value.identifier),
            Text(", ".join(value.organisms) or "—"),
            str(value.sample_count) if value.sample_count is not None else "—",
            Text(value.experiment_type or "—"),
            Text(value.title),
        )
    return table


def _study_panel(study: Study) -> Panel:
    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold cyan", no_wrap=True)
    details.add_column()
    fields = (
        ("Title", study.title),
        ("Summary", study.summary or "—"),
        ("Organism", ", ".join(study.organisms) or "—"),
        ("Type", study.experiment_type or "—"),
        (
            "Samples",
            str(study.sample_count) if study.sample_count is not None else "—",
        ),
        ("Platforms", ", ".join(study.platform_ids) or "—"),
        ("Publications", ", ".join(study.publication_ids) or "—"),
        ("BioProject", study.bioproject_id or "—"),
        ("Released", str(study.released_on) if study.released_on else "—"),
        ("Retrieved", study.provenance.retrieved_at.isoformat()),
        ("Source", study.provenance.source_uri or "—"),
        ("Checksum", study.provenance.checksum or "—"),
    )
    for label, value in fields:
        details.add_row(label, Text(value))
    return Panel(details, title=Text(study.identifier), border_style="cyan")


if __name__ == "__main__":
    app()
