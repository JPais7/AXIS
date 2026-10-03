"""Small discovery inspection commands; scientific logic lives in services."""

import json
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import duckdb
import typer
from rich.console import Console
from rich.table import Table

from axis.discovery import DiscoveryService
from axis.discovery.curation import import_curated_erap1
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.storage.ownership import StoreOwnershipError

app = typer.Typer(help="Inspect discovery projects and conceptual proposals.")
project_app = typer.Typer(help="Discovery project inspection.")
question_app = typer.Typer(help="Project uncertainty inspection.")
strategy_app = typer.Typer(help="Competing strategies; no automatic ranking.")
perturbation_app = typer.Typer(help="Proposed and performed perturbations.")
app.add_typer(project_app, name="project")
app.add_typer(question_app, name="question")
app.add_typer(strategy_app, name="strategy")
app.add_typer(perturbation_app, name="perturbation")


def _default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"cannot encode {type(value).__name__}")


def _run(context: typer.Context, action: Callable[[EvidenceStore], Any]) -> Any:
    settings = context.find_root().obj
    database = getattr(settings, "database", None)
    if not isinstance(database, Path):
        raise RuntimeError("AXIS database settings are missing")
    try:
        with EvidenceStore(database) as store:
            return action(store)
    except (
        RecordNotFoundError,
        RecordConflictError,
        ValueError,
        duckdb.Error,
        OSError,
        StoreOwnershipError,
    ) as error:
        typer.echo(f"Discovery error: {error}", err=True)
        raise typer.Exit(code=1) from error


def _output(value: object) -> None:
    typer.echo(json.dumps(value, default=_default, indent=2, ensure_ascii=True))


@app.command("demo")
def create_demo(context: typer.Context) -> None:
    """Create an idempotent DEVELOPMENT fixture with no imported evidence/results."""
    traversal = _run(context, lambda store: DiscoveryService(store).create_erap1_demo())
    typer.echo("DEVELOPMENT/DEMO: proposals only; no imported scientific evidence.")
    typer.echo(f"Created {traversal.project.project_id}; no strategy selected.")


@app.command("import-erap1")
def import_erap1(context: typer.Context) -> None:
    """Explicitly import the frozen source-grounded ERAP1 package; no network."""
    traversal = _run(context, import_curated_erap1)
    typer.echo(f"Imported {traversal.project.project_id}; expert review pending.")
    typer.echo("13 primary-source assertions; proposals remain separately labelled.")


@project_app.command("list")
def list_projects(
    context: typer.Context,
    as_json: Annotated[
        bool, typer.Option("--json", help="Machine-readable records.")
    ] = False,
) -> None:
    projects = _run(context, lambda store: store.projects.list_all())
    if as_json:
        _output(projects)
        return
    table = Table("Project", "Target × disease pair", "Status", "Objective")
    for project in projects:
        table.add_row(
            project.project_id,
            project.target_disease_pair,
            project.status.value,
            project.objective,
        )
    Console().print(table)


@project_app.command("show")
def show_project(
    context: typer.Context,
    project_id: str,
    as_json: Annotated[
        bool, typer.Option("--json", help="Complete stored traversal.")
    ] = False,
) -> None:
    traversal = _run(
        context, lambda store: DiscoveryService(store).inspect_project(project_id)
    )
    if as_json:
        _output(traversal)
        return
    typer.echo(f"{traversal.pair.target.label} x {traversal.pair.disease.label}")
    typer.echo(f"{project_id} [{traversal.project.status.value}]")
    typer.echo(traversal.project.objective)
    typer.echo(
        "Claims (inspect epistemic kind; membership does not establish evidence):"
    )
    for claim in traversal.claims:
        typer.echo(f"  {claim.identifier} [{claim.knowledge_kind.value}]")
        typer.echo(
            f"    {claim.subject.label} -> {claim.predicate} -> {claim.object.label}"
        )
        typer.echo(
            f"    Source: {claim.provenance.source_kind.value}: "
            f"{claim.provenance.source_identifier}"
        )
    for mechanism in traversal.mechanisms:
        typer.echo(
            f"Mechanism [{mechanism.classification.value}]: {mechanism.claim_id}"
        )
        typer.echo(f"  {mechanism.reasoning}")
    for perturbation in traversal.perturbations:
        typer.echo(
            f"Perturbation [{perturbation.status.value}; "
            f"{perturbation.knowledge_kind.value}]: {perturbation.perturbation_id}"
        )
        typer.echo(
            "  Observed effect claim: "
            f"{perturbation.observed_effect_claim_id or 'none'}"
        )
    typer.echo("Competing strategies (no winner selected):")
    for strategy in traversal.strategies:
        typer.echo(f"  {strategy.description} [{strategy.knowledge_kind.value}]")
    for question in traversal.questions:
        typer.echo(f"Open question [{question.status.value}]: {question.question}")
    for experiment in traversal.experiments:
        typer.echo(
            f"Proposed experiment [{experiment.knowledge_kind.value}; "
            f"{experiment.suggestion_origin.value}]: {experiment.title}"
        )
        typer.echo(f"  Rationale: {experiment.rationale}")
        for outcome in traversal.outcomes:
            if outcome.experiment_id == experiment.experiment_id:
                typer.echo(f"  Possible outcome: {outcome.possible_outcome}")
                typer.echo(f"    Interpretation: {outcome.interpretation}")
    typer.echo(
        "Use --json for complete context, provenance, links and transformations."
    )


@question_app.command("list")
def list_questions(context: typer.Context, project_id: str) -> None:
    _output(_run(context, lambda store: store.questions.list_for_project(project_id)))


@strategy_app.command("list")
def list_strategies(context: typer.Context, project_id: str) -> None:
    _output(_run(context, lambda store: store.strategies.list_for_project(project_id)))


@perturbation_app.command("list")
def list_perturbations(context: typer.Context, project_id: str) -> None:
    _output(
        _run(context, lambda store: store.perturbations.list_for_project(project_id))
    )
