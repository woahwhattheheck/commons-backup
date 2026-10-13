"""Deterministic exports into a retained, pre-provisioned directory generation."""

import csv
import io
import json
import os
import stat
from pathlib import Path

from rights_model import *
from rights_store import connect, _queues_from_connection as _store_queues_from_connection


def _snapshot_from_connection(con):
    """Capture the complete export snapshot from one already-retained connection."""
    assets = [
        dict(row)
        for row in con.execute(
            "SELECT asset_id,sha256,parent_asset_id FROM assets ORDER BY asset_id"
        )
    ]
    grants = []
    for row in con.execute("SELECT * FROM grants ORDER BY grant_id"):
        grants.append(
            {
                "grant_id": row["grant_id"],
                "asset_id": row["asset_id"],
                "authority_ref": row["authority_ref"],
                "valid_from": row["valid_from"],
                "valid_until": row["valid_until"],
                "channels": json.loads(row["channels_json"]),
                "territories": json.loads(row["territories_json"]),
                "revoked_at": row["revoked_at"],
            }
        )
    placements = [
        dict(row)
        for row in con.execute(
            "SELECT request_id,intent_sha256,asset_id,channel,territory,"
            "starts_at,ends_at,grant_id,recorded_at "
            "FROM placements ORDER BY request_id"
        )
    ]
    audit = [
        dict(row)
        for row in con.execute(
            "SELECT seq,event_type,ref_id,at,payload_sha256 FROM audit ORDER BY seq"
        )
    ]
    row = con.execute(
        "SELECT value FROM meta WHERE key='manifest_sha256'"
    ).fetchone()
    body = {
        "schema": EXPORT_SCHEMA,
        "manifest_sha256": None if row is None else row[0],
        "assets": assets,
        "grants": grants,
        "placements": placements,
        "audit": audit,
    }
    body["snapshot_sha256"] = sha256_bytes(canonical_bytes(body))
    return body


def _queues_from_connection(con, as_of, horizon_days=30):
    """Use the store's parsed-instant queue semantics on this retained transaction."""
    return _store_queues_from_connection(con, as_of, horizon_days)


def export_files(path, as_of, horizon_days=30):
    # Acquire one connection and one SQLite transaction before either logical view.
    # The DB pathname is never reopened after acquisition, so a symlink retarget or
    # pathname substitution cannot splice a second SQLite object into the export.
    # BEGIN IMMEDIATE waits out any prior writer and blocks later writers until both
    # the snapshot and operational queues are captured from this retained object.
    guard = connect(path)
    try:
        guard.execute("BEGIN IMMEDIATE")
        snap = _snapshot_from_connection(guard)
        queues = _queues_from_connection(guard, as_of, horizon_days)
    finally:
        if guard.in_transaction:
            guard.execute("ROLLBACK")
        guard.close()

    output = {
        "snapshot.json": canonical_bytes(snap),
        "queues.json": canonical_bytes(queues),
    }
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    columns = (
        "request_id",
        "asset_id",
        "channel",
        "territory",
        "starts_at",
        "ends_at",
        "grant_id",
        "recorded_at",
    )
    writer.writerow(columns)
    for placement in snap["placements"]:
        writer.writerow([placement[key] for key in columns])
    output["placements.csv"] = text.getvalue().encode()
    lines = [
        "# Content Rights & Usage-Window Operations Desk",
        "",
        f"Snapshot SHA-256: `{snap['snapshot_sha256']}`",
        "",
        f"Assets: {len(snap['assets'])}",
        f"Grants: {len(snap['grants'])}",
        f"Placements: {len(snap['placements'])}",
        f"Renewal/expiry review rows: {len(queues['renewal_review'])}",
        f"Retraction review rows: {len(queues['retraction_review'])}",
        "",
        "Operational gate only: supplied authority facts are not a legal rights determination.",
        "",
    ]
    output["summary.md"] = "\n".join(lines).encode()
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "snapshot_sha256": snap["snapshot_sha256"],
        "files": [
            {"path": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
            for name, raw in sorted(output.items())
        ],
    }
    output["receipt.json"] = canonical_bytes(receipt)
    return output


def _same_identity(current, identity):
    return (current.st_dev, current.st_ino) == identity


# Capability is a platform/process property. Capture it before hostile tests (or
# other instrumentation) monkey-patch individual os functions; the publication
# path still invokes the current functions and therefore remains fully testable.
_SECURE_EXPORT_SUPPORTED = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
    and os.listdir in os.supports_fd
)


def _secure_export_supported():
    return _SECURE_EXPORT_SUPPORTED


def _entry_stat(name, dir_fd):
    return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)


def _absolute_components(path):
    absolute = os.path.abspath(os.fspath(path))
    drive, tail = os.path.splitdrive(absolute)
    require(
        not drive,
        "secure export publication does not support drive-qualified paths on this host",
    )
    parts = [part for part in tail.split(os.sep) if part and part != "."]
    require(parts, "output path must name a directory")
    require(all(part != ".." for part in parts), "output path traversal is not allowed")
    return absolute, parts


def _open_componentwise(path):
    # Walk from the filesystem root and retain every generation transition long
    # enough to prove that no path component is a symlink or replacement object.
    _, parts = _absolute_components(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(os.sep, flags)
    try:
        for part in parts:
            before = os.stat(part, dir_fd=fd, follow_symlinks=False)
            require(
                stat.S_ISDIR(before.st_mode),
                "output path component must be a real directory",
            )
            next_fd = os.open(part, flags, dir_fd=fd)
            current = os.fstat(next_fd)
            if not (
                stat.S_ISDIR(current.st_mode)
                and _same_identity(current, (before.st_dev, before.st_ino))
            ):
                os.close(next_fd)
                raise RightsError("output directory identity changed during publication")
            os.close(fd)
            fd = next_fd
        current = os.fstat(fd)
        return fd, (current.st_dev, current.st_ino)
    except Exception:
        os.close(fd)
        raise


def _open_retained_output(out_dir):
    # Keep the whole-path observation/open fence as an extra substitution check,
    # then independently walk every component with dir_fd + O_NOFOLLOW.
    try:
        before = os.stat(out_dir, follow_symlinks=False)
    except FileNotFoundError as error:
        raise RightsError(f"output directory must already exist: {out_dir}") from error
    require(
        stat.S_ISDIR(before.st_mode),
        "output must be a real directory, not a symlink or other file",
    )
    identity = (before.st_dev, before.st_ino)
    probe = None
    try:
        probe = os.open(out_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        current = os.fstat(probe)
        require(
            stat.S_ISDIR(current.st_mode) and _same_identity(current, identity),
            "output directory identity changed during publication",
        )
    finally:
        if probe is not None:
            os.close(probe)
    fd, walk_identity = _open_componentwise(out_dir)
    try:
        require(
            walk_identity == identity,
            "output directory identity changed during publication",
        )
        require(os.listdir(fd) == [], "output directory must be empty before publication")
        return fd, identity
    except Exception:
        os.close(fd)
        raise


def _rollback_created(dir_fd, created):
    # There is no portable atomic unlink-if-inode operation. Never perform the
    # unsafe stat(name)->unlink(name) sequence. Roll back only through retained
    # owned FDs; failed exports may leave zero-byte transaction tombstones.
    for _, _, fd in reversed(created):
        try:
            os.ftruncate(fd, 0)
            os.fsync(fd)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        os.fsync(dir_fd)
    except OSError:
        pass


def _close_created(created):
    for _, _, fd in created:
        try:
            os.close(fd)
        except OSError:
            pass


def publish_export(path, out_dir, as_of, horizon_days=30):
    out_dir = Path(out_dir)
    require(out_dir.name not in {"", ".", ".."}, "output path must name a directory")
    files = export_files(path, as_of, horizon_days)
    require(
        _secure_export_supported(),
        "secure export publication requires component-wise descriptor-relative no-follow filesystem support",
    )
    dir_fd, dir_identity = _open_retained_output(out_dir)
    created = []
    try:
        try:
            for name, raw in sorted(files.items()):
                require(
                    "/" not in name and "\\" not in name and name not in {"", ".", ".."},
                    "export leaf name invalid",
                )
                fd = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=dir_fd,
                )
                try:
                    file_stat = os.fstat(fd)
                    identity = (file_stat.st_dev, file_stat.st_ino)
                    created.append((name, identity, fd))
                except Exception:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    raise
                view = memoryview(raw)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short export write")
                    view = view[written:]
                os.fsync(fd)
            os.fsync(dir_fd)
            visible_fd, visible_identity = _open_componentwise(out_dir)
            try:
                require(
                    visible_identity == dir_identity,
                    "output directory identity changed during publication",
                )
            finally:
                os.close(visible_fd)
            expected = sorted(name for name, _, _ in created)
            require(
                sorted(os.listdir(dir_fd)) == expected,
                "output directory entries changed during publication",
            )
            for name, identity, _ in created:
                current = _entry_stat(name, dir_fd)
                require(
                    stat.S_ISREG(current.st_mode) and _same_identity(current, identity),
                    f"export leaf identity changed during publication: {name}",
                )
            _close_created(created)
            created.clear()
            return {
                "status": "EXPORTED",
                "output": str(out_dir),
                "files": len(files),
                "receipt_sha256": sha256_bytes(files["receipt.json"]),
            }
        except Exception:
            _rollback_created(dir_fd, created)
            created.clear()
            raise
    finally:
        _close_created(created)
        os.close(dir_fd)
