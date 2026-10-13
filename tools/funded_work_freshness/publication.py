"""Alias-safe, rollback-capable publication helpers for funded-work artifacts."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
from typing import Callable, Mapping

from errors import PreflightInputError


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _lexical_absolute(path: Path) -> Path:
    """Return an absolute lexical path without resolving symlink components."""

    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _require_plain_parent(path: Path, *, label: str = "publication target") -> None:
    """Reject any existing symlink or non-directory ancestor of *path*.

    This deliberately uses lstat() while walking lexical ancestors instead of
    Path.resolve(), so a symlinked parent cannot become publication authority.
    Missing ancestors are allowed here because publication may create them; the
    walk is repeated after mkdir and again immediately before replacement.
    """

    parent = _lexical_absolute(path).parent
    current = Path(parent.anchor)
    for component in parent.parts[1:]:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise PreflightInputError(
                f"{label} parent cannot be safely inspected: {current}"
            ) from exc
        if stat.S_ISLNK(info.st_mode):
            raise PreflightInputError(f"{label} parent must not traverse a symlink: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise PreflightInputError(f"{label} parent component must be a directory: {current}")


def paths_alias(left: Path, right: Path) -> bool:
    """Return True for lexical, symlink-resolved, or existing inode aliases."""

    left = Path(left)
    right = Path(right)
    if _resolved(left) == _resolved(right):
        return True
    try:
        if left.exists() and right.exists() and os.path.samefile(left, right):
            return True
    except OSError:
        # Resolution equality above still catches lexical/symlink aliases where possible.
        pass
    return False


def require_distinct_artifacts(paths: Mapping[str, Path | None]) -> None:
    """Fail before evidence reads when named input/output/cache paths alias."""

    material = [(name, Path(path)) for name, path in paths.items() if path is not None]
    for index, (left_name, left) in enumerate(material):
        for right_name, right in material[index + 1 :]:
            if paths_alias(left, right):
                raise PreflightInputError(
                    f"{left_name} and {right_name} must not reference the same filesystem object"
                )

    for name, path in material:
        if name == "input":
            continue
        _require_plain_parent(path, label=f"{name} publication target")
        if path.is_symlink():
            raise PreflightInputError(f"{name} publication target must not be a symlink")
        if path.exists() and not path.is_file():
            raise PreflightInputError(f"{name} publication target must be a regular file")


def _stage_text(path: Path, text: str) -> Path:
    _require_plain_parent(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_plain_parent(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.stage.", dir=str(path.parent), text=True)
    staged = Path(temporary)
    owned_fd: int | None = fd
    try:
        # Close the long preflight-to-publication window: if an existing parent was
        # exchanged for a symlink while work ran, reject before writing payload bytes.
        _require_plain_parent(path)
        handle = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
        owned_fd = None
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        return staged
    except BaseException:
        if owned_fd is not None:
            try:
                os.close(owned_fd)
            except OSError:
                pass
        try:
            staged.unlink()
        except FileNotFoundError:
            pass
        raise


def _backup_existing(path: Path) -> Path | None:
    _require_plain_parent(path)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise PreflightInputError(f"publication target {path} must be a regular file")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.backup.", dir=str(path.parent))
    os.close(fd)
    backup = Path(temporary)
    backup.unlink()
    _require_plain_parent(path)
    os.link(path, backup)
    return backup


def publish_text_bundle(
    artifacts: Mapping[Path, str],
    *,
    replace: Callable[[os.PathLike[str] | str, os.PathLike[str] | str], None] = os.replace,
) -> None:
    """Publish file artifacts as one exception-safe bundle.

    Every new payload is fsynced before the first target replacement. Existing targets are
    hard-linked to same-directory backups. Existing parent components are checked with
    no-follow lstat semantics before staging and again before every replacement. If any
    replacement fails, already-published targets are restored (or removed when they did
    not previously exist), preventing a normal process error from leaving a mixed old/new
    report-cache pair.
    """

    items = [(Path(path), text) for path, text in artifacts.items()]
    if not items:
        return
    require_distinct_artifacts({f"artifact[{i}]": path for i, (path, _) in enumerate(items)})

    staged: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    committed: list[Path] = []
    preserve_backups: set[Path] = set()
    try:
        for path, text in items:
            staged[path] = _stage_text(path, text)
        for path, _ in items:
            backups[path] = _backup_existing(path)

        for path, _ in items:
            _require_plain_parent(path)
            replace(staged[path], path)
            committed.append(path)

    except BaseException:
        for path in reversed(committed):
            backup = backups.get(path)
            try:
                _require_plain_parent(path)
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    os.replace(backup, path)
                    backups[path] = None
            except BaseException:
                # Preserve the original exception and retain any backup that still
                # exists rather than deleting the last known-good copy.
                if backup is not None:
                    preserve_backups.add(backup)
        raise
    finally:
        for temporary in staged.values():
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        for backup in backups.values():
            if backup is None or backup in preserve_backups:
                continue
            try:
                backup.unlink()
            except FileNotFoundError:
                pass
