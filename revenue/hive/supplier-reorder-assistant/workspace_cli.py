#!/usr/bin/env python3
"""Use the supplier browser's existing SQLite workspace from the command line."""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
from typing import Sequence, TextIO

from desk import DeskError, INPUT_FIELDS, MAX_CSV, Store, packed


def positive_revision(value: str) -> int:
    try:
        revision = int(value)
        if revision < 1:
            raise ValueError
        return revision
    except ValueError as exc:
        raise argparse.ArgumentTypeError('revision must be a positive integer') from exc


def read_csv_text(path: Path) -> str:
    """Read bounded UTF-8 without universal-newline rewriting of source bytes."""
    with path.open('rb') as handle:
        data = handle.read(MAX_CSV + 1)
    if len(data) > MAX_CSV:
        raise DeskError(f'{path.name}: CSV exceeds {MAX_CSV} bytes')
    try:
        return data.decode('utf-8')
    except UnicodeError as exc:
        raise DeskError(f'{path.name}: expected UTF-8 CSV') from exc


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--db', type=Path, required=True,
                        help='the SAME workspace.sqlite3 passed to desk.py')
    commands = result.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='save an unsent plan in the shared workspace')
    create.add_argument('--operation-id', required=True)
    create.add_argument('--title', required=True)
    for kind in INPUT_FIELDS:
        create.add_argument(f'--{kind}', type=Path, required=True)
    create.add_argument('--as-of', required=True)
    create.add_argument('--currency', default='USD')
    create.add_argument('--pipeline-includes-draft', action='store_true')
    receive = commands.add_parser('receive', help='apply receipts through the browser Store')
    receive.add_argument('run_id')
    receive.add_argument('--receipts', type=Path, required=True)
    receive.add_argument('--expected-revision', type=positive_revision, required=True)
    receive.add_argument('--operation-id', required=True)
    commands.add_parser('list', help='list saved plans')
    show = commands.add_parser('show', help='show a current or historical saved snapshot')
    show.add_argument('run_id')
    show.add_argument('--revision', type=positive_revision)
    show.add_argument('--format', choices=['json', 'stock', 'receipt-log'], default='json')
    history = commands.add_parser('history', help='list retained revisions')
    history.add_argument('run_id')
    source = commands.add_parser('source', help='write an unchanged imported CSV to stdout')
    source.add_argument('run_id')
    source.add_argument('kind', choices=list(INPUT_FIELDS))
    source.add_argument('--revision', type=positive_revision)
    return result


def execute(args: argparse.Namespace) -> str:
    """Delegate every read/mutation to Store; no second ledger or SQL schema."""
    if args.command != 'create' and not args.db.is_file():
        raise DeskError('workspace does not exist; check --db (no empty workspace created)', 404)
    # Read all inputs before opening storage. Preserve BOM, CRLF and exact text.
    request = None
    if args.command == 'create':
        inputs = {kind: read_csv_text(getattr(args, kind)) for kind in INPUT_FIELDS}
        inputs.update(as_of=args.as_of, currency=args.currency,
                      pipeline_includes_draft=args.pipeline_includes_draft)
        request = {'operation_id': args.operation_id, 'title': args.title, 'inputs': inputs}
    elif args.command == 'receive':
        request = {'operation_id': args.operation_id, 'expected_revision': args.expected_revision,
                   'csv': read_csv_text(args.receipts)}
    store = Store(args.db)
    if args.command == 'create':
        result = store.create(request)
    elif args.command == 'receive':
        result = store.receive(args.run_id, request)
    elif args.command == 'list':
        result = store.list()
    elif args.command == 'history':
        result = store.history(args.run_id)
    else:
        result = store.get(args.run_id, args.revision)
        if args.command == 'source':
            return result['inputs'][args.kind]
        if args.format == 'stock':
            return result['updated_stock']
        if args.format == 'receipt-log':
            result = result['receipt_log']
    return packed(result) + '\n'


def write_output(value: str, stream: TextIO) -> None:
    # Binary stdout avoids changing source CRLF bytes on Windows.
    if hasattr(stream, 'buffer'):
        stream.buffer.write(value.encode('utf-8'))
    else:
        stream.write(value)
    stream.flush()


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None,
         stderr: TextIO | None = None) -> int:
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    args = parser().parse_args(argv)
    try:
        response = execute(args)
    except DeskError as exc:
        err.write(packed({'error': str(exc), 'status': exc.status}) + '\n')
        return 2
    except (OSError, sqlite3.Error) as exc:
        err.write(packed({'error': f'input or workspace unavailable: {exc}', 'status': 503}) + '\n')
        return 2
    try:
        write_output(response, out)
    except (OSError, UnicodeError):
        err.write(packed({'error': 'output failed after command execution; a mutation may already '
                                  'have committed. Replay the SAME operation ID and arguments, '
                                  'or use show to inspect the current saved plan.', 'status': 503}) + '\n')
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
