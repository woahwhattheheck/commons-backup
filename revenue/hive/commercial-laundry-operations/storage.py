"""SQLite-aware offline copies for laundry backup and restore.

A copy is published under a new filename only after SQLite and native event
checks pass. Nothing here initializes, checkpoints, or overwrites the source.
Use an operator-owned directory; paths are not a hostile-process boundary.
"""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
from typing import Any

from laundry_desk import LaundryDesk, LaundryDeskError, ValidationError

_REQUIRED_TABLES = frozenset({
    "meta", "customers", "sites", "agreements", "service_plans", "routes",
    "stops", "linen_counts", "container_custody", "exceptions", "invoices",
    "operations", "events",
})
_SIDECARS = ("-wal", "-shm", "-journal")


def _unused_destination(path: Path) -> None:
    for candidate in (path, *(Path(str(path) + suffix) for suffix in _SIDECARS)):
        if os.path.lexists(candidate):
            raise FileExistsError(f"destination or SQLite sidecar already exists: {candidate}")


def copy_database(source: str | Path, destination: str | Path) -> dict[str, Any]:
    """Copy committed state, including WAL frames, without replacing any file.

    Backup and restore intentionally share this implementation. Restoring is a
    verified copy to a new working database, never an in-place repair.
    """
    source = Path(source)
    destination = Path(destination)
    if not stat.S_ISREG(source.lstat().st_mode):
        raise ValidationError("source database must be a regular file, not a symlink")
    if not destination.parent.is_dir():
        raise ValidationError("destination parent directory must already exist")
    _unused_destination(destination)
    desk = LaundryDesk.open_read_only(source)

    # Stage on the destination filesystem so the final hard link is atomic and
    # create-exclusive. Private staging also contains any temporary journals.
    with tempfile.TemporaryDirectory(
        prefix=".laundry-copy-", dir=destination.parent, ignore_cleanup_errors=True
    ) as directory:
        staged = Path(directory) / "snapshot.sqlite3"
        descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        deadline = time.monotonic() + 60.0

        def progress(status: int, remaining: int, total: int) -> None:
            if time.monotonic() > deadline:
                raise TimeoutError("SQLite copy exceeded 60 seconds; source is unchanged")

        with closing(desk._connect()) as reader, closing(
            sqlite3.connect(str(staged), timeout=8.0, isolation_level=None)
        ) as writer:
            reader.backup(writer, pages=256, progress=progress, sleep=0.05)
            # Make the result a standalone database, not a main-file-only copy
            # that depends on an unshipped WAL or rollback journal.
            mode = writer.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            if mode != "delete":
                raise LaundryDeskError("copied database could not become standalone")
            tables = {row[0] for row in writer.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not _REQUIRED_TABLES <= tables:
                raise LaundryDeskError("copied database is missing laundry schema tables")
            if writer.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise LaundryDeskError("copied database failed SQLite integrity check")
            if writer.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise LaundryDeskError("copied database contains broken references")

        integrity = LaundryDesk.open_read_only(staged).verify_integrity()
        with staged.open("rb") as handle:
            os.fsync(handle.fileno())
        size = staged.stat().st_size
        # Check again after copying, while the final os.link still provides the
        # no-overwrite guarantee if another process creates the target itself.
        _unused_destination(destination)
        os.link(staged, destination)
        if os.name == "posix":
            try:
                descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except OSError as exc:
                raise LaundryDeskError(
                    f"copy exists at {destination}, but directory durability could not "
                    "be confirmed; preserve and inspect it before retrying"
                ) from exc
        return {
            "source": str(source), "destination": str(destination), "bytes": size,
            "schema_version": integrity["schema_version"],
            "operations": integrity["operations"], "events": integrity["events"],
            "integrity": integrity["integrity"],
        }
