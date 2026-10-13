#!/usr/bin/env python3
"""Deterministic creative-review bundle rendering, publication, and verification."""
from __future__ import annotations

import os
import stat
from typing import Any

from _projection import _derive
from _render import _render_annotations_csv, _render_assets_csv, _render_markdown
from _validation import (
    AUTHORITY,
    MAX_JSON_BYTES,
    RECEIPT_SCHEMA,
    InvalidState,
    canonical_bytes,
    sha256_bytes,
    sha256_json,
    strict_json_loads,
)

def _open_dir_nofollow(path: os.PathLike[str] | str) -> tuple[int, tuple[int, int]]:
    if os.name != "posix" or not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
        raise InvalidState("safe directory traversal is unsupported on this host")
    full = os.path.abspath(os.fspath(path))
    drive, tail = os.path.splitdrive(full)
    if drive:
        raise InvalidState("safe directory traversal is unsupported for drive paths")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0))
    try:
        for part in (part for part in tail.split(os.sep) if part and part != "."):
            if part == "..":
                raise InvalidState("parent traversal is not allowed")
            next_fd = os.open(part, flags, dir_fd=fd)
            info = os.fstat(next_fd)
            if not stat.S_ISDIR(info.st_mode):
                os.close(next_fd)
                raise InvalidState("path component is not a directory")
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        return fd, (info.st_dev, info.st_ino)
    except Exception:
        os.close(fd)
        raise


def _read_fd_all(fd: int, cap: int) -> bytes:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size > cap:
        raise InvalidState("bundle member is not a bounded regular file")
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = info.st_size
    while remaining:
        chunk = os.read(fd, min(1_048_576, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) != info.st_size:
        raise InvalidState("bundle member changed while reading")
    return data


def _bundle_bytes(manifest: dict[str, Any]) -> dict[str, bytes]:
    manifest_bytes = canonical_bytes(manifest)
    assets_csv = _render_assets_csv(manifest)
    annotations_csv = _render_annotations_csv(manifest)
    markdown = _render_markdown(manifest)
    files = {
        "manifest.json": manifest_bytes,
        "review.md": markdown,
        "assets.csv": assets_csv,
        "annotations.csv": annotations_csv,
    }
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "campaign_id": manifest["campaign"]["campaign_id"],
        "campaign_revision": manifest["campaign"]["revision"],
        "campaign_state": manifest["derived"]["campaign_state"],
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "derived_sha256": sha256_json(manifest["derived"]),
        "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        "authority": dict(AUTHORITY),
    }
    files["receipt.json"] = canonical_bytes(receipt)
    return files


def publish_bundle(directory: os.PathLike[str] | str, files: dict[str, bytes]) -> dict[str, Any]:
    expected = set(files)
    if not expected or any("/" in name or name in {".", ".."} for name in expected):
        raise InvalidState("invalid bundle member name")
    dir_fd, identity = _open_dir_nofollow(directory)
    created: dict[str, tuple[int, int]] = {}
    try:
        if os.listdir(dir_fd):
            raise InvalidState("output directory must already exist and be empty")
        for name in sorted(files):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
            try:
                data = files[name]
                offset = 0
                while offset < len(data):
                    written = os.write(fd, data[offset:])
                    if written <= 0:
                        raise InvalidState("short write while publishing bundle")
                    offset += written
                os.fsync(fd)
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size != len(data):
                    raise InvalidState("created bundle member identity/size mismatch")
                created[name] = (info.st_dev, info.st_ino)
            finally:
                os.close(fd)
        os.fsync(dir_fd)
        if set(os.listdir(dir_fd)) != expected:
            raise InvalidState("output directory entry set changed during publication")
        for name, member_identity in created.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=dir_fd)
            try:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) != member_identity:
                    raise InvalidState("bundle member identity changed during publication")
                if sha256_bytes(_read_fd_all(fd, MAX_JSON_BYTES * 5)) != sha256_bytes(files[name]):
                    raise InvalidState("bundle member bytes changed during publication")
            finally:
                os.close(fd)
        reopened_fd, reopened_identity = _open_dir_nofollow(directory)
        os.close(reopened_fd)
        if reopened_identity != identity:
            raise InvalidState("output directory identity changed during publication")
        return {"published": True, "files": {name: sha256_bytes(data) for name, data in sorted(files.items())}}
    except Exception:
        for name, member_identity in created.items():
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
                try:
                    info = os.fstat(fd)
                    same = (info.st_dev, info.st_ino) == member_identity
                finally:
                    os.close(fd)
                if same:
                    os.unlink(name, dir_fd=dir_fd)
            except OSError:
                pass
        raise
    finally:
        os.close(dir_fd)


def read_bundle(directory: os.PathLike[str] | str) -> dict[str, bytes]:
    expected = {"manifest.json", "review.md", "assets.csv", "annotations.csv", "receipt.json"}
    dir_fd, identity = _open_dir_nofollow(directory)
    try:
        if set(os.listdir(dir_fd)) != expected:
            raise InvalidState("bundle must contain the exact expected file set")
        out: dict[str, bytes] = {}
        for name in sorted(expected):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=dir_fd)
            try:
                out[name] = _read_fd_all(fd, MAX_JSON_BYTES * 5)
            finally:
                os.close(fd)
        reopened_fd, reopened_identity = _open_dir_nofollow(directory)
        os.close(reopened_fd)
        if reopened_identity != identity:
            raise InvalidState("bundle directory identity changed while reading")
        return out
    finally:
        os.close(dir_fd)


def verify_bundle(directory: os.PathLike[str] | str) -> dict[str, Any]:
    files = read_bundle(directory)
    manifest = strict_json_loads(files["manifest.json"])
    if type(manifest) is not dict or set(manifest) != {"schema", "campaign", "events", "assets", "derived"}:
        raise InvalidState("manifest has unexpected keys")
    raw = {key: manifest[key] for key in ("schema", "campaign", "events", "assets")}
    recomputed = _derive(raw)
    if recomputed != manifest["derived"]:
        raise InvalidState("manifest derived state does not match semantic recomputation")
    expected_files = _bundle_bytes(manifest)
    if expected_files != files:
        raise InvalidState("bundle bytes do not match deterministic regeneration")
    receipt = strict_json_loads(files["receipt.json"])
    if receipt["authority"] != AUTHORITY or any(receipt["authority"].values()):
        raise InvalidState("receipt authority boundary is not fail-closed")
    return {
        "integrity_checked": True,
        "campaign_id": manifest["campaign"]["campaign_id"],
        "campaign_revision": manifest["campaign"]["revision"],
        "campaign_state": manifest["derived"]["campaign_state"],
        "manifest_sha256": sha256_bytes(files["manifest.json"]),
        "receipt_sha256": sha256_bytes(files["receipt.json"]),
    }
