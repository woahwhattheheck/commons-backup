"""Descriptor-retained, create-exclusive artifact publication."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping

try:
    from . import _engine as core
except ImportError:
    import _engine as core  # type: ignore[no-redef]

DeskError = core.DeskError


def _walk_output_directory(
    path: str | os.PathLike[str], *, create_final: bool
) -> tuple[int, Path]:
    if os.name == "nt" or not hasattr(os, "O_DIRECTORY"):
        raise DeskError("descriptor-bound publication requires a POSIX directory API")
    display = Path(path)
    absolute = Path(os.path.abspath(os.fspath(display)))
    components = absolute.parts[1:]
    flags = (
        os.O_RDONLY | os.O_DIRECTORY
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    current_fd = os.open(os.sep, flags)
    try:
        for index, component in enumerate(components):
            if component in ("", ".", ".."):
                raise DeskError("output path contains an unsafe component")
            final = index == len(components) - 1
            try:
                next_fd = os.open(component, flags, dir_fd=current_fd)
            except FileNotFoundError:
                if not final or not create_final:
                    raise DeskError("output directory is no longer visible at its admitted pathname") from None
                try:
                    os.mkdir(component, mode=0o700, dir_fd=current_fd)
                    next_fd = os.open(component, flags, dir_fd=current_fd)
                except OSError as exc:
                    raise DeskError(f"cannot create output directory safely: {exc}") from exc
            except OSError as exc:
                raise DeskError(f"cannot open output directory safely: {exc}") from exc
            os.close(current_fd)
            current_fd = next_fd
        if not stat.S_ISDIR(os.fstat(current_fd).st_mode):
            raise DeskError("output path must resolve to a retained directory")
        return current_fd, display
    except Exception:
        os.close(current_fd)
        raise


def _open_output_directory(path: str | os.PathLike[str]) -> tuple[int, Path]:
    return _walk_output_directory(path, create_final=True)


def _open_visible_output_directory(path: str | os.PathLike[str]) -> int:
    directory_fd, _ = _walk_output_directory(path, create_final=False)
    return directory_fd


def _same_generation(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _verify_visible_publication(
    output_dir: str | os.PathLike[str],
    directory_fd: int,
    published_fds: Mapping[str, int],
) -> None:
    visible_fd = _open_visible_output_directory(output_dir)
    try:
        if not _same_generation(os.fstat(directory_fd), os.fstat(visible_fd)):
            raise DeskError("output pathname detached from admitted directory generation")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        for name, retained_fd in published_fds.items():
            try:
                visible_file_fd = os.open(name, flags, dir_fd=visible_fd)
            except OSError as exc:
                raise DeskError(f"published pathname is no longer visible for {name}: {exc}") from exc
            try:
                retained = os.fstat(retained_fd)
                visible = os.fstat(visible_file_fd)
                if not stat.S_ISREG(visible.st_mode) or not _same_generation(retained, visible):
                    raise DeskError(f"published pathname detached from created file generation: {name}")
            finally:
                os.close(visible_file_fd)
    finally:
        os.close(visible_fd)


def publish_artifacts(
    packet: Mapping[str, Any],
    output_dir: str | os.PathLike[str],
    artifact_builder: Callable[[Mapping[str, Any]], dict[str, bytes]],
) -> list[str]:
    directory_fd, display = _open_output_directory(output_dir)
    artifacts = artifact_builder(packet)
    published_fds: dict[str, int] = {}
    try:
        for name in artifacts:
            try:
                entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(entry.st_mode):
                raise DeskError(f"refusing final symlink: {name}")
            raise DeskError(f"refusing existing output: {name}")

        published: list[str] = []
        for name, payload in artifacts.items():
            flags = (
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            )
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            try:
                fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
            except OSError as exc:
                raise DeskError(f"failed create-exclusive publication for {name}: {exc}") from exc
            published_fds[name] = fd
            total = 0
            while total < len(payload):
                written = os.write(fd, payload[total:])
                if written <= 0:
                    raise DeskError(f"short write while publishing {name}")
                total += written
            os.fsync(fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise DeskError(f"published target is not regular: {name}")
            published.append(str(display / name))
        os.fsync(directory_fd)
        _verify_visible_publication(output_dir, directory_fd, published_fds)
        return published
    finally:
        for fd in published_fds.values():
            try:
                os.close(fd)
            except OSError:
                pass
        os.close(directory_fd)
