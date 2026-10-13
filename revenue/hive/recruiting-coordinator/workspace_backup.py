#!/usr/bin/env python3
"""Portable, no-overwrite SQLite backup/recovery for Recruiting Coordinator.

Uses the SQLite online backup API, not a copy of the live database file.
Archives contain personal workspace data: keep them in private storage.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import zipfile

FORMAT = "hive-recruiting-backup/v1"
DATABASE = "workspace.sqlite3"
MANIFEST = "manifest.json"
DEFAULT_MAX_BYTES = 256 * 1024 * 1024
MANIFEST_LIMIT = 64 * 1024
CHUNK = 1024 * 1024


class BackupError(ValueError):
    """A backup operation could not complete; existing outputs are retained."""


def _limits(max_bytes: int, timeout: float = 30.0) -> None:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 512:
        raise BackupError("max_bytes must be an integer of at least 512")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise BackupError("timeout must be finite and positive")


def _read_connection(path: Path) -> sqlite3.Connection:
    # mode=ro refuses missing files. Do not use immutable=1 on a live WAL database.
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _database_info(path: Path) -> dict:
    try:
        with closing(_read_connection(path)) as connection:
            if [row[0] for row in connection.execute("PRAGMA quick_check")] != ["ok"]:
                raise BackupError("SQLite quick_check did not pass")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise BackupError("SQLite foreign-key consistency check did not pass")
            schema = list(connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"))
            counts = {}
            for kind, name, _, _ in schema:
                if kind == "table" and not name.startswith("sqlite_"):
                    quoted = '"' + name.replace('"', '""') + '"'
                    counts[name] = connection.execute("SELECT count(*) FROM " + quoted).fetchone()[0]
            return {"user_version": connection.execute("PRAGMA user_version").fetchone()[0],
                    "application_id": connection.execute("PRAGMA application_id").fetchone()[0],
                    "schema_sha256": hashlib.sha256(_json(schema)).hexdigest(),
                    "table_rows": counts}
    except sqlite3.Error as exc:
        raise BackupError("Invalid or unsupported SQLite workspace: " + str(exc)) from exc


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def _unique_pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("Duplicate manifest key")
        result[key] = value
    return result


def _new_destination(path: Path, *, database: bool = False) -> None:
    if path.exists() or path.is_symlink():
        raise BackupError("Destination already exists; choose a new path")
    if not path.parent.is_dir():
        raise BackupError("Destination parent directory does not exist")
    if database and any(Path(str(path) + suffix).exists() or
                        Path(str(path) + suffix).is_symlink()
                        for suffix in ("-wal", "-shm", "-journal")):
        raise BackupError("Destination has SQLite sidecar files; choose a new path")


def _publish(source: Path, destination: Path, *, database: bool = False) -> None:
    # Both paths are in the same filesystem. Hard-link publication is atomic and
    # fails rather than overwriting even when two processes race for one name.
    _new_destination(destination, database=database)
    with source.open("rb") as stream:
        os.fsync(stream.fileno())
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise BackupError("Destination was created concurrently; it was not overwritten") from exc
    if os.name == "posix":
        fd = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def create_backup(database: str | Path, archive: str | Path, *,
                  max_bytes: int = DEFAULT_MAX_BYTES, timeout: float = 30.0) -> dict:
    """Snapshot a live database and atomically create a new private ZIP file.

    The snapshot is consistent, not promised to be the state at function entry
    or to include writes committed after snapshot completion.
    """
    _limits(max_bytes, timeout)
    source, destination = Path(database).absolute(), Path(archive).absolute()
    if not source.is_file():
        raise BackupError("Source database does not exist or is not a regular file")
    _new_destination(destination)
    started = datetime.now(timezone.utc).isoformat()
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryDirectory(prefix=".recruiting-backup-", dir=destination.parent) as directory:
        work = Path(directory)
        snapshot = work / DATABASE
        snapshot.touch(mode=0o600)
        try:
            with closing(_read_connection(source)) as src, closing(sqlite3.connect(snapshot)) as dst:
                page_size = src.execute("PRAGMA page_size").fetchone()[0]

                def progress(status: int, remaining: int, total: int) -> None:
                    if total * page_size > max_bytes:
                        raise BackupError("Database exceeds max_bytes")
                    if time.monotonic() > deadline:
                        raise BackupError("Online snapshot exceeded timeout; no archive created")

                src.backup(dst, pages=128, progress=progress, sleep=0.02)
                # Only the private copy is changed. A restored copy needs no WAL.
                dst.execute("PRAGMA journal_mode=DELETE")
        except sqlite3.Error as exc:
            raise BackupError("SQLite snapshot failed: " + str(exc)) from exc
        if snapshot.stat().st_size > max_bytes:
            raise BackupError("Database exceeds max_bytes")
        manifest = {"format": FORMAT, "started_at": started,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "database": {"member": DATABASE, "bytes": snapshot.stat().st_size,
                                 "sha256": _digest(snapshot), **_database_info(snapshot)},
                    "privacy": "Contains workspace records; not encrypted. Keep private.",
                    "consistency": "SQLite online snapshot; writes after completion are not included."}
        manifest_bytes = _json(manifest)
        if len(manifest_bytes) > MANIFEST_LIMIT:
            raise BackupError("Workspace metadata exceeds manifest size limit")
        staged = work / "backup.zip"
        staged.touch(mode=0o600)
        with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as output:
            output.write(snapshot, DATABASE)
            output.writestr(MANIFEST, manifest_bytes)
        _publish(staged, destination)
    return {"archive": str(destination), "archive_sha256": _digest(destination),
            "manifest": manifest}


def _unpack_verified(archive: Path, snapshot: Path, max_bytes: int) -> dict:
    """Read only our two members, never extract arbitrary paths from an archive."""
    if not archive.is_file() or archive.stat().st_size > max_bytes + CHUNK:
        raise BackupError("Archive missing or above size limit")
    try:
        with zipfile.ZipFile(archive) as source:
            names = source.namelist()
            if len(names) != 2 or set(names) != {DATABASE, MANIFEST}:
                raise BackupError("Expected exactly one database and one manifest member")
            info = source.getinfo(MANIFEST)
            if info.file_size > MANIFEST_LIMIT:
                raise BackupError("Manifest exceeds size limit")
            manifest = json.loads(source.read(MANIFEST), object_pairs_hook=_unique_pairs,
                                  parse_constant=lambda _: (_ for _ in ()).throw(BackupError("Nonfinite manifest")))
            if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
                raise BackupError("Unsupported backup format")
            database = manifest.get("database")
            if not isinstance(database, dict) or database.get("member") != DATABASE:
                raise BackupError("Invalid database manifest")
            size, digest = database.get("bytes"), database.get("sha256")
            if type(size) is not int or not 512 <= size <= max_bytes:
                raise BackupError("Invalid or oversized database length")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise BackupError("Invalid database digest")
            member = source.getinfo(DATABASE)
            if member.file_size != size:
                raise BackupError("Database size differs from manifest")
            hasher = hashlib.sha256()
            count = 0
            with source.open(DATABASE) as content, snapshot.open("xb") as target:
                os.chmod(snapshot, 0o600)
                while block := content.read(CHUNK):
                    count += len(block)
                    if count > size:
                        raise BackupError("Database expanded beyond declared length")
                    hasher.update(block)
                    target.write(block)
            if count != size or hasher.hexdigest() != digest:
                raise BackupError("Database digest differs from manifest")
        observed = _database_info(snapshot)
        if any(database.get(key) != value for key, value in observed.items()):
            raise BackupError("Database schema or row counts differ from manifest")
        return manifest
    except (zipfile.BadZipFile, RuntimeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupError("Invalid backup archive: " + str(exc)) from exc


def verify_backup(archive: str | Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """Check archive/SQLite integrity without returning any candidate records."""
    _limits(max_bytes)
    with tempfile.TemporaryDirectory(prefix="recruiting-verify-") as directory:
        return _unpack_verified(Path(archive), Path(directory) / DATABASE, max_bytes)


def restore_backup(archive: str | Path, database: str | Path, *,
                   max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """Validate and restore to a new path. Never overwrites an existing workspace."""
    _limits(max_bytes)
    destination = Path(database).absolute()
    _new_destination(destination, database=True)
    with tempfile.TemporaryDirectory(prefix=".recruiting-restore-", dir=destination.parent) as directory:
        snapshot = Path(directory) / DATABASE
        manifest = _unpack_verified(Path(archive), snapshot, max_bytes)
        _publish(snapshot, destination, database=True)
    return {"database": str(destination), "sha256": manifest["database"]["sha256"],
            "restored": True, "manifest": manifest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup", help="Create a private online SQLite snapshot")
    backup.add_argument("database"); backup.add_argument("archive")
    backup.add_argument("--timeout", type=float, default=30.0)
    verify = sub.add_parser("verify", help="Verify archive and database integrity")
    verify.add_argument("archive")
    restore = sub.add_parser("restore", help="Restore to a NEW database path")
    restore.add_argument("archive"); restore.add_argument("database")
    for command in (backup, verify, restore):
        command.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = create_backup(args.database, args.archive, max_bytes=args.max_bytes, timeout=args.timeout)
        elif args.command == "verify":
            result = verify_backup(args.archive, max_bytes=args.max_bytes)
        else:
            result = restore_backup(args.archive, args.database, max_bytes=args.max_bytes)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BackupError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
