"""Bounded, byte-preserving attachment intake for Hive migration concierge.

This component reads a POSIX export directory without following symlinks.
It does not write files or a database. Return values can be inserted as SQLite
BLOBs in the same transaction as contacts, tasks and the migration journal.
Only Python's standard library is required; no network or provider calls.
"""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Iterable, TypedDict

DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_TOTAL_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_ROWS = 10_000


class AttachmentError(ValueError):
    """An export attachment cannot be copied consistently."""


class AttachmentContent(TypedDict):
    data: bytes
    sha256: str
    size: int
    source_path: str


class PreparedAttachment(AttachmentContent):
    id: str
    contact_id: str
    filename: str


def _positive(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise AttachmentError(f'{name} must be a positive integer')
    return value


def _parts(relative_path: str) -> list[str]:
    if not isinstance(relative_path, str) or not relative_path:
        raise AttachmentError('attachment path must be nonempty text')
    # Use portable relative export names, never absolute/drive/UNC paths.
    if '\\' in relative_path or ':' in relative_path or '\x00' in relative_path:
        raise AttachmentError('use a relative POSIX path inside the source export')
    parts = relative_path.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise AttachmentError('attachment path contains an empty, dot or parent component')
    return parts


def _identity(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def read_attachment(root: Path | str, relative_path: str, *,
                    max_bytes: int = DEFAULT_MAX_BYTES) -> AttachmentContent:
    """Read one regular file, hash the bytes actually read, and retain its name.

    Each directory is opened relative to its already-open parent descriptor.
    Symlinks at every level (including the supplied root) are rejected. A FIFO
    or other special file never enters a blocking read. An in-place change or
    final-path replacement during reading is detected and raises AttachmentError.
    The caller must supply a stable source export: this is not a filesystem
    snapshot or protection against a concurrently privileged writer.
    """
    _positive(max_bytes, 'max_bytes')
    parts = _parts(relative_path)
    if not all(hasattr(os, name) for name in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_NONBLOCK')):
        raise AttachmentError('attachment intake requires POSIX descriptor-relative file access')
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        raise AttachmentError('attachment intake requires descriptor-relative open and stat')
    descriptors: list[int] = []
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current = os.open(os.fspath(root), directory_flags)
        descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise AttachmentError('attachment must be a regular file')
        if before.st_size > max_bytes:
            raise AttachmentError('attachment exceeds max_bytes')
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b''.join(chunks)
        if len(data) > max_bytes:
            raise AttachmentError('attachment exceeds max_bytes')
        after = os.fstat(fd)
        current_entry = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
        if (_identity(before) != _identity(after)
                or _identity(after) != _identity(current_entry)
                or len(data) != after.st_size or not stat.S_ISREG(current_entry.st_mode)):
            raise AttachmentError('attachment changed while being read; take a stable export')
        return {'data': data, 'sha256': hashlib.sha256(data).hexdigest(),
                'size': len(data), 'source_path': '/'.join(parts)}
    except OSError as exc:
        # Do not echo absolute source paths or customer bytes into routine logs.
        raise AttachmentError(f'attachment read failed (errno {exc.errno})') from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def prepare_attachments(root: Path | str, rows: Iterable[dict], contact_ids: Iterable[str], *,
                        max_bytes: int = DEFAULT_MAX_BYTES,
                        max_total_bytes: int = DEFAULT_TOTAL_BYTES,
                        max_rows: int = DEFAULT_MAX_ROWS) -> list[PreparedAttachment]:
    """Prepare CSV-derived id/contact_id/filename/path rows for one transaction.

    Exact repeated IDs coalesce. Any differing metadata or bytes for the same ID
    raises instead of silently choosing a version. IDs and contact relationships
    remain exact (no case-folding, number conversion or whitespace trimming).
    A bounded read budget includes repeated rows, so duplicate input cannot cause
    unbounded file I/O. Extra source columns belong in the caller's source-row
    journal; this function returns the normalized attachment transfer fields only.
    """
    _positive(max_bytes, 'max_bytes')
    _positive(max_total_bytes, 'max_total_bytes')
    _positive(max_rows, 'max_rows')
    if isinstance(contact_ids, (str, bytes)):
        raise AttachmentError('contact_ids must be an iterable of complete identifiers')
    contact_values = list(contact_ids)
    if any(not isinstance(value, str) or not value or value != value.strip() for value in contact_values):
        raise AttachmentError('contact identifiers must be nonempty exact strings')
    contacts = set(contact_values)
    prepared: dict[str, PreparedAttachment] = {}
    total = 0
    for index, row in enumerate(rows, 1):
        if index > max_rows:
            raise AttachmentError('attachment row count exceeds max_rows')
        if not isinstance(row, dict):
            raise AttachmentError('attachment row must be a mapping')
        for field in ('id', 'contact_id', 'filename', 'path'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise AttachmentError(f'attachment row {index}: missing {field}')
        if any(row[field] != row[field].strip() for field in ('id', 'contact_id')):
            raise AttachmentError(f'attachment row {index}: identifier has surrounding whitespace')
        if row['contact_id'] not in contacts:
            raise AttachmentError(f'attachment row {index}: contact relationship is missing')
        content = read_attachment(root, row['path'], max_bytes=min(max_bytes, max(1, max_total_bytes - total)))
        total += content['size']
        if total > max_total_bytes:
            raise AttachmentError('attachment bytes exceed max_total_bytes')
        item: PreparedAttachment = dict(content, id=row['id'], contact_id=row['contact_id'], filename=row['filename'])
        prior = prepared.get(item['id'])
        if prior is not None and prior != item:
            raise AttachmentError(f'attachment row {index}: conflicting duplicate identifier')
        prepared[item['id']] = item
    return list(prepared.values())
