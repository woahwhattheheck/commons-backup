#!/usr/bin/env python3
"""Deterministic SHA-256 keyed artifact-custody registry.

This module records *where an already-hashed artifact was observed*.  It does
not claim that a remote GitHub/Slack/Actions object has been re-downloaded and
rehashed.  Producers must supply the artifact SHA-256 they actually measured;
the registry binds that digest to durable coordinates without relabelling one
coordinate as another.

The on-disk format is intentionally small and standard-library-only so every
Commons seat can validate it offline.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import hashlib
import json
import math
import os
import re
import tempfile
import time
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

SCHEMA = "commons-artifact-registry/v1"
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")

SOURCE_KINDS = {
    "git_blob",
    "git_commit",
    "path",
    "slack_file",
    "workflow_artifact",
}

JOB_CONCLUSIONS = {
    "success",
    "failure",
    "cancelled",
    "skipped",
    "timed_out",
    "action_required",
    "neutral",
    "stale",
    "startup_failure",
}

_ALLOWED_FIELDS = {
    "git_blob": {"kind", "repo", "blob_sha", "url"},
    "git_commit": {"kind", "repo", "commit_sha", "url"},
    "path": {"kind", "repo", "commit_sha", "path", "url"},
    "slack_file": {"kind", "workspace", "channel_id", "file_id", "permalink"},
    "workflow_artifact": {
        "kind", "repo", "run_id", "job_id", "artifact_id", "name",
        "job_conclusion", "url",
    },
}

_REQUIRED_FIELDS = {
    "git_blob": {"kind", "repo", "blob_sha"},
    "git_commit": {"kind", "repo", "commit_sha"},
    "path": {"kind", "repo", "commit_sha", "path"},
    "slack_file": {"kind", "channel_id", "file_id"},
    "workflow_artifact": {
        "kind", "repo", "run_id", "job_id", "artifact_id", "name",
        "job_conclusion",
    },
}


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key: %s" % key)
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError("non-finite JSON value: %s" % value)))


def normalize_sha256(value: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError("sha256 must be exactly 64 hexadecimal characters")
    return value.lower()


def _git_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise ValueError("%s must be exactly 40 hexadecimal characters" % field)
    return value.lower()


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % field)
    return value.strip()


def _positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0:  # bool is intentionally rejected.
        raise ValueError("%s must be a positive integer" % field)
    return value


def _size(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("size_bytes must be a non-negative integer")
    return value


def _repo(value: Any) -> str:
    value = _nonempty_string(value, "repo")
    if not _REPO_RE.fullmatch(value):
        raise ValueError("repo must be owner/name")
    return value


def normalize_source(source: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(source, Mapping):
        raise ValueError("source must be a JSON object")
    kind = source.get("kind")
    if kind not in SOURCE_KINDS:
        raise ValueError("unsupported source kind: %r" % (kind,))
    extra = set(source) - _ALLOWED_FIELDS[kind]
    missing = _REQUIRED_FIELDS[kind] - set(source)
    if missing:
        raise ValueError("missing source fields: %s" % ", ".join(sorted(missing)))
    if extra:
        raise ValueError("unexpected source fields: %s" % ", ".join(sorted(extra)))

    out = dict(source)
    out["kind"] = kind
    if "repo" in out:
        out["repo"] = _repo(out["repo"])
    if "blob_sha" in out:
        out["blob_sha"] = _git_sha(out["blob_sha"], "blob_sha")
    if "commit_sha" in out:
        out["commit_sha"] = _git_sha(out["commit_sha"], "commit_sha")
    for field in ("run_id", "job_id", "artifact_id"):
        if field in out:
            out[field] = _positive_int(out[field], field)
    if "path" in out:
        # Git filenames are literal coordinates: trimming whitespace would
        # relabel a distinct committed file (including whitespace-only names).
        if not isinstance(out["path"], str) or not out["path"]:
            raise ValueError("path must be a non-empty string")
    for field in ("channel_id", "file_id", "name"):
        if field in out:
            out[field] = _nonempty_string(out[field], field)
    for field in ("workspace", "permalink", "url"):
        if field in out:
            out[field] = _nonempty_string(out[field], field)
    if kind == "workflow_artifact":
        conclusion = _nonempty_string(out["job_conclusion"], "job_conclusion").lower()
        if conclusion not in JOB_CONCLUSIONS:
            raise ValueError("unsupported job_conclusion: %s" % conclusion)
        out["job_conclusion"] = conclusion
    return {key: out[key] for key in sorted(out)}


def source_identity(source: Mapping[str, Any]) -> str:
    return _normalized_source_identity(normalize_source(source))


def _normalized_source_identity(source: Mapping[str, Any]) -> str:
    """Return the identity of coordinates already checked by normalize_source."""
    kind = source["kind"]
    if kind == "git_blob":
        parts = (kind, source["repo"], source["blob_sha"])
    elif kind == "git_commit":
        parts = (kind, source["repo"], source["commit_sha"])
    elif kind == "path":
        parts = (kind, source["repo"], source["commit_sha"], source["path"])
    elif kind == "slack_file":
        parts = (kind, source.get("workspace", ""), source["channel_id"], source["file_id"])
    else:
        parts = (kind, source["repo"], str(source["artifact_id"]))
    return "\x1f".join(parts)


def empty_registry() -> Dict[str, Any]:
    return {"schema": SCHEMA, "artifacts": {}}


def validate_registry(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("registry must be a JSON object")
    if set(value) != {"schema", "artifacts"}:
        raise ValueError("registry must contain exactly schema and artifacts")
    if value.get("schema") != SCHEMA:
        raise ValueError("unsupported registry schema")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("artifacts must be a JSON object")

    normalized: Dict[str, Any] = {"schema": SCHEMA, "artifacts": {}}
    seen_locator: Dict[str, str] = {}
    for raw_digest in sorted(artifacts):
        digest = normalize_sha256(raw_digest)
        if digest != raw_digest:
            raise ValueError("artifact keys must be lowercase sha256 values")
        row = artifacts[raw_digest]
        if not isinstance(row, Mapping):
            raise ValueError("artifact row must be an object: %s" % digest)
        if set(row) - {"sha256", "size_bytes", "sources", "labels"}:
            raise ValueError("unexpected artifact row fields: %s" % digest)
        if normalize_sha256(row.get("sha256")) != digest:
            raise ValueError("artifact row sha256 must match its key")
        sources = row.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("artifact row must have at least one source")
        size_bytes = row.get("size_bytes")
        if size_bytes is not None:
            size_bytes = _size(size_bytes)
        labels = row.get("labels", [])
        if not isinstance(labels, list) or any(not isinstance(x, str) or not x.strip() for x in labels):
            raise ValueError("labels must be non-empty strings")
        normalized_sources: List[Dict[str, Any]] = []
        local_ids = set()
        for raw_source in sources:
            source = normalize_source(raw_source)
            identity = _normalized_source_identity(source)
            if identity in local_ids:
                raise ValueError("duplicate source locator in artifact row: %s" % identity)
            local_ids.add(identity)
            other = seen_locator.get(identity)
            if other is not None and other != digest:
                raise ValueError("source locator is bound to two sha256 values: %s" % identity)
            seen_locator[identity] = digest
            normalized_sources.append(source)
        normalized_sources.sort(key=_normalized_source_identity)
        out_row: Dict[str, Any] = {"sha256": digest, "sources": normalized_sources}
        if size_bytes is not None:
            out_row["size_bytes"] = size_bytes
        if labels:
            out_row["labels"] = sorted(set(x.strip() for x in labels))
        normalized["artifacts"][digest] = out_row
    return normalized


def add_artifact(registry: Mapping[str, Any], sha256: str, source: Mapping[str, Any],
                 size_bytes: Optional[int] = None, labels: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    current = validate_registry(registry)
    digest = normalize_sha256(sha256)
    source = normalize_source(source)
    identity = _normalized_source_identity(source)
    if size_bytes is not None:
        size_bytes = _size(size_bytes)
    clean_labels = []
    for label in labels or []:
        clean_labels.append(_nonempty_string(label, "label"))

    # A durable coordinate may identify only one measured byte string.
    for other_digest, other_row in current["artifacts"].items():
        if other_digest == digest:
            continue
        for other_source in other_row["sources"]:
            if _normalized_source_identity(other_source) == identity:
                raise ValueError("source locator already belongs to sha256 %s" % other_digest)

    row = dict(current["artifacts"].get(digest) or {"sha256": digest, "sources": []})
    old_size = row.get("size_bytes")
    if size_bytes is not None and old_size is not None and old_size != size_bytes:
        raise ValueError("size_bytes conflicts with existing artifact row")
    if size_bytes is not None:
        row["size_bytes"] = size_bytes
    by_identity = {_normalized_source_identity(item): item for item in row["sources"]}
    if identity in by_identity and by_identity[identity] != source:
        raise ValueError("source locator metadata conflicts with existing record")
    by_identity[identity] = source
    row["sources"] = [by_identity[key] for key in sorted(by_identity)]
    if clean_labels or row.get("labels"):
        row["labels"] = sorted(set(row.get("labels", [])) | set(clean_labels))
    current["artifacts"][digest] = row
    return validate_registry(current)


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk_size)
            if not block:
                break
            digest.update(block)
            total += len(block)
    return digest.hexdigest(), total


def load_registry(path: str, *, missing_ok: bool = False) -> Dict[str, Any]:
    if not os.path.exists(path):
        if missing_ok:
            return empty_registry()
        raise FileNotFoundError("registry file does not exist: %s" % path)
    with open(path, "r", encoding="utf-8") as fh:
        return validate_registry(loads_strict(fh.read()))


def dump_registry(registry: Mapping[str, Any]) -> str:
    normalized = validate_registry(registry)
    text = json.dumps(normalized, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    # os.fsdecode represents non-UTF-8 filename bytes as surrogate escapes.
    # Escape those in JSON while retaining readable ordinary Unicode names.
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def write_registry(path: str, registry: Mapping[str, Any]) -> None:
    """Atomically replace one snapshot; use add_artifact_file for shared additions."""
    # Reads follow symlinks; publish to the same target without replacing an
    # alias with a second, disconnected ledger.
    path = os.path.realpath(os.fspath(path))
    text = dump_registry(registry)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".artifact-registry-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def _registry_lock(path: str, timeout: float):
    """Serialize writers without deleting the shared lock inode between updates."""
    path = os.path.realpath(os.fspath(path))
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("lock timeout must be a finite non-negative number")
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    # Keep this sidecar after release. Removing it could let a new process lock
    # a different inode while another writer is still waiting on the old one.
    with open(path + ".lock", "a+b") as handle:
        if os.name == "nt":
            import msvcrt

            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()

            def acquire():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

            def release():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            def release():
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

        deadline = time.monotonic() + timeout
        while True:
            try:
                acquire()
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("registry is busy: %s (waited %.3gs)" % (path, timeout)) from error
                time.sleep(min(0.05, remaining))
        try:
            yield
        finally:
            release()


def add_artifact_file(path: str, sha256: str, source: Mapping[str, Any],
                      size_bytes: Optional[int] = None, labels: Optional[Iterable[str]] = None,
                      *, lock_timeout: float = 10.0) -> Dict[str, Any]:
    """Load, add and atomically save under one interprocess writer lock.

    Every cooperating writer rereads after acquiring the lock, so both distinct
    additions and conflicts with another process's newly written locator survive.
    Reads remain lock-free because write_registry replaces complete snapshots.
    """
    # Every symlink alias must share both the publication target and its lock.
    path = os.path.realpath(os.fspath(path))
    with _registry_lock(path, lock_timeout):
        registry = load_registry(path, missing_ok=True)
        registry = add_artifact(registry, sha256, source, size_bytes, labels)
        write_registry(path, registry)
        return registry


def _source_arg(text: str) -> Dict[str, Any]:
    value = loads_strict(text)
    if not isinstance(value, dict):
        raise ValueError("--source-json must decode to an object")
    return value


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SHA-256 keyed Commons artifact registry")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate and normalize a registry")
    validate.add_argument("registry")
    get = sub.add_parser("get", help="print one artifact row")
    get.add_argument("registry")
    get.add_argument("sha256")
    add = sub.add_parser("add", help="add one durable source coordinate")
    add.add_argument("registry")
    add.add_argument("sha256")
    add.add_argument("--source-json", required=True)
    add.add_argument("--size-bytes", type=int)
    add.add_argument("--label", action="append", default=[])
    add.add_argument("--lock-timeout", type=float, default=10.0,
                     help="seconds to wait for another registry writer (default: 10)")
    hash_cmd = sub.add_parser("hash", help="hash a local file without changing a registry")
    hash_cmd.add_argument("path")
    args = parser.parse_args(argv)

    try:
        if args.command == "hash":
            digest, size = sha256_file(args.path)
            print(json.dumps({"sha256": digest, "size_bytes": size}, sort_keys=True))
            return 0
        if args.command == "add":
            registry = add_artifact_file(
                args.registry, args.sha256, _source_arg(args.source_json),
                size_bytes=args.size_bytes, labels=args.label, lock_timeout=args.lock_timeout,
            )
            print(json.dumps(registry["artifacts"][normalize_sha256(args.sha256)],
                             sort_keys=True, indent=2) + "\n", end="")
            return 0
        registry = load_registry(args.registry)
        if args.command == "validate":
            print(dump_registry(registry), end="")
            return 0
        if args.command == "get":
            digest = normalize_sha256(args.sha256)
            row = registry["artifacts"].get(digest)
            if row is None:
                raise ValueError("artifact not found: %s" % digest)
            print(json.dumps(row, sort_keys=True, indent=2) + "\n", end="")
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
