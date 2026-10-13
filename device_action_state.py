#!/usr/bin/env python3
"""Fail-closed transport state for Commons device ACTION records.

The hosted prepare job reserves a deterministic bounded prefix of currently
OPEN device actions on fresh main before any self-hosted runner is scheduled.
The runner checks out that exact prepared commit, validates the whole batch,
executes its reservations sequentially in sorted id order, and emits bounded
receipts.  A fresh hosted finalizer validates every receipt before creating
terminal result records.

PREPARED without a valid terminal record is permanently UNKNOWN.  There is no
TTL, unreserve, or automatic replay.  The guarantee is deliberately scoped to
canonical GitHub workflow scheduling across runs/reruns; arbitrary shell code
cannot provide universal exactly-once external effects.  The self-hosted runner
and same-privilege device payload are a trust boundary for receipt truth: the
hosted finalizer runs only after the executor job succeeds, but this protocol
does not authenticate files against a detached process with that same OS
identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import action_executor

ROOT = Path(__file__).resolve().parent
RESERVATIONS = ROOT / "actions" / "device-reservations"
BATCHES = ROOT / "actions" / "device-batches"
RESULTS = ROOT / "actions" / "results"

RESERVATION_SCHEMA = "COMMONS_DEVICE_RESERVATION.v1"
BATCH_SCHEMA = "COMMONS_DEVICE_BATCH.v1"
RESULT_SCHEMA = "COMMONS_DEVICE_RESULT.v1"
PREPARED = "PREPARED"
REPORTED_SUCCEEDED = "REPORTED_SUCCEEDED"
REPORTED_FAILED = "REPORTED_FAILED"

MAX_JSON_BYTES = 64 * 1024
MAX_BATCH_ACTIONS = 16
CAS_RETRY = 75
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_RE = re.compile(r"^[1-9][0-9]{0,19}$")
STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

PROTOCOL_FILES = (
    "action_executor.py",
    "device_action_state.py",
    ".github/workflows/commons-device-executor.yml",
    ".github/workflows/commons-device-cycle.yml",
)

RESERVATION_KEYS = {
    "schema", "state", "id", "action_path", "action_sha256", "action_blob_oid",
    "payload_sha256", "verb", "target", "run_id", "run_attempt",
    "prepared_from_main", "prepared_at", "workflow_sha", "workflow_ref",
    "executor_sha256", "protocol_sha256", "caller_workflow_sha256",
    "cycle_workflow_sha256",
}
BATCH_KEYS = {
    "schema", "run_id", "run_attempt", "prepared_from_main", "prepared_at",
    "workflow_sha", "workflow_ref", "reservations",
}
BATCH_ENTRY_KEYS = {"id", "path", "sha256"}
RESULT_KEYS = {
    "schema", "state", "id", "scope", "verb", "target", "action_path",
    "action_sha256", "action_blob_oid", "payload_sha256", "reservation_path",
    "reservation_sha256", "batch_path", "batch_sha256", "prepared_commit",
    "prepared_from_main", "workflow_sha", "workflow_ref", "executor_sha256",
    "protocol_sha256", "caller_workflow_sha256", "cycle_workflow_sha256",
    "run_id", "run_attempt", "ok", "attempted_at", "executed_at", "error_code",
}


class StateError(ValueError):
    """A fail-closed state, schema, provenance, or transport violation."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(row: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _reject_constant(value: str) -> None:
    raise StateError("non-finite JSON number is forbidden: %s" % value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise StateError("duplicate JSON key: %s" % key)
        out[key] = value
    return out


def strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise StateError("%s exceeds the JSON size limit" % label)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StateError("%s is not UTF-8" % label) from exc
    try:
        row = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise StateError("%s is not strict JSON" % label) from exc
    if type(row) is not dict:
        raise StateError("%s must be a JSON object" % label)
    if canonical_bytes(row) != raw:
        raise StateError("%s is not canonical JSON" % label)
    return row


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=check,
    )


def head(ref: str = "HEAD") -> str:
    value = git("rev-parse", ref).stdout.strip().lower()
    if not SHA_RE.fullmatch(value):
        raise StateError("invalid git revision: %s" % ref)
    return value


def require_full_history() -> None:
    inside = git("rev-parse", "--is-inside-work-tree", check=False)
    shallow = git("rev-parse", "--is-shallow-repository", check=False)
    if inside.returncode or inside.stdout.strip() != "true":
        raise StateError("device state requires a Git worktree")
    if shallow.returncode or shallow.stdout.strip() != "false":
        raise StateError("device state requires reachable full main history")


def require_actions_checkout() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise StateError("device state mutation is restricted to GitHub Actions")
    require_full_history()


def require_github_run_context(run_id: str, run_attempt: int) -> None:
    if os.environ.get("GITHUB_RUN_ID") != run_id:
        raise StateError("GitHub run id does not match the bound reservation")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != str(run_attempt):
        raise StateError("GitHub run attempt does not match the bound reservation")


def require_clean_checkout() -> None:
    if git("status", "--porcelain=v1", "--untracked-files=all").stdout:
        raise StateError("device state writer requires a clean checkout")


def _regular_file_bytes(path: Path, *, root: Path | None = None, label: str | None = None) -> bytes:
    root = (root or ROOT).resolve()
    try:
        rel = path.relative_to(root)
    except ValueError as exc:
        raise StateError("path escapes its trusted root") from exc
    cursor = root
    for part in rel.parts[:-1]:
        cursor = cursor / part
        if not cursor.exists():
            raise StateError("missing parent directory for %s" % (label or rel))
        mode = os.lstat(cursor).st_mode
        if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
            raise StateError("non-directory or symlink parent for %s" % (label or rel))
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as exc:
        raise StateError("missing file: %s" % (label or rel)) from exc
    if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
        raise StateError("file must be regular and not a symlink: %s" % (label or rel))
    return path.read_bytes()


def _ensure_real_directory(path: Path, *, root: Path | None = None) -> None:
    """Create a directory without traversing a symlink or non-directory."""
    trusted = root or ROOT
    try:
        rel = path.relative_to(trusted)
    except ValueError as exc:
        raise StateError("directory escapes its trusted root") from exc
    try:
        root_mode = os.lstat(trusted).st_mode
    except FileNotFoundError as exc:
        raise StateError("trusted directory root is missing") from exc
    if not stat.S_ISDIR(root_mode) or stat.S_ISLNK(root_mode):
        raise StateError("trusted directory root must be a real directory")
    cursor = trusted
    for part in rel.parts:
        cursor = cursor / part
        try:
            mode = os.lstat(cursor).st_mode
        except FileNotFoundError:
            cursor.mkdir()
            mode = os.lstat(cursor).st_mode
        if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
            raise StateError("state directory contains a symlink or non-directory")


def load_canonical_file(path: Path, *, root: Path | None = None, label: str | None = None) -> tuple[dict[str, Any], bytes]:
    raw = _regular_file_bytes(path, root=root, label=label)
    return strict_json(raw, label=label or str(path)), raw


def git_bytes(ref: str, rel: str) -> bytes:
    proc = subprocess.run(
        ["git", "show", "%s:%s" % (ref, rel)], cwd=ROOT, capture_output=True,
    )
    if proc.returncode:
        raise StateError("%s is absent at %s" % (rel, ref))
    return proc.stdout


def git_path_ever(ref: str, rel: str) -> bool:
    # --full-history is required when a side branch adds and removes a latch
    # before being merged into a tree where the path is absent.
    proc = git("log", "--full-history", "-1", "--format=%H", ref, "--", rel)
    return bool(proc.stdout.strip())


def reservation_rel(ident: str) -> str:
    require_id(ident)
    return "actions/device-reservations/%s.json" % ident


def batch_rel(run_id: str, run_attempt: int) -> str:
    require_run(run_id, run_attempt)
    return "actions/device-batches/%s-%s.json" % (run_id, run_attempt)


def result_rel(ident: str) -> str:
    require_id(ident)
    return "actions/results/%s.json" % ident


def artifact_name(ident: str, run_id: str, run_attempt: int) -> str:
    require_id(ident)
    require_run(run_id, run_attempt)
    return "commons-device-receipt-%s-%s-%s" % (ident, run_id, run_attempt)


def require_id(ident: Any) -> str:
    if type(ident) is not str or not action_executor.ID_RE.fullmatch(ident):
        raise StateError("invalid Commons action id")
    return ident


def require_run(run_id: Any, run_attempt: Any) -> tuple[str, int]:
    if type(run_id) is not str or not RUN_RE.fullmatch(run_id):
        raise StateError("invalid GitHub run id")
    if type(run_attempt) is not int or run_attempt < 1 or run_attempt > 1_000_000:
        raise StateError("invalid GitHub run attempt")
    return run_id, run_attempt


def require_sha(value: Any, *, label: str, length: int = 64) -> str:
    pattern = HASH_RE if length == 64 else SHA_RE
    if type(value) is not str or not pattern.fullmatch(value):
        raise StateError("invalid %s" % label)
    return value


def require_stamp(value: Any, *, label: str) -> str:
    if type(value) is not str or not STAMP_RE.fullmatch(value):
        raise StateError("invalid %s" % label)
    return value


def require_exact_keys(row: dict[str, Any], keys: set[str], *, label: str) -> None:
    if set(row) != keys:
        raise StateError(
            "%s key mismatch; missing=%r extra=%r"
            % (label, sorted(keys - set(row)), sorted(set(row) - keys))
        )


def protocol_hashes_at_ref(ref: str) -> dict[str, str]:
    return {rel: sha256_bytes(git_bytes(ref, rel)) for rel in PROTOCOL_FILES}


def _require_checkout_file_matches(ref: str, rel: str) -> bytes:
    """Accept exact bytes or Git's mechanical LF-to-CRLF checkout conversion."""
    blob = git_bytes(ref, rel)
    working = _regular_file_bytes(ROOT / rel, label=rel)
    if working != blob and working.replace(b"\r\n", b"\n") != blob:
        raise StateError("working checkout bytes differ from bound Git bytes: %s" % rel)
    return blob


def validate_reservation(
    row: dict[str, Any], *, ident: str | None = None, run_id: str | None = None,
    run_attempt: int | None = None,
) -> dict[str, Any]:
    require_exact_keys(row, RESERVATION_KEYS, label="device reservation")
    if row["schema"] != RESERVATION_SCHEMA or row["state"] != PREPARED:
        raise StateError("invalid device reservation schema/state")
    got_id = require_id(row["id"])
    if ident is not None and got_id != ident:
        raise StateError("reservation id mismatch")
    if row["action_path"] != "p/%s.md" % got_id:
        raise StateError("reservation action path is not canonical")
    require_sha(row["action_sha256"], label="action sha256")
    require_sha(row["action_blob_oid"], label="action blob oid", length=40)
    require_sha(row["payload_sha256"], label="payload sha256")
    if (
        type(row["verb"]) is not str
        or not row["verb"]
        or len(row["verb"]) > action_executor.MAX_ACTION_VERB_CHARS
    ):
        raise StateError("invalid reserved verb")
    if (
        type(row["target"]) is not str
        or len(row["target"]) > action_executor.MAX_DEVICE_TARGET_CHARS
        or "\n" in row["target"]
        or not action_executor.is_device_target(row["target"])
    ):
        raise StateError("reservation target is not a device")
    require_run(row["run_id"], row["run_attempt"])
    if run_id is not None and row["run_id"] != run_id:
        raise StateError("reservation run id mismatch")
    if run_attempt is not None and row["run_attempt"] != run_attempt:
        raise StateError("reservation run attempt mismatch")
    require_sha(row["prepared_from_main"], label="prepared-from-main", length=40)
    require_stamp(row["prepared_at"], label="prepared-at")
    require_sha(row["workflow_sha"], label="workflow sha", length=40)
    if type(row["workflow_ref"]) is not str or not row["workflow_ref"] or len(row["workflow_ref"]) > 300 or "\n" in row["workflow_ref"]:
        raise StateError("invalid workflow ref")
    for key in (
        "executor_sha256", "protocol_sha256", "caller_workflow_sha256",
        "cycle_workflow_sha256",
    ):
        require_sha(row[key], label=key.replace("_", " "))
    return row


def validate_batch(
    row: dict[str, Any], *, expected_path: str | None = None,
    run_id: str | None = None, run_attempt: int | None = None,
) -> dict[str, Any]:
    require_exact_keys(row, BATCH_KEYS, label="device batch")
    if row["schema"] != BATCH_SCHEMA:
        raise StateError("invalid device batch schema")
    got_run, got_attempt = require_run(row["run_id"], row["run_attempt"])
    if run_id is not None and got_run != run_id:
        raise StateError("batch run id mismatch")
    if run_attempt is not None and got_attempt != run_attempt:
        raise StateError("batch run attempt mismatch")
    if expected_path is not None and expected_path != batch_rel(got_run, got_attempt):
        raise StateError("batch path mismatch")
    require_sha(row["prepared_from_main"], label="batch source commit", length=40)
    require_stamp(row["prepared_at"], label="batch prepared-at")
    require_sha(row["workflow_sha"], label="batch workflow sha", length=40)
    if type(row["workflow_ref"]) is not str or not row["workflow_ref"] or len(row["workflow_ref"]) > 300 or "\n" in row["workflow_ref"]:
        raise StateError("invalid batch workflow ref")
    entries = row["reservations"]
    if type(entries) is not list or not entries:
        raise StateError("device batch must contain reservations")
    if len(entries) > MAX_BATCH_ACTIONS:
        raise StateError("device batch exceeds the bounded execution size")
    ids: list[str] = []
    for entry in entries:
        if type(entry) is not dict:
            raise StateError("batch reservation entry must be an object")
        require_exact_keys(entry, BATCH_ENTRY_KEYS, label="batch reservation entry")
        ident = require_id(entry["id"])
        if entry["path"] != reservation_rel(ident):
            raise StateError("batch reservation path mismatch")
        require_sha(entry["sha256"], label="reservation sha256")
        ids.append(ident)
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise StateError("batch reservation ids must be unique and sorted")
    return row


def validate_result(
    row: dict[str, Any], *, reservation: dict[str, Any], reservation_sha: str,
    batch_path: str, batch_sha: str, prepared_commit: str,
) -> dict[str, Any]:
    require_exact_keys(row, RESULT_KEYS, label="device result")
    if row["schema"] != RESULT_SCHEMA:
        raise StateError("invalid device result schema")
    if row["state"] not in {REPORTED_SUCCEEDED, REPORTED_FAILED}:
        raise StateError("invalid reported result state")
    if type(row["ok"]) is not bool:
        raise StateError("device result ok must be boolean")
    if (row["state"] == REPORTED_SUCCEEDED) != row["ok"]:
        raise StateError("device result state/ok mismatch")
    if row["error_code"] is not None and type(row["error_code"]) is not str:
        raise StateError("device result error code must be null or string")
    expected_error = None if row["ok"] else "EXECUTION_FAILED"
    if row["error_code"] != expected_error:
        raise StateError("device result error code mismatch")
    if row["scope"] != "device":
        raise StateError("device result scope mismatch")
    for key in (
        "id", "verb", "target", "action_path", "action_sha256", "action_blob_oid",
        "payload_sha256", "prepared_from_main", "workflow_sha", "workflow_ref",
        "executor_sha256", "protocol_sha256", "caller_workflow_sha256",
        "cycle_workflow_sha256", "run_id", "run_attempt",
    ):
        if row[key] != reservation[key]:
            raise StateError("device result %s mismatch" % key)
    if row["reservation_path"] != reservation_rel(reservation["id"]):
        raise StateError("device result reservation path mismatch")
    if row["reservation_sha256"] != reservation_sha:
        raise StateError("device result reservation hash mismatch")
    if row["batch_path"] != batch_path or row["batch_sha256"] != batch_sha:
        raise StateError("device result batch binding mismatch")
    if row["prepared_commit"] != prepared_commit:
        raise StateError("device result prepared commit mismatch")
    require_stamp(row["attempted_at"], label="attempted-at")
    require_stamp(row["executed_at"], label="executed-at")
    return row


def _action_binding(rec: dict[str, Any], source_commit: str, hashes: dict[str, str]) -> dict[str, Any]:
    ident = rec["meta"]["id"]
    action_path = "p/%s.md" % ident
    if rec["path"] != action_path:
        raise StateError("action source path is not canonical")
    raw = _require_checkout_file_matches(source_commit, action_path)
    blob = git("rev-parse", "%s:%s" % (source_commit, action_path), check=False)
    if blob.returncode or not SHA_RE.fullmatch(blob.stdout.strip().lower()):
        raise StateError("action is not committed at the prepared source commit")
    return {
        "id": ident,
        "action_path": action_path,
        "action_sha256": sha256_bytes(raw),
        "action_blob_oid": blob.stdout.strip().lower(),
        "payload_sha256": sha256_bytes(rec["payload"].encode("utf-8")),
        "verb": rec["verb"],
        "target": rec["target"],
        "executor_sha256": hashes["action_executor.py"],
        "protocol_sha256": hashes["device_action_state.py"],
        "caller_workflow_sha256": hashes[".github/workflows/commons-device-executor.yml"],
        "cycle_workflow_sha256": hashes[".github/workflows/commons-device-cycle.yml"],
    }


def _write_json(path: Path, row: dict[str, Any]) -> bytes:
    raw = canonical_bytes(row)
    if len(raw) > MAX_JSON_BYTES:
        raise StateError("generated state exceeds the JSON size limit")
    _ensure_real_directory(path.parent)
    _write_new_bytes(path, raw, label=str(path.relative_to(ROOT)))
    return raw


def _write_new_bytes(path: Path, raw: bytes, *, label: str) -> None:
    """Create one regular file atomically without following a late symlink."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise StateError("refusing to overwrite state path: %s" % label) from exc
    except OSError as exc:
        raise StateError("could not create bounded state path: %s" % label) from exc
    with os.fdopen(fd, "wb") as dst:
        dst.write(raw)


def _write_outputs(path: Path | None, values: dict[str, Any]) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as dst:
        for key, value in values.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, separators=(",", ":"), sort_keys=True)
            dst.write("%s=%s\n" % (key, value))


def _prepared_commit_for(batch_path: str, ref: str = "HEAD") -> str:
    proc = git("log", "--full-history", "-1", "--format=%H", ref, "--", batch_path)
    value = proc.stdout.strip().lower()
    if not SHA_RE.fullmatch(value):
        raise StateError("cannot locate prepared commit for batch")
    return value


def _matrix(batch: dict[str, Any], prepared_commit: str, batch_path: str, batch_sha: str) -> list[dict[str, Any]]:
    return [
        {
            "id": entry["id"],
            "prepared_commit": prepared_commit,
            "batch_path": batch_path,
            "batch_sha256": batch_sha,
        }
        for entry in batch["reservations"]
    ]


def _publish_prepare_outputs(
    output: Path | None, batch: dict[str, Any] | None = None,
    prepared_commit: str = "", batch_path: str = "", batch_sha: str = "",
) -> None:
    if batch is None:
        _write_outputs(output, {
            "reservation_count": 0, "matrix": [], "prepared_commit": "",
            "batch_path": "", "batch_sha256": "",
        })
        return
    _write_outputs(output, {
        "reservation_count": len(batch["reservations"]),
        "matrix": _matrix(batch, prepared_commit, batch_path, batch_sha),
        "prepared_commit": prepared_commit,
        "batch_path": batch_path,
        "batch_sha256": batch_sha,
    })


def _verify_remote_files(ref: str, expected: dict[str, bytes]) -> bool:
    try:
        return all(git_bytes(ref, rel) == raw for rel, raw in expected.items())
    except StateError:
        return False


def prepare_once(
    run_id: str, run_attempt: int, workflow_sha: str, workflow_ref: str,
    output: Path | None = None,
) -> int:
    require_actions_checkout()
    require_run(run_id, run_attempt)
    require_github_run_context(run_id, run_attempt)
    require_sha(workflow_sha, label="workflow sha", length=40)
    if not workflow_ref or "\n" in workflow_ref or len(workflow_ref) > 300:
        raise StateError("invalid workflow ref")
    require_clean_checkout()
    source_commit = head()
    if source_commit != head("origin/main"):
        raise StateError("prepare checkout is not exact current main")
    if git("merge-base", "--is-ancestor", workflow_sha, source_commit, check=False).returncode:
        raise StateError("workflow definition is not reachable from prepared main")
    for rel in PROTOCOL_FILES:
        if git_bytes(workflow_sha, rel) != git_bytes(source_commit, rel):
            raise StateError("protocol bytes changed after this run was created: %s" % rel)

    path_rel = batch_rel(run_id, run_attempt)
    path = ROOT / path_rel
    if os.path.lexists(path):
        batch, raw = load_canonical_file(path, label=path_rel)
        validate_batch(batch, expected_path=path_rel, run_id=run_id, run_attempt=run_attempt)
        prepared_commit = _prepared_commit_for(path_rel)
        validate_prepared_bundle(
            prepared_commit, path_rel, sha256_bytes(raw), run_id, run_attempt,
            workflow_sha=workflow_sha, workflow_ref=workflow_ref,
            require_remote=True,
        )
        _publish_prepare_outputs(output, batch, prepared_commit, path_rel, sha256_bytes(raw))
        return 0
    if git_path_ever("HEAD", path_rel):
        raise StateError("historical batch path was removed; refusing to recreate it")

    # Receipts are finalized only after the sequential self-hosted batch job
    # completes.  Leave later OPEN actions
    # unreserved for a subsequent cycle rather than latching an oversized set.
    rows = action_executor.pending("device")[:MAX_BATCH_ACTIONS]
    if not rows:
        _publish_prepare_outputs(output)
        return 0
    hashes = protocol_hashes_at_ref(source_commit)
    stamp = utc_now()
    entries: list[dict[str, str]] = []
    expected: dict[str, bytes] = {}
    for rec in rows:
        ident = rec["meta"]["id"]
        binding = _action_binding(rec, source_commit, hashes)
        reservation = {
            "schema": RESERVATION_SCHEMA,
            "state": PREPARED,
            **binding,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "prepared_from_main": source_commit,
            "prepared_at": stamp,
            "workflow_sha": workflow_sha,
            "workflow_ref": workflow_ref,
        }
        validate_reservation(reservation, ident=ident, run_id=run_id, run_attempt=run_attempt)
        rel = reservation_rel(ident)
        if git_path_ever("HEAD", rel) or os.path.lexists(ROOT / rel):
            raise StateError("action became latched during preparation: %s" % ident)
        raw = _write_json(ROOT / rel, reservation)
        expected[rel] = raw
        entries.append({"id": ident, "path": rel, "sha256": sha256_bytes(raw)})

    batch = {
        "schema": BATCH_SCHEMA,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "prepared_from_main": source_commit,
        "prepared_at": stamp,
        "workflow_sha": workflow_sha,
        "workflow_ref": workflow_ref,
        "reservations": entries,
    }
    validate_batch(batch, expected_path=path_rel, run_id=run_id, run_attempt=run_attempt)
    batch_raw = _write_json(path, batch)
    expected[path_rel] = batch_raw
    names = sorted(expected)
    changed = sorted(
        name for name in git("status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
        if name
    )
    # A clean start plus exact path-limited add below keeps unrelated bytes out;
    # this count is an additional guard against a writer bug.
    if len(changed) != len(names):
        raise StateError("prepare produced an unexpected working-tree change set")
    git("add", "--", *names)
    staged = sorted(git("diff", "--cached", "--name-only").stdout.splitlines())
    if staged != names:
        raise StateError("prepare staged an unexpected path set")
    git("config", "user.name", "commons-device-state")
    git("config", "user.email", "commons-device-state@users.noreply.github.com")
    git("commit", "-m", "reserve Commons device actions")
    candidate = head()
    pushed = git("push", "origin", "HEAD:main", check=False)
    git("fetch", "origin", "main", check=False)
    if pushed.returncode:
        if not _verify_remote_files("origin/main", expected):
            return CAS_RETRY
        candidate = _prepared_commit_for(path_rel, "origin/main")
    if not _verify_remote_files("origin/main", expected):
        raise StateError("prepared state failed remote readback")
    _publish_prepare_outputs(output, batch, candidate, path_rel, sha256_bytes(batch_raw))
    return 0


def _validate_action_at_ref(reservation: dict[str, Any], ref: str) -> dict[str, Any]:
    action_raw = git_bytes(ref, reservation["action_path"])
    if sha256_bytes(action_raw) != reservation["action_sha256"]:
        raise StateError("reserved action bytes changed")
    blob = git("rev-parse", "%s:%s" % (ref, reservation["action_path"]), check=False)
    if blob.returncode or blob.stdout.strip().lower() != reservation["action_blob_oid"]:
        raise StateError("reserved action blob changed")
    path = ROOT / reservation["action_path"]
    if ref == "HEAD":
        _require_checkout_file_matches(ref, reservation["action_path"])
        rec = action_executor.parse_record(path)
    else:
        # parse_record intentionally accepts a Path.  A temporary parser would
        # add a second grammar, so parse the checked-out prepared commit only.
        rec = None
    if rec is not None:
        if rec["path"] != reservation["action_path"]:
            raise StateError("reserved action path mismatch")
        if rec["meta"]["id"] != reservation["id"]:
            raise StateError("reserved action id mismatch")
        if rec["verb"] != reservation["verb"] or rec["target"] != reservation["target"]:
            raise StateError("reserved verb or target changed")
        if sha256_bytes(rec["payload"].encode("utf-8")) != reservation["payload_sha256"]:
            raise StateError("reserved payload changed")
    return rec


def validate_prepared_bundle(
    prepared_commit: str, batch_path: str, batch_sha: str, run_id: str,
    run_attempt: int, *, workflow_sha: str, workflow_ref: str,
    require_remote: bool, allow_terminal_history: bool = False,
) -> tuple[dict[str, Any], list[tuple[dict[str, Any], str]]]:
    require_sha(prepared_commit, label="prepared commit", length=40)
    require_sha(batch_sha, label="batch sha256")
    require_run(run_id, run_attempt)
    if batch_path != batch_rel(run_id, run_attempt):
        raise StateError("noncanonical batch path")
    batch_raw = git_bytes(prepared_commit, batch_path)
    if sha256_bytes(batch_raw) != batch_sha:
        raise StateError("prepared batch hash mismatch")
    batch = strict_json(batch_raw, label="prepared batch")
    validate_batch(batch, expected_path=batch_path, run_id=run_id, run_attempt=run_attempt)
    if batch["workflow_sha"] != workflow_sha or batch["workflow_ref"] != workflow_ref:
        raise StateError("prepared batch workflow binding mismatch")
    parents = git("rev-list", "--parents", "-n", "1", prepared_commit).stdout.split()
    if len(parents) != 2 or parents[1].lower() != batch["prepared_from_main"]:
        raise StateError("prepared commit is not a one-parent commit on its bound source")
    statuses = [
        line.split("\t", 1) for line in
        git("diff-tree", "--no-commit-id", "--name-status", "-r", prepared_commit).stdout.splitlines()
        if line
    ]
    expected_paths = sorted([batch_path] + [entry["path"] for entry in batch["reservations"]])
    if any(len(row) != 2 or row[0] != "A" for row in statuses):
        raise StateError("prepared commit may only add state files")
    if sorted(row[1] for row in statuses) != expected_paths:
        raise StateError("prepared commit contains an unexpected path")
    if require_remote:
        if git("merge-base", "--is-ancestor", prepared_commit, "origin/main", check=False).returncode:
            raise StateError("prepared commit is not reachable from current main")
        if git_bytes("origin/main", batch_path) != batch_raw:
            raise StateError("current main does not retain the prepared batch")
    reservations: list[tuple[dict[str, Any], str]] = []
    for entry in batch["reservations"]:
        raw = git_bytes(prepared_commit, entry["path"])
        if sha256_bytes(raw) != entry["sha256"]:
            raise StateError("prepared reservation hash mismatch")
        reservation = strict_json(raw, label=entry["path"])
        validate_reservation(
            reservation, ident=entry["id"], run_id=run_id, run_attempt=run_attempt,
        )
        for key in ("prepared_from_main", "prepared_at", "workflow_sha", "workflow_ref"):
            if reservation[key] != batch[key]:
                raise StateError("reservation/batch %s mismatch" % key)
        _validate_action_at_ref(reservation, prepared_commit)
        bound_protocol = {
            "action_executor.py": reservation["executor_sha256"],
            "device_action_state.py": reservation["protocol_sha256"],
            ".github/workflows/commons-device-executor.yml": reservation["caller_workflow_sha256"],
            ".github/workflows/commons-device-cycle.yml": reservation["cycle_workflow_sha256"],
        }
        for rel, digest in bound_protocol.items():
            if sha256_bytes(git_bytes(prepared_commit, rel)) != digest:
                raise StateError("reservation protocol hash mismatch: %s" % rel)
        if require_remote:
            if git_bytes("origin/main", entry["path"]) != raw:
                raise StateError("current main does not retain the reservation")
            if git_bytes("origin/main", reservation["action_path"]) != git_bytes(prepared_commit, reservation["action_path"]):
                raise StateError("current main changed the reserved action")
            terminal = result_rel(reservation["id"])
            if not allow_terminal_history and git_path_ever("origin/main", terminal):
                raise StateError("reserved action already has terminal history")
        reservations.append((reservation, entry["sha256"]))
    return batch, reservations


def _execution_bundle(
    run_id: str, run_attempt: int, prepared_commit: str, batch_path: str,
    batch_sha: str, workflow_sha: str, workflow_ref: str,
) -> tuple[dict[str, Any], list[tuple[dict[str, Any], str]]]:
    require_actions_checkout()
    require_run(run_id, run_attempt)
    require_github_run_context(run_id, run_attempt)
    require_clean_checkout()
    if head() != prepared_commit:
        raise StateError("self-hosted checkout is not the exact prepared commit")
    git("fetch", "origin", "main")
    batch, reservations = validate_prepared_bundle(
        prepared_commit, batch_path, batch_sha, run_id, run_attempt,
        workflow_sha=workflow_sha, workflow_ref=workflow_ref, require_remote=True,
    )
    hashes = protocol_hashes_at_ref("HEAD")
    for reservation, _reservation_sha in reservations:
        expected_hashes = {
            "action_executor.py": reservation["executor_sha256"],
            "device_action_state.py": reservation["protocol_sha256"],
            ".github/workflows/commons-device-executor.yml": reservation["caller_workflow_sha256"],
            ".github/workflows/commons-device-cycle.yml": reservation["cycle_workflow_sha256"],
        }
        if hashes != expected_hashes:
            raise StateError("prepared executor/protocol/workflow bytes changed")
    for rel in PROTOCOL_FILES:
        _require_checkout_file_matches("HEAD", rel)
    return batch, reservations


def _runner_root() -> Path:
    runner_temp = os.environ.get("RUNNER_TEMP")
    if not runner_temp:
        raise StateError("RUNNER_TEMP is required for bounded receipt transport")
    runner_root = Path(runner_temp)
    _ensure_real_directory(runner_root, root=runner_root)
    return runner_root


def _execute_reserved(
    reservation: dict[str, Any], reservation_sha: str, *, batch_path: str,
    batch_sha: str, prepared_commit: str, runner_root: Path,
    defer_receipt: bool = False,
) -> tuple[Path, bytes]:
    ident = reservation["id"]
    rec = _validate_action_at_ref(reservation, "HEAD")
    if rec is None:
        raise StateError("reserved action did not parse at prepared HEAD")
    start_path = runner_root / (".commons-device-started-" + reservation_sha)
    try:
        _write_new_bytes(
            start_path, (prepared_commit + "\n").encode("ascii"),
            label="reservation start marker",
        )
    except StateError as exc:
        raise StateError("this job workspace already started the reservation") from exc

    attempted_at = utc_now()
    try:
        result = action_executor.execute(rec, "device")
        ok = result.get("ok") is True
    except Exception:
        ok = False
    executed_at = utc_now()
    row = {
        "schema": RESULT_SCHEMA,
        "state": REPORTED_SUCCEEDED if ok else REPORTED_FAILED,
        "id": ident,
        "scope": "device",
        "verb": reservation["verb"],
        "target": reservation["target"],
        "action_path": reservation["action_path"],
        "action_sha256": reservation["action_sha256"],
        "action_blob_oid": reservation["action_blob_oid"],
        "payload_sha256": reservation["payload_sha256"],
        "reservation_path": reservation_rel(ident),
        "reservation_sha256": reservation_sha,
        "batch_path": batch_path,
        "batch_sha256": batch_sha,
        "prepared_commit": prepared_commit,
        "prepared_from_main": reservation["prepared_from_main"],
        "workflow_sha": reservation["workflow_sha"],
        "workflow_ref": reservation["workflow_ref"],
        "executor_sha256": reservation["executor_sha256"],
        "protocol_sha256": reservation["protocol_sha256"],
        "caller_workflow_sha256": reservation["caller_workflow_sha256"],
        "cycle_workflow_sha256": reservation["cycle_workflow_sha256"],
        "run_id": reservation["run_id"],
        "run_attempt": reservation["run_attempt"],
        "ok": ok,
        "attempted_at": attempted_at,
        "executed_at": executed_at,
        "error_code": None if ok else "EXECUTION_FAILED",
    }
    validate_result(
        row, reservation=reservation, reservation_sha=reservation_sha,
        batch_path=batch_path, batch_sha=batch_sha, prepared_commit=prepared_commit,
    )
    receipt_raw = canonical_bytes(row)
    if len(receipt_raw) > MAX_JSON_BYTES:
        raise StateError("generated receipt exceeds the JSON size limit")
    receipt_dir = (
        runner_root / "device-receipts"
        / artifact_name(ident, reservation["run_id"], reservation["run_attempt"])
    )
    receipt_path = receipt_dir / "receipt.json"
    if not defer_receipt:
        # The action payload runs before this directory exists.  A
        # payload-created symlink/non-directory is rejected, and the leaf uses
        # exclusive no-follow creation.
        _ensure_real_directory(receipt_dir, root=runner_root)
        _write_new_bytes(receipt_path, receipt_raw, label="device receipt")
    return receipt_path, receipt_raw


def execute_one(
    ident: str, run_id: str, run_attempt: int, prepared_commit: str,
    batch_path: str, batch_sha: str, workflow_sha: str, workflow_ref: str,
) -> int:
    require_id(ident)
    _batch, reservations = _execution_bundle(
        run_id, run_attempt, prepared_commit, batch_path, batch_sha,
        workflow_sha, workflow_ref,
    )
    matches = [(row, digest) for row, digest in reservations if row["id"] == ident]
    if len(matches) != 1:
        raise StateError("action is not uniquely reserved")
    reservation, reservation_sha = matches[0]
    _execute_reserved(
        reservation, reservation_sha, batch_path=batch_path,
        batch_sha=batch_sha, prepared_commit=prepared_commit,
        runner_root=_runner_root(),
    )
    return 0


def execute_batch(
    run_id: str, run_attempt: int, prepared_commit: str, batch_path: str,
    batch_sha: str, workflow_sha: str, workflow_ref: str,
) -> int:
    _batch, reservations = _execution_bundle(
        run_id, run_attempt, prepared_commit, batch_path, batch_sha,
        workflow_sha, workflow_ref,
    )
    runner_root = _runner_root()
    # validate_batch requires sorted unique ids; keep that exact order so this
    # preserves action_executor.main's historical sequential execution law.
    deferred: list[tuple[Path, bytes]] = []
    for reservation, reservation_sha in reservations:
        deferred.append(_execute_reserved(
            reservation, reservation_sha, batch_path=batch_path,
            batch_sha=batch_sha, prepared_commit=prepared_commit,
            runner_root=runner_root, defer_receipt=True,
        ))
    # Keep authoritative receipts in the Python parent until every payload has
    # returned.  A later action therefore cannot rewrite an earlier receipt;
    # any pre-created path/symlink makes the whole batch fail closed here.
    for receipt_path, receipt_raw in deferred:
        _ensure_real_directory(receipt_path.parent, root=runner_root)
        _write_new_bytes(receipt_path, receipt_raw, label="device receipt")
    return 0


def _artifact_receipts(
    source: Path, batch: dict[str, Any], reservations: list[tuple[dict[str, Any], str]],
    batch_path: str, batch_sha: str, prepared_commit: str,
) -> dict[str, bytes]:
    try:
        root_mode = os.lstat(source).st_mode
    except FileNotFoundError as exc:
        raise StateError("device receipt artifact root is missing") from exc
    if not stat.S_ISDIR(root_mode) or stat.S_ISLNK(root_mode):
        raise StateError("device receipt artifact root must be a real directory")
    expected_dirs = {
        artifact_name(row["id"], row["run_id"], row["run_attempt"]): (row, digest)
        for row, digest in reservations
    }
    actual_dirs = {entry.name: entry for entry in os.scandir(source)}
    if set(actual_dirs) != set(expected_dirs):
        raise StateError("device receipt artifact directory set mismatch")
    receipts: dict[str, bytes] = {}
    for name, (reservation, reservation_sha) in expected_dirs.items():
        entry = actual_dirs[name]
        if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
            raise StateError("device receipt artifact member must be a real directory")
        children = {child.name: child for child in os.scandir(entry.path)}
        if set(children) != {"receipt.json"}:
            raise StateError("device receipt artifact must contain only receipt.json")
        receipt_entry = children["receipt.json"]
        if receipt_entry.is_symlink() or not receipt_entry.is_file(follow_symlinks=False):
            raise StateError("device receipt must be a regular file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(receipt_entry.path, flags)
        except OSError as exc:
            raise StateError("could not open device receipt safely") from exc
        try:
            receipt_stat = os.fstat(fd)
            if not stat.S_ISREG(receipt_stat.st_mode):
                raise StateError("device receipt must remain a regular file")
            if receipt_stat.st_size > MAX_JSON_BYTES:
                raise StateError("device receipt exceeds the JSON size limit")
            chunks: list[bytes] = []
            remaining = MAX_JSON_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(fd)
        if len(raw) > MAX_JSON_BYTES:
            raise StateError("device receipt exceeds the JSON size limit")
        row = strict_json(raw, label="device receipt %s" % reservation["id"])
        validate_result(
            row, reservation=reservation, reservation_sha=reservation_sha,
            batch_path=batch_path, batch_sha=batch_sha, prepared_commit=prepared_commit,
        )
        receipts[reservation["id"]] = canonical_bytes(row)
    return receipts


def finalize_once(
    source: Path, run_id: str, run_attempt: int, prepared_commit: str,
    batch_path: str, batch_sha: str, workflow_sha: str, workflow_ref: str,
) -> int:
    require_actions_checkout()
    require_run(run_id, run_attempt)
    require_github_run_context(run_id, run_attempt)
    require_clean_checkout()
    if head() != head("origin/main"):
        raise StateError("finalizer checkout is not exact current main")
    batch, reservations = validate_prepared_bundle(
        prepared_commit, batch_path, batch_sha, run_id, run_attempt,
        workflow_sha=workflow_sha, workflow_ref=workflow_ref, require_remote=True,
        allow_terminal_history=True,
    )
    current_hashes = protocol_hashes_at_ref("HEAD")
    for reservation, _reservation_sha in reservations:
        expected_hashes = {
            "action_executor.py": reservation["executor_sha256"],
            "device_action_state.py": reservation["protocol_sha256"],
            ".github/workflows/commons-device-executor.yml": reservation["caller_workflow_sha256"],
            ".github/workflows/commons-device-cycle.yml": reservation["cycle_workflow_sha256"],
        }
        if current_hashes != expected_hashes:
            raise StateError("current finalizer protocol differs from the prepared protocol")
    for rel in PROTOCOL_FILES:
        _require_checkout_file_matches("HEAD", rel)
    # A fully landed batch is durably idempotent even after transient artifacts
    # expire.  Validate every current terminal against its reservation before
    # accepting that no-op; partial batches still require the complete artifact
    # set so finalization remains all-or-none.
    landed = 0
    for reservation, reservation_sha in reservations:
        rel = result_rel(reservation["id"])
        path = ROOT / rel
        if not os.path.lexists(path):
            continue
        row, raw = load_canonical_file(path, label=rel)
        validate_result(
            row, reservation=reservation, reservation_sha=reservation_sha,
            batch_path=batch_path, batch_sha=batch_sha,
            prepared_commit=prepared_commit,
        )
        if git_bytes("origin/main", rel) != raw:
            raise StateError("current main does not retain the terminal result")
        landed += 1
    if landed == len(reservations):
        return 0
    # Validate the entire hostile artifact tree before writing one terminal.
    for reservation, _reservation_sha in reservations:
        _validate_action_at_ref(reservation, "HEAD")
    receipts = _artifact_receipts(
        source, batch, reservations, batch_path, batch_sha, prepared_commit,
    )
    to_write: dict[str, bytes] = {}
    for reservation, _reservation_sha in reservations:
        ident = reservation["id"]
        rel = result_rel(ident)
        path = ROOT / rel
        expected = receipts[ident]
        if os.path.lexists(path):
            current = _regular_file_bytes(path, label=rel)
            if current != expected:
                raise StateError("refusing to overwrite divergent terminal result: %s" % ident)
            continue
        if git_path_ever("HEAD", rel):
            raise StateError("terminal result was removed from reachable history: %s" % ident)
        to_write[rel] = expected
    if not to_write:
        return 0
    _ensure_real_directory(RESULTS)
    for rel, raw in to_write.items():
        path = ROOT / rel
        if os.path.lexists(path):
            raise StateError("terminal path appeared during finalization")
        _write_new_bytes(path, raw, label=rel)
    names = sorted(to_write)
    status_names = sorted(
        line[3:] for line in git("status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
        if len(line) > 3
    )
    if status_names != names:
        raise StateError("finalizer produced an unexpected working-tree change set")
    git("add", "--", *names)
    staged = sorted(git("diff", "--cached", "--name-only").stdout.splitlines())
    if staged != names:
        raise StateError("finalizer staged an unexpected path set")
    git("config", "user.name", "commons-device-state")
    git("config", "user.email", "commons-device-state@users.noreply.github.com")
    git("commit", "-m", "record reported Commons device results")
    pushed = git("push", "origin", "HEAD:main", check=False)
    git("fetch", "origin", "main", check=False)
    if pushed.returncode:
        exact = True
        for rel, raw in to_write.items():
            try:
                if git_bytes("origin/main", rel) != raw:
                    exact = False
                    break
            except StateError:
                exact = False
                break
        return 0 if exact else CAS_RETRY
    for rel, raw in to_write.items():
        if git_bytes("origin/main", rel) != raw:
            raise StateError("terminal result failed remote readback")
    return 0


def preflight(output: Path | None) -> int:
    require_full_history()
    value = "true" if action_executor.pending("device") else "false"
    _write_outputs(output, {"has_pending": value})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    p_pre = sub.add_parser("preflight")
    p_pre.add_argument("--github-output", type=Path)

    for name in ("prepare", "execute-one", "execute-batch", "finalize"):
        parser = sub.add_parser(name)
        parser.add_argument("--run-id", required=True)
        parser.add_argument("--run-attempt", required=True, type=int)
        parser.add_argument("--workflow-sha")
        parser.add_argument("--workflow-ref")
        if name != "prepare":
            parser.add_argument("--prepared-commit", required=True)
            parser.add_argument("--batch-path", required=True)
            parser.add_argument("--batch-sha256", required=True)
        if name == "prepare":
            parser.add_argument("--github-output", type=Path)
        elif name == "execute-one":
            parser.add_argument("--id", required=True)
        elif name == "finalize":
            parser.add_argument("--source", required=True, type=Path)

    args = ap.parse_args()
    try:
        if args.command == "preflight":
            return preflight(args.github_output)
        workflow_sha = args.workflow_sha or os.environ.get("GITHUB_WORKFLOW_SHA", "")
        workflow_ref = args.workflow_ref or os.environ.get("GITHUB_WORKFLOW_REF", "")
        common = (args.run_id, args.run_attempt, workflow_sha, workflow_ref)
        if args.command == "prepare":
            return prepare_once(*common, output=args.github_output)
        if args.command == "execute-one":
            return execute_one(
                args.id, args.run_id, args.run_attempt, args.prepared_commit,
                args.batch_path, args.batch_sha256, workflow_sha, workflow_ref,
            )
        if args.command == "execute-batch":
            return execute_batch(
                args.run_id, args.run_attempt, args.prepared_commit,
                args.batch_path, args.batch_sha256, workflow_sha, workflow_ref,
            )
        return finalize_once(
            args.source, args.run_id, args.run_attempt, args.prepared_commit,
            args.batch_path, args.batch_sha256, workflow_sha, workflow_ref,
        )
    except StateError as exc:
        print("DEVICE_STATE_BLOCKED: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
