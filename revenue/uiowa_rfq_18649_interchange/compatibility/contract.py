"""Independent UIOWA-096 data-loss oracle and workbench/report join diagnostics.

Diagnostics do not assess University maturity, authenticate evidence, or grant
any authority. JSON comparisons ignore object-key ordering, not scalar types,
array order, missing fields, Unicode code points, or decimal precision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

GROUPS = ('ESS', 'RIS', 'IAM')
DIMENSIONS_BY_REPORT_SCHEMA = {
    # The app's built-in demo is explicitly NOT compiler output. Its original
    # spelling must not be promoted into the parent compiler's vocabulary.
    'SYNTHETIC_UI_DEMO_NOT_COMPILER_OUTPUT':
        ('software_development', 'security', 'deployment', 'ai_readiness'),
    'uiowa-rfq18649-workshare-report/v2':
        ('software', 'security', 'deployment', 'ai_readiness'),
}
AUTHORITY_FIELDS = ('buyer_approved', 'prime_approved', 'current_evidence_review_authority',
                    'submission_authorized', 'signature_authorized',
                    'invoice_or_payment_authorized', 'recognized_revenue')


def loads_exact(text: str | bytes) -> Any:
    """Reject duplicate keys/nonfinite constants; do not round JSON decimals."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key!r}')
            result[key] = value
        return result
    def invalid(token):
        raise ValueError(f'nonfinite JSON number: {token}')
    return json.loads(text, object_pairs_hook=pairs, parse_float=Decimal,
                      parse_constant=invalid)


def pointer(parent: str, key: Any) -> str:
    return parent + '/' + str(key).replace('~', '~0').replace('/', '~1')


def differences(before: Any, after: Any, at: str = '') -> list[dict[str, str]]:
    """Return all type/value/structure differences without logging source values."""
    result = []
    if type(before) is not type(after):
        return [{'pointer': at, 'code': 'TYPE_CHANGED',
                 'before_type': type(before).__name__, 'after_type': type(after).__name__}]
    if isinstance(before, dict):
        for key in sorted(before.keys() - after.keys()):
            result.append({'pointer': pointer(at, key), 'code': 'FIELD_MISSING'})
        for key in sorted(after.keys() - before.keys()):
            result.append({'pointer': pointer(at, key), 'code': 'FIELD_ADDED'})
        for key in sorted(before.keys() & after.keys()):
            result.extend(differences(before[key], after[key], pointer(at, key)))
    elif isinstance(before, list):
        if len(before) != len(after):
            result.append({'pointer': at, 'code': 'ARRAY_LENGTH_CHANGED'})
        for index, (left, right) in enumerate(zip(before, after)):
            result.extend(differences(left, right, pointer(at, index)))
    elif before != after or (isinstance(before, Decimal) and before.is_zero()
                            and before.is_signed() != after.is_signed()):
        result.append({'pointer': at, 'code': 'VALUE_CHANGED'})
    return result


def compare_json(before: str | bytes, after: str | bytes) -> dict[str, Any]:
    left = before.encode('utf-8') if isinstance(before, str) else before
    right = after.encode('utf-8') if isinstance(after, str) else after
    diff = differences(loads_exact(left), loads_exact(right))
    return {'result': 'FAIL' if diff else 'PASS', 'differences': diff,
            'original_sha256': hashlib.sha256(left).hexdigest(),
            'returned_sha256': hashlib.sha256(right).hexdigest(),
            'byte_identical': left == right,
            'meaning': 'JSON structure/types/exact decimal values; not evidence authentication'}


def audit_pair(report: Any, handoff: Any) -> list[dict[str, str]]:
    """Diagnose a draft/report pair using the actual workbench export contract."""
    findings = []
    def note(code, path):
        findings.append({'code': code, 'pointer': path})
    if not isinstance(report, dict) or not isinstance(handoff, dict):
        return [{'code': 'DOCUMENT_NOT_OBJECT', 'pointer': ''}]
    if handoff.get('schema') != 'uiowa-rfq18649-analyst-handoff-draft/v1':
        note('HANDOFF_SCHEMA_MISMATCH', '/handoff/schema')
    if handoff.get('status') != 'DRAFT_NON_AUTHORITATIVE':
        note('DRAFT_STATUS_CHANGED', '/handoff/status')
    receipt = report.get('receipt_sha256')
    if (not isinstance(receipt, str) or len(receipt) != 64
            or any(c not in '0123456789abcdef' for c in receipt)):
        note('REPORT_RECEIPT_INVALID', '/report/receipt_sha256')
    if receipt != handoff.get('report_receipt_sha256'):
        note('REPORT_GENERATION_MISMATCH', '/handoff/report_receipt_sha256')
    for report_key, handoff_key in [('mode', 'report_mode'), ('aggregate_state', 'aggregate_state')]:
        if report.get(report_key) != handoff.get(handoff_key):
            note('REPORT_METADATA_MISMATCH', '/handoff/' + handoff_key)
    if report.get('mode') != 'UNTRUSTED_INSPECTION':
        note('NOT_WORKBENCH_INSPECTION', '/report/mode')
    trust = report.get('trust')
    if not isinstance(trust, dict) or trust.get('current_evidence_review_authority') is not False:
        note('REPORT_AUTHORITY_NOT_FALSE', '/report/trust/current_evidence_review_authority')
    if handoff.get('synthetic_demo') is not (report.get('synthetic_demo') is True):
        note('SYNTHETIC_LABEL_MISMATCH', '/handoff/synthetic_demo')
    authority = handoff.get('authority')
    if not isinstance(authority, dict):
        note('HANDOFF_AUTHORITY_MISSING', '/handoff/authority')
    else:
        for key in AUTHORITY_FIELDS:
            if authority.get(key) is not False:
                note('HANDOFF_AUTHORITY_NOT_FALSE', '/handoff/authority/' + key)
    schema = report.get('schema')
    dimensions = DIMENSIONS_BY_REPORT_SCHEMA.get(schema) if isinstance(schema, str) else None
    if dimensions is None:
        note('REPORT_SCHEMA_UNSUPPORTED', '/report/schema')
        return findings
    expected = {(g, d) for g in GROUPS for d in dimensions}
    def index_rows(rows, name):
        indexed = {}
        if not isinstance(rows, list):
            note('CELLS_NOT_ARRAY', name)
            return indexed
        for i, row in enumerate(rows):
            loc = pointer(name, i)
            if not isinstance(row, dict) or not isinstance(row.get('group'), str) or not isinstance(row.get('dimension'), str):
                note('CELL_KEY_INVALID', loc)
                continue
            key = (row['group'], row['dimension'])
            if key not in expected:
                note('CELL_KEY_UNKNOWN', loc)
            if key in indexed:
                note('CELL_KEY_DUPLICATE', loc)
            indexed[key] = row
        if set(indexed) != expected:
            note('TWELVE_CELL_SET_MISMATCH', name)
        return indexed
    matrix = index_rows(report.get('assessment_matrix'), '/report/assessment_matrix')
    notes = index_rows(handoff.get('cell_notes'), '/handoff/cell_notes')
    for key in sorted(matrix.keys() & notes.keys()):
        row, draft = matrix[key], notes[key]
        loc = '/handoff/cell_notes/' + key[0] + '/' + key[1]
        if not isinstance(row.get('status'), str) or row['status'] != draft.get('compiler_status'):
            note('CELL_STATUS_MISMATCH', loc)
        for field in ('analyst_note', 'disposition'):
            if not isinstance(draft.get(field), str):
                note('DRAFT_TEXT_NOT_STRING', loc + '/' + field)
        for field in ('source_ids', 'source_record_sha256s', 'reason_codes'):
            if not isinstance(row.get(field), list):
                note('SOURCE_CONTEXT_NOT_RETAINED', '/report/assessment_matrix/' + key[0] + '/' + key[1] + '/' + field)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    compare = commands.add_parser('compare')
    compare.add_argument('original', type=Path)
    compare.add_argument('returned', type=Path)
    pair = commands.add_parser('pair')
    pair.add_argument('report', type=Path)
    pair.add_argument('handoff', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'compare':
            result = compare_json(args.original.read_bytes(), args.returned.read_bytes())
        else:
            findings = audit_pair(loads_exact(args.report.read_bytes()), loads_exact(args.handoff.read_bytes()))
            result = {'result': 'FAIL' if findings else 'PASS', 'diagnostics': findings,
                      'meaning': 'draft/report consistency only; not underlying evidence verification'}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(result['result'] != 'PASS')
    except (ValueError, OSError) as error:
        print(json.dumps({'result': 'ERROR', 'error': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
