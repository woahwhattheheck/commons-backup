"""Exact committed-tree Git source capsules for Commons context packets."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Sequence

HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
ORDINARY_BLOB_MODES = {"100644", "100755"}
TREE_MODE = "40000"
MAX_SOURCE_PATHS = 32
MAX_FILE_BYTES_CEILING = 1_048_576
GIT_SOURCE_KEYS = {
    "commit",
    "tree_sha",
    "observed_main_head",
    "source_commit_matches_observed_main",
    "max_file_bytes",
    "requested_paths",
    "capsules",
}
CAPSULE_BASE_KEYS = {"path", "mode", "blob_sha", "content_sha256", "bytes", "text_included"}
CAPSULE_OMISSION_REASONS = {"FILE_TOO_LARGE", "NON_UTF8", "NON_TEXT_CONTROL", "PACKET_BUDGET"}
GIT_REPOSITORY_REDIRECT_ENV = {
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_WORK_TREE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_INDEX_FILE",
    "GIT_SHALLOW_FILE",
    "GIT_QUARANTINE_PATH",
}
GIT_PATHSPEC_ENV = {
    "GIT_LITERAL_PATHSPECS",
    "GIT_GLOB_PATHSPECS",
    "GIT_NOGLOB_PATHSPECS",
    "GIT_ICASE_PATHSPECS",
}
GIT_CONFIG_INJECTION_ENV = {
    "GIT_CONFIG",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_SYSTEM",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
}


class GitSourceError(ValueError):
    pass


def _git_env() -> dict[str, str]:
    """Return a local, exact-repository, literal-path Git environment."""
    env = os.environ.copy()
    # ``git -C repo`` does not override inherited repository-routing variables such
    # as GIT_DIR. Remove every repository/object-store redirect so the explicit
    # repository argument is the authority boundary. Pathspec and command-line
    # config injection are likewise process-owned rather than caller-controlled.
    for key in GIT_REPOSITORY_REDIRECT_ENV | GIT_PATHSPEC_ENV | GIT_CONFIG_INJECTION_ENV:
        env.pop(key, None)
    for key in list(env):
        if key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
            env.pop(key, None)
    env["GIT_LITERAL_PATHSPECS"] = "1"
    # Exact-source reads are local-only: replacement objects and promisor-remote
    # lazy fetches may not supply bytes outside the selected local object database.
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def _run(repo: Path, args: Sequence[str], *, input_bytes: bytes | None = None) -> bytes:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=_git_env(),
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitSourceError(f"git command timed out after 30 seconds: {' '.join(args)}") from exc
    except OSError as exc:
        raise GitSourceError(f"git unavailable: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise GitSourceError(f"git command failed: {' '.join(args)}: {detail[:240]}")
    return proc.stdout


def _git_object_oid(kind: str, raw: bytes) -> str:
    header = f"{kind} {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _canonical_path(raw: str) -> str:
    if not isinstance(raw, str):
        raise GitSourceError("source path must be a string")
    if not raw or raw != raw.strip() or len(raw) > 512:
        raise GitSourceError("source path must be 1..512 canonical characters")
    if raw.startswith("/") or "\\" in raw or "\x00" in raw or raw.startswith(":"):
        raise GitSourceError(f"unsafe source path: {raw!r}")
    if any(ch in raw for ch in "*?[]"):
        raise GitSourceError(f"pathspec metacharacters are not allowed: {raw!r}")
    pieces = raw.split("/")
    if any(piece in ("", ".", "..") for piece in pieces):
        raise GitSourceError(f"non-canonical source path: {raw!r}")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        raise GitSourceError(f"control character in source path: {raw!r}")
    return raw


def _object_type(repo: Path, oid: str) -> str:
    return _run(repo, ["cat-file", "-t", oid]).decode("ascii", "strict").strip()


def _commit_tree(repo: Path, commit: str) -> str:
    raw = _run(repo, ["cat-file", "commit", commit])
    if _git_object_oid("commit", raw) != commit:
        raise GitSourceError(f"commit object id mismatch for {commit}")
    for line in raw.split(b"\n"):
        if line.startswith(b"tree "):
            try:
                tree = line[5:].decode("ascii", "strict")
            except UnicodeDecodeError as exc:
                raise GitSourceError("commit has malformed tree header") from exc
            if HEX40.fullmatch(tree):
                return tree
            break
    raise GitSourceError("commit has no canonical 40-hex tree")


def _observed_main(repo: Path) -> str | None:
    try:
        raw = _run(repo, ["rev-parse", "--verify", "refs/heads/main"]).decode("ascii", "strict").strip()
    except GitSourceError:
        return None
    return raw if HEX40.fullmatch(raw) else None


def _tree_rows(repo: Path, oid: str) -> dict[bytes, tuple[str, str]]:
    raw = _run(repo, ["cat-file", "tree", oid])
    if _git_object_oid("tree", raw) != oid:
        raise GitSourceError(f"tree object id mismatch for {oid}")

    rows: dict[bytes, tuple[str, str]] = {}
    offset = 0
    while offset < len(raw):
        space = raw.find(b" ", offset)
        nul = raw.find(b"\0", space + 1) if space >= 0 else -1
        if space <= offset or nul <= space + 1 or nul + 21 > len(raw):
            raise GitSourceError(f"malformed tree object {oid}")
        mode_raw = raw[offset:space]
        name = raw[space + 1 : nul]
        object_raw = raw[nul + 1 : nul + 21]
        try:
            mode = mode_raw.decode("ascii", "strict")
        except UnicodeDecodeError as exc:
            raise GitSourceError(f"malformed tree mode in {oid}") from exc
        if not name or b"/" in name or name in rows:
            raise GitSourceError(f"malformed tree name in {oid}")
        rows[name] = (mode, object_raw.hex())
        offset = nul + 21
    return rows


def _tree_entry(
    repo: Path, tree_sha: str, path: str,
    *, tree_cache: dict[str, dict[bytes, tuple[str, str]]] | None = None,
) -> tuple[str, str, str]:
    current_tree = tree_sha
    pieces = path.split("/")
    for index, piece in enumerate(pieces):
        if tree_cache is None:
            rows = _tree_rows(repo, current_tree)
        else:
            if current_tree not in tree_cache:
                tree_cache[current_tree] = _tree_rows(repo, current_tree)
            rows = tree_cache[current_tree]
        item = rows.get(piece.encode("utf-8", "strict"))
        if item is None:
            raise GitSourceError(f"source path is missing from committed tree: {path}")
        mode, oid = item
        if index < len(pieces) - 1:
            if mode != TREE_MODE:
                raise GitSourceError(f"source path crosses a non-tree entry: {path}")
            current_tree = oid
            continue
        if mode not in ORDINARY_BLOB_MODES or not HEX40.fullmatch(oid):
            raise GitSourceError(f"source path is not an ordinary committed blob: {path} mode={mode}")
        return mode, "blob", oid
    raise GitSourceError(f"source path did not resolve: {path}")


def _blob(repo: Path, oid: str, expected_size: int, collect_limit: int) -> tuple[str, bytes | None]:
    try:
        proc = subprocess.Popen(
            ["git", "-C", str(repo), "cat-file", "blob", oid],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_env(),
        )
    except OSError as exc:
        raise GitSourceError(f"git unavailable: {exc}") from exc
    if proc.stdout is None:
        proc.kill()
        raise GitSourceError("git cat-file stdout unavailable")
    content_hasher = hashlib.sha256()
    object_hasher = hashlib.sha1()
    object_hasher.update(f"blob {expected_size}\0".encode("ascii"))
    collected = bytearray() if expected_size <= collect_limit else None
    seen = 0
    while True:
        chunk = proc.stdout.read(65536)
        if not chunk:
            break
        seen += len(chunk)
        content_hasher.update(chunk)
        object_hasher.update(chunk)
        if collected is not None:
            collected.extend(chunk)
    if proc.stdout is not None:
        proc.stdout.close()
    stderr = proc.stderr.read() if proc.stderr is not None else b""
    if proc.stderr is not None:
        proc.stderr.close()
    code = proc.wait()
    if code != 0:
        raise GitSourceError(f"git cat-file blob failed: {stderr.decode('utf-8', 'replace')[:240]}")
    if seen != expected_size:
        raise GitSourceError(f"blob size changed while reading {oid}: expected {expected_size}, got {seen}")
    if object_hasher.hexdigest() != oid:
        raise GitSourceError(f"blob object id mismatch for {oid}")
    return content_hasher.hexdigest(), bytes(collected) if collected is not None else None


def _text_status(raw: bytes | None, *, oversized: bool) -> tuple[str | None, str | None]:
    if oversized:
        return None, "FILE_TOO_LARGE"
    if raw is None:
        raise GitSourceError("blob bytes unavailable below collection limit")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return None, "NON_UTF8"
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        return None, "NON_TEXT_CONTROL"
    return text, None


def collect_git_source(
    repository: str | Path,
    commit: str,
    paths: Sequence[str],
    *,
    max_file_bytes: int = 16_384,
) -> dict[str, Any]:
    """Read only exact committed Git objects for explicitly requested paths."""
    repo = Path(repository)
    if not repo.is_dir():
        raise GitSourceError(f"repository path is not a directory: {repo}")
    if not isinstance(commit, str) or not HEX40.fullmatch(commit):
        raise GitSourceError("source commit must be exact lowercase 40-hex")
    if type(max_file_bytes) is not int or not (1 <= max_file_bytes <= MAX_FILE_BYTES_CEILING):
        raise GitSourceError(f"max_file_bytes must be 1..{MAX_FILE_BYTES_CEILING}")
    if isinstance(paths, (str, bytes)):
        raise GitSourceError("source paths must be a sequence of explicit paths")
    canonical_paths = sorted({_canonical_path(path) for path in paths})
    if not canonical_paths:
        raise GitSourceError("at least one explicit source path is required")
    if len(canonical_paths) > MAX_SOURCE_PATHS:
        raise GitSourceError(f"source path count exceeds {MAX_SOURCE_PATHS}")
    if _object_type(repo, commit) != "commit":
        raise GitSourceError("source commit does not name a commit object")

    tree_sha = _commit_tree(repo, commit)
    observed_main = _observed_main(repo)
    capsules: list[dict[str, Any]] = []
    # Git object IDs bind immutable bytes. Reuse only objects verified during
    # this collection, never an observation from another repository or call.
    tree_cache: dict[str, dict[bytes, tuple[str, str]]] = {}
    blob_cache: dict[str, tuple[int, str, str | None, str | None]] = {}
    for path in canonical_paths:
        mode, _, blob_sha = _tree_entry(repo, tree_sha, path, tree_cache=tree_cache)
        if blob_sha not in blob_cache:
            size_text = _run(repo, ["cat-file", "-s", blob_sha]).decode("ascii", "strict").strip()
            try:
                size = int(size_text)
            except ValueError as exc:
                raise GitSourceError(f"invalid blob size for {path}") from exc
            if size < 0:
                raise GitSourceError(f"negative blob size for {path}")
            content_sha256, raw = _blob(repo, blob_sha, size, max_file_bytes)
            text, reason = _text_status(raw, oversized=size > max_file_bytes)
            blob_cache[blob_sha] = (size, content_sha256, text, reason)
        size, content_sha256, text, reason = blob_cache[blob_sha]
        row: dict[str, Any] = {
            "path": path,
            "mode": mode,
            "blob_sha": blob_sha,
            "content_sha256": content_sha256,
            "bytes": size,
        }
        if text is None:
            row["text"] = None
            row["source_omission_reason"] = reason
        else:
            row["text"] = text
        capsules.append(row)

    return {
        "commit": commit,
        "tree_sha": tree_sha,
        "observed_main_head": observed_main,
        "source_commit_matches_observed_main": None if observed_main is None else observed_main == commit,
        "max_file_bytes": max_file_bytes,
        "requested_paths": canonical_paths,
        "capsules": capsules,
    }


def _validate_packet_capsule(row: Any) -> tuple[bool, str]:
    """Validate exact packet capsule schema before equality/coercion is possible."""
    if type(row) is not dict:
        return False, "git-source-capsule-shape"
    included = row.get("text_included")
    if type(included) is not bool:
        return False, "git-source-inclusion-flag"
    expected_keys = CAPSULE_BASE_KEYS | ({"text"} if included else {"omission_reason"})
    if set(row) != expected_keys:
        return False, "git-source-capsule-shape"
    path = row.get("path")
    try:
        if type(path) is not str or _canonical_path(path) != path:
            return False, "git-source-path"
    except GitSourceError:
        return False, "git-source-path"
    if type(row.get("mode")) is not str or row["mode"] not in ORDINARY_BLOB_MODES:
        return False, "git-source-mode"
    if type(row.get("blob_sha")) is not str or not HEX40.fullmatch(row["blob_sha"]):
        return False, "git-source-blob-sha"
    if type(row.get("content_sha256")) is not str or not HEX64.fullmatch(row["content_sha256"]):
        return False, "git-source-content-sha256"
    if type(row.get("bytes")) is not int or row["bytes"] < 0:
        return False, "git-source-bytes"
    if included:
        if type(row.get("text")) is not str:
            return False, "git-source-text"
    else:
        if type(row.get("omission_reason")) is not str or row["omission_reason"] not in CAPSULE_OMISSION_REASONS:
            return False, "git-source-omission"
    return True, "ok"


def _verified_git_source(bundle: Any, repository: str | Path) -> tuple[dict[str, Any] | None, str]:
    """Return the checked collection for reuse within this verification call."""
    if type(bundle) is not dict or set(bundle) != GIT_SOURCE_KEYS:
        return None, "git-source-shape"
    commit = bundle.get("commit")
    tree_sha = bundle.get("tree_sha")
    observed_main = bundle.get("observed_main_head")
    source_matches_main = bundle.get("source_commit_matches_observed_main")
    requested = bundle.get("requested_paths")
    max_file_bytes = bundle.get("max_file_bytes")
    capsules = bundle.get("capsules")
    if type(commit) is not str or not HEX40.fullmatch(commit):
        return None, "git-source-commit"
    if type(tree_sha) is not str or not HEX40.fullmatch(tree_sha):
        return None, "git-source-tree-sha"
    if observed_main is not None and (type(observed_main) is not str or not HEX40.fullmatch(observed_main)):
        return None, "git-source-observed-main-head"
    if source_matches_main is not None and type(source_matches_main) is not bool:
        return None, "git-source-main-match"
    if type(max_file_bytes) is not int or not (1 <= max_file_bytes <= MAX_FILE_BYTES_CEILING):
        return None, "git-source-max-file-bytes"
    if type(requested) is not list or not all(type(path) is str for path in requested) or type(capsules) is not list:
        return None, "git-source-shape"
    for packet_row in capsules:
        valid, reason = _validate_packet_capsule(packet_row)
        if not valid:
            return None, reason
    try:
        expected = collect_git_source(repository, commit, requested, max_file_bytes=max_file_bytes)
    except (GitSourceError, TypeError):
        return None, "git-source-read"
    for key in ("commit", "tree_sha", "max_file_bytes", "requested_paths"):
        if bundle.get(key) != expected.get(key):
            return None, f"git-source-{key.replace('_', '-')}"
    # observed main is drift metadata, never source authority; it may legitimately move later.
    actual_by_path = {row["path"]: row for row in expected["capsules"]}
    if len(actual_by_path) != len(capsules):
        return None, "git-source-capsule-count"
    for packet_row in capsules:
        path = packet_row["path"]
        actual = actual_by_path.get(path)
        if actual is None:
            return None, "git-source-path"
        for key in ("mode", "blob_sha", "content_sha256", "bytes"):
            if packet_row[key] != actual.get(key):
                return None, f"git-source-{key.replace('_', '-')}"
        if packet_row["text_included"] is True:
            if packet_row["text"] != actual.get("text") or actual.get("text") is None:
                return None, "git-source-text"
        else:
            reason = packet_row["omission_reason"]
            if actual.get("text") is None:
                if reason != actual.get("source_omission_reason"):
                    return None, "git-source-omission"
            elif reason != "PACKET_BUDGET":
                return None, "git-source-omission"
    return expected, "ok"


def verify_git_source(bundle: Any, repository: str | Path) -> tuple[bool, str]:
    """Re-read committed objects and verify packet source metadata/text against them."""
    actual, reason = _verified_git_source(bundle, repository)
    return actual is not None, reason


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def verify_packet_git_source(packet: Any, repository: str | Path) -> tuple[bool, str]:
    """Re-read Git and replay compile-time source admission for a semantic-valid packet."""
    if not isinstance(packet, dict):
        return False, "git-source-packet-shape"
    source = packet.get("git_source")
    if source is None:
        return True, "ok"
    if not isinstance(source, dict):
        return False, "git-source-shape"
    actual, _ = _verified_git_source(source, repository)
    if actual is None:
        return False, "git-source-readback"
    try:
        limits = packet["limits"]
        max_chars = limits["max_chars"]
        omitted_final = packet["omitted"]
        recent_final = packet["recent"]
        resources_final = packet["resources"]
    except (GitSourceError, KeyError, TypeError):
        return False, "git-source-packet-shape"
    if type(max_chars) is not int or max_chars < 0:
        return False, "git-source-packet-shape"
    if not isinstance(omitted_final, dict) or not isinstance(recent_final, list) or not isinstance(resources_final, list):
        return False, "git-source-packet-shape"
    for key in ("claims", "coordination", "recent", "resources", "git_source_text_files", "git_source_text_bytes"):
        if type(omitted_final.get(key)) is not int or omitted_final[key] < 0:
            return False, "git-source-omitted-shape"

    packet_rows = source.get("capsules")
    if not isinstance(packet_rows, list):
        return False, "git-source-shape"
    omitted_rows = [row for row in packet_rows if row["text_included"] is False]
    omitted_files = len(omitted_rows)
    omitted_bytes = sum(row["bytes"] for row in omitted_rows)
    if omitted_final.get("git_source_text_files") != omitted_files:
        return False, "git-source-omitted-files"
    if omitted_final.get("git_source_text_bytes") != omitted_bytes:
        return False, "git-source-omitted-bytes"

    actual_by_path = {row["path"]: row for row in actual["capsules"]}
    # Restore the exact packet boundary used by compile_packet immediately before source
    # text admission: claims/coordination are final, recent/resources are not admitted yet,
    # and every source row is metadata-only. Final included+omitted recovers the later
    # section pool counts without requiring the original input files.
    probe = copy.deepcopy(packet)
    probe.pop("semantic_sha256", None)
    probe["recent"] = []
    probe["resources"] = []
    omitted = dict(probe["omitted"])
    omitted["recent"] = omitted_final["recent"] + len(recent_final)
    omitted["resources"] = omitted_final["resources"] + len(resources_final)
    probe["omitted"] = omitted
    source_probe = probe.get("git_source")
    if not isinstance(source_probe, dict) or not isinstance(source_probe.get("capsules"), list):
        return False, "git-source-shape"
    for row in source_probe["capsules"]:
        if not isinstance(row, dict):
            return False, "git-source-capsule-shape"
        actual_row = actual_by_path.get(row.get("path"))
        if actual_row is None:
            return False, "git-source-path"
        row.pop("text", None)
        row["text_included"] = False
        if actual_row.get("text") is None:
            row["omission_reason"] = actual_row.get("source_omission_reason")
        else:
            row["omission_reason"] = "PACKET_BUDGET"
    omitted["git_source_text_files"] = len(source_probe["capsules"])
    omitted["git_source_text_bytes"] = sum(row["bytes"] for row in source_probe["capsules"])

    def size() -> int:
        sized = copy.deepcopy(probe)
        sized["semantic_sha256"] = "0" * 64
        return len(_canonical(sized))

    by_path = {row["path"]: row for row in source_probe["capsules"]}
    requested = source.get("requested_paths")
    if not isinstance(requested, list):
        return False, "git-source-shape"
    for path in requested:
        actual_row = actual_by_path.get(path)
        row = by_path.get(path)
        if actual_row is None or row is None:
            return False, "git-source-path"
        text = actual_row.get("text")
        if text is None:
            continue
        row["text"] = text
        row["text_included"] = True
        row.pop("omission_reason", None)
        omitted["git_source_text_files"] -= 1
        omitted["git_source_text_bytes"] -= row["bytes"]
        if size() > max_chars:
            row.pop("text", None)
            row["text_included"] = False
            row["omission_reason"] = "PACKET_BUDGET"
            omitted["git_source_text_files"] += 1
            omitted["git_source_text_bytes"] += row["bytes"]

    expected_by_path = {row["path"]: row for row in source_probe["capsules"]}
    for packet_row in packet_rows:
        if not isinstance(packet_row, dict):
            return False, "git-source-capsule-shape"
        expected = expected_by_path.get(packet_row.get("path"))
        if expected is None:
            return False, "git-source-path"
        for key in ("text_included", "omission_reason", "text"):
            if packet_row.get(key) != expected.get(key) or (key in packet_row) != (key in expected):
                return False, "git-source-admission"
    return True, "ok"
