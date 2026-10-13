"""CLI for exact-head ship fence with descriptor-pinned output custody."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import sys
from typing import Any, Callable

from .fence import (
    EvidenceError,
    MAX_JSON_BYTES,
    canonical_json_bytes,
    compile_current,
    parse_json_bytes,
    render_markdown,
    verify_current,
)


def _fd_flags(*, directory: bool = False, write: bool = False) -> int:
    flags = os.O_WRONLY if write else os.O_RDONLY
    if directory:
        if not hasattr(os, "O_DIRECTORY"):
            raise EvidenceError("directory-descriptor custody unsupported")
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _same_generation(a: os.stat_result, b: os.stat_result) -> bool:
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _read_fd(fd: int, label: str, max_bytes: int) -> bytes:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        raise EvidenceError(f"not a regular file: {label}")
    if st.st_size > max_bytes:
        raise EvidenceError(f"file too large: {label}")
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    while remaining:
        part = os.read(fd, min(65536, remaining))
        if not part:
            break
        chunks.append(part)
        remaining -= len(part)
    data = b"".join(chunks)
    if len(data) > max_bytes:
        raise EvidenceError(f"file too large: {label}")
    st2 = os.fstat(fd)
    if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (
        st2.st_dev, st2.st_ino, st2.st_size, st2.st_mtime_ns
    ):
        raise EvidenceError(f"file changed while reading: {label}")
    return data


def _read_regular(path: Path, max_bytes: int = MAX_JSON_BYTES) -> bytes:
    fd = os.open(path, _fd_flags())
    try:
        return _read_fd(fd, str(path), max_bytes)
    finally:
        os.close(fd)


def _read_at(dir_fd: int, name: str, max_bytes: int = MAX_JSON_BYTES) -> bytes:
    fd = os.open(name, _fd_flags(), dir_fd=dir_fd)
    try:
        return _read_fd(fd, name, max_bytes)
    finally:
        os.close(fd)


def _open_directory(path: Path) -> int:
    fd = os.open(path, _fd_flags(directory=True))
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise EvidenceError(f"not a directory: {path}")
    return fd


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]
    os.fsync(fd)


def _create_member(dir_fd: int, name: str, data: bytes) -> tuple[int, os.stat_result]:
    flags = _fd_flags(write=True) | os.O_CREAT | os.O_EXCL
    fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
    owned = os.fstat(fd)
    try:
        _write_all(fd, data)
        return fd, owned
    except BaseException:
        try:
            if _member_is_owned(dir_fd, name, owned):
                os.unlink(name, dir_fd=dir_fd)
        except OSError:
            pass
        os.close(fd)
        raise


def _member_is_owned(dir_fd: int, name: str, owned: os.stat_result) -> bool:
    try:
        visible = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return stat.S_ISREG(visible.st_mode) and _same_generation(visible, owned)


def _directory_is_visible(parent_fd: int, leaf: str, full_path: Path, owned: os.stat_result) -> bool:
    try:
        relative = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        visible = os.stat(full_path, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return (
        stat.S_ISDIR(relative.st_mode)
        and stat.S_ISDIR(visible.st_mode)
        and _same_generation(relative, owned)
        and _same_generation(visible, owned)
    )


def _write_bundle(
    output_dir: Path,
    report: dict[str, Any],
    _after_first: Callable[[Path], None] | None = None,
) -> None:
    if output_dir.name in ("", ".", ".."):
        raise EvidenceError("output directory must name a new child")
    parent = output_dir.parent if str(output_dir.parent) else Path(".")
    parent_fd = _open_directory(parent)
    dir_fd = -1
    owned_members: list[tuple[str, int, os.stat_result]] = []
    owned_dir: os.stat_result | None = None
    try:
        os.mkdir(output_dir.name, 0o700, dir_fd=parent_fd)
        owned_dir = os.stat(output_dir.name, dir_fd=parent_fd, follow_symlinks=False)
        os.fsync(parent_fd)
        dir_fd = os.open(output_dir.name, _fd_flags(directory=True), dir_fd=parent_fd)
        if not _same_generation(os.fstat(dir_fd), owned_dir):
            raise EvidenceError("output directory generation changed during open")

        json_fd, json_st = _create_member(
            dir_fd, "report.json", canonical_json_bytes(report) + b"\n"
        )
        owned_members.append(("report.json", json_fd, json_st))
        if _after_first is not None:
            _after_first(output_dir)
        md_fd, md_st = _create_member(
            dir_fd, "report.md", render_markdown(report).encode("utf-8")
        )
        owned_members.append(("report.md", md_fd, md_st))

        os.fsync(dir_fd)
        for name, _, st_owned in owned_members:
            if not _member_is_owned(dir_fd, name, st_owned):
                raise EvidenceError(f"output member generation changed: {name}")
        if not _directory_is_visible(parent_fd, output_dir.name, output_dir, owned_dir):
            raise EvidenceError("output directory generation changed")
        os.fsync(parent_fd)
    except BaseException:
        if dir_fd >= 0:
            for name, _, st_owned in reversed(owned_members):
                try:
                    if _member_is_owned(dir_fd, name, st_owned):
                        os.unlink(name, dir_fd=dir_fd)
                except OSError:
                    pass
            try:
                os.fsync(dir_fd)
            except OSError:
                pass
        if owned_dir is not None:
            try:
                relative = os.stat(output_dir.name, dir_fd=parent_fd, follow_symlinks=False)
                if _same_generation(relative, owned_dir):
                    os.rmdir(output_dir.name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
            except OSError:
                pass
        raise
    finally:
        for _, fd, _ in owned_members:
            try:
                os.close(fd)
            except OSError:
                pass
        if dir_fd >= 0:
            os.close(dir_fd)
        os.close(parent_fd)


def _generation_token(st: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size,
        st.st_mtime_ns, st.st_ctime_ns,
    )


def _read_at_generation(
    dir_fd: int, name: str, max_bytes: int = MAX_JSON_BYTES
) -> tuple[bytes, tuple[int, int, int, int, int, int, int]]:
    fd = os.open(name, _fd_flags(), dir_fd=dir_fd)
    try:
        data = _read_fd(fd, name, max_bytes)
        owned = _generation_token(os.fstat(fd))
    finally:
        os.close(fd)
    try:
        visible = _generation_token(os.stat(name, dir_fd=dir_fd, follow_symlinks=False))
    except FileNotFoundError as exc:
        raise EvidenceError(f"bundle member disappeared: {name}") from exc
    if visible != owned:
        raise EvidenceError(f"bundle member generation changed: {name}")
    return data, owned


def _read_bundle(output_dir: Path):
    dir_fd = _open_directory(output_dir)
    owned_dir = os.fstat(dir_fd)
    try:
        report, report_generation = _read_at_generation(dir_fd, "report.json")
        markdown, markdown_generation = _read_at_generation(dir_fd, "report.md")
        try:
            visible = os.stat(output_dir, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise EvidenceError("bundle directory disappeared") from exc
        if not _same_generation(visible, owned_dir):
            raise EvidenceError("bundle directory generation changed")
        generations = (
            _generation_token(owned_dir),
            report_generation,
            markdown_generation,
        )
        return report, markdown, generations
    finally:
        os.close(dir_fd)


def _compile(args: argparse.Namespace) -> int:
    snapshot = parse_json_bytes(_read_regular(Path(args.snapshot)))
    report = compile_current(snapshot)
    _write_bundle(Path(args.output_dir), report)
    print(report["receipt_sha256"])
    return 0


def _verify(args: argparse.Namespace) -> int:
    snapshot = parse_json_bytes(_read_regular(Path(args.snapshot)))
    bundle_path = Path(args.output_dir)
    report_bytes, md_bytes, generations = _read_bundle(bundle_path)
    report = parse_json_bytes(report_bytes)
    md = md_bytes.decode("utf-8", "strict")
    if not verify_current(report, snapshot):
        raise EvidenceError("semantic verification failed")
    if md != render_markdown(report):
        raise EvidenceError("Markdown projection mismatch")
    current_report, current_md, current_generations = _read_bundle(bundle_path)
    if (
        current_generations != generations
        or current_report != report_bytes
        or current_md != md_bytes
    ):
        raise EvidenceError("bundle generation changed during verification")
    print("VERIFIED")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="exact-head-ship-fence")
    sub = parser.add_subparsers(dest="command", required=True)
    p_compile = sub.add_parser("compile", help="compile snapshot to create-exclusive bundle")
    p_compile.add_argument("snapshot")
    p_compile.add_argument("output_dir")
    p_compile.set_defaults(func=_compile)
    p_verify = sub.add_parser("verify", help="verify bundle against source snapshot")
    p_verify.add_argument("snapshot")
    p_verify.add_argument("output_dir")
    p_verify.set_defaults(func=_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except (EvidenceError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
