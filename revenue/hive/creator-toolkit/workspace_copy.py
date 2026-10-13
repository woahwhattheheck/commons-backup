"""Consistent Creator Desk snapshots; restore only to a new destination file.

Uses SQLite's online backup API, not a live database file copy. No mail or
provider calls, no source mutations, and no overwrite of existing destinations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path

DEFAULT_MAX_BYTES = 64 * 1024 * 1024
REQUIRED = {
    "resources": {"id", "title", "description", "kind", "target", "filename", "data", "sha256", "sequence", "active", "revision", "created_at"},
    "members": {"id", "email", "name", "opted_in", "revision", "updated_at"},
    "consents": {"member_id", "opted_in", "wording", "source", "created_at"},
    "requests": {"id", "member_id", "resource_id", "created_at"},
    "outbox": {"id", "request_id", "member_id", "step", "subject", "body", "state", "due_at", "receipt", "updated_at"},
    "inquiries": {"id", "member_id", "body", "state", "created_at"},
    "operations": {"id", "fingerprint", "result"},
}


class CopyError(ValueError):
    """Copy failed without replacing the source or an existing destination."""


def _check(db):
    if db.execute("PRAGMA integrity_check(1)").fetchone()[0] != "ok":
        raise CopyError("Snapshot failed SQLite integrity check")
    for table, expected in REQUIRED.items():
        # Table names are fixed format definitions, not user-provided SQL.
        columns = {row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
        if not expected <= columns:
            raise CopyError(f"Not a Creator Desk workspace: incomplete {table} table")
    if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise CopyError("Snapshot has a broken record relationship")
    for kind, target, data, expected in db.execute("SELECT kind,target,data,sha256 FROM resources"):
        if kind == "file" and isinstance(data, bytes):
            actual = hashlib.sha256(data).hexdigest()
        elif kind == "link" and isinstance(target, str):
            actual = hashlib.sha256(target.encode("utf-8")).hexdigest()
        else:
            raise CopyError("Snapshot has an invalid resource")
        if actual != expected:
            raise CopyError("Snapshot resource bytes do not match their stored SHA-256")
    return {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in REQUIRED}


def _hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_workspace(source, destination, *, max_bytes=DEFAULT_MAX_BYTES,
                   timeout_seconds=30):
    """Back up or restore an existing workspace to a NEW database.

    The SQLite snapshot includes committed WAL data. Completed output is linked
    into place atomically; an existing destination, including a symlink, wins.
    Returned metadata contains counts/hashes, not member email addresses.
    """
    if type(max_bytes) is not int or max_bytes <= 0:
        raise CopyError("max_bytes must be a positive integer")
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 3600):
        raise CopyError("timeout_seconds must be greater than zero and at most 3600")
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if not source.is_file():
        raise CopyError("Source must be an existing workspace file")
    if os.path.lexists(destination):
        raise CopyError("Destination already exists; choose a new file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=".creator-copy-", suffix=".sqlite3", dir=destination.parent)
    os.close(handle)
    temporary = Path(name)
    deadline = time.monotonic() + timeout_seconds
    try:
        # mode=ro avoids creating or changing the source database.
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)) as original:
            page_size = original.execute("PRAGMA page_size").fetchone()[0]
            if original.execute("PRAGMA page_count").fetchone()[0] * page_size > max_bytes:
                raise CopyError("Workspace exceeds this snapshot size limit")

            def progress(_status, _remaining, total):
                if total * page_size > max_bytes:
                    raise CopyError("Workspace exceeds this snapshot size limit")
                if time.monotonic() > deadline:
                    raise CopyError("Snapshot timed out; source was left in place")

            with closing(sqlite3.connect(temporary)) as snapshot:
                original.backup(snapshot, pages=256, progress=progress, sleep=0.01)
                counts = _check(snapshot)
        size = temporary.stat().st_size
        if size > max_bytes:
            raise CopyError("Workspace exceeds this snapshot size limit")
        digest = _hash_file(temporary)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and never replaces an existing path.
        try:
            os.link(temporary, destination)
        except FileExistsError:
            raise CopyError("Destination already exists; choose a new file") from None
        return {"format": "creator-desk-sqlite-v1", "bytes": size,
                "sha256": digest, "counts": counts, "destination": str(destination)}
    except sqlite3.Error as exc:
        raise CopyError("Could not read a complete Creator Desk SQLite workspace") from exc
    finally:
        temporary.unlink(missing_ok=True)


def snapshot_bytes(source, *, max_bytes=DEFAULT_MAX_BYTES):
    """Create a checked, consistent download in an ephemeral directory."""
    with tempfile.TemporaryDirectory(prefix="creator-download-") as folder:
        path = Path(folder) / "creator-workspace.sqlite3"
        receipt = copy_workspace(source, path, max_bytes=max_bytes)
        data = path.read_bytes()
        if len(data) != receipt["bytes"] or hashlib.sha256(data).hexdigest() != receipt["sha256"]:
            raise CopyError("Snapshot changed before download")
        return data, {key: value for key, value in receipt.items() if key != "destination"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, help="New database path; never an existing workspace")
    parser.add_argument("--max-mib", type=int, default=64, help="Maximum snapshot size (default 64 MiB)")
    args = parser.parse_args()
    try:
        result = copy_workspace(args.source, args.destination, max_bytes=args.max_mib * 1024 * 1024)
    except (CopyError, OSError) as exc:
        parser.exit(1, f"Workspace not copied: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
