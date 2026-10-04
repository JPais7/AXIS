"""Retrospective validation commands: sealed cases, cutoff runs, reveal, review.

Nothing here touches the network or a language model; every run is deterministic
and replays from the frozen benchmark package.
"""

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from axis.cli.target_identity import database
from axis.storage import EvidenceStore
from axis.validation.service import BenchmarkError, BenchmarkService

app = typer.Typer(help="Retrospective scientific validation and temporal backtesting.")
Case = Annotated[str, typer.Argument(help="Benchmark case identifier.")]


def _echo(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _service(context: typer.Context, store: EvidenceStore) -> BenchmarkService:
    root = context.obj.get("benchmark_root") if isinstance(context.obj, dict) else None
    return BenchmarkService(store, root)


def _guard(action: Any) -> Any:
    try:
        return action()
    except BenchmarkError as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(2) from error


@app.command("list")
def list_cases(context: typer.Context) -> None:
    """Register (idempotently) and list sealed benchmark cases."""
    with EvidenceStore(database(context)) as store:
        service = _service(context, store)
        service.register()
        for case in service.list_cases():
            tag = f"  [{case['label']}]" if case["label"] else ""
            typer.echo(
                f"{case['case_id']}  {case['status']}  {case['benchmark_kind']}  "
                f"T={case['cutoff']}{tag}"
            )


@app.command("show")
def show(
    context: typer.Context,
    case_id: Case,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    with EvidenceStore(database(context)) as store:
        view = _guard(lambda: _service(context, store).show(case_id))
    if as_json:
        _echo(view)
        return
    typer.echo(f"{view['case_id']}  status={view['status']}  {view['label']}")
    protocol = view["protocol"]
    typer.echo(f"cutoff {protocol['cutoff']}: {protocol['cutoff_rationale']}")
    typer.echo(f"question: {protocol['question']}")
    typer.echo(f"protocol fingerprint: {protocol['protocol_fingerprint']}")
    if view["cutoff_run"]:
        state = view["cutoff_run"]["state"]
        typer.echo(f"critical uncertainty at T: {state['critical_uncertainty_id']}")
        typer.echo(f"recommended at T: {state['recommended_experiment_id']}")
    if view["assessment"]:
        typer.echo(f"conclusion: {view['assessment']['conclusion']['conclusion']}")


@app.command("snapshot")
def snapshot(context: typer.Context, case_id: Case) -> None:
    """Build and store the fingerprinted evidence snapshot at the cutoff."""
    with EvidenceStore(database(context)) as store:
        _echo(_guard(lambda: _service(context, store).snapshot(case_id)))


@app.command("run")
def run(
    context: typer.Context,
    case_id: Case,
    mode: Annotated[str | None, typer.Option(help="exploratory or reviewed.")] = None,
) -> None:
    """Decide at the cutoff from the sealed window only, then audit for leakage."""
    with EvidenceStore(database(context)) as store:
        result = _guard(lambda: _service(context, store).run(case_id, mode))
    state = result["state"]
    typer.echo(f"run {result['run_id']}")
    typer.echo(f"critical uncertainty: {state['critical_uncertainty_id']}")
    typer.echo(f"recommended experiment: {state['recommended_experiment_id']}")
    if not result["valid"]:
        typer.echo(result["label"], err=True)
        for finding in result["audit"]["findings"]:
            typer.echo(f"  {finding['category']}: {finding['detail']}", err=True)
        raise typer.Exit(3)
    typer.echo("leakage audit: valid")


@app.command("leakage-audit")
def leakage_audit(context: typer.Context, case_id: Case) -> None:
    with EvidenceStore(database(context)) as store:
        result = _guard(lambda: _service(context, store).leakage_audit(case_id))
    _echo(result)
    if not result["valid"]:
        raise typer.Exit(3)


@app.command("import-baseline")
def import_baseline(
    context: typer.Context,
    case_id: Case,
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Freeze externally produced baseline outputs; refused after the reveal."""
    document = json.loads(file.read_text())
    with EvidenceStore(database(context)) as store:
        labels = _guard(
            lambda: _service(context, store).import_baseline(case_id, document)
        )
    typer.echo(f"froze {len(labels)} baseline run(s): {', '.join(labels)}")


@app.command("reveal")
def reveal(context: typer.Context, case_id: Case) -> None:
    """Open the sealed future evidence and assess what the decision at T missed."""
    with EvidenceStore(database(context)) as store:
        result = _guard(lambda: _service(context, store).reveal(case_id))
    assessment = result["assessment"]
    typer.echo(f"conclusion: {assessment['conclusion']['conclusion']}")
    for source, item in assessment["relevance"].items():
        typer.echo(f"  {source}: {item['relevance']}")
    for dimension, value in assessment["matrix"].items():
        typer.echo(f"  {dimension}: {value['result']}")


@app.command("compare")
def compare(context: typer.Context, case_id: Case) -> None:
    """Show frozen baselines against the decision at T (after the reveal)."""
    with EvidenceStore(database(context)) as store:
        view = _guard(lambda: _service(context, store).show(case_id))
    if not view["assessment"]:
        typer.echo("refused: reveal the case first", err=True)
        raise typer.Exit(2)
    _echo(view["assessment"]["baseline_comparison"])


@app.command("blind-packet")
def blind_packet(context: typer.Context, case_id: Case) -> None:
    with EvidenceStore(database(context)) as store:
        _echo(_guard(lambda: _service(context, store).blind_packet(case_id)))


@app.command("review")
def review(
    context: typer.Context,
    case_id: Case,
    reviewer: Annotated[str, typer.Option(help="Human reviewer name.")],
    preference: Annotated[str, typer.Option(help="A, B, neither or cannot_judge.")],
    conclusion: Annotated[str, typer.Option(help="Your own conclusion label.")],
    rationale: Annotated[str, typer.Option()],
    note: Annotated[
        list[str] | None,
        typer.Option(help="dimension=agree|disagree|unsure:text (repeatable)."),
    ] = None,
) -> None:
    """Record a blind human review, separate from the system's assessment."""
    dimensions: dict[str, dict[str, str]] = {}
    for item in note or []:
        key, _, rest = item.partition("=")
        verdict, _, text = rest.partition(":")
        dimensions[key] = {"verdict": verdict, "note": text}
    with EvidenceStore(database(context)) as store:
        saved = _guard(
            lambda: _service(context, store).review(
                case_id,
                reviewer,
                dimensions=dimensions,
                preference=preference,
                conclusion_opinion=conclusion,
                rationale=rationale,
            )
        )
    typer.echo(f"recorded {saved['id']}")


@app.command("unblind")
def unblind(context: typer.Context, case_id: Case) -> None:
    with EvidenceStore(database(context)) as store:
        _echo(_guard(lambda: _service(context, store).unblind(case_id)))


@app.command("report")
def report(
    context: typer.Context,
    set_id: Annotated[str | None, typer.Option("--set")] = None,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Benchmark report with failure analysis, written to stdout or a file."""
    with EvidenceStore(database(context)) as store:
        service = _service(context, store)
        service.register()
        text = service.report(set_id)
    if output:
        output.write_text(text)
        typer.echo(f"wrote {output}")
    else:
        typer.echo(text)
