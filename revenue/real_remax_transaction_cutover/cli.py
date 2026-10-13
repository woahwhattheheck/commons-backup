from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Any

from .engine import compile_cutover, verify_report
from .schema import CutoverError, canonical_bytes

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 200_000


class DuplicateKeyError(ValueError):
    pass


class _PublicationError(CutoverError, OSError):
    """Filesystem publication failure normalized into the CLI contract."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _nonfinite(token: str) -> None:
    raise ValueError(f"non-finite number is forbidden: {token}")


def _check_json_shape(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise CutoverError(f"JSON exceeds {MAX_JSON_NODES} nodes")
        if depth > MAX_JSON_DEPTH:
            raise CutoverError(f"JSON exceeds maximum depth {MAX_JSON_DEPTH}")
        if type(current) is dict:
            stack.extend((child, depth + 1) for child in current.values())
        elif type(current) is list:
            stack.extend((child, depth + 1) for child in current)


def load_strict_json(path: str) -> Any:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CutoverError(f"cannot open input {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise CutoverError(f"input is not a regular file: {path}")
        if before.st_size > MAX_INPUT_BYTES:
            raise CutoverError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        data = bytearray()
        while True:
            chunk = os.read(fd, min(1 << 20, MAX_INPUT_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_INPUT_BYTES:
                raise CutoverError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        after = os.fstat(fd)
        fingerprint_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_mode)
        fingerprint_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_mode)
        if fingerprint_before != fingerprint_after:
            raise CutoverError(f"input changed while being read: {path}")
    finally:
        os.close(fd)
    try:
        text = bytes(data).decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKeyError, ValueError, RecursionError) as exc:
        raise CutoverError(f"invalid strict JSON in {path}: {exc}") from exc
    _check_json_shape(value)
    if canonical_bytes(value) != bytes(data):
        raise CutoverError(f"input is not canonical JSON: {path}")
    return value


def _same_file_generation(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _assert_visible_output_generation(
    path: str,
    *,
    fd: int,
    expected_size: int,
    parent: Path,
    parent_fd: int | None,
    leaf: str,
) -> None:
    owned = os.fstat(fd)
    if not stat.S_ISREG(owned.st_mode) or owned.st_size != expected_size:
        raise CutoverError(f"owned output generation changed before publication: {path}")
    try:
        if parent_fd is not None:
            visible = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            retained_parent = os.fstat(parent_fd)
            visible_parent = os.stat(parent, follow_symlinks=True)
            if not _same_file_generation(retained_parent, visible_parent):
                raise CutoverError(f"output parent generation changed before publication: {path}")
        else:
            visible = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise CutoverError(f"output path disappeared before publication: {path}: {exc}") from exc
    if not stat.S_ISREG(visible.st_mode) or not _same_file_generation(owned, visible):
        raise CutoverError(f"visible output generation changed before publication: {path}")


def write_exclusive(path: str, value: Any) -> None:
    data = canonical_bytes(value)
    output = Path(path)
    parent = output.parent
    leaf = output.name
    if not leaf or leaf in {".", ".."}:
        raise CutoverError(f"invalid output leaf: {path}")
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _PublicationError(f"cannot prepare output parent {parent}: {exc}") from exc
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    use_dir_fd = (
        hasattr(os, "supports_dir_fd")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
    )
    parent_fd: int | None = None
    if use_dir_fd:
        parent_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            parent_flags |= os.O_DIRECTORY
        try:
            parent_fd = os.open(parent, parent_flags)
        except OSError as exc:
            raise CutoverError(f"cannot retain output parent {parent}: {exc}") from exc

    try:
        try:
            if parent_fd is not None:
                fd = os.open(leaf, flags, 0o600, dir_fd=parent_fd)
            else:
                fd = os.open(path, flags, 0o600)
        except OSError as exc:
            raise CutoverError(f"refusing non-exclusive output {path}: {exc}") from exc
        try:
            view = memoryview(data)
            while view:
                n = os.write(fd, view)
                if n <= 0:
                    raise CutoverError(f"short write for {path}")
                view = view[n:]
            os.fsync(fd)
            if parent_fd is not None:
                try:
                    os.fsync(parent_fd)
                except OSError:
                    pass
            _assert_visible_output_generation(
                path,
                fd=fd,
                expected_size=len(data),
                parent=parent,
                parent_fd=parent_fd,
                leaf=leaf,
            )
        except Exception as exc:
            # Never pathname-unlink on rollback: another actor could have swapped the
            # visible name after this descriptor was reserved. Fail visibly by
            # truncating only the inode we still own through the retained fd.
            try:
                os.ftruncate(fd, 0)
                os.fsync(fd)
            except OSError:
                pass
            finally:
                os.close(fd)
            if isinstance(exc, CutoverError):
                raise
            if isinstance(exc, OSError):
                raise _PublicationError(f"cannot publish output {path}: {exc}") from exc
            raise
        else:
            os.close(fd)
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile or verify Real/REMAX cutover evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--source", required=True)
        p.add_argument("--target", required=True)
        p.add_argument("--identity-map", required=True)
        p.add_argument("--policy", required=True)
        if name == "compile":
            p.add_argument("--output", required=True)
        else:
            p.add_argument("--report", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        source = load_strict_json(args.source)
        target = load_strict_json(args.target)
        identity_map = load_strict_json(args.identity_map)
        policy = load_strict_json(args.policy)
        if args.command == "compile":
            report = compile_cutover(source, target, identity_map, policy)
            write_exclusive(args.output, report)
            print(report["decision"])
            return 0 if report["decision"] == "PARITY" else 2
        report = load_strict_json(args.report)
        ok = verify_report(source, target, identity_map, policy, report)
        print("VERIFIED" if ok else "INVALID")
        return 0 if ok else 3
    except CutoverError as exc:
        print(f"ERROR: {exc}")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
