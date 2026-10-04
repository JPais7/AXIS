"""Cooperative one-process ownership for local AXIS database sessions."""

import os
import sys
from pathlib import Path
from typing import BinaryIO


class StoreOwnershipError(RuntimeError):
    """Another AXIS CLI/server session currently owns this database."""


class StoreOwnership:
    def __init__(self, database: Path) -> None:
        self.path = Path(str(database.resolve()) + ".axis-lock")
        self._file: BinaryIO | None = None

    def acquire(self) -> None:
        stream = self.path.open("a+b")
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            raise StoreOwnershipError(
                "This database is owned by another AXIS session. Stop that server "
                "or CLI session before opening it here. The lock file is not a "
                "stale-lock marker and must not be deleted."
            ) from error
        self._file = stream

    def release(self) -> None:
        if self._file is not None:
            stream = self._file
            stream.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()
            self._file = None
