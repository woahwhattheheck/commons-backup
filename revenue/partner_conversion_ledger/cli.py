from __future__ import annotations

import argparse
import os
import stat
import sys
from typing import Any

from .ledger import LedgerError, MAX_JSON_BYTES, canonical_bytes, compile_current, loads_strict, render_markdown, verify_current


def _read_bounded_regular(path: str) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise LedgerError(f"cannot open input: {exc.strerror}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise LedgerError("input must be a regular file")
        if before.st_size > MAX_JSON_BYTES:
            raise LedgerError("input exceeds size limit")
        chunks: list[bytes] = []
        remaining = MAX_JSON_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_JSON_BYTES:
            raise LedgerError("input exceeds size limit")
        after = os.fstat(fd)
        fingerprint_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_mode)
        fingerprint_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_mode)
        if fingerprint_before != fingerprint_after or len(raw) != after.st_size:
            raise LedgerError("input generation changed during read")
        return raw
    finally:
        os.close(fd)


def _reserve_output(path: str) -> dict[str, Any]:
    parent = os.path.dirname(os.path.abspath(path)) or "."
    if not os.path.isdir(parent):
        raise LedgerError("output parent must exist")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise LedgerError(f"cannot create output: {exc.strerror}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise LedgerError("output must be a regular file")
        return {"path": path, "fd": fd, "identity": (st.st_dev, st.st_ino)}
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _write_reserved(item: dict[str, Any], data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            written = os.write(item["fd"], view)
        except OSError as exc:
            raise LedgerError(f"cannot write output: {exc.strerror}") from exc
        if written <= 0:
            raise LedgerError("short write")
        view = view[written:]
    try:
        os.fsync(item["fd"])
    except OSError as exc:
        raise LedgerError(f"cannot sync output: {exc.strerror}") from exc


def _validate_reserved(item: dict[str, Any], expected_size: int) -> None:
    try:
        owned = os.fstat(item["fd"])
    except OSError as exc:
        raise LedgerError(f"cannot verify owned output: {exc.strerror}") from exc
    if (owned.st_dev, owned.st_ino) != item["identity"] or not stat.S_ISREG(owned.st_mode) or owned.st_size != expected_size:
        raise LedgerError("output inode or size changed during publication")
    try:
        visible = os.lstat(item["path"])
    except OSError as exc:
        raise LedgerError(f"output path changed during publication: {exc.strerror}") from exc
    if (visible.st_dev, visible.st_ino) != item["identity"] or not stat.S_ISREG(visible.st_mode) or visible.st_size != expected_size:
        raise LedgerError("output path identity or size changed during publication")


def _retire_reserved(item: dict[str, Any]) -> None:
    """Retire only our retained inode; never pathname-delete rollback state.

    Portable pathname unlink has no atomic "only if this is still my inode"
    condition. On failure we therefore truncate the retained descriptor best-effort
    and leave any still-visible owned name as a zero-byte tombstone. If the name was
    replaced by foreign state, only our renamed/unlinked inode is touched.
    """
    try:
        try:
            os.ftruncate(item["fd"], 0)
            os.fsync(item["fd"])
        except OSError:
            pass
    finally:
        try:
            os.close(item["fd"])
        except OSError:
            pass


def _write_exclusive(path: str, data: bytes) -> None:
    item = _reserve_output(path)
    try:
        _write_reserved(item, data)
        _validate_reserved(item, len(data))
    except Exception:
        _retire_reserved(item)
        raise
    else:
        os.close(item["fd"])


def _write_pair_exclusive(first_path: str, first_data: bytes, second_path: str, second_data: bytes) -> None:
    if os.path.abspath(first_path) == os.path.abspath(second_path):
        raise LedgerError("JSON and Markdown outputs must use different paths")
    opened: list[dict[str, Any]] = []
    payloads = ((first_path, first_data), (second_path, second_data))
    try:
        # Reserve the whole output set before writing either payload. A reservation
        # failure cannot make us delete any existing/foreign pathname.
        for path, _ in payloads:
            opened.append(_reserve_output(path))
        for item, (_, data) in zip(opened, payloads, strict=True):
            _write_reserved(item, data)
        for item, (_, data) in zip(opened, payloads, strict=True):
            _validate_reserved(item, len(data))
    except Exception:
        for item in reversed(opened):
            _retire_reserved(item)
        raise
    else:
        for item in opened:
            os.close(item["fd"])


def _load_packet(path: str):
    return loads_strict(_read_bounded_regular(path))


def _load_report(path: str):
    return loads_strict(_read_bounded_regular(path))


def cmd_compile(args: argparse.Namespace) -> int:
    packet = _load_packet(args.input)
    report = compile_current(packet)
    markdown = render_markdown(report).encode("utf-8")
    if report["markdown_sha256"] != __import__("hashlib").sha256(markdown).hexdigest():
        raise LedgerError("internal markdown digest mismatch")
    _write_pair_exclusive(
        args.json_output,
        canonical_bytes(report) + b"\n",
        args.markdown_output,
        markdown,
    )
    print(report["receipt_sha256"])
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    packet = _load_packet(args.input)
    report = _load_report(args.report)
    if not verify_current(packet, report):
        print("CURRENT_VERIFICATION_FAILED", file=sys.stderr)
        return 2
    print("CURRENT_VERIFIED")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Partner Conversion Ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("input")
    compile_p.add_argument("json_output")
    compile_p.add_argument("markdown_output")
    compile_p.set_defaults(func=cmd_compile)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("input")
    verify_p.add_argument("report")
    verify_p.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except LedgerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
