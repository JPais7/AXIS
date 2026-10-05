"""Chemical-learning commands (extend `axis chemistry`). Services hold the science."""

import json
from typing import Annotated, Any

import typer

from axis.cli.campaign import chemistry_app
from axis.cli.target_identity import database
from axis.learning.service import LearningError, LearningService
from axis.storage import EvidenceStore

dataset_app = typer.Typer(help="Frozen, context-correct learning datasets.")
sar_app = typer.Typer(help="Observed SAR and inferred SAR hypotheses (kept apart).")
model_app = typer.Typer(help="Eligibility, bounded models and their validation.")
prediction_app = typer.Typer(help="Frozen predictions (never measurements).")
chemistry_app.add_typer(dataset_app, name="dataset")
chemistry_app.add_typer(sar_app, name="sar")
chemistry_app.add_typer(model_app, name="model")
chemistry_app.add_typer(prediction_app, name="prediction")
Project = Annotated[str, typer.Option(help="Project identifier.")]


def _echo(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _guard(action: Any) -> Any:
    try:
        return action()
    except LearningError as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(2) from error


@dataset_app.command("build")
def dataset_build(
    context: typer.Context,
    project: Project = "",
    synthetic: Annotated[
        bool, typer.Option(help="Build the SYNTHETIC test fixture.")
    ] = False,
    cutoff: Annotated[
        str | None, typer.Option(help="Synthetic only: evidence cutoff date.")
    ] = None,
) -> None:
    """Freeze one dataset per assay context from existing measurements."""
    with EvidenceStore(database(context)) as store:
        service = LearningService(store)

        def run() -> list[str]:
            if synthetic:
                proj, records = service.synthetic_records(cutoff)
                return service.build_datasets(proj, records, synthetic=True)
            if not project:
                raise LearningError("--project is required for indexed evidence")
            return service.build_datasets(project, service.indexed_records(project))

        for dataset_id in _guard(run):
            typer.echo(dataset_id)


@dataset_app.command("list")
def dataset_list(context: typer.Context, project: Project) -> None:
    with EvidenceStore(database(context)) as store:
        for d in LearningService(store).datasets(project):
            tag = f"  [{d['label']}]" if d["label"] else ""
            typer.echo(
                f"{d['id']}  n={d['compounds']}  r{d['revision']}  {d['review_state']}{tag}"
            )


@dataset_app.command("show")
def dataset_show(context: typer.Context, dataset_id: str) -> None:
    with EvidenceStore(database(context)) as store:
        _echo(_guard(lambda: LearningService(store).dataset(dataset_id)))


@sar_app.command("show")
def sar_show(
    context: typer.Context,
    dataset_id: str,
    derive: Annotated[bool, typer.Option(help="Compute and store first.")] = False,
) -> None:
    with EvidenceStore(database(context)) as store:
        service = LearningService(store)
        if derive:
            _guard(lambda: service.derive_sar(dataset_id))
        _echo(_guard(lambda: service.observed_sar(dataset_id)))


@sar_app.command("pairs")
def sar_pairs(context: typer.Context, dataset_id: str) -> None:
    with EvidenceStore(database(context)) as store:
        data = _guard(lambda: LearningService(store).observed_sar(dataset_id))
    for p in data["observed"]["matched_pairs"]:
        typer.echo(p["statement"])


@model_app.command("eligibility")
def model_eligibility(context: typer.Context, dataset_id: str) -> None:
    """Assess whether a model may be built; refusal is a valid result."""
    with EvidenceStore(database(context)) as store:
        result = _guard(lambda: LearningService(store).assess_eligibility(dataset_id))
    typer.echo(f"{result['conclusion']}  ({result['readiness']})")
    for reason in result["reasons"]:
        typer.echo(f"- {reason}")


@model_app.command("train")
def model_train(
    context: typer.Context,
    dataset_id: str,
    algorithm: Annotated[str, typer.Option()] = "ridge",
    split: Annotated[str, typer.Option()] = "scaffold",
    seed: Annotated[int, typer.Option()] = 7,
) -> None:
    """Explicit training. Refuses (MODEL NOT BUILT) when the dataset is not eligible."""
    with EvidenceStore(database(context)) as store:
        result = _guard(
            lambda: LearningService(store).train(dataset_id, algorithm, split, seed)
        )
    if not result["model_built"]:
        typer.echo(f"{result['status']}: {result.get('statement', '')}")
        for reason in result.get("reasons", []):
            typer.echo(f"- {reason}")
        raise typer.Exit(3)
    typer.echo(result["model_id"])


@model_app.command("list")
def model_list(context: typer.Context, project: Project) -> None:
    with EvidenceStore(database(context)) as store:
        for r in store.learning.rows(
            "chemical_models", "WHERE project_id=?", [project]
        ):
            typer.echo(f"{r['id']}  {r['algorithm']}  {r['fingerprint'][:12]}")


@model_app.command("show")
def model_show(context: typer.Context, model_id: str) -> None:
    with EvidenceStore(database(context)) as store:
        value = _guard(lambda: LearningService(store).model(model_id))
    value = {k: v for k, v in value.items() if k != "model"}
    _echo(value)


@prediction_app.command("list")
def prediction_list(context: typer.Context, project: Project) -> None:
    with EvidenceStore(database(context)) as store:
        for r in store.learning.rows(
            "chemical_predictions", "WHERE project_id=?", [project]
        ):
            p = r["payload"]
            typer.echo(
                f"{r['id']}  {p['intent']}  {p['predicted_value']} {p['unit']}  {p['applicability']['status']}  PREDICTION — NOT A MEASUREMENT"
            )


@prediction_app.command("show")
def prediction_show(context: typer.Context, prediction_id: str) -> None:
    with EvidenceStore(database(context)) as store:
        _echo(_guard(lambda: LearningService(store).prediction(prediction_id)))


@chemistry_app.command("learning-state")
def learning_state(context: typer.Context, project: Project) -> None:
    """Snapshot of what has been learned (versioned; history is never rewritten)."""
    with EvidenceStore(database(context)) as store:
        _echo(LearningService(store).learning_state(project))


@chemistry_app.command("next-compounds")
def next_compounds(
    context: typer.Context,
    dataset_id: str,
    project: Project,
    model: Annotated[str | None, typer.Option()] = None,
    candidate: Annotated[
        list[str] | None, typer.Option(help="ref=SMILES (repeatable).")
    ] = None,
    record: Annotated[
        bool, typer.Option(help="Store the proposal in a new learning state.")
    ] = False,
) -> None:
    """Propose informative next compounds by explicit rules; no acquisition score exists."""
    pairs = {}
    for item in candidate or []:
        ref, _, smiles = item.partition("=")
        pairs[ref] = smiles
    with EvidenceStore(database(context)) as store:
        service = LearningService(store)
        result = _guard(lambda: service.next_compounds(dataset_id, model, pairs))
        if record:
            service.learning_state(project, result)
    typer.echo(result["statement"])
    for row in result["selected"]:
        typer.echo(f"{row['compound_ref']}: {', '.join(row['rationales'])}")
    for line in result["not_asserted"]:
        typer.echo(f"- {line}")
