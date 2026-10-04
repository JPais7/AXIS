"""Computational campaign commands. Services hold the science; this only calls them."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from axis.cli.target_identity import database
from axis.computational.service import CampaignError, CampaignService
from axis.storage import EvidenceStore

campaign_app = typer.Typer(help="Bounded computational chemical campaigns.")
chemistry_app = typer.Typer(help="Chemical hypotheses and chemical spaces.")
hypothesis_app = typer.Typer(help="Chemical hypotheses (never observations).")
space_app = typer.Typer(help="Frozen chemical spaces.")
compound_app = typer.Typer(help="Compound-level computational views.")
chemistry_app.add_typer(hypothesis_app, name="hypothesis")
chemistry_app.add_typer(space_app, name="space")
Campaign = Annotated[str, typer.Argument(help="Campaign identifier (e.g. ...@r1).")]


def _echo(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _guard(action: Any) -> Any:
    try:
        return action()
    except CampaignError as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(2) from error


def _service(
    context: typer.Context, store: EvidenceStore, root: Path | None = None
) -> CampaignService:
    return CampaignService(store, root)


@campaign_app.command("register")
def register(
    context: typer.Context,
    package: Annotated[str, typer.Argument(help="Frozen package, e.g. erap1.")],
) -> None:
    """Register a frozen campaign plan (planned state; nothing is computed)."""
    with EvidenceStore(database(context)) as store:
        typer.echo(_guard(lambda: _service(context, store).register(package)))


@campaign_app.command("list")
def list_campaigns(
    context: typer.Context,
    project: Annotated[str | None, typer.Option()] = None,
) -> None:
    with EvidenceStore(database(context)) as store:
        for c in _service(context, store).list_campaigns(project):
            tag = f"  [{c['label']}]" if c["label"] else ""
            typer.echo(f"{c['campaign_id']}  {c['status']}  {c['project_id']}{tag}")


@campaign_app.command("show")
def show(
    context: typer.Context,
    campaign_id: Campaign,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    with EvidenceStore(database(context)) as store:
        view = _guard(lambda: _service(context, store).view(campaign_id))
    if as_json:
        _echo(view)
        return
    c = view["campaign"]
    typer.echo(f"{c['campaign_id']}  status={c['status']}  {c['label']}")
    typer.echo(f"question: {c['question']}")
    if view["prioritization"]:
        typer.echo(f"outcome: {view['prioritization']['outcome']}")


@campaign_app.command("prepare")
def prepare(context: typer.Context, campaign_id: Campaign) -> None:
    """Prepare compounds explicitly (records what was and was not done)."""
    with EvidenceStore(database(context)) as store:
        _echo(_guard(lambda: _service(context, store).prepare(campaign_id)))


@campaign_app.command("run")
def run(context: typer.Context, campaign_id: Campaign) -> None:
    """Run the bounded methods and prioritize. Completion is not success."""
    with EvidenceStore(database(context)) as store:
        result = _guard(lambda: _service(context, store).run(campaign_id))
    _echo(result)
    if result["status"] == "failed":
        raise typer.Exit(3)


@campaign_app.command("candidates")
def candidates(context: typer.Context, campaign_id: Campaign) -> None:
    with EvidenceStore(database(context)) as store:
        view = _guard(lambda: _service(context, store).view(campaign_id))
    prio = view["prioritization"]
    if not prio:
        typer.echo("not run")
        return
    typer.echo(f"outcome: {prio['outcome']} (no aggregate score exists)")
    for e in prio["panel"]:
        typer.echo(
            f"{e['compound_ref']}  {e['role']}  cluster {e['cluster']}  "
            f"{e['review_state']}"
        )
        typer.echo(f"  {e['why_this_molecule']}")
    for s in prio["statements"]:
        typer.echo(f"- {s}")


@campaign_app.command("report")
def report(
    context: typer.Context,
    campaign_id: Campaign,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    with EvidenceStore(database(context)) as store:
        text = _guard(lambda: _service(context, store).report(campaign_id))
    if output:
        output.write_text(text)
        typer.echo(f"wrote {output}")
    else:
        typer.echo(text)


@campaign_app.command("review")
def review(
    context: typer.Context,
    campaign_id: Campaign,
    reviewer: Annotated[str, typer.Option()],
    decision: Annotated[str, typer.Option()],
    rationale: Annotated[str, typer.Option()],
    object_id: Annotated[str, typer.Option()] = "panel",
    conditions: Annotated[str | None, typer.Option()] = None,
) -> None:
    with EvidenceStore(database(context)) as store:
        typer.echo(
            _guard(
                lambda: _service(context, store).review(
                    campaign_id, object_id, reviewer, decision, rationale, conditions
                )
            )
        )


@hypothesis_app.command("list")
def hypothesis_list(context: typer.Context) -> None:
    with EvidenceStore(database(context)) as store:
        for row in store.computational.rows("chemical_hypotheses"):
            p = row["payload"]
            typer.echo(f"{row['id']}  {row['epistemic_status']}  {p['statement']}")


@hypothesis_app.command("show")
def hypothesis_show(context: typer.Context, hypothesis_id: str) -> None:
    with EvidenceStore(database(context)) as store:
        value = store.computational.get("chemical_hypotheses", hypothesis_id)
    if value is None:
        typer.echo("refused: unknown hypothesis", err=True)
        raise typer.Exit(2)
    _echo(value)


@space_app.command("list")
def space_list(context: typer.Context) -> None:
    with EvidenceStore(database(context)) as store:
        for row in store.computational.rows("chemical_spaces"):
            typer.echo(
                f"{row['id']}  {row['project_id']}  sha256 {row['checksum'][:16]}"
            )


@space_app.command("show")
def space_show(context: typer.Context, space_id: str) -> None:
    with EvidenceStore(database(context)) as store:
        space = store.computational.get("chemical_spaces", space_id)
        members = store.computational.rows(
            "chemical_space_members", "WHERE space_id=?", [space_id]
        )
    if space is None:
        typer.echo("refused: unknown chemical space", err=True)
        raise typer.Exit(2)
    _echo({**space, "members": [m["payload"] for m in members]})


@compound_app.command("computational")
def compound_computational(context: typer.Context, compound_ref: str) -> None:
    """Computational observations for one compound across campaigns (not evidence)."""
    with EvidenceStore(database(context)) as store:
        rows = store.computational.rows(
            "computational_observations", "WHERE compound_ref=?", [compound_ref]
        )
    typer.echo("computational observations; none is an experimental result")
    for r in rows:
        typer.echo(f"{r['campaign_id']}  {r['method']}  {r['epistemic_class']}")
