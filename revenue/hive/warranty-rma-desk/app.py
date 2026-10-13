#!/usr/bin/env python3
"""Hardened public entry point for the Warranty & RMA Operations Desk.

The original whole-product implementation lives in ``app_core.py``.  This
successor keeps that reviewed business logic byte-for-byte and adds two narrow
boundary repairs: exact create-exclusive export publication and loopback HTTP
request fencing.
"""
from __future__ import annotations

import importlib.util as _importlib_util
import os as _os
import stat as _stat
from pathlib import Path as _Path
from typing import Any as _Any

_CORE_PATH = _Path(__file__).with_name("app_core.py")
_SPEC = _importlib_util.spec_from_file_location("_warranty_rma_core", _CORE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load warranty/rma core")
_core = _importlib_util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_core)

# Preserve the original reviewed surface, including helpers used by the existing
# exact-head tests.  The definitions below intentionally replace only the two
# hardened boundaries.
for _name in dir(_core):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_core, _name)

_LEGACY_MAKE_HANDLER = _core.make_handler


def _split_loopback_host(value: str) -> tuple[str, int | None] | None:
    if type(value) is not str:
        return None
    text = value.strip().lower()
    if not text or any(ch.isspace() for ch in text):
        return None
    if text.startswith("["):
        end = text.find("]")
        if end < 0:
            return None
        host = text[1:end]
        rest = text[end + 1 :]
        if host != "::1":
            return None
        if not rest:
            return host, None
        if not rest.startswith(":"):
            return None
        port_text = rest[1:]
    else:
        if text.count(":") > 1:
            return None
        if ":" in text:
            host, port_text = text.rsplit(":", 1)
        else:
            host, port_text = text, ""
        if host not in {"127.0.0.1", "localhost"}:
            return None
        if not port_text:
            return host, None
    if not port_text.isascii() or not port_text.isdigit():
        return None
    port = int(port_text)
    if port < 1 or port > 65535:
        return None
    return host, port


def _require_loopback_host(handler: _Any) -> None:
    values = handler.headers.get_all("Host") or []
    if len(values) != 1 or _split_loopback_host(values[0]) is None:
        raise DeskError(421, "LOOPBACK_HOST_REQUIRED", "Host must name loopback exactly")


def _require_json_content_type(handler: _Any) -> None:
    values = handler.headers.get_all("Content-Type") or []
    if len(values) != 1:
        raise DeskError(415, "JSON_CONTENT_TYPE_REQUIRED", "exactly one application/json Content-Type is required")
    media_type = values[0].split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise DeskError(415, "JSON_CONTENT_TYPE_REQUIRED", "application/json Content-Type is required")


def make_handler(store: Store, operator_auth: OperatorAuth, index_html: bytes):
    base = _LEGACY_MAKE_HANDLER(store, operator_auth, index_html)

    class HardenedHandler(base):
        def do_GET(self) -> None:
            try:
                _require_loopback_host(self)
            except DeskError as exc:
                self._error(exc)
                return
            super().do_GET()

        def do_POST(self) -> None:
            try:
                _require_loopback_host(self)
                # Preserve the core's stronger framing failures first.  A body
                # that can actually reach JSON parsing must be non-simple JSON,
                # which also denies browser cross-origin simple POSTs.
                if not self.headers.get("Transfer-Encoding") and self.headers.get("Content-Length") is not None:
                    _require_json_content_type(self)
            except DeskError as exc:
                self._error(exc)
                return
            super().do_POST()

    return HardenedHandler


def _same_inode(a: _Any, b: _Any) -> bool:
    return int(a.st_dev) == int(b.st_dev) and int(a.st_ino) == int(b.st_ino)


def _read_visible_exact(path: _Path, created: _Any, expected: bytes) -> None:
    flags = _os.O_RDONLY
    if hasattr(_os, "O_NOFOLLOW"):
        flags |= _os.O_NOFOLLOW
    rfd = _os.open(path, flags)
    try:
        current = _os.fstat(rfd)
        if not _same_inode(current, created):
            raise OSError("published pathname no longer names the created inode")
        if not _stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
            raise OSError("published output must remain a single-link regular file")
        chunks: list[bytes] = []
        remaining = len(expected)
        while remaining:
            chunk = _os.read(rfd, min(remaining, 1024 * 1024))
            if not chunk:
                raise OSError("published output read back short")
            chunks.append(chunk)
            remaining -= len(chunk)
        if _os.read(rfd, 1):
            raise OSError("published output grew during readback")
        if b"".join(chunks) != expected:
            raise OSError("published output bytes differ from source bytes")
        # Re-check the pathname after readback.  Opening the correct inode is not
        # enough: a concurrent rename/replacement or new hardlink during the read
        # must not allow success with foreign visible bytes or shared custody.
        after = _os.lstat(path)
        if not _same_inode(after, created):
            raise OSError("published pathname changed during readback")
        if not _stat.S_ISREG(after.st_mode) or after.st_nlink != 1:
            raise OSError("published output link state changed during readback")
    finally:
        _os.close(rfd)


def _publish_bytes(path: _Path, raw: bytes) -> None:
    if type(raw) is not bytes:
        raise TypeError("raw must be bytes")
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    flags = _os.O_WRONLY | _os.O_CREAT | _os.O_EXCL
    if hasattr(_os, "O_NOFOLLOW"):
        flags |= _os.O_NOFOLLOW
    fd = _os.open(path, flags, 0o600)
    created = _os.fstat(fd)
    try:
        if not _stat.S_ISREG(created.st_mode) or created.st_nlink != 1 or created.st_size != 0:
            raise OSError("new output is not an empty single-link regular file")
        view = memoryview(raw)
        offset = 0
        while offset < len(view):
            written = _os.write(fd, view[offset:])
            if type(written) is not int or written <= 0 or written > len(view) - offset:
                raise OSError("output write made invalid progress")
            offset += written
        _os.fsync(fd)
        final = _os.fstat(fd)
        if not _same_inode(final, created):
            raise OSError("output descriptor identity changed")
        if not _stat.S_ISREG(final.st_mode) or final.st_nlink != 1:
            raise OSError("published output must remain a single-link regular file")
        if final.st_size != len(raw):
            raise OSError("published output size differs from source bytes")
        visible = _os.lstat(path)
        if not _same_inode(visible, created):
            raise OSError("published pathname was replaced")
        _read_visible_exact(path, created, raw)
    finally:
        # Deliberately never unlink a pathname on failure.  A check-then-unlink
        # cleanup cannot be made inode-conditional with portable os.unlink: a
        # concurrent replacement between lstat and unlink could delete foreign
        # data.  Failed create-exclusive artifacts therefore remain for operator
        # inspection/removal; foreign replacements and aliases are never deleted.
        _os.close(fd)


def main(argv: list[str] | None = None) -> int:
    args = _core._parse_args(argv)
    if args.command == "export":
        out = _Path(args.out)
        store = Store(args.db)
        try:
            raw = store.export_case(args.case_id)
        finally:
            store.close()
        try:
            _publish_bytes(out, raw)
        except FileExistsError as exc:
            raise SystemExit("refusing to overwrite output") from exc
        return 0

    # The reviewed core owns all product semantics.  Only the HTTP handler
    # factory is replaced so ``serve`` receives the loopback request fences.
    _core.make_handler = make_handler
    return _core.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
