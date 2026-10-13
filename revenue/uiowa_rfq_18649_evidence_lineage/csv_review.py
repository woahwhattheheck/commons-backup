"""Build an offline evidence review from explicit CSV inventories and citations.

CSV is an intake format, not a source-hash, source-identity or approval oracle.
Python 3.10+, standard library only. No input or referenced source is changed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
from typing import Any

if __package__:
    from . import lineage
    from .render_review import render
else:
    import lineage
    from render_review import render

RECORD_COLUMNS = ('record_id', 'document_id', 'version', 'title', 'location', 'sha256')
CITATION_COLUMNS = ('record_id', 'sha256', 'locator')


def read_table(path: Path, required: tuple[str, ...]) -> tuple[list[str], list[tuple[int, dict[str, str]]], str]:
    """Retain text cells exactly; reject ambiguous headers and ragged records."""
    if not path.is_file():
        raise ValueError(f'{path}: a regular CSV input file is required')
    with path.open('rb') as stream:
        raw = stream.read(lineage.MAX_BYTES + 1)
    if len(raw) > lineage.MAX_BYTES:
        raise ValueError(f'{path}: CSV exceeds {lineage.MAX_BYTES} bytes')
    text = raw.decode('utf-8-sig')
    # csv's field-size setting is process-wide; restore it after this read.
    previous_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(lineage.MAX_BYTES)
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = next(reader, None)
        if not header or any(not name.strip() for name in header):
            raise ValueError(f'{path}: a nonempty header with named columns is required')
        if len(header) != len(set(header)):
            raise ValueError(f'{path}: duplicate column names are not supported')
        missing = [name for name in required if name not in header]
        if missing:
            raise ValueError(f'{path}: missing required columns: {", ".join(missing)}')
        rows = []
        for cells in reader:
            if not cells:  # A physically blank line is not a CSV record.
                continue
            if len(cells) != len(header):
                raise ValueError(f'{path}:{reader.line_num}: expected {len(header)} cells, received {len(cells)}')
            rows.append((reader.line_num, dict(zip(header, cells))))
    finally:
        csv.field_size_limit(previous_limit)
    return header, rows, hashlib.sha256(raw).hexdigest()


def json_cell(value: str, expected: type, where: str) -> Any:
    if not value.strip():
        return expected()
    # Reuse the comparator's duplicate-key/non-finite JSON contract.
    result = json.loads(value, object_pairs_hook=lineage._pairs, parse_constant=lineage._constant)
    if not isinstance(result, expected):
        raise ValueError(f'{where}: expected a JSON {expected.__name__}')
    lineage.encoded(result)
    return result


def manifest_from_csv(path: Path, collection_id: str, synthetic: bool) -> dict:
    header, rows, raw_sha = read_table(path, RECORD_COLUMNS)
    records = []
    special = set(RECORD_COLUMNS) | {'metadata_json', 'supersedes_json'}
    for line, row in rows:
        where = f'{path}:{line}'
        record: dict[str, Any] = {name: row[name] for name in RECORD_COLUMNS}
        record['metadata'] = json_cell(row.get('metadata_json', ''), dict, where + '.metadata_json')
        record['supersedes'] = json_cell(row.get('supersedes_json', ''), list, where + '.supersedes_json')
        extras = {key: value for key, value in row.items() if key not in special}
        if extras:
            record['csv_columns'] = extras
        records.append(record)
    # Existing validation controls identities, digests, required text and graph
    # reference shape. No filename/version/row-order inference is introduced.
    return lineage.validate_manifest({
        'schema': lineage.SCHEMA, 'collection_id': collection_id,
        'synthetic': synthetic, 'records': records,
        'csv_source': {'format': 'UTF-8 CSV', 'columns': header, 'sha256': raw_sha},
    })


def findings_from_csv(path: Path) -> dict:
    header, rows, raw_sha = read_table(path, ('finding_id',) + CITATION_COLUMNS)
    findings: dict[str, dict] = {}
    metadata_keys: dict[str, str] = {}
    uncited_ids: set[str] = set()
    special = {'finding_id', 'finding_metadata_json'} | set(CITATION_COLUMNS)
    for line, row in rows:
        where = f'{path}:{line}'
        fid = lineage.text(row['finding_id'], where + '.finding_id')
        metadata = json_cell(row.get('finding_metadata_json', ''), dict, where + '.finding_metadata_json')
        metadata_key = lineage.encoded(metadata)
        if fid in metadata_keys and metadata_keys[fid] != metadata_key:
            raise ValueError(f'{where}: finding {fid!r} has conflicting metadata; repeat the same metadata on every row')
        if fid not in findings:
            findings[fid] = {'finding_id': fid, 'metadata': metadata, 'citations': []}
            metadata_keys[fid] = metadata_key
        finding = findings[fid]
        extras = {key: value for key, value in row.items() if key not in special}
        present = [bool(row[name]) for name in CITATION_COLUMNS]
        if not any(present):
            if finding['citations'] or fid in uncited_ids:
                raise ValueError(f'{where}: finding {fid!r} mixes an uncited marker with other rows')
            uncited_ids.add(fid)
            if extras:
                finding['uncited_csv_columns'] = extras
            continue
        if not all(present):
            raise ValueError(f'{where}: record_id, sha256 and locator must all be supplied, or all empty for an uncited finding')
        if fid in uncited_ids:
            raise ValueError(f'{where}: finding {fid!r} has both an uncited marker and a citation')
        citation = {name: row[name] for name in CITATION_COLUMNS}
        if extras:
            citation['csv_columns'] = extras
        # Do not de-duplicate identical rows: the supplied citation population
        # remains observable and the existing comparator reports each one.
        finding['citations'].append(citation)
    return {'findings': list(findings.values()),
            'csv_source': {'format': 'UTF-8 CSV', 'columns': header, 'sha256': raw_sha}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path, help='Before source-inventory CSV')
    parser.add_argument('after', type=Path, help='After source-inventory CSV')
    parser.add_argument('--before-id', default='before-csv', help='Explicit before collection label')
    parser.add_argument('--after-id', default='after-csv', help='Explicit after collection label')
    parser.add_argument('--data-kind', choices=('private', 'synthetic'), default='private',
                        help='Operator declaration; defaults to private, not inferred from contents')
    parser.add_argument('--findings', type=Path, help='Optional finding/citation CSV')
    parser.add_argument('--output', type=Path, required=True, help='New self-contained HTML output')
    parser.add_argument('--title', default='Evidence lineage review', help='Plain-text display title')
    args = parser.parse_args(argv)
    try:
        synthetic = args.data_kind == 'synthetic'
        before = manifest_from_csv(args.before, args.before_id, synthetic)
        after = manifest_from_csv(args.after, args.after_id, synthetic)
        findings = findings_from_csv(args.findings) if args.findings is not None else None
        page, report = render(before, after, findings, args.title)
        with args.output.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(page)
        print(json.dumps({'output': str(args.output), 'status': report['status'],
                          'synthetic': report['synthetic'], 'summary': report['summary']},
                         ensure_ascii=True))
        return 0
    except (OSError, ValueError, TypeError, RecursionError, csv.Error) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
