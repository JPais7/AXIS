"""Local read-first workspace command."""

from pathlib import Path
from typing import Annotated

import typer

from axis.api.server import WorkspaceServer
from axis.discovery.curation import import_curated_erap1
from axis.storage import EvidenceStore
from axis.storage.ownership import StoreOwnershipError


def serve(
    context: typer.Context,
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8765,
    import_curated: Annotated[
        bool, typer.Option(help="Explicit frozen ERAP1 import before serving.")
    ] = False,
) -> None:
    """Serve a read-only workspace on 127.0.0.1, exclusively owning its store."""
    database = getattr(context.find_root().obj, "database", None)
    if not isinstance(database, Path):
        raise RuntimeError("AXIS database settings are missing")
    try:
        if import_curated:
            with EvidenceStore(database) as store:
                import_curated_erap1(store)
        with (
            EvidenceStore(database, read_only=True) as store,
            WorkspaceServer(store, port) as server,
        ):
            typer.echo(f"AXIS read-first workspace: http://127.0.0.1:{port}")
            typer.echo(
                "Exclusive store owner; stop this server before using the CLI "
                "on this database."
            )
            server.serve_forever()
    except KeyboardInterrupt:
        typer.echo("Workspace stopped; store ownership released.")
    except (StoreOwnershipError, OSError, ValueError) as error:
        typer.echo(f"Workspace error: {error}", err=True)
        raise typer.Exit(code=1) from error
