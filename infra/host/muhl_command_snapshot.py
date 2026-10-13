#!/usr/bin/env python3
"""Freeze and validate Muhlnickel command-ticket snapshots before dispatch."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Mapping, Any
from urllib.parse import quote

MAX_COMMAND_BYTES = 64 * 1024
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
KEY_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
SKIP_NAMES = frozenset({
    "how.txt", "inbox.txt", "readme.txt",
    "template_say.txt", "template_surface.txt",
})
SUPPORTED_KINDS = frozenset({"surface", "say", "dump", "analyzer"})
_FORBIDDEN_SEPARATORS = frozenset({"\u0085", "\u2028", "\u2029", "\ufeff"})


class SnapshotError(ValueError):
    """Raised before dispatch when a command snapshot cannot be frozen safely."""


def _identity(info: os.stat_result) -> tuple[int, int, int]:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def _generation(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        info.st_size,
        getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000)),
    )


def _read_fd_bounded(fd: int) -> bytes:
    chunks: list[bytes] = []
    remaining = MAX_COMMAND_BYTES + 1
    while remaining:
        chunk = os.read(fd, min(16 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) > MAX_COMMAND_BYTES:
        raise SnapshotError(f"command exceeds {MAX_COMMAND_BYTES} byte limit")
    return data


def read_stable_file(path: str | os.PathLike[str]) -> bytes:
    """Freeze one regular local file using one descriptor and two identical reads."""
    path = os.fspath(path)
    try:
        before_path = os.lstat(path)
    except OSError as exc:
        raise SnapshotError(f"{path}: cannot stat command: {exc}") from exc
    if stat.S_ISLNK(before_path.st_mode):
        raise SnapshotError(f"{path}: command path must not be a symlink")
    if not stat.S_ISREG(before_path.st_mode):
        raise SnapshotError(f"{path}: command path must be a regular file")
    if before_path.st_size > MAX_COMMAND_BYTES:
        raise SnapshotError(f"{path}: command exceeds {MAX_COMMAND_BYTES} byte limit")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SnapshotError(f"{path}: cannot open command safely: {exc}") from exc

    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise SnapshotError(f"{path}: opened command must be a regular file")
        if _identity(before_path) != _identity(opened):
            raise SnapshotError(f"{path}: command path changed before open")

        first = _read_fd_bounded(fd)
        first_done = os.fstat(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        second = _read_fd_bounded(fd)
        second_done = os.fstat(fd)

        if first != second:
            raise SnapshotError(f"{path}: command changed while being frozen")
        if not (_generation(opened) == _generation(first_done) == _generation(second_done)):
            raise SnapshotError(f"{path}: command metadata changed while being frozen")
        try:
            after_path = os.lstat(path)
        except OSError as exc:
            raise SnapshotError(f"{path}: command path changed after read: {exc}") from exc
        if _identity(after_path) != _identity(second_done):
            raise SnapshotError(f"{path}: command path changed after read")
        return second
    finally:
        os.close(fd)


def _decode_utf8(data: bytes, source: str) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        raise SnapshotError(f"{source}: UTF-8 BOM is not allowed")
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SnapshotError(f"{source}: command is not strict UTF-8: {exc}") from exc


def _validate_text_grammar(text: str, source: str) -> None:
    for char in text:
        if char == "\n":
            continue
        if char in _FORBIDDEN_SEPARATORS or unicodedata.category(char) == "Cc":
            raise SnapshotError(
                f"{source}: forbidden control/separator U+{ord(char):04X}"
            )


def _reject_duplicate_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise SnapshotError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _reject_nonfinite(token: str) -> None:
    raise SnapshotError(f"non-finite JSON number {token!r} is not allowed")


def _json_loads(text: str, source: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except SnapshotError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SnapshotError(f"{source}: invalid JSON: {exc}") from exc


def _validate_object_strings(value: Any, source: str) -> None:
    if isinstance(value, str):
        for char in value:
            if char == "\n":
                continue
            if char in _FORBIDDEN_SEPARATORS or unicodedata.category(char) == "Cc":
                raise SnapshotError(
                    f"{source}: JSON string contains forbidden control/separator U+{ord(char):04X}"
                )
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_object_strings(key, source)
            _validate_object_strings(item, source)
    elif isinstance(value, list):
        for item in value:
            _validate_object_strings(item, source)


def _parse_text_ticket(text: str, source: str) -> tuple[dict[str, str], bool]:
    _validate_text_grammar(text, source)
    fields: dict[str, str] = {}
    body_lines: list[str] | None = None
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for lineno, raw_line in enumerate(lines, 1):
        if body_lines is not None:
            body_lines.append(raw_line)
            continue
        stripped = raw_line.strip(" ")
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "---":
            body_lines = []
            continue
        if "=" not in raw_line:
            raise SnapshotError(f"{source}: line {lineno}: expected key=value or ---")
        key, value = raw_line.split("=", 1)
        key = key.strip(" ")
        value = value.strip(" ")
        if not KEY_RE.fullmatch(key):
            raise SnapshotError(f"{source}: line {lineno}: invalid key {key!r}")
        if key in fields:
            raise SnapshotError(f"{source}: line {lineno}: duplicate key {key!r}")
        fields[key] = value
    if body_lines is not None:
        fields["body"] = "\n".join(body_lines)
    return fields, body_lines is not None


def _require_string(cmd: Mapping[str, Any], key: str, source: str) -> str:
    value = cmd.get(key)
    if not isinstance(value, str):
        raise SnapshotError(f"{source}: {key} must be a string")
    return value


def validate_command(
    cmd: Mapping[str, Any],
    *,
    source: str,
    filename: str | None = None,
    body_present: bool | None = None,
) -> None:
    for key in ("id", "kind", "approved", "claimed_from", "authenticated_player"):
        if key not in cmd:
            raise SnapshotError(f"{source}: missing required field {key!r}")

    command_id = _require_string(cmd, "id", source)
    if not ID_RE.fullmatch(command_id):
        raise SnapshotError(f"{source}: unsafe command id {command_id!r}")
    if filename is not None and Path(filename).stem != command_id:
        raise SnapshotError(
            f"{source}: filename/id mismatch: {Path(filename).stem!r} != {command_id!r}"
        )

    kind = _require_string(cmd, "kind", source)
    if kind not in SUPPORTED_KINDS:
        raise SnapshotError(f"{source}: unsupported kind {kind!r}")
    if _require_string(cmd, "approved", source) != "YES":
        raise SnapshotError(f"{source}: approved must be exactly YES")
    if not _require_string(cmd, "claimed_from", source):
        raise SnapshotError(f"{source}: claimed_from must be non-empty")
    if _require_string(cmd, "authenticated_player", source) != "UNKNOWN":
        raise SnapshotError(f"{source}: authenticated_player must be exactly UNKNOWN")

    if kind == "surface":
        if body_present is True or cmd.get("body") not in (None, ""):
            raise SnapshotError(f"{source}: surface command must not contain a body")
    elif kind == "say":
        src = _require_string(cmd, "from", source)
        dest = _require_string(cmd, "to", source)
        if not src or not dest:
            raise SnapshotError(f"{source}: say command requires non-empty from/to")
        body = _require_string(cmd, "body", source)
        if not body.strip():
            raise SnapshotError(f"{source}: say command requires non-empty body")
        if src.upper() == "KITE" and dest.upper() == "GROK":
            if cmd.get("owner_ok") != "BRYCE":
                raise SnapshotError(f"{source}: KITE->GROK say requires owner_ok=BRYCE")
    else:
        path = _require_string(cmd, "path", source)
        if not path:
            raise SnapshotError(f"{source}: {kind} command requires non-empty path")


def parse_command_bytes(
    data: bytes,
    *,
    name: str,
    source: str,
) -> list[dict[str, Any]]:
    text = _decode_utf8(data, source)
    low = name.lower()
    if low.endswith(".txt"):
        fields, body_present = _parse_text_ticket(text, source)
        validate_command(fields, source=source, filename=name, body_present=body_present)
        return [dict(fields)]

    if low.endswith(".json"):
        obj = _json_loads(text, source)
        if not isinstance(obj, dict):
            raise SnapshotError(f"{source}: JSON command must be an object")
        _validate_object_strings(obj, source)
        if "id" not in obj:
            obj["id"] = Path(name).stem
        validate_command(obj, source=source, filename=name)
        return [obj]

    if low.endswith(".jsonl"):
        out: list[dict[str, Any]] = []
        for lineno, raw_line in enumerate(text.split("\n"), 1):
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            obj = _json_loads(raw_line, f"{source}:{lineno}")
            if not isinstance(obj, dict):
                raise SnapshotError(f"{source}:{lineno}: JSONL command must be an object")
            _validate_object_strings(obj, f"{source}:{lineno}")
            validate_command(obj, source=f"{source}:{lineno}")
            out.append(obj)
        return out

    raise SnapshotError(f"{source}: unsupported command extension")


def _add_commands(
    out: dict[str, dict[str, Any]],
    commands: Iterable[dict[str, Any]],
    *,
    source_prefix: str,
) -> None:
    for index, command in enumerate(commands, 1):
        command_id = str(command["id"])
        if command_id in out:
            raise SnapshotError(f"duplicate command id {command_id!r}")
        copied = dict(command)
        copied["_source"] = source_prefix if index == 1 else f"{source_prefix}:{index}"
        out[command_id] = copied


def _candidate_name(name: str) -> bool:
    low = name.lower()
    if low in SKIP_NAMES or low.startswith("template"):
        return False
    return low.endswith((".txt", ".json", ".jsonl"))


def load_local_commands(root: str | os.PathLike[str]) -> dict[str, dict[str, Any]]:
    """Freeze a directory name-set, then freeze+validate each listed candidate."""
    root = os.fspath(root)
    if not os.path.isdir(root):
        return {}
    try:
        names = sorted(os.listdir(root))
    except OSError as exc:
        raise SnapshotError(f"{root}: cannot list command directory: {exc}") from exc

    out: dict[str, dict[str, Any]] = {}
    for name in names:
        if not _candidate_name(name):
            continue
        if Path(name).name != name:
            raise SnapshotError(f"{root}: invalid command filename {name!r}")
        path = os.path.join(root, name)
        data = read_stable_file(path)
        digest = hashlib.sha256(data).hexdigest()
        source = f"local:{path}@sha256:{digest}"
        commands = parse_command_bytes(data, name=name, source=source)
        _add_commands(out, commands, source_prefix=source)
    return out


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def _decode_github_blob(obj: Mapping[str, Any], source: str) -> bytes:
    if obj.get("encoding") != "base64":
        raise SnapshotError(f"{source}: GitHub content encoding must be base64")
    size = obj.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise SnapshotError(f"{source}: GitHub size is invalid")
    if size > MAX_COMMAND_BYTES:
        raise SnapshotError(f"{source}: command exceeds {MAX_COMMAND_BYTES} byte limit")
    content = obj.get("content")
    if not isinstance(content, str):
        raise SnapshotError(f"{source}: GitHub content is missing")
    compact = "".join(content.splitlines())
    try:
        data = base64.b64decode(compact, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise SnapshotError(f"{source}: invalid GitHub base64 content") from exc
    if len(data) != size:
        raise SnapshotError(f"{source}: GitHub size/content mismatch")
    if len(data) > MAX_COMMAND_BYTES:
        raise SnapshotError(f"{source}: command exceeds {MAX_COMMAND_BYTES} byte limit")
    return data


def load_github_commands(
    fetch_json: Callable[[str], Any],
) -> tuple[dict[str, dict[str, Any]], str]:
    """Freeze one GitHub main commit, then fetch every candidate from that SHA."""
    commit_obj = fetch_json("commits/main")
    if not isinstance(commit_obj, dict):
        raise SnapshotError("GitHub main commit response is not an object")
    commit_sha = commit_obj.get("sha")
    if not isinstance(commit_sha, str) or not COMMIT_RE.fullmatch(commit_sha):
        raise SnapshotError("GitHub main commit SHA is invalid")

    ref = quote(commit_sha, safe="")
    listing = fetch_json(f"contents/COMMANDS?ref={ref}")
    if not isinstance(listing, list):
        raise SnapshotError("GitHub COMMANDS listing is not an array")

    out: dict[str, dict[str, Any]] = {}
    for item in listing:
        if not isinstance(item, dict):
            raise SnapshotError("GitHub COMMANDS listing contains a non-object")
        name = item.get("name")
        if not isinstance(name, str) or not _candidate_name(name):
            continue
        if item.get("type") != "file":
            raise SnapshotError(f"GitHub candidate {name!r} is not a regular file entry")
        path = item.get("path")
        listed_sha = item.get("sha")
        if not isinstance(path, str) or PurePosixPath(path).parts != ("COMMANDS", name):
            raise SnapshotError(f"GitHub candidate {name!r} has unsafe path")
        if not isinstance(listed_sha, str) or not COMMIT_RE.fullmatch(listed_sha):
            raise SnapshotError(f"GitHub candidate {name!r} has invalid blob SHA")

        encoded_path = quote(path, safe="/")
        obj = fetch_json(f"contents/{encoded_path}?ref={ref}")
        if not isinstance(obj, dict):
            raise SnapshotError(f"github:{path}@{commit_sha}: content response is not an object")
        if obj.get("sha") != listed_sha:
            raise SnapshotError(f"github:{path}@{commit_sha}: listing/content blob SHA mismatch")

        source = f"github:{path}@{commit_sha}:{listed_sha}"
        data = _decode_github_blob(obj, source)
        if git_blob_sha(data) != listed_sha:
            raise SnapshotError(f"{source}: bytes do not match Git blob SHA")
        commands = parse_command_bytes(data, name=name, source=source)
        _add_commands(out, commands, source_prefix=source)

    return out, commit_sha
