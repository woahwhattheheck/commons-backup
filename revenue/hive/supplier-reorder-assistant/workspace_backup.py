#!/usr/bin/env python3
"""Consistent SQLite workspace archives and non-overwriting restoration."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import zipfile

SCHEMA = 'commons-supplier-reorder-backup-v1'
MAX_DATABASE = 512 * 1024 * 1024
MAX_MANIFEST = 65536
TABLES = {
    'runs': {'id', 'revision', 'document'},
    'revisions': {'run_id', 'revision', 'document'},
    'operations': {'id', 'fingerprint', 'response'},
}


class BackupError(ValueError):
    """An archive or destination cannot complete the requested operation."""


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=15)


def inspect_database(path):
    """Check SQLite integrity and the desk's required tables, not business facts."""
    with closing(readonly(path)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise BackupError('database integrity check failed')
        counts = {}
        for table, columns in TABLES.items():
            actual = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
            if not columns <= actual:
                raise BackupError(f'database is missing workspace columns in {table}')
            counts[table] = db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
        return counts


def file_digest(path):
    checksum = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(block)
            size += len(block)
    return size, checksum.hexdigest()


def publish_new(source, destination):
    """Publish one completed file atomically without replacing any existing path."""
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise BackupError('destination already exists; choose a new path') from exc
    except OSError as exc:
        raise BackupError(f'cannot publish completed file with a non-overwriting hard link: {exc}') from exc


def snapshot(database, archive, *, max_bytes=MAX_DATABASE, timeout_seconds=30):
    database, archive = Path(database), Path(archive)
    if not database.is_file():
        raise BackupError('source database does not exist')
    if type(max_bytes) is not int or max_bytes < 1 or timeout_seconds <= 0:
        raise BackupError('size and time limits must be positive')
    if archive.exists() or archive.is_symlink():
        raise BackupError('destination already exists; choose a new path')
    archive.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    def progress(status, remaining, total):
        if time.monotonic() - started > timeout_seconds:
            raise BackupError('online snapshot exceeded its time limit; retry when write traffic is lower')

    with tempfile.TemporaryDirectory(prefix='.reorder-backup-', dir=archive.parent) as temporary:
        root = Path(temporary)
        copy = root / 'workspace.sqlite3'
        with closing(readonly(database)) as source, closing(sqlite3.connect(copy)) as target:
            estimated = source.execute('PRAGMA page_count').fetchone()[0] * source.execute('PRAGMA page_size').fetchone()[0]
            if estimated > max_bytes:
                raise BackupError('database exceeds snapshot size limit')
            source.backup(target, pages=128, progress=progress, sleep=0.05)
        counts = inspect_database(copy)
        size, checksum = file_digest(copy)
        if size > max_bytes:
            raise BackupError('database exceeds snapshot size limit')
        manifest = {'schema': SCHEMA, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'database_bytes': size, 'database_sha256': checksum, 'tables': counts,
                    'sqlite_version': sqlite3.sqlite_version}
        bundle = root / 'backup.zip'
        with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as writer:
            writer.writestr('manifest.json', json.dumps(manifest, sort_keys=True, indent=2) + '\n')
            writer.write(copy, 'workspace.sqlite3')
        publish_new(bundle, archive)
        return {'archive': str(archive), **manifest}


def read_manifest(bundle, max_bytes):
    if sorted(bundle.namelist()) != ['manifest.json', 'workspace.sqlite3']:
        raise BackupError('archive must contain exactly one manifest and one workspace database')
    metadata = bundle.getinfo('manifest.json')
    payload = bundle.getinfo('workspace.sqlite3')
    if metadata.file_size > MAX_MANIFEST or payload.file_size > max_bytes:
        raise BackupError('archive exceeds size limit')
    try:
        manifest = json.loads(bundle.read(metadata).decode('utf-8'))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BackupError('archive manifest is not valid JSON') from exc
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA:
        raise BackupError('unsupported archive schema')
    size = manifest.get('database_bytes')
    checksum = manifest.get('database_sha256')
    counts = manifest.get('tables')
    if type(size) is not int or not 0 < size <= max_bytes or size != payload.file_size:
        raise BackupError('manifest database size does not match the archive')
    if not isinstance(checksum, str) or re.fullmatch(r'[0-9a-f]{64}', checksum) is None:
        raise BackupError('manifest database digest is invalid')
    if not isinstance(counts, dict) or set(counts) != set(TABLES):
        raise BackupError('manifest table counts are invalid')
    if any(type(n) is not int or n < 0 for n in counts.values()):
        raise BackupError('manifest table counts must be nonnegative integers')
    return manifest


def restore(archive, database, *, max_bytes=MAX_DATABASE):
    archive, database = Path(archive), Path(database)
    if type(max_bytes) is not int or max_bytes < 1:
        raise BackupError('size limit must be positive')
    if database.exists() or database.is_symlink():
        raise BackupError('destination already exists; choose a new path')
    database.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.reorder-restore-', dir=database.parent) as temporary:
        copy = Path(temporary) / 'workspace.sqlite3'
        with zipfile.ZipFile(archive) as bundle:
            manifest = read_manifest(bundle, max_bytes)
            checksum = hashlib.sha256()
            total = 0
            with bundle.open('workspace.sqlite3') as source, copy.open('xb') as target:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    total += len(block)
                    if total > max_bytes or total > manifest['database_bytes']:
                        raise BackupError('expanded database exceeds declared size')
                    checksum.update(block)
                    target.write(block)
            if total != manifest['database_bytes'] or checksum.hexdigest() != manifest['database_sha256']:
                raise BackupError('database digest does not match the manifest')
        counts = inspect_database(copy)
        if counts != manifest['tables']:
            raise BackupError('database table counts do not match the manifest')
        publish_new(copy, database)
        return {**manifest, 'database': str(database), 'verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    make = commands.add_parser('snapshot', help='snapshot a running workspace to a new archive')
    make.add_argument('--db', type=Path, required=True)
    make.add_argument('--out', type=Path, required=True)
    recover = commands.add_parser('restore', help='restore an archive into a new database path')
    recover.add_argument('--archive', type=Path, required=True)
    recover.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = snapshot(args.db, args.out) if args.command == 'snapshot' else restore(args.archive, args.db)
        print(json.dumps(result, sort_keys=True, indent=2))
    except (BackupError, OSError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as exc:
        parser.exit(2, f'workspace backup: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
