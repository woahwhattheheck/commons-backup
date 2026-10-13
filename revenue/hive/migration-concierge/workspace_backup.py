# SPDX-License-Identifier: Apache-2.0
"""Portable, private recovery of a Migration Desk database and original assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

from intake import KINDS, MigrationError
from migrate import read_state, validate_state

FORMAT = "migration-recovery-v1"
DATABASE = "workspace.sqlite3"
MANIFEST = "MANIFEST.json"
MARKER = ".RESTORE_INCOMPLETE"
MAX_BYTES = 2 * 1024**3
MAX_MEMBERS = 100_002
MAX_MANIFEST = 4 * 1024**2
CHUNK = 1024**2
SHA = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED_COLUMNS = {
    "records": {"kind", "id", "namespace", "external_id", "data", "source", "revision"},
    "runs": {"operation", "plan_id", "status", "created_at", "plan", "report"},
    "changes": {"operation", "record_id", "before_state", "after_state"},
}


class RecoveryError(MigrationError):
    """Recovery could not complete; the source workspace remains unchanged."""


def _exists(path: Path) -> bool:
    return os.path.lexists(path)


def _readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise RecoveryError("Source database does not exist or is not a regular file")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)


def _json(raw: bytes | str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RecoveryError("Duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise RecoveryError("Nonfinite JSON value: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def _references(database: Path) -> tuple[dict[str, int], dict[str, int]]:
    """Include before/after images, not only currently visible attachments."""
    refs: dict[str, int] = {}

    def remember(record):
        if not isinstance(record, dict) or record.get("kind") not in KINDS:
            raise RecoveryError("Invalid record in database or change journal")
        if record["kind"] != "attachments":
            return
        data = record.get("data")
        if not isinstance(data, dict):
            raise RecoveryError("Attachment metadata must be an object")
        sha, size = data.get("sha256"), data.get("bytes")
        if not isinstance(sha, str) or not SHA.fullmatch(sha) or type(size) is not int or size < 0:
            raise RecoveryError("Invalid attachment content address or byte count")
        if sha in refs and refs[sha] != size:
            raise RecoveryError("Conflicting sizes for one attachment content address")
        refs[sha] = size

    db = _readonly(database)
    try:
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RecoveryError("Database integrity check failed")
        for table, required in REQUIRED_COLUMNS.items():
            columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            if not required <= columns:
                raise RecoveryError("Not a Migration Desk database: missing " + table + " columns")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RecoveryError("Database foreign-key check failed")
        counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in REQUIRED_COLUMNS}
        state = read_state(database)
        validate_state(state)
        for record in state.values():
            remember(record)
        for before, after in db.execute("SELECT before_state,after_state FROM changes"):
            if before is not None:
                remember(_json(before))
            remember(_json(after))
        counts["attachments"] = len(refs)
        return refs, counts
    finally:
        db.close()


def _copy(source, target, limit: int) -> dict:
    digest, count = hashlib.sha256(), 0
    while chunk := source.read(CHUNK):
        count += len(chunk)
        if count > limit:
            raise RecoveryError("Recovery byte limit exceeded")
        target.write(chunk)
        digest.update(chunk)
    return {"sha256": digest.hexdigest(), "bytes": count}


def _open_asset(path: Path):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if path.is_symlink():
        raise RecoveryError("Attachment must be an ordinary file")
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RecoveryError("Attachment must be an ordinary file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def backup_workspace(database: Path, assets: Path, archive: Path) -> dict:
    """Snapshot live SQLite (including committed WAL) and publish without overwrite."""
    database, assets, archive = Path(database), Path(assets), Path(archive)
    if _exists(archive):
        raise RecoveryError("Choose a new archive path; existing files are preserved")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".migration-backup-", dir=archive.parent) as folder:
        snapshot, packet = Path(folder) / DATABASE, Path(folder) / "recovery.zip"
        source = _readonly(database)
        try:
            target = sqlite3.connect(snapshot)
            try:
                deadline = time.monotonic() + 60

                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise RecoveryError("Snapshot exceeded 60 seconds; retry when writes settle")

                source.backup(target, pages=256, progress=progress, sleep=0.05)
            finally:
                target.close()
        finally:
            source.close()
        refs, counts = _references(snapshot)
        if len(refs) + 2 > MAX_MEMBERS:
            raise RecoveryError("Too many attachment versions for one recovery archive")
        files, used = {}, 0
        with zipfile.ZipFile(packet, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, path in [(DATABASE, snapshot)] + [("assets/" + sha, assets / sha) for sha in sorted(refs)]:
                with _open_asset(path) as raw, bundle.open(name, "w", force_zip64=True) as entry:
                    metadata = _copy(raw, entry, MAX_BYTES - used)
                if name != DATABASE and metadata != {"sha256": path.name, "bytes": refs[path.name]}:
                    raise RecoveryError("Attachment differs from the snapshot's content address: " + path.name)
                files[name] = metadata
                used += metadata["bytes"]
            manifest = {"format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                        "files": files, "counts": counts}
            raw = (json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
            if len(raw) > MAX_MANIFEST:
                raise RecoveryError("Manifest exceeds the recovery format's size limit")
            bundle.writestr(MANIFEST, raw)
        with packet.open("rb") as stream:
            os.fsync(stream.fileno())
        # Same-filesystem exclusive publication: a delayed contender cannot overwrite a winner.
        packet.chmod(0o600)
        os.link(packet, archive)
        return {"archive": str(archive), "format": FORMAT, "counts": counts, "bytes": used}


def _unpack_verified(archive: Path, staging: Path) -> dict:
    """Read each member once to controlled names; never use extract/extractall."""
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or len(names) > MAX_MEMBERS or names.count(MANIFEST) != 1:
            raise RecoveryError("Duplicate, excessive or missing archive members")
        info = bundle.getinfo(MANIFEST)
        if info.file_size > MAX_MANIFEST:
            raise RecoveryError("Manifest exceeds its size limit")
        with bundle.open(info) as stream:
            raw = stream.read(MAX_MANIFEST + 1)
        if len(raw) > MAX_MANIFEST:
            raise RecoveryError("Manifest exceeds its size limit")
        manifest = _json(raw)
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise RecoveryError("Unrecognized recovery format")
        files = manifest.get("files")
        if not isinstance(files, dict) or DATABASE not in files or set(names) != set(files) | {MANIFEST}:
            raise RecoveryError("Archive members do not match the manifest")
        used = 0
        for name, metadata in files.items():
            if name != DATABASE and not (name.startswith("assets/") and SHA.fullmatch(name[7:])):
                raise RecoveryError("Invalid recovery member name")
            if not isinstance(metadata, dict) or set(metadata) != {"sha256", "bytes"}:
                raise RecoveryError("Invalid recovery file metadata")
            sha, size = metadata["sha256"], metadata["bytes"]
            if not isinstance(sha, str) or not SHA.fullmatch(sha) or type(size) is not int or size < 0:
                raise RecoveryError("Invalid recovery digest or size")
            used += size
            if used > MAX_BYTES or bundle.getinfo(name).file_size != size:
                raise RecoveryError("Recovery size limit or member size mismatch")
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(name) as source, target.open("xb") as output:
                actual = _copy(source, output, size)
            if actual != metadata:
                raise RecoveryError("Recovery member hash mismatch: " + name)
        refs, counts = _references(staging / DATABASE)
        expected = {"assets/" + sha: {"sha256": sha, "bytes": size} for sha, size in refs.items()}
        if {k: v for k, v in files.items() if k != DATABASE} != expected:
            raise RecoveryError("Archive does not cover the database's complete attachment history")
        if (not isinstance(manifest.get("counts"), dict)
                or any(type(value) is not int for value in manifest["counts"].values())
                or manifest["counts"] != counts):
            raise RecoveryError("Database counts differ from the manifest")
        (staging / MANIFEST).write_bytes(raw)
        return manifest


def verify_archive(archive: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="migration-verify-") as folder:
        return _unpack_verified(Path(archive), Path(folder))


def restore_workspace(archive: Path, destination: Path) -> dict:
    """Verify first, then reserve a NEW directory. Never overwrite an existing path."""
    archive, destination = Path(archive), Path(destination)
    if _exists(destination):
        raise RecoveryError("Choose a new recovery directory; existing paths are preserved")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".migration-restore-", dir=destination.parent) as folder:
        staging = Path(folder)
        manifest = _unpack_verified(archive, staging)
        destination.mkdir(mode=0o700)  # Exclusive reservation; simultaneous restores have one winner.
        marker = destination / MARKER
        marker.write_text("INCOMPLETE: do not open this workspace. Restore to a new directory.\n", encoding="utf-8")
        (destination / "assets").mkdir()
        # A transfer failure intentionally leaves the incomplete marker, never deletes user data.
        for name in sorted(manifest["files"]) + [MANIFEST]:
            with (staging / name).open("rb") as source, (destination / name).open("xb") as target:
                shutil.copyfileobj(source, target, CHUNK)
                target.flush()
                os.fsync(target.fileno())
        marker.unlink()
        return {"destination": str(destination), "database": str(destination / DATABASE),
                "assets": str(destination / "assets"), "counts": manifest["counts"], "restored": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("backup")
    command.add_argument("--database", type=Path, required=True)
    command.add_argument("--assets", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    commands.add_parser("verify").add_argument("archive", type=Path)
    command = commands.add_parser("restore")
    command.add_argument("archive", type=Path)
    command.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = backup_workspace(args.database, args.assets, args.output)
        elif args.command == "verify":
            manifest = verify_archive(args.archive)
            result = {"verified": True, "format": manifest["format"], "counts": manifest["counts"]}
        else:
            result = restore_workspace(args.archive, args.destination)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (MigrationError, OSError, sqlite3.Error, zipfile.BadZipFile, zlib.error, RuntimeError,
            ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"error": str(exc), "completed": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
