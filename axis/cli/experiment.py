"""Explicit commands for experimental results and scientific review.

Nothing here rebuilds a DecisionState: importing or reviewing changes stored facts;
`axis decision rebuild` is the separate, explicit step that creates a new state.
"""

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from axis.cli.target_identity import database
from axis.decision.service import DecisionService
from axis.experiments.results import ResultsService
from axis.storage import EvidenceStore

app = typer.Typer(help="Performed experiments, results and scientific review.")
result_app = typer.Typer(help="Experimental results.")
app.add_typer(result_app, name="result")
Project = Annotated[str, typer.Argument(help="Discovery project identifier.")]


def _echo(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _protein(store: EvidenceStore, project: str) -> str:
    proteins = store.targets.project_ids(project)
    if len(proteins) != 1:
        raise typer.BadParameter("project must have exactly one imported protein")
    return proteins[0]


@result_app.command("import-signatures")
def import_signatures(
    context: typer.Context,
    project: Project,
    directory: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Import frozen anticipated-outcome signatures (AI-suggested, review pending)."""
    with EvidenceStore(database(context)) as store:
        _echo(ResultsService(store).import_signatures(project, directory))


@result_app.command("validate")
def validate(
    context: typer.Context,
    project: Project,
    directory: Annotated[Path | None, typer.Option()] = None,
    allow_synthetic: Annotated[bool, typer.Option()] = False,
) -> None:
    """Check a result package without writing anything."""
    with EvidenceStore(database(context)) as store:
        _echo(
            ResultsService(store).validate_package(
                project, directory, allow_synthetic=allow_synthetic
            )
        )


@result_app.command("import")
def import_results(
    context: typer.Context,
    project: Project,
    directory: Annotated[Path | None, typer.Option()] = None,
    allow_synthetic: Annotated[bool, typer.Option()] = False,
) -> None:
    """Import results (idempotent). Does not change any DecisionState."""
    with EvidenceStore(database(context)) as store:
        _echo(
            ResultsService(store).import_package(
                project, directory, allow_synthetic=allow_synthetic
            )
        )


@result_app.command("show")
def show(context: typer.Context, project: Project, result: str) -> None:
    with EvidenceStore(database(context)) as store:
        _echo(ResultsService(store).result_detail(project, result))


@result_app.command("list")
def list_results(context: typer.Context, project: Project) -> None:
    with EvidenceStore(database(context)) as store:
        for x in ResultsService(store).ledger(project):
            typer.echo(
                f"{x['result_row']}  {x['edge']} / {x['scope_type']}:{x['scope_id']} "
                f"-> {x['state']}  eligibility={x['eligibility']['state']}  "
                f"match={x['scenario_match']}  review={x['interpretation_review']}"
                f"{'  [SYNTHETIC]' if x['synthetic'] else ''}"
            )


@result_app.command("review")
def review(
    context: typer.Context,
    project: Project,
    object_type: Annotated[
        str,
        typer.Option(
            help="experimental_result | result_interpretation | scenario_mapping "
            "| candidate_design | evidence_assessment"
        ),
    ],
    object_id: Annotated[str, typer.Option()],
    decision: Annotated[
        str,
        typer.Option(
            help="accepted | accepted_with_caveat | rejected | needs_revision | pending"
        ),
    ],
    reviewer: Annotated[str, typer.Option()],
    rationale: Annotated[str, typer.Option()],
    caveat: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Record an explicit reviewer decision (append-only; AI cannot review)."""
    with EvidenceStore(database(context)) as store:
        _echo(
            ResultsService(store).record_review(
                project, object_type, object_id, reviewer, decision, rationale, caveat
            )
        )


@result_app.command("packet")
def packet(context: typer.Context, project: Project, result: str) -> None:
    with EvidenceStore(database(context)) as store:
        _echo(ResultsService(store).review_packet(project, result))


@result_app.command("impact")
def impact(
    context: typer.Context,
    project: Project,
    interpretation: Annotated[str, typer.Option()],
    mode: Annotated[str, typer.Option()] = "exploratory",
) -> None:
    """Preview the decision impact if an interpretation were accepted (not applied)."""
    with EvidenceStore(database(context)) as store:
        _echo(
            DecisionService(store).impact_preview(
                project, _protein(store, project), interpretation, mode=mode
            )
        )


@result_app.command("withdraw")
def withdraw(
    context: typer.Context,
    project: Project,
    result: str,
    investigator: Annotated[str, typer.Option()],
    note: Annotated[str, typer.Option()] = "",
) -> None:
    with EvidenceStore(database(context)) as store:
        _echo(ResultsService(store).withdraw(project, result, investigator, note))


@result_app.command("verify-artifacts")
def verify_artifacts(
    context: typer.Context,
    project: Project,
    directory: Annotated[Path, typer.Option()],
) -> None:
    """Re-hash artifact files and report any mismatch."""
    with EvidenceStore(database(context)) as store:
        problems = ResultsService(store).verify_artifacts(project, directory)
        _echo({"ok": not problems, "problems": problems})
        if problems:
            raise typer.Exit(1)
