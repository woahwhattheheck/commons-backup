from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

MAX_SAFE_INTEGER = (1 << 53) - 1


class GuardError(ValueError):
    pass


def _constant(token: str) -> Any:
    raise GuardError(f"non-finite JSON number forbidden: {token}")


def _float(token: str) -> Any:
    raise GuardError(f"floating JSON number forbidden: {token}")


def _int(token: str, _max_safe: int = MAX_SAFE_INTEGER) -> int:
    digits = token.lstrip("-")
    if not digits or len(digits) > 16:
        raise GuardError("JSON integer exceeds safe range")
    try:
        value = int(token)
    except ValueError as exc:
        raise GuardError("invalid JSON integer") from exc
    if abs(value) > _max_safe:
        raise GuardError("JSON integer exceeds safe range")
    return value


def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in rows:
        if key in out:
            raise GuardError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads(
    text: str,
    _loads_fn=json.loads,
    _pairs_fn=_pairs,
    _constant_fn=_constant,
    _float_fn=_float,
    _int_fn=_int,
) -> Any:
    if type(text) is not str:
        raise GuardError("JSON input must be exact str")
    try:
        text.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise GuardError("invalid UTF-8 JSON text") from exc
    try:
        return _loads_fn(
            text,
            object_pairs_hook=_pairs_fn,
            parse_constant=_constant_fn,
            parse_float=_float_fn,
            parse_int=_int_fn,
        )
    except GuardError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise GuardError(f"invalid JSON: {exc}") from exc


def _dir_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


def _token(st: os.stat_result, *, leaf_file: bool, _ifmt=stat.S_IFMT) -> tuple[int, ...]:
    base = (st.st_dev, st.st_ino, _ifmt(st.st_mode))
    if leaf_file:
        return base + (st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    return base


def _abs_parts(path: Path) -> tuple[str, ...]:
    absolute = path.absolute()
    if not absolute.is_absolute():
        raise GuardError(f"path did not become absolute: {path}")
    parts = absolute.parts
    if not parts:
        raise GuardError(f"empty path: {path}")
    return tuple(parts[1:])


def _open_visible(
    path: Path,
    *,
    want_file: bool,
    _abs_parts_fn=_abs_parts,
    _dir_open_flags: int = _dir_flags(),
    _file_open_flags: int = _file_flags(),
    _open_fn=os.open,
    _close_fn=os.close,
    _fstat_fn=os.fstat,
    _token_fn=_token,
    _isreg_fn=stat.S_ISREG,
    _isdir_fn=stat.S_ISDIR,
) -> tuple[int, list[tuple[str, tuple[int, ...]]]]:
    """Open path component-by-component without following symlinks.

    Returns an fd for the final object and the exact visible generation tokens for
    every component below filesystem root. The caller owns the returned fd.
    """
    parts = _abs_parts_fn(path)
    try:
        fd = _open_fn(os.sep, _dir_open_flags)
    except OSError as exc:
        raise GuardError(f"cannot open filesystem root: {exc}") from exc
    tokens: list[tuple[str, tuple[int, ...]]] = []
    try:
        for index, name in enumerate(parts):
            last = index == len(parts) - 1
            flags = _file_open_flags if last and want_file else _dir_open_flags
            try:
                child = _open_fn(name, flags, dir_fd=fd)
            except OSError as exc:
                kind = "file" if last and want_file else "directory"
                raise GuardError(f"cannot open {kind} component {name!r} of {path}: {exc}") from exc
            _close_fn(fd)
            fd = child
            st = _fstat_fn(fd)
            if last and want_file:
                if not _isreg_fn(st.st_mode):
                    raise GuardError(f"input must be regular non-symlink file: {path}")
            elif not _isdir_fn(st.st_mode):
                raise GuardError(f"path component must be directory: {name!r}")
            tokens.append((name, _token_fn(st, leaf_file=last and want_file)))
        if not parts and want_file:
            raise GuardError("filesystem root cannot be read as a text file")
        return fd, tokens
    except Exception:
        try:
            _close_fn(fd)
        except OSError:
            pass
        raise


def _visible_tokens(path: Path, *, want_file: bool, _open_fn=_open_visible, _close_fn=os.close) -> list[tuple[str, tuple[int, ...]]]:
    fd, tokens = _open_fn(path, want_file=want_file)
    _close_fn(fd)
    return tokens


def read_text(
    path: Path,
    limit: int,
    _open_fn=_open_visible,
    _visible_fn=_visible_tokens,
    _fstat_fn=os.fstat,
    _read_fn=os.read,
    _close_fn=os.close,
) -> str:
    if type(limit) is not int or limit <= 0:
        raise GuardError("byte limit must be positive integer")
    path = Path(path)
    fd, generation = _open_fn(path, want_file=True)
    try:
        before = _fstat_fn(fd)
        if before.st_size > limit:
            raise GuardError(f"input exceeds byte limit: {path}")
        chunks: list[bytes] = []
        left = limit + 1
        while left > 0:
            chunk = _read_fn(fd, min(65536, left))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        data = b"".join(chunks)
        after = _fstat_fn(fd)
        if len(data) > limit:
            raise GuardError(f"input exceeds byte limit: {path}")
        before_full = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        after_full = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if before_full != after_full:
            raise GuardError(f"input changed during read: {path}")
    finally:
        _close_fn(fd)

    # A pinned fd proves which bytes were read; this second component-wise walk
    # proves those bytes still belong to the visible declared pathname generation.
    if _visible_fn(path, want_file=True) != generation:
        raise GuardError(f"visible path generation changed during read: {path}")

    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise GuardError(f"input is not strict UTF-8: {path}") from exc
    if any(0xD800 <= ord(char) <= 0xDFFF for char in text):
        raise GuardError(f"input contains surrogate code point: {path}")
    return text


def read_text_under_root(root: Path, rel: str, limit: int, _read_text_fn=read_text) -> str:
    root = Path(root).absolute()
    if type(rel) is not str or not rel or rel.startswith(("/", "\\")):
        raise GuardError("relative surface path required")
    normalized = rel.replace("\\", "/")
    parts = Path(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise GuardError(f"surface path is not normalized: {rel}")
    return _read_text_fn(root.joinpath(*parts), limit)


def dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise GuardError(f"cannot encode report JSON: {exc}") from exc
