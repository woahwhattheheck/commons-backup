"""Validate the retained Tennessee response packet, not bidder qualification.

The existing values remain an internal, unaccepted proposal. Validation checks
its declared data contract; it cannot grant contact or submission authority.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re

SCHEMA = 'tn-31701-03850-response-lab/v1'
POSTURES = {'PRIME_PRODUCT_EVIDENCE', 'SPECIALIST_WORKSHARE', 'DEMO_SUPPORTED', 'GAP_QUESTION'}
DOMAINS = {'AUDIT_SECURITY', 'COMPATIBILITY', 'INTERFACES', 'DASHBOARDS_REPORTING',
           'DOCUMENT_SOLUTIONS', 'FUNCTIONAL', 'FINANCIAL_ACCOUNTING'}
OPTIONAL = {20, 35, 47, 58, 75, 76, 77, 82}
FALSE_AUTH = {'buyer_contact': False, 'question_submission': False,
              'response_submission': False, 'partner_contact': False,
              'contract_acceptance': False, 'payment': False,
              'revenue_recognized': False}
_COLUMNS = {'id', 'domain', 'required', 'summary', 'posture'}


class ResponseLabError(ValueError):
    """The supplied packet does not meet the retained response-lab contract."""


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResponseLabError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ResponseLabError(f'nonfinite: {value}')


def _read_bytes(path: str | Path, label: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as error:
        raise ResponseLabError(f'cannot read {label}') from error


def load_json(path: str | Path) -> object:
    try:
        return json.loads(_read_bytes(path, 'manifest').decode('utf-8'),
                          object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ResponseLabError('invalid manifest JSON') from error


def _parse_rows(raw: bytes) -> list[dict[str, str]]:
    """Keep quoted newlines and reject columns DictReader would silently lose."""
    try:
        reader = csv.reader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True)
        header = next(reader, [])
        if len(header) != len(_COLUMNS) or set(header) != _COLUMNS:
            raise ResponseLabError('crosswalk header drift')
        rows = []
        for values in reader:
            if not values:  # Preserve support for blank physical CSV records.
                continue
            if len(values) != len(header):
                raise ResponseLabError(f'crosswalk row width drift at line {reader.line_num}')
            rows.append(dict(zip(header, values)))
    except (UnicodeError, csv.Error) as error:
        raise ResponseLabError('invalid crosswalk CSV') from error
    if not rows:
        raise ResponseLabError('crosswalk has no requirements')
    return rows


def load_rows(path: str | Path) -> list[dict[str, str]]:
    return _parse_rows(_read_bytes(path, 'crosswalk CSV'))


def _exact(value: object, expected: object, label: str) -> None:
    # bool subclasses int; equality alone also equates 0.0 with False and 1.0
    # with 1. The packet's integer and boolean declarations must stay distinct.
    if type(value) is not type(expected) or value != expected:
        raise ResponseLabError(f'{label} drift')


def validate(manifest_path: str | Path) -> dict:
    mp = Path(manifest_path)
    doc = load_json(mp)
    keys = {'schema', 'solicitation', 'title', 'buyer', 'source_url', 'issued',
            'questions_due_ct', 'state_answers', 'response_due_ct',
            'response_page_limit', 'minimum_font_points', 'question_submissions_per_vendor',
            'embedded_external_landing_pages_allowed', 'commercial', 'authority', 'crosswalk'}
    if type(doc) is not dict or set(doc) != keys:
        raise ResponseLabError('top-level fields drifted')
    for key in ('schema', 'solicitation', 'title', 'buyer', 'source_url', 'issued',
                'questions_due_ct', 'state_answers', 'response_due_ct'):
        if type(doc[key]) is not str or not doc[key].strip():
            raise ResponseLabError(f'{key} must be nonempty text')
    if doc['schema'] != SCHEMA or doc['solicitation'] != '31701-03850':
        raise ResponseLabError('wrong solicitation/schema')
    if (doc['questions_due_ct'] != '2026-09-25T14:00:00-05:00'
            or doc['response_due_ct'] != '2026-10-13T14:00:00-05:00'):
        raise ResponseLabError('deadline drift')
    for key, expected in {'response_page_limit': 20, 'minimum_font_points': 12,
                          'question_submissions_per_vendor': 1,
                          'embedded_external_landing_pages_allowed': False}.items():
        _exact(doc[key], expected, key)

    cw = doc['crosswalk']
    if type(cw) is not dict or set(cw) != {'file', 'sha256', 'row_count'}:
        raise ResponseLabError('crosswalk binding drift')
    _exact(cw['file'], 'requirement_crosswalk.csv', 'crosswalk filename')
    _exact(cw['row_count'], 120, 'crosswalk row count')
    if type(cw['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', cw['sha256']):
        raise ResponseLabError('crosswalk binding drift')
    raw = _read_bytes(mp.with_name(cw['file']), 'crosswalk CSV')
    if hashlib.sha256(raw).hexdigest() != cw['sha256']:
        raise ResponseLabError('crosswalk SHA drift')
    # Parse the exact bytes just hashed, rather than opening the file a second time.
    rows = _parse_rows(raw)
    try:
        ids = [int(row['id']) for row in rows]
    except (TypeError, ValueError) as error:
        raise ResponseLabError('invalid requirement id') from error
    if len(rows) != 120 or ids != list(range(1, 121)):
        raise ResponseLabError('requirements must be exact ordered 1..120')
    for requirement_id, row in zip(ids, rows):
        if (row['domain'] not in DOMAINS or row['posture'] not in POSTURES
                or row['required'] not in {'Y', 'N'} or not row['summary'].strip()):
            raise ResponseLabError('crosswalk vocabulary drift')
        if (row['required'] == 'Y') != (requirement_id not in OPTIONAL):
            raise ResponseLabError('optional-marker drift')

    commercial = {'model': 'partner-first specialist workshare',
                  'fixed_price_usd': 25000, 'state': 'PROPOSED_NOT_ACCEPTED'}
    if type(doc['commercial']) is not dict or set(doc['commercial']) != set(commercial):
        raise ResponseLabError('commercial truth drift')
    for key, expected in commercial.items():
        _exact(doc['commercial'][key], expected, f'commercial {key}')
    if type(doc['authority']) is not dict or set(doc['authority']) != set(FALSE_AUTH):
        raise ResponseLabError('authority must remain false')
    for key in FALSE_AUTH:
        if doc['authority'][key] is not False:
            raise ResponseLabError(f'authority {key} must be boolean false')
    if not re.fullmatch(r'https://www\.tn\.gov/.+', doc['source_url']):
        raise ResponseLabError('source must remain first-party Tennessee URL')
    return {'requirements': 120, 'required': 112, 'optional': 8,
            'postures': {p: sum(row['posture'] == p for row in rows) for p in sorted(POSTURES)},
            'authority': FALSE_AUTH.copy()}


if __name__ == '__main__':
    import sys
    print(json.dumps(validate(sys.argv[1] if len(sys.argv) > 1
                              else Path(__file__).with_name('response_manifest.json')),
                     sort_keys=True))
