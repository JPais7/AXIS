"""Explicit, bounded decision commands; builds never touch the network."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from axis.cli.target_identity import database
from axis.decision.service import DecisionService
from axis.storage import EvidenceStore

app = typer.Typer(help="Experimental decision engine and critical uncertainty.")
Project = Annotated[str, typer.Argument(help="Discovery project identifier.")]


def _protein(store: EvidenceStore, project: str) -> str:
    proteins = store.targets.project_ids(project)
    if len(proteins) != 1:
        raise typer.BadParameter("project must have exactly one imported protein")
    return proteins[0]


def _echo(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False, default=str))


@app.command("import-package")
def import_package(
    context: typer.Context,
    project: Annotated[str, typer.Option()],
    protein: Annotated[str, typer.Option()],
    directory: Annotated[Path | None, typer.Option()] = None,
) -> None:
    with EvidenceStore(database(context)) as store:
        typer.echo(
            str(DecisionService(store).import_package(project, protein, directory))
        )


@app.command("build")
def build(context: typer.Context, project: Project) -> None:
    """Derive and persist the next DecisionState (idempotent if unchanged)."""
    with EvidenceStore(database(context)) as store:
        state = DecisionService(store).build(project, _protein(store, project))
        typer.echo(
            f"DecisionState v{state['version']} {state['id']}\n"
            f"critical uncertainty: {state['critical_uncertainty_id']}\n"
            f"recommended experiment: {state['recommended_experiment_id']}"
        )


@app.command("show")
def show(context: typer.Context, project: Project) -> None:
    with EvidenceStore(database(context)) as store:
        state = DecisionService(store).current(project, _protein(store, project))
        typer.echo(
            f"{state['disclaimer']}\n\n"
            f"DecisionState v{state['version']} ({state['id']})"
        )
        typer.echo("Supported:")
        for item in state["position"]["supported"]:
            typer.echo(f"  - {item['statement']}")
        typer.echo("Unresolved:")
        for item in state["position"]["unresolved"]:
            typer.echo(f"  - {item['statement']}")
        typer.echo(f"Critical uncertainty: {state['critical_uncertainty_id']}")
        typer.echo(f"Recommended: {state['recommended_experiment_id']}")


@app.command("history")
def history(context: typer.Context, project: Project) -> None:
    with EvidenceStore(database(context)) as store:
        page = store.decisions.history(project, _protein(store, project))
        for state in page["items"]:
            typer.echo(
                f"v{state['version']} {state['id']} critical="
                f"{state['critical_uncertainty_id']} recommended="
                f"{state['recommended_experiment_id']}"
            )
            for change in (state["diff"] or {}).get("changes", []):
                typer.echo(f"    {change}")


@app.command("explain")
def explain(
    context: typer.Context,
    project: Project,
    question: Annotated[
        str,
        typer.Option(
            help="why_critical | evidence_against | why_not | "
            "what_would_change_our_mind"
        ),
    ] = "why_critical",
    experiment: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Answer only from the stored DecisionState; never creates facts."""
    with EvidenceStore(database(context)) as store:
        _echo(
            DecisionService(store).answer(
                project, _protein(store, project), question, experiment
            )
        )


@app.command("experiments")
def experiments(context: typer.Context, project: Project) -> None:
    with EvidenceStore(database(context)) as store:
        state = DecisionService(store).current(project, _protein(store, project))
        for item in state["candidates"]:
            typer.echo(
                f"{item['experiment_id']}  rank={item['rank']}  "
                f"{item['role_label']}  feasibility={item['feasibility']['level']}  "
                f"cost={item['cost']}\n    {item['reason']}"
            )


@app.command("constraints")
def constraints(
    context: typer.Context,
    project: Project,
    investigator: Annotated[str, typer.Option()],
    model: Annotated[list[str] | None, typer.Option()] = None,
    compound: Annotated[list[str] | None, typer.Option()] = None,
    assay: Annotated[list[str] | None, typer.Option()] = None,
    equipment: Annotated[list[str] | None, typer.Option()] = None,
    collaboration: Annotated[list[str] | None, typer.Option()] = None,
    exclude_experiment: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    """Record investigator-entered resources (a new immutable version)."""
    with EvidenceStore(database(context)) as store:
        typer.echo(
            str(
                DecisionService(store).set_constraints(
                    project,
                    investigator,
                    available_models=model or [],
                    available_compounds=compound or [],
                    available_assays=assay or [],
                    available_equipment=equipment or [],
                    external_collaborations=collaboration or [],
                    excluded_experiment_ids=exclude_experiment or [],
                )
            )
        )


@app.command("select-experiment")
def select_experiment(
    context: typer.Context,
    project: Project,
    experiment: Annotated[str, typer.Option()],
    status: Annotated[str, typer.Option()],
    investigator: Annotated[str, typer.Option()],
    note: Annotated[str, typer.Option()] = "",
    result_claim: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Explicit investigator status change; never automatic."""
    with EvidenceStore(database(context)) as store:
        typer.echo(
            str(
                DecisionService(store).set_experiment_status(
                    project, experiment, status, investigator, note, result_claim
                )
            )
        )


@app.command("promote-explanation")
def promote_explanation(
    context: typer.Context,
    project: Project,
    explanation: Annotated[str, typer.Option()],
    investigator: Annotated[str, typer.Option()],
    note: Annotated[str, typer.Option()] = "",
) -> None:
    with EvidenceStore(database(context)) as store:
        typer.echo(
            str(
                DecisionService(store).promote_explanation(
                    project, explanation, investigator, note
                )
            )
        )


@app.command("rebuild")
def rebuild(
    context: typer.Context,
    project: Project,
    mode: Annotated[str, typer.Option(help="exploratory | reviewed")] = "exploratory",
    trigger: Annotated[str, typer.Option()] = "explicit rebuild",
) -> None:
    """Create the next immutable DecisionState after results or reviews changed."""
    with EvidenceStore(database(context)) as store:
        state = DecisionService(store).rebuild(
            project, _protein(store, project), mode=mode, trigger=trigger
        )
        diff = state.get("diff") or {}
        typer.echo(
            f"DecisionState v{state['version']} {state['id']} "
            f"(mode: {state['review_mode']})"
        )
        typer.echo(
            "Did the decision change? "
            + (diff.get("decision_changed") or {"answer": "first state"})["answer"]
        )
        for line in diff.get("changes", []):
            typer.echo(f"  - {line}")


@app.command("diff")
def diff(
    context: typer.Context,
    project: Project,
    from_version: Annotated[int | None, typer.Option("--from")] = None,
    to_version: Annotated[int | None, typer.Option("--to")] = None,
) -> None:
    """Show the cause-attributed scientific diff between two stored states."""
    with EvidenceStore(database(context)) as store:
        protein = _protein(store, project)
        items = {
            s["version"]: s
            for s in store.decisions.history(project, protein, 100)["items"]
        }
        if not items:
            raise typer.BadParameter("no DecisionState exists")
        high = to_version or max(items)
        low = from_version or (high - 1)
        if low < 1 or high not in items or low not in items:
            raise typer.BadParameter("unknown version range")
        _echo(DecisionService.diff(items[low], items[high]))
