#!/usr/bin/env python3
"""Create a consistent, separately reopenable copy of catering event storage."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def backup_events(source: Path | str, destination: Path | str) -> dict:
    """Use SQLite's online backup API; retain the source and every prior backup.

    The destination is new, not a replacement for existing data. To restore,
    point event_store.py at the returned copy with --database.
    """
    source = Path(source).resolve()
    destination = Path(destination).absolute()
    if not source.is_file():
        raise FileNotFoundError(f'Event database not found: {source}')
    if source == destination.resolve():
        raise ValueError('Source and backup must be different files')
    # Read-only opening never creates a missing source or writes its contents.
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=10)) as original:
        tables = {row[0] for row in original.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'events', 'revisions', 'operations'} <= tables:
            raise ValueError('Source is not a catering event-store database')
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidental replacement of a previous copy.
        with destination.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(str(destination), timeout=10)) as copied:
                original.backup(copied)
                checks = [row[0] for row in copied.execute('PRAGMA quick_check')]
                if checks != ['ok']:
                    raise ValueError('Copied database did not pass SQLite quick_check')
                counts = {name: copied.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
                          for name in ('events', 'revisions', 'operations')}
            digest = hashlib.sha256()
            size = 0
            with destination.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    size += len(chunk)
                    digest.update(chunk)
        except BaseException:
            # Only this invocation's incomplete new copy is removed.
            destination.unlink(missing_ok=True)
            raise
    return {'backup': str(destination), 'bytes': size, 'sha256': digest.hexdigest(),
            'counts': counts, 'sqlite_quick_check': 'ok'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path.home() / '.hive-catering' / 'event_store.sqlite3')
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = backup_events(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f'Backup not created: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
