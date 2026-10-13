"""Retained-directory publisher for authenticated pursuit-portfolio artifacts.

The caller must create the destination directory first. This module opens that
exact directory generation through the no-symlink component walk and creates
final files relative to the retained descriptor. Every final pathname and the
exact bytes on its retained readable descriptor are revalidated after package
directory durability before success. That is a finalization-point integrity
check, not a claim of future immutability against a same-authority writer after
return; consumers must still verify immediately before use. A late failure
preserves already-published files; rollback never unlinks by pathname.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from .core import MAX_FILE_BYTES, PortfolioError
from .current import (
    MAX_AUTHORITY_BYTES,
    AuthorizedPortfolio,
    _open_dir_chain,
    _read_relative,
)
from .host import HostAuthorizedPortfolio


_FileIdentity = tuple[int, int]
_PublishedLeaf = tuple[str, int, _FileIdentity, bytes]


def _identity(info: os.stat_result) -> _FileIdentity:
    return (int(info.st_dev), int(info.st_ino))


def _require_visible_identity(
    dir_fd: int, name: str, expected: _FileIdentity
) -> None:
    try:
        visible = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except OSError as exc:
        raise PortfolioError(f"publication: visible output disappeared: {name}") from exc
    if _identity(visible) != expected:
        raise PortfolioError(f"publication: visible output ownership changed: {name}")
    if not stat.S_ISREG(visible.st_mode) or visible.st_nlink != 1:
        raise PortfolioError(
            f"publication: visible output is not a private regular file: {name}"
        )


def _require_owned_exact(fd: int, name: str, expected: bytes) -> None:
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size != len(expected)
        ):
            raise PortfolioError(
                f"publication: retained output metadata changed: {name}"
            )
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = len(expected) + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
    except PortfolioError:
        raise
    except OSError as exc:
        raise PortfolioError(
            f"publication: retained output readback failed: {name}"
        ) from exc

    if (
        _identity(before) != _identity(after)
        or before.st_size != after.st_size
        or before.st_nlink != after.st_nlink
    ):
        raise PortfolioError(
            f"publication: retained output generation changed: {name}"
        )
    if b"".join(chunks) != expected:
        raise PortfolioError(f"publication: output content changed: {name}")


def _write_owned_relative(
    dir_fd: int, name: str, data: bytes
) -> tuple[int, _FileIdentity]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise PortfolioError(
                f"publication: {name} is not a private regular file"
            )
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise PortfolioError(f"publication: short write for {name}")
            view = view[written:]
        os.fsync(fd)
        _require_owned_exact(fd, name, data)
        final = os.fstat(fd)
        identity = _identity(final)
        _require_visible_identity(dir_fd, name, identity)
        return fd, identity
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _published_names(published: list[_PublishedLeaf]) -> str:
    return ",".join(name for name, _fd, _identity_value, _data in published) or "none"


def _publish_files(out_dir: str | Path, files: tuple[tuple[str, bytes], ...]) -> None:
    dir_fd = _open_dir_chain(out_dir)
    published: list[_PublishedLeaf] = []
    try:
        try:
            for filename, raw in files:
                fd, identity = _write_owned_relative(dir_fd, filename, raw)
                published.append((filename, fd, identity, raw))
            os.fsync(dir_fd)

            # Earlier path checks are not enough for a multi-file package. Bind
            # every visible name and exact retained bytes again after all writes
            # and package-directory durability, then recheck the visible name.
            for filename, fd, identity, raw in published:
                _require_visible_identity(dir_fd, filename, identity)
                _require_owned_exact(fd, filename, raw)
                _require_visible_identity(dir_fd, filename, identity)
        except Exception as exc:
            message = (
                "publication failed; retained output generation preserved; "
                f"already-published files: {_published_names(published)}"
            )
            if isinstance(exc, PortfolioError):
                message = f"{message}; {exc}"
            raise PortfolioError(message) from exc
    finally:
        for _filename, fd, _identity_value, _raw in published:
            try:
                os.close(fd)
            except OSError:
                pass
        os.close(dir_fd)


def publish_authorized(value: AuthorizedPortfolio, out_dir: str | Path) -> None:
    """Internal explicit-key publisher used by focused current-layer tests."""
    _publish_files(
        out_dir,
        (
            ("portfolio.json", value.compiled.result_bytes),
            ("portfolio.md", value.compiled.markdown_bytes),
            ("receipt.json", value.compiled.receipt_bytes),
            ("upstream-authority.json", value.authority_bytes),
            ("current-receipt.json", value.current_receipt_bytes),
        ),
    )


def publish_current(value: HostAuthorizedPortfolio, out_dir: str | Path) -> None:
    """Production publisher: includes the fixed-host HMAC seal."""
    authorized = value.authorized
    _publish_files(
        out_dir,
        (
            ("portfolio.json", authorized.compiled.result_bytes),
            ("portfolio.md", authorized.compiled.markdown_bytes),
            ("receipt.json", authorized.compiled.receipt_bytes),
            ("upstream-authority.json", authorized.authority_bytes),
            ("current-receipt.json", authorized.current_receipt_bytes),
            ("host-seal.json", value.host_seal_bytes),
        ),
    )


def read_current(out_dir: str | Path) -> tuple[bytes, bytes, bytes, bytes, bytes, bytes]:
    """Read one retained production package generation."""
    dir_fd = _open_dir_chain(out_dir)
    try:
        return (
            _read_relative(dir_fd, "portfolio.json", MAX_FILE_BYTES, "portfolio.json"),
            _read_relative(dir_fd, "portfolio.md", MAX_FILE_BYTES, "portfolio.md"),
            _read_relative(dir_fd, "receipt.json", MAX_FILE_BYTES, "receipt.json"),
            _read_relative(
                dir_fd,
                "upstream-authority.json",
                MAX_AUTHORITY_BYTES,
                "upstream-authority.json",
            ),
            _read_relative(
                dir_fd,
                "current-receipt.json",
                MAX_AUTHORITY_BYTES,
                "current-receipt.json",
            ),
            _read_relative(
                dir_fd,
                "host-seal.json",
                MAX_AUTHORITY_BYTES,
                "host-seal.json",
            ),
        )
    finally:
        os.close(dir_fd)
