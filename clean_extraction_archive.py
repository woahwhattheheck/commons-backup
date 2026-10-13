"""Manual fail-closed ZIP/TAR extraction helpers for clean replay."""
from __future__ import annotations

import stat
import tarfile
import zipfile
from pathlib import Path

from clean_extraction_manifest import ReplayError, normalize_path


def _register(rel, seen, folded):
    if rel in seen:
        raise ReplayError(f"duplicate archive member path: {rel}")
    fold = rel.casefold()
    if fold in folded and folded[fold] != rel:
        raise ReplayError("case-fold ambiguous archive paths")
    seen.add(rel)
    folded[fold] = rel


def _copy_stream(src, dst, expected: int, total: int, limit: int) -> int:
    count = 0
    while True:
        chunk = src.read(1 << 20)
        if not chunk:
            break
        count += len(chunk)
        if count > expected or total + count > limit:
            raise ReplayError("archive expands beyond declared/allowed bytes")
        dst.write(chunk)
    if count != expected:
        raise ReplayError("archive member size mismatch")
    return count


def extract_zip(archive: Path, root: Path, max_files: int, max_bytes: int):
    seen, folded = set(), {}
    files = declared = actual = 0
    try:
        handle = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReplayError(f"invalid ZIP: {exc}") from exc
    with handle:
        members = handle.infolist()
        if len(members) > max_files:
            raise ReplayError("archive member count exceeds limit")
        for member in members:
            is_dir = member.is_dir()
            rel = normalize_path(member.filename, directory=is_dir)
            _register(rel, seen, folded)
            if member.flag_bits & 1:
                raise ReplayError("encrypted ZIP member is not allowed")
            if member.create_system == 3:
                kind = stat.S_IFMT((member.external_attr >> 16) & 0xFFFF)
                if kind == stat.S_IFLNK:
                    raise ReplayError("ZIP symlink is not allowed")
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ReplayError("ZIP special member is not allowed")
                if (kind == stat.S_IFDIR and not is_dir) or (
                    kind == stat.S_IFREG and is_dir
                ):
                    raise ReplayError("ZIP type metadata conflicts with member name")
            target = root / rel
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
                continue
            files += 1
            declared += member.file_size
            if files > max_files or member.file_size < 0 or declared > max_bytes:
                raise ReplayError("archive declared file/byte limits exceeded")
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with handle.open(member) as src, target.open("xb") as dst:
                    actual += _copy_stream(
                        src, dst, member.file_size, actual, max_bytes
                    )
            except FileExistsError as exc:
                raise ReplayError("archive extraction path collision") from exc
    return files, actual


def extract_tar(archive: Path, root: Path, max_files: int, max_bytes: int):
    seen, folded = set(), {}
    files = declared = actual = 0
    try:
        handle = tarfile.open(archive, "r:*")
    except (OSError, tarfile.TarError) as exc:
        raise ReplayError(f"invalid TAR: {exc}") from exc
    with handle:
        members = handle.getmembers()
        if len(members) > max_files:
            raise ReplayError("archive member count exceeds limit")
        for member in members:
            is_dir = member.isdir()
            rel = normalize_path(
                member.name,
                directory=is_dir and member.name.endswith("/"),
            )
            _register(rel, seen, folded)
            if member.issym():
                raise ReplayError("TAR symlink is not allowed")
            if member.islnk():
                raise ReplayError("TAR hardlink is not allowed")
            target = root / rel
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ReplayError("TAR special member is not allowed")
            files += 1
            declared += member.size
            if files > max_files or member.size < 0 or declared > max_bytes:
                raise ReplayError("archive declared file/byte limits exceeded")
            target.parent.mkdir(parents=True, exist_ok=True)
            src = handle.extractfile(member)
            if src is None:
                raise ReplayError("TAR member has no data stream")
            try:
                with src, target.open("xb") as dst:
                    actual += _copy_stream(src, dst, member.size, actual, max_bytes)
            except FileExistsError as exc:
                raise ReplayError("archive extraction path collision") from exc
    return files, actual
