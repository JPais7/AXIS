"""Explicit offline package import; reads never retrieve remote chemistry."""

from pathlib import Path
from typing import Annotated

import typer

from axis.cli.target_identity import database
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore

app = typer.Typer(help="Chemical identity and assay-contextual measurements.")


@app.command("import-package")
def import_package(
    context: typer.Context,
    project: Annotated[str, typer.Option()],
    protein: Annotated[str, typer.Option()],
    directory: Annotated[Path | None, typer.Option()] = None,
) -> None:
    with EvidenceStore(database(context)) as store:
        identifiers = PharmacologyService(store).import_package(
            project, protein, directory
        )
        typer.echo(f"FROZEN PHARMACOLOGY IMPORT: {len(identifiers)} compounds")
