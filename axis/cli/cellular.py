"""Explicit import; never a side effect of viewing evidence."""

from pathlib import Path
from typing import Annotated

import typer

from axis.cellular.service import CellularPharmacologyService
from axis.cli.target_identity import database
from axis.storage import EvidenceStore

app = typer.Typer(help="Cellular evidence and translational gaps.")


@app.command("import-package")
def import_package(
    context: typer.Context,
    project: Annotated[str, typer.Option()],
    protein: Annotated[str, typer.Option()],
    directory: Annotated[Path | None, typer.Option()] = None,
) -> None:
    with EvidenceStore(database(context)) as store:
        result = CellularPharmacologyService(store).import_package(
            project, protein, directory
        )
        typer.echo(str(result))
