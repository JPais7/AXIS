"""Explicit live versus frozen protein identity commands."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from axis.domain.protein import sequence_checksum
from axis.storage import EvidenceStore
from axis.targets.identity import TargetIdentityService

app = typer.Typer(help="Protein identity infrastructure, not disease evidence.")


def database(context: typer.Context) -> Path:
    value = getattr(context.find_root().obj, "database", None)
    if not isinstance(value, Path):
        raise RuntimeError("missing database settings")
    return value


@app.command("import-package")
def import_package(
    context: typer.Context,
    project: Annotated[str, typer.Option()],
    directory: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """FROZEN PACKAGE IMPORT: default is the pinned human ERAP1 package."""
    with EvidenceStore(database(context)) as store:
        identifier = TargetIdentityService(store).import_package(project, directory)
        typer.echo(f"FROZEN PACKAGE IMPORT: {identifier}")


@app.command("import-uniprot")
def import_uniprot(
    context: typer.Context,
    accession: str,
    project: Annotated[str, typer.Option()],
    taxon: Annotated[int, typer.Option(min=1)],
) -> None:
    """LIVE SOURCE IMPORT: explicit network request, no automatic refresh."""
    with EvidenceStore(database(context)) as store:
        identifier = TargetIdentityService(store).import_live(
            project, accession, expected_taxon=taxon
        )
        typer.echo(f"LIVE SOURCE IMPORT: {identifier}")


@app.command("show")
def show(context: typer.Context, accession: str) -> None:
    with EvidenceStore(database(context)) as store:
        values = store.targets.by_accession("uniprot", accession)
        typer.echo(
            json.dumps([asdict(value) for value in values], default=str, indent=2)
        )


@app.command("verify")
def verify(context: typer.Context, accession: str) -> None:
    with EvidenceStore(database(context)) as store:
        values = store.targets.by_accession("uniprot", accession)
        if not values:
            raise typer.BadParameter("accession not imported")
        for value in values:
            if sequence_checksum(value.sequence) != value.sequence_checksum:
                raise ValueError("stored sequence checksum mismatch")
            for isoform in store.targets.isoforms(value.id):
                if (
                    isoform.sequence
                    and sequence_checksum(isoform.sequence) != isoform.sequence_checksum
                ):
                    raise ValueError("stored isoform checksum mismatch")
        typer.echo(f"Verified stored sequence integrity for {len(values)} snapshot(s).")
