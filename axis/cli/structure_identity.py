"""Explicit frozen/live structural imports."""

from pathlib import Path
from typing import Annotated

import typer

from axis.cli.target_identity import database
from axis.storage import EvidenceStore
from axis.structures.service import StructureIdentityService

app = typer.Typer(help="Experimental structure identity, not therapeutic evidence.")


@app.command("import-package")
def import_package(
    context: typer.Context,
    project: Annotated[str, typer.Option()],
    protein: Annotated[str, typer.Option()],
    directory: Annotated[Path | None, typer.Option()] = None,
) -> None:
    with EvidenceStore(database(context)) as store:
        identifier = StructureIdentityService(store).import_package(
            project, protein, directory
        )
        typer.echo(f"FROZEN STRUCTURE IMPORT: {identifier}")


@app.command("import-pdb")
def import_pdb(
    context: typer.Context,
    pdb_id: str,
    project: Annotated[str, typer.Option()],
    protein: Annotated[str, typer.Option()],
) -> None:
    with EvidenceStore(database(context)) as store:
        identifier = StructureIdentityService(store).import_live(
            project, protein, pdb_id
        )
        typer.echo(f"LIVE STRUCTURE IMPORT: {identifier}")
