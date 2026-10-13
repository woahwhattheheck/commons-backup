#!/usr/bin/env python3
"""Fail-closed package-vs-checkout freshness gate for TITAN V4 native execution.

This module does not build, mutate, or extract a package. It authenticates an
already-built tar archive, binds the live files to an exact Git commit, derives
the canonical package source map from the exact publisher contract, and compares
every published source-mapped member against that checkout.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tarfile
from typing import Iterable

SCHEMA = "titan.v4.native_freshness.v1"
CORE_PATHS = (
    "main.py",
    "titan_runtime.py",
    "scheduler.py",
    "frozen_selected.py",
    "TITAN-CONFIG.json",
)
CANONICAL_LIVE_DIR = "revenue/kaggriculture/cloud-execution-lab"
PUBLISHER = "build_integrated.py"
SOURCE_MANIFEST = "SOURCE.json"
RELEASE_METADATA = "runtime/integrated-selected/RELEASE.json"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXTRACTED_BYTES = 64 * 1024 * 1024
MAX_CORE_MEMBER_BYTES = 4 * 1024 * 1024
MAX_TAR_MEMBERS = 4096
_HEX = frozenset("0123456789abcdef")


class InvalidEvidence(ValueError):
    """Raised when inputs cannot support a freshness claim."""


def _is_hex(value: str, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(c in _HEX for c in value)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise InvalidEvidence("git binding failed: " + detail.strip()) from exc
    return proc.stdout.strip()


def _assert_no_tracked_deletions(repo_root: Path, expected_commit: str) -> None:
    """Reject fixed-HEAD worktree deletions that could shrink dynamic source enumeration."""
    deleted = _git(
        repo_root,
        "diff",
        "--no-ext-diff",
        "--no-renames",
        "--name-only",
        "--diff-filter=D",
        expected_commit,
        "--",
    )
    if deleted:
        raise InvalidEvidence(
            "tracked file deletion(s) can alter publisher source enumeration"
        )


def _safe_relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise InvalidEvidence("live directory must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise InvalidEvidence("live directory must be normalized and repository-relative")
    return path


def _safe_archive_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise InvalidEvidence("archive member path must be a normalized relative POSIX path")
    raw_parts = value.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise InvalidEvidence(f"unsafe archive member path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise InvalidEvidence(f"unsafe archive member path: {value!r}")
    return value


def _repo_relative_source(live_rel: PurePosixPath, value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise InvalidEvidence("source_path must be a non-empty repository-relative POSIX path")
    raw_parts = value.split("/")
    if any(part in ("", ".") for part in raw_parts):
        raise InvalidEvidence(f"source_path is not normalized: {value!r}")
    if PurePosixPath(value).is_absolute():
        raise InvalidEvidence(f"source_path must be relative: {value!r}")
    parts = list(live_rel.parts)
    for part in raw_parts:
        if part == "..":
            if not parts:
                raise InvalidEvidence(f"source_path escapes repository root: {value!r}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise InvalidEvidence(f"source_path resolves to repository root: {value!r}")
    return PurePosixPath(*parts)


def _no_symlink_ancestry(root: Path, relative: PurePosixPath) -> Path:
    current = root
    if current.is_symlink():
        raise InvalidEvidence("repository root may not be a symlink")
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise InvalidEvidence(f"missing live path: {relative.as_posix()}") from exc
        if stat.S_ISLNK(mode):
            raise InvalidEvidence(f"symlink live path forbidden: {relative.as_posix()}")
    return current


def _read_live_file(repo_root: Path, relative: PurePosixPath) -> bytes:
    path = _no_symlink_ancestry(repo_root, relative)
    try:
        before = path.stat()
    except OSError as exc:
        raise InvalidEvidence(f"cannot stat live file: {relative.as_posix()}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise InvalidEvidence(f"live source member is not a regular file: {relative.as_posix()}")
    if before.st_size > MAX_CORE_MEMBER_BYTES:
        raise InvalidEvidence(f"live source member exceeds size bound: {relative.as_posix()}")
    try:
        data = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise InvalidEvidence(f"cannot read live file: {relative.as_posix()}") from exc
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(data) != after.st_size:
        raise InvalidEvidence(f"live file changed during read: {relative.as_posix()}")
    return data


def _pairs_no_dupes(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InvalidEvidence(f"duplicate JSON object key: {key!r}")
        out[key] = value
    return out


def _reject_constant(value: str):
    raise InvalidEvidence(f"non-finite JSON constant forbidden: {value}")


def _strict_json(raw: bytes, *, label: str):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidEvidence(f"{label} is not UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=_reject_constant,
        )
    except InvalidEvidence:
        raise
    except json.JSONDecodeError as exc:
        raise InvalidEvidence(f"{label} is not valid JSON: {exc}") from exc


def _read_release_metadata(
    repo_root: Path,
    live_rel: PurePosixPath,
    expected_commit: str,
) -> tuple[dict, str]:
    """Read RELEASE exactly once and bind those bytes to the expected commit."""
    release_rel = live_rel / PurePosixPath(RELEASE_METADATA)
    raw = _read_live_file(repo_root, release_rel)
    live_blob = _git_blob(raw)
    tracked_blob = _git(
        repo_root,
        "rev-parse",
        f"{expected_commit}:{release_rel.as_posix()}",
    )
    if not _is_hex(tracked_blob, 40) or tracked_blob != live_blob:
        raise InvalidEvidence(
            f"release metadata is not byte-identical to expected commit: {release_rel.as_posix()}"
        )
    metadata = _strict_json(raw, label=RELEASE_METADATA)
    if type(metadata) is not dict:
        raise InvalidEvidence("RELEASE.json must contain an object")
    return metadata, live_blob


class _ReturnValue(Exception):
    def __init__(self, value):
        super().__init__()
        self.value = value


_RESERVED_NAMES = frozenset({"str", "ROOT", "RUNTIME", "__builtins__"})


def _require_live_path(path: Path, live_root: Path, *, operation: str) -> PurePosixPath:
    try:
        relative = path.relative_to(live_root)
    except ValueError as exc:
        raise InvalidEvidence(
            f"publisher {operation} path escapes canonical live root"
        ) from exc
    pure = PurePosixPath(relative.as_posix())
    if any(part in ("", ".", "..") for part in pure.parts):
        raise InvalidEvidence(
            f"publisher {operation} path is not normalized under canonical live root"
        )
    return pure


def _bind_target(target: ast.AST, value, env: dict) -> None:
    if not isinstance(target, ast.Name):
        raise InvalidEvidence(
            f"publisher interpreter requires simple loop target, got {type(target).__name__}"
        )
    if target.id in _RESERVED_NAMES:
        raise InvalidEvidence(f"publisher may not rebind reserved name: {target.id}")
    env[target.id] = value


def _eval_publisher_expr(node: ast.AST, env: dict, *, live_root: Path):
    """Evaluate the narrow read-only expression grammar used by source_files()."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, bool, type(None))):
            return node.value
        raise InvalidEvidence(
            f"publisher expression contains unsupported constant: {type(node.value).__name__}"
        )

    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise InvalidEvidence(f"publisher expression references unknown name: {node.id}")

    if isinstance(node, (ast.List, ast.Tuple)):
        out = []
        for element in node.elts:
            if isinstance(element, ast.Starred):
                expanded = _eval_publisher_expr(element.value, env, live_root=live_root)
                if not isinstance(expanded, (list, tuple)):
                    raise InvalidEvidence("publisher starred expression must expand a sequence")
                out.extend(expanded)
            else:
                out.append(_eval_publisher_expr(element, env, live_root=live_root))
        return out if isinstance(node, ast.List) else tuple(out)

    if isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            raise InvalidEvidence("publisher dict unpacking is not supported")
        return {
            _eval_publisher_expr(key, env, live_root=live_root):
            _eval_publisher_expr(value, env, live_root=live_root)
            for key, value in zip(node.keys, node.values)
        }

    if isinstance(node, ast.BinOp):
        left = _eval_publisher_expr(node.left, env, live_root=live_root)
        right = _eval_publisher_expr(node.right, env, live_root=live_root)
        if isinstance(node.op, ast.Add) and isinstance(left, str) and isinstance(right, str):
            return left + right
        if isinstance(node.op, ast.Div) and isinstance(left, Path) and isinstance(right, str):
            return left / right
        raise InvalidEvidence(
            f"publisher expression contains unsupported binary operation: {type(node.op).__name__}"
        )

    if isinstance(node, ast.Attribute):
        value = _eval_publisher_expr(node.value, env, live_root=live_root)
        if node.attr == "parts" and isinstance(value, Path):
            return value.parts
        raise InvalidEvidence(f"publisher expression contains unsafe attribute read: {node.attr}")

    if isinstance(node, ast.Call):
        if node.keywords:
            raise InvalidEvidence("publisher calls may not use keyword arguments")
        if isinstance(node.func, ast.Name):
            if node.func.id != "str" or len(node.args) != 1:
                raise InvalidEvidence(f"publisher contains unsafe call: {node.func.id}")
            value = _eval_publisher_expr(node.args[0], env, live_root=live_root)
            if not isinstance(value, (str, Path, PurePosixPath)):
                raise InvalidEvidence("publisher str() argument has unsupported type")
            return str(value)

        if not isinstance(node.func, ast.Attribute):
            raise InvalidEvidence("publisher contains unsupported callable expression")
        receiver = _eval_publisher_expr(node.func.value, env, live_root=live_root)
        method = node.func.attr
        if not isinstance(receiver, Path):
            raise InvalidEvidence(f"publisher method receiver is not a Path: {method}")

        if method == "relative_to" and len(node.args) == 1:
            base = _eval_publisher_expr(node.args[0], env, live_root=live_root)
            if not isinstance(base, Path) or base != live_root:
                raise InvalidEvidence("publisher relative_to() base must be canonical live root")
            return _require_live_path(receiver, live_root, operation="relative_to")

        if method == "rglob" and len(node.args) == 1:
            pattern = _eval_publisher_expr(node.args[0], env, live_root=live_root)
            if pattern != "*":
                raise InvalidEvidence("publisher rglob() pattern must be literal '*'")
            _require_live_path(receiver, live_root, operation="rglob")
            out = []
            for path in receiver.rglob("*"):
                out.append(path)
                if len(out) > MAX_TAR_MEMBERS:
                    raise InvalidEvidence("publisher rglob() result exceeds accepted bound")
            return out

        if method == "is_file" and not node.args:
            _require_live_path(receiver, live_root, operation="is_file")
            return receiver.is_file()

        raise InvalidEvidence(f"publisher contains unsafe Path method call: {method}")

    if isinstance(node, ast.Compare):
        left = _eval_publisher_expr(node.left, env, live_root=live_root)
        values = [left]
        values.extend(
            _eval_publisher_expr(comp, env, live_root=live_root)
            for comp in node.comparators
        )
        for index, op in enumerate(node.ops):
            a, b = values[index], values[index + 1]
            if isinstance(op, ast.In):
                ok = a in b
            elif isinstance(op, ast.NotIn):
                ok = a not in b
            elif isinstance(op, ast.Eq):
                ok = a == b
            elif isinstance(op, ast.NotEq):
                ok = a != b
            else:
                raise InvalidEvidence(
                    f"publisher comparison is unsupported: {type(op).__name__}"
                )
            if not ok:
                return False
        return True

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(
                bool(_eval_publisher_expr(value, env, live_root=live_root))
                for value in node.values
            )
        if isinstance(node.op, ast.Or):
            return any(
                bool(_eval_publisher_expr(value, env, live_root=live_root))
                for value in node.values
            )
        raise InvalidEvidence(f"publisher bool operation is unsupported: {type(node.op).__name__}")

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not bool(_eval_publisher_expr(node.operand, env, live_root=live_root))

    if isinstance(node, (ast.ListComp, ast.DictComp)):
        if len(node.generators) != 1 or node.generators[0].is_async:
            raise InvalidEvidence("publisher comprehensions require one synchronous generator")
        generator = node.generators[0]
        iterable = _eval_publisher_expr(generator.iter, env, live_root=live_root)
        if not isinstance(iterable, (list, tuple)):
            raise InvalidEvidence("publisher comprehension iterable must be a finite sequence")
        list_out = []
        dict_out = {}
        for item in iterable:
            local = dict(env)
            _bind_target(generator.target, item, local)
            if not all(
                bool(_eval_publisher_expr(cond, local, live_root=live_root))
                for cond in generator.ifs
            ):
                continue
            if isinstance(node, ast.ListComp):
                list_out.append(_eval_publisher_expr(node.elt, local, live_root=live_root))
            else:
                key = _eval_publisher_expr(node.key, local, live_root=live_root)
                value = _eval_publisher_expr(node.value, local, live_root=live_root)
                if key in dict_out:
                    raise InvalidEvidence(f"publisher comprehension duplicates key: {key!r}")
                dict_out[key] = value
        return list_out if isinstance(node, ast.ListComp) else dict_out

    raise InvalidEvidence(
        f"publisher expression syntax is unsupported: {type(node).__name__}"
    )


def _execute_publisher_statements(
    statements: list[ast.stmt],
    env: dict,
    *,
    live_root: Path,
) -> None:
    for statement in statements:
        if isinstance(statement, ast.Expr):
            if isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
                continue
            raise InvalidEvidence("publisher source_files() may not execute expression statements")

        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1:
                raise InvalidEvidence("publisher assignments must have one target")
            value = _eval_publisher_expr(statement.value, env, live_root=live_root)
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                if target.id in _RESERVED_NAMES:
                    raise InvalidEvidence(f"publisher may not rebind reserved name: {target.id}")
                env[target.id] = value
                continue
            if isinstance(target, ast.Subscript):
                if not isinstance(target.value, ast.Name) or target.value.id != "mapping":
                    raise InvalidEvidence("publisher may subscript-assign only to mapping")
                mapping = env.get("mapping")
                if type(mapping) is not dict:
                    raise InvalidEvidence("publisher mapping target is not a dict")
                key = _eval_publisher_expr(target.slice, env, live_root=live_root)
                if not isinstance(key, str):
                    raise InvalidEvidence("publisher mapping key must be text")
                mapping[key] = value
                continue
            raise InvalidEvidence(
                f"publisher assignment target is unsupported: {type(target).__name__}"
            )

        if isinstance(statement, ast.For):
            if statement.orelse:
                raise InvalidEvidence("publisher for-else is not supported")
            iterable = _eval_publisher_expr(statement.iter, env, live_root=live_root)
            if not isinstance(iterable, (list, tuple)):
                raise InvalidEvidence("publisher for-loop iterable must be a finite sequence")
            for item in iterable:
                _bind_target(statement.target, item, env)
                _execute_publisher_statements(statement.body, env, live_root=live_root)
            continue

        if isinstance(statement, ast.If):
            branch = statement.body if bool(
                _eval_publisher_expr(statement.test, env, live_root=live_root)
            ) else statement.orelse
            _execute_publisher_statements(branch, env, live_root=live_root)
            continue

        if isinstance(statement, ast.Return):
            raise _ReturnValue(
                _eval_publisher_expr(statement.value, env, live_root=live_root)
            )

        raise InvalidEvidence(
            f"publisher statement syntax is unsupported: {type(statement).__name__}"
        )


def _publisher_source_map(
    repo_root: Path,
    live_rel: PurePosixPath,
    expected_commit: str,
) -> dict[str, str]:
    """Structurally interpret exact tracked source_files() without executing publisher code."""
    publisher_rel = live_rel / PUBLISHER
    source = _read_live_file(repo_root, publisher_rel)
    live_blob = _git_blob(source)
    tracked_blob = _git(
        repo_root,
        "rev-parse",
        f"{expected_commit}:{publisher_rel.as_posix()}",
    )
    if not _is_hex(tracked_blob, 40) or tracked_blob != live_blob:
        raise InvalidEvidence(
            f"publisher is not byte-identical to expected commit: {publisher_rel.as_posix()}"
        )
    try:
        tree = ast.parse(source, filename=publisher_rel.as_posix())
    except SyntaxError as exc:
        raise InvalidEvidence(f"publisher source does not parse: {exc}") from exc

    runtime_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "RUNTIME"
    ]
    source_nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "source_files"
    ]
    if (
        len(runtime_nodes) != 1
        or len(source_nodes) != 1
        or isinstance(source_nodes[0], ast.AsyncFunctionDef)
    ):
        raise InvalidEvidence(
            "publisher must expose one top-level RUNTIME assignment and source_files()"
        )
    source_node = source_nodes[0]
    if source_node.decorator_list:
        raise InvalidEvidence("publisher source_files() must not be decorated")
    args = source_node.args
    if (
        args.posonlyargs
        or args.args
        or args.kwonlyargs
        or args.vararg is not None
        or args.kwarg is not None
    ):
        raise InvalidEvidence("publisher source_files() must take no arguments")

    live_root = repo_root / Path(*live_rel.parts)
    runtime = _eval_publisher_expr(runtime_nodes[0].value, {}, live_root=live_root)
    if not isinstance(runtime, list) or not all(isinstance(value, str) for value in runtime):
        raise InvalidEvidence("publisher RUNTIME must structurally resolve to a text list")

    env = {"ROOT": live_root, "RUNTIME": runtime}
    try:
        _execute_publisher_statements(source_node.body, env, live_root=live_root)
    except _ReturnValue as returned:
        mapping = returned.value
    else:
        raise InvalidEvidence("publisher source_files() did not return a value")

    if type(mapping) is not dict or not mapping:
        raise InvalidEvidence("publisher source_files() must return a non-empty object")

    normalized: dict[str, str] = {}
    for member, source_path in mapping.items():
        member = _safe_archive_path(member)
        if member == SOURCE_MANIFEST:
            raise InvalidEvidence("publisher source map may not claim SOURCE.json")
        if not isinstance(source_path, str):
            raise InvalidEvidence(f"publisher source_path for {member!r} must be text")
        _repo_relative_source(live_rel, source_path)
        if member in normalized:
            raise InvalidEvidence(f"publisher source map duplicates member: {member}")
        normalized[member] = source_path
    missing = [name for name in CORE_PATHS if name not in normalized]
    if missing:
        raise InvalidEvidence("publisher source map missing core member(s): " + ", ".join(missing))
    return normalized


def _read_archive_core(
    archive: Path,
    expected_sha256: str,
) -> tuple[str, dict[str, bytes], dict[str, str], dict]:
    if not _is_hex(expected_sha256, 64):
        raise InvalidEvidence("expected archive sha256 must be lowercase 64-hex")
    if archive.is_symlink():
        raise InvalidEvidence("archive path may not be a symlink")
    try:
        st = archive.stat()
    except OSError as exc:
        raise InvalidEvidence("archive is missing or unreadable") from exc
    if not stat.S_ISREG(st.st_mode):
        raise InvalidEvidence("archive must be a regular file")
    if st.st_size <= 0 or st.st_size > MAX_ARCHIVE_BYTES:
        raise InvalidEvidence("archive size is outside the accepted bound")
    try:
        raw = archive.read_bytes()
    except OSError as exc:
        raise InvalidEvidence("archive read failed") from exc
    actual_sha256 = _sha256(raw)
    if actual_sha256 != expected_sha256:
        raise InvalidEvidence("archive sha256 does not match the authenticated digest")

    found: dict[str, bytes] = {}
    total_extracted = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tf:
            for index, member in enumerate(tf, start=1):
                if index > MAX_TAR_MEMBERS:
                    raise InvalidEvidence("archive member count exceeds accepted bound")
                name = _safe_archive_path(member.name)
                if name in found:
                    raise InvalidEvidence(f"duplicate archive member: {name}")
                if not member.isfile():
                    raise InvalidEvidence(f"archive member is not a regular file: {name}")
                if member.size < 0 or member.size > MAX_CORE_MEMBER_BYTES:
                    raise InvalidEvidence(f"archive member exceeds size bound: {name}")
                total_extracted += member.size
                if total_extracted > MAX_EXTRACTED_BYTES:
                    raise InvalidEvidence("archive uncompressed size exceeds accepted bound")
                stream = tf.extractfile(member)
                if stream is None:
                    raise InvalidEvidence(f"archive member is unreadable: {name}")
                data = stream.read(MAX_CORE_MEMBER_BYTES + 1)
                if len(data) != member.size or len(data) > MAX_CORE_MEMBER_BYTES:
                    raise InvalidEvidence(f"archive member size mismatch: {name}")
                found[name] = data
    except InvalidEvidence:
        raise
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise InvalidEvidence("archive is not a readable tar package") from exc

    source_raw = found.get(SOURCE_MANIFEST)
    if source_raw is None:
        raise InvalidEvidence("archive missing SOURCE.json")
    manifest = _strict_json(source_raw, label=SOURCE_MANIFEST)
    if type(manifest) is not dict:
        raise InvalidEvidence("SOURCE.json must contain an object")
    runtime = manifest.get("runtime")
    if type(runtime) is not dict or not runtime:
        raise InvalidEvidence("SOURCE.json runtime must be a non-empty object")

    source_map: dict[str, str] = {}
    required_row_keys = {"source_path", "sha256", "bytes"}
    for name, row in runtime.items():
        name = _safe_archive_path(name)
        if name == SOURCE_MANIFEST:
            raise InvalidEvidence("SOURCE.json runtime may not claim SOURCE.json")
        if type(row) is not dict:
            raise InvalidEvidence(f"SOURCE.json runtime row for {name!r} must be an object")
        if set(row) != required_row_keys:
            raise InvalidEvidence(
                f"SOURCE.json runtime row for {name!r} must contain exactly source_path, sha256, bytes"
            )
        source_path = row.get("source_path")
        expected_member_sha = row.get("sha256")
        expected_member_bytes = row.get("bytes")
        if not isinstance(source_path, str) or not source_path:
            raise InvalidEvidence(f"SOURCE.json runtime row for {name!r} lacks source_path")
        if not _is_hex(expected_member_sha, 64):
            raise InvalidEvidence(f"SOURCE.json runtime row for {name!r} has invalid sha256")
        if type(expected_member_bytes) is not int or expected_member_bytes < 0:
            raise InvalidEvidence(f"SOURCE.json runtime row for {name!r} has invalid bytes")
        if expected_member_bytes > MAX_CORE_MEMBER_BYTES:
            raise InvalidEvidence(f"SOURCE.json runtime row for {name!r} exceeds size bound")
        data = found.get(name)
        if data is None:
            raise InvalidEvidence(f"archive missing source-mapped member: {name}")
        if len(data) != expected_member_bytes or _sha256(data) != expected_member_sha:
            raise InvalidEvidence(f"archive member disagrees with SOURCE.json: {name}")
        source_map[name] = source_path

    missing = [name for name in CORE_PATHS if name not in source_map]
    if missing:
        raise InvalidEvidence("SOURCE.json missing core member(s): " + ", ".join(missing))
    expected_members = set(source_map) | {SOURCE_MANIFEST}
    actual_members = set(found)
    if actual_members != expected_members:
        undeclared = sorted(actual_members - expected_members)
        missing_mapped = sorted(expected_members - actual_members)
        detail = []
        if undeclared:
            detail.append("undeclared=" + ",".join(undeclared))
        if missing_mapped:
            detail.append("missing=" + ",".join(missing_mapped))
        raise InvalidEvidence("archive member set disagrees with SOURCE.json: " + "; ".join(detail))
    return actual_sha256, {name: found[name] for name in source_map}, source_map, manifest


def verify_freshness(
    *,
    repo_root: Path,
    live_dir: str,
    archive: Path,
    expected_archive_sha256: str,
    expected_commit: str,
) -> dict:
    """Return deterministic CURRENT/STALE/INVALID evidence for one package."""
    base = {
        "schema": SCHEMA,
        "verdict": "INVALID",
        "expected_commit": expected_commit,
        "expected_archive_sha256": expected_archive_sha256,
        "coverage": "canonical_publisher_source_map",
        "core_paths": list(CORE_PATHS),
        "files": [],
        "stale_paths": [],
        "problems": [],
    }
    try:
        repo_root = Path(repo_root)
        archive = Path(archive)
        if repo_root.is_symlink() or not repo_root.is_dir():
            raise InvalidEvidence("repo root must be an existing non-symlink directory")
        if not _is_hex(expected_commit, 40):
            raise InvalidEvidence("expected commit must be lowercase 40-hex")
        if live_dir != CANONICAL_LIVE_DIR:
            raise InvalidEvidence(
                f"live directory must be canonical: {CANONICAL_LIVE_DIR}"
            )
        live_rel = _safe_relative_path(live_dir)
        head = _git(repo_root, "rev-parse", "HEAD")
        if head != expected_commit:
            raise InvalidEvidence(f"checkout HEAD drift: expected {expected_commit}, got {head}")
        base["commit"] = head

        _assert_no_tracked_deletions(repo_root, expected_commit)
        publisher_map = _publisher_source_map(repo_root, live_rel, expected_commit)
        release_metadata, release_blob = _read_release_metadata(
            repo_root, live_rel, expected_commit
        )
        actual_archive_sha256, package, source_map, source_manifest = _read_archive_core(
            archive, expected_archive_sha256
        )
        base["archive_sha256"] = actual_archive_sha256
        if source_map != publisher_map:
            package_only = sorted(set(source_map) - set(publisher_map))
            publisher_only = sorted(set(publisher_map) - set(source_map))
            remapped = sorted(
                name
                for name in set(source_map) & set(publisher_map)
                if source_map[name] != publisher_map[name]
            )
            detail = []
            if package_only:
                detail.append("package_only=" + ",".join(package_only))
            if publisher_only:
                detail.append("publisher_only=" + ",".join(publisher_only))
            if remapped:
                detail.append("remapped=" + ",".join(remapped))
            raise InvalidEvidence(
                "SOURCE.json runtime does not match canonical publisher source map"
                + (": " + "; ".join(detail) if detail else "")
            )

        expected_source_metadata = dict(release_metadata)
        expected_source_metadata.pop("runtime", None)
        expected_source_metadata.update(
            entrypoint="main.py::agent",
            config="TITAN-CONFIG.json",
            default=_strict_json(
                package["TITAN-CONFIG.json"],
                label="packaged TITAN-CONFIG.json",
            ),
        )
        actual_source_metadata = dict(source_manifest)
        actual_source_metadata.pop("runtime", None)
        if actual_source_metadata != expected_source_metadata:
            raise InvalidEvidence(
                "SOURCE.json non-runtime metadata does not match authenticated RELEASE metadata"
            )

        stale: list[str] = []
        records = []
        live_cache: dict[str, tuple[bytes, str, str]] = {}
        for name in sorted(source_map):
            repo_rel = _repo_relative_source(live_rel, source_map[name])
            repo_key = repo_rel.as_posix()
            cached = live_cache.get(repo_key)
            if cached is None:
                live = _read_live_file(repo_root, repo_rel)
                live_blob = _git_blob(live)
                tracked_blob = _git(
                    repo_root,
                    "rev-parse",
                    f"{expected_commit}:{repo_key}",
                )
                if not _is_hex(tracked_blob, 40) or tracked_blob != live_blob:
                    raise InvalidEvidence(
                        f"live file is not byte-identical to expected commit: {repo_key}"
                    )
                live_cache[repo_key] = (live, live_blob, tracked_blob)
            else:
                live, live_blob, tracked_blob = cached
            packed = package[name]
            package_blob = _git_blob(packed)
            same = live == packed
            if not same:
                stale.append(name)
            records.append(
                {
                    "path": name,
                    "source_path": source_map[name],
                    "same": same,
                    "live": {
                        "bytes": len(live),
                        "git_blob": live_blob,
                        "sha256": _sha256(live),
                    },
                    "package": {
                        "bytes": len(packed),
                        "git_blob": package_blob,
                        "sha256": _sha256(packed),
                    },
                }
            )

        _assert_no_tracked_deletions(repo_root, expected_commit)
        final_publisher_map = _publisher_source_map(repo_root, live_rel, expected_commit)
        if final_publisher_map != publisher_map:
            raise InvalidEvidence("canonical publisher source map changed during verification")
        for repo_key, (_, _, tracked_blob) in live_cache.items():
            live_final = _read_live_file(repo_root, PurePosixPath(repo_key))
            if _git_blob(live_final) != tracked_blob:
                raise InvalidEvidence(f"live file changed during verification: {repo_key}")

        final_release_metadata, final_release_blob = _read_release_metadata(
            repo_root, live_rel, expected_commit
        )
        if final_release_blob != release_blob or final_release_metadata != release_metadata:
            raise InvalidEvidence("release metadata changed during verification")

        final_head = _git(repo_root, "rev-parse", "HEAD")
        if final_head != expected_commit:
            raise InvalidEvidence(
                f"checkout HEAD changed during verification: expected {expected_commit}, got {final_head}"
            )

        base["publisher_members"] = len(source_map)
        base["files"] = records
        base["stale_paths"] = stale
        base["verdict"] = "STALE" if stale else "CURRENT"
        return base
    except InvalidEvidence as exc:
        base["problems"] = [str(exc)]
        return base


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", required=True, type=Path)
    p.add_argument(
        "--live-dir",
        default=CANONICAL_LIVE_DIR,
        help="repository-relative directory containing the live production core",
    )
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--expected-archive-sha256", required=True)
    p.add_argument("--expected-commit", required=True)
    return p


def main(argv: Iterable[str] | None = None) -> int:
    ns = _parser().parse_args(argv)
    report = verify_freshness(
        repo_root=ns.repo_root,
        live_dir=ns.live_dir,
        archive=ns.archive,
        expected_archive_sha256=ns.expected_archive_sha256,
        expected_commit=ns.expected_commit,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return {"CURRENT": 0, "STALE": 1, "INVALID": 2}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
