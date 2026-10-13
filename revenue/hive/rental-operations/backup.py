"""Create a consistent Fleetline database copy without replacing existing files.

Adapted from the existing catering event_backup.py online-backup pattern
(Git blob 6f661fe753533c54aa164ed97962944df5d4997d). The catering source is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

REQUIRED = {
    'assets': {'id', 'name', 'notes', 'unit', 'rate_cents', 'minimum_units', 'revision'},
    'reservations': {'id', 'asset_id', 'kind', 'status', 'start_us', 'end_us',
                     'customer', 'contact', 'notes', 'unit', 'rate_cents', 'minimum_units',
                     'billed_units', 'total_cents', 'revision', 'handover', 'returned'},
    'operations': {'id', 'digest', 'result'},
    'audit': {'seq', 'at', 'action', 'entity_id', 'before_json', 'after_json'},
}


class BackupError(ValueError):
    """The source cannot produce a usable Fleetline backup."""


def validate(db):
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(REQUIRED) <= tables:
        raise BackupError('The source is not a Fleetline database.')
    for table, required in REQUIRED.items():
        columns = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
        if not required <= columns:
            raise BackupError(f'The {table} table is not compatible with Fleetline.')


def backup_workspace(source: Path | str, destination: Path | str, *, max_seconds=30) -> dict:
    """Use SQLite backup for a consistent snapshot, including committed WAL pages.

    The source opens read-only. Destination creation is exclusive with mode 0600;
    prior backups are never overwritten. Reopen a successful copy with server.py
    --db rather than replacing a running database. Use a trusted private directory.
    max_seconds is checked by SQLite's progress callback, not a hard OS deadline.
    """
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise BackupError('max_seconds must be a positive finite number.')
    source = Path(source).expanduser().resolve()
    destination = Path(destination).expanduser().absolute()
    if not source.is_file():
        raise FileNotFoundError('Source database does not exist.')
    if source == destination.resolve():
        raise BackupError('Source and backup must be different files.')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)) as original:
        validate(original)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        owned = os.fstat(fd)
        os.close(fd)
        try:
            deadline = time.monotonic() + max_seconds
            def progress(status, remaining, total):
                if time.monotonic() > deadline:
                    raise BackupError('Backup exceeded its progress-callback time budget; source is unchanged.')
            with closing(sqlite3.connect(destination, timeout=5)) as copied:
                original.backup(copied, pages=256, progress=progress, sleep=0.05)
                validate(copied)
                if [row[0] for row in copied.execute('PRAGMA quick_check')] != ['ok']:
                    raise BackupError('The copy did not pass SQLite quick_check.')
                if copied.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise BackupError('The copy contains a broken relationship.')
                counts = {table: copied.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                          for table in REQUIRED}
            digest = hashlib.sha256()
            size = 0
            with destination.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
                    size += len(chunk)
        except BaseException:
            # Remove only the incomplete file created by this call, not a replacement.
            try:
                current = destination.lstat()
                if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                    destination.unlink()
            except FileNotFoundError:
                pass
            raise
    return {'format': 'fleetline-sqlite-backup-v1', 'backup': str(destination),
            'bytes': size, 'sha256': digest.hexdigest(), 'counts': counts,
            'sqlite_quick_check': 'ok', 'foreign_key_check': 'ok'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path.home() / '.fleetline' / 'fleet.sqlite')
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--max-seconds', type=float, default=30)
    args = parser.parse_args()
    try:
        result = backup_workspace(args.source, args.destination, max_seconds=args.max_seconds)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f'Backup not created: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
