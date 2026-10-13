#!/usr/bin/env python3
"""Offline documentation-usability worksheet evaluator; no scores or live actions.

Consumes DOCWEAVER's original UIOWA-048 CSV columns. It assesses supplied
records, not document authenticity, personnel or University-wide practice.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from typing import Any

INVENTORY = ('doc_id', 'group', 'doc_kind', 'title', 'reference', 'state',
             'maintainer_role', 'last_reviewed', 'notes')
TASKS = ('task_id', 'group', 'task_name', 'criticality', 'required_doc_kinds',
         'doc_ids', 'evidence_type', 'observed_on', 'result', 'notes')
KINDS = {'architecture_overview', 'decision_record', 'onboarding_guide',
         'operating_documentation'}
STATES = {'available', 'not_located', 'unknown', 'superseded'}
EVIDENCE = {'observed_walkthrough', 'artifact_review', 'interview_report',
            'not_observed'}
RESULTS = {'completed', 'assisted', 'blocked', 'unknown'}
MAX_BYTES = 2_000_000
MAX_ROWS = 10_000
MAX_CELL = 16_384
SCHEMA = 'uiowa048.task-review.v1'


class InputError(ValueError):
    """Malformed input or an invalid explicit interpretation parameter."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + '\n').encode('utf-8')


def day(value: str, label: str, *, optional: bool = False) -> date | None:
    if value == '' and optional:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise InputError(f'{label}: expected YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f'{label}: invalid calendar date') from exc


def items(value: str, label: str) -> list[str] | None:
    """Blank = unknown; [] = explicitly none. IDs are never normalized."""
    if value == '':
        return None
    try:
        result = json.loads(value)
    except (ValueError, RecursionError) as exc:
        raise InputError(f'{label}: expected a JSON string array or blank') from exc
    if not isinstance(result, list) or any(
            not isinstance(x, str) or not x.strip() for x in result):
        raise InputError(f'{label}: expected nonblank strings in a JSON array')
    if len(set(result)) != len(result):
        raise InputError(f'{label}: duplicate list entry')
    return result


def validate_rows(rows: list[dict[str, str]], columns: tuple[str, ...],
                  label: str) -> list[dict[str, str]]:
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise InputError(f'{label}: expected at most {MAX_ROWS} rows')
    result, seen = [], set()
    key = columns[0]
    for index, row in enumerate(rows, 2):
        where = f'{label} row {index}'
        if not isinstance(row, dict) or not set(columns).issubset(row):
            raise InputError(f'{where}: missing required columns')
        if any(not isinstance(k, str) or not k.strip() for k in row):
            raise InputError(f'{where}: invalid column name')
        if any(not isinstance(v, str) or len(v) > MAX_CELL or '\x00' in v
               for v in row.values()):
            raise InputError(f'{where}: values must be bounded NUL-free strings')
        for field in (key, 'group'):
            if not row[field].strip():
                raise InputError(f'{where}: {field} must not be blank')
        if row[key] in seen:
            raise InputError(f'{where}: duplicate {key} {row[key]!r}')
        seen.add(row[key])
        if columns == INVENTORY:
            if row['doc_kind'] not in KINDS or row['state'] not in STATES:
                raise InputError(f'{where}: invalid doc_kind or state')
            day(row['last_reviewed'], f'{where} last_reviewed', optional=True)
        else:
            if row['evidence_type'] not in EVIDENCE or row['result'] not in RESULTS:
                raise InputError(f'{where}: invalid evidence_type or result')
            if row['criticality'] not in {'high', 'medium', 'low', 'unknown'}:
                raise InputError(f'{where}: invalid criticality')
            kinds = items(row['required_doc_kinds'], f'{where} required_doc_kinds')
            if kinds is not None and not set(kinds).issubset(KINDS):
                raise InputError(f'{where}: unrecognized required document kind')
            items(row['doc_ids'], f'{where} doc_ids')
            day(row['observed_on'], f'{where} observed_on', optional=True)
        result.append(dict(row))
    return result


def parse_csv(data: bytes, columns: tuple[str, ...], label: str) -> list[dict[str, str]]:
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise InputError(f'{label}: expected at most {MAX_BYTES} bytes')
    try:
        text = data.decode('utf-8-sig')
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = next(reader, None)
        if (not header or any(not x.strip() for x in header)
                or len(set(header)) != len(header)
                or not set(columns).issubset(header)):
            raise InputError(f'{label}: invalid, duplicate or missing header')
        rows = []
        for number, fields in enumerate(reader, 2):
            if len(rows) >= MAX_ROWS:
                raise InputError(f'{label}: too many rows')
            if len(fields) != len(header):
                raise InputError(f'{label} record {number}: field count differs from header')
            rows.append(dict(zip(header, fields)))
    except (UnicodeError, csv.Error) as exc:
        raise InputError(f'{label}: invalid UTF-8 or CSV: {exc}') from exc
    return validate_rows(rows, columns, label)


def read_input(path: Path) -> bytes:
    with path.open('rb') as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise InputError(f'{path.name}: input exceeds {MAX_BYTES} bytes')
    return data


def assess(inventory: list[dict[str, str]], tasks: list[dict[str, str]], *,
           as_of: str, review_age_days: int = 180,
           context: str = 'synthetic') -> dict[str, Any]:
    """Evaluate the supplied records; direct callers receive the CSV checks too."""
    cutoff = day(as_of, 'as_of')
    if type(review_age_days) is not int or not 0 <= review_age_days <= 36500:
        raise InputError('review_age_days: expected integer in [0, 36500]')
    if context not in {'synthetic', 'supplied_records'}:
        raise InputError('context: expected synthetic or supplied_records')
    docs = validate_rows(inventory, INVENTORY, 'inventory')
    observations = validate_rows(tasks, TASKS, 'tasks')
    by_id = {r['doc_id']: r for r in docs}
    signals: list[dict[str, Any]] = []
    documents, task_results = [], []
    accounts: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    def signal(code: str, entity: str, question: str,
               related: list[str] | None = None) -> None:
        signals.append({'code': code, 'entity_id': entity,
                        'related_ids': sorted(related or []), 'follow_up': question})

    for row in sorted(docs, key=lambda r: r['doc_id']):
        ident = row['doc_id']
        reviewed = day(row['last_reviewed'], ident, optional=True)
        age = None if reviewed is None else (cutoff - reviewed).days
        recency = ('UNKNOWN' if age is None else 'AFTER_AS_OF' if age < 0
                   else 'REVIEW_DUE' if age > review_age_days else 'WITHIN_WINDOW')
        if row['state'] != 'available':
            signal('DOCUMENT_' + row['state'].upper(), ident,
                   'Locate the current task aid or record its scope; do not infer the practice is absent.')
        elif not row['reference'].strip():
            signal('SOURCE_REFERENCE_MISSING', ident, 'Record a source/version/section locator for this aid.')
        if not row['maintainer_role'].strip():
            signal('MAINTAINER_UNRECORDED', ident, 'Which role maintains this aid after a change?')
        if recency == 'REVIEW_DUE':
            signal('REVIEW_AGE_PROMPT', ident,
                   'Check this aid against a current task. Age alone does not establish stale content.')
        elif recency == 'AFTER_AS_OF':
            signal('REVIEW_AFTER_AS_OF', ident, 'Use a review dated within the assessment period.')
        elif recency == 'UNKNOWN':
            signal('REVIEW_DATE_UNKNOWN', ident, 'Find the last review or an event-triggered review record.')
        documents.append({'doc_id': ident, 'group': row['group'],
                          'discovery': row['state'], 'source_reference': row['reference'],
                          'maintainer_role': row['maintainer_role'] or None,
                          'review_recency': recency, 'review_age_days': age,
                          'content_correctness': 'NOT_DETERMINED'})

    for row in sorted(observations, key=lambda r: r['task_id']):
        ident = row['task_id']
        linked = items(row['doc_ids'], ident)
        required = items(row['required_doc_kinds'], ident)
        observed = day(row['observed_on'], ident, optional=True)
        etype, outcome = row['evidence_type'], row['result']
        if etype == 'not_observed':
            status = 'NOT_OBSERVED'
            if outcome != 'unknown':
                signal('OUTCOME_WITHOUT_OBSERVATION', ident, 'Explain the claimed result or correct the evidence type.')
        elif observed is None:
            status = 'DATE_UNKNOWN'
            signal('OBSERVATION_DATE_UNKNOWN', ident, 'Establish when this account applies before using it as current evidence.')
        elif observed > cutoff:
            status = 'AFTER_AS_OF'
            signal('OBSERVATION_AFTER_AS_OF', ident, 'Retain this later account separately from the as-of assessment.')
        elif etype == 'artifact_review':
            status = 'ARTIFACT_REVIEW_ONLY'
            signal('TASK_EXECUTION_NOT_OBSERVED', ident, 'Can another practitioner complete the task using the aid?')
        elif outcome == 'unknown':
            status = 'OUTCOME_UNKNOWN'
        else:
            prefix = 'RECORDED_' if etype == 'observed_walkthrough' else 'REPORTED_'
            status = prefix + outcome.upper()
        if linked is None:
            signal('DOCUMENT_LINKS_UNKNOWN', ident, 'Which exact aids were used or sought for this task?')
        elif not linked:
            signal('NO_DOCUMENT_LINKS', ident, 'Was no documentation needed, or was required support unavailable?')
        found = [by_id[d] for d in (linked or []) if d in by_id]
        missing = sorted(set(linked or []) - by_id.keys())
        if missing:
            signal('UNRESOLVED_DOCUMENT_IDS', ident, 'Resolve the exact IDs; similarly named documents are not substitutes.', missing)
        unusable = [d['doc_id'] for d in found if d['state'] != 'available']
        if unusable:
            signal('DOCUMENT_SUPPORT_UNRESOLVED', ident,
                   'Reconcile task outcome with unavailable, superseded or unknown support.', unusable)
        cross = [d['doc_id'] for d in found if d['group'] != row['group']]
        if cross:
            signal('CROSS_GROUP_REFERENCE', ident,
                   'Confirm the declared shared-service context; do not count this aid as independent group evidence.', cross)
        available = {d['doc_kind'] for d in found if d['state'] == 'available'}
        if required is None:
            signal('EXPECTED_SUPPORT_UNKNOWN', ident, 'Define the document types, if any, this bounded task needs.')
        elif linked is not None:
            absent = sorted(set(required) - available)
            if absent:
                signal('EXPECTED_SUPPORT_NOT_LINKED', ident,
                       'Locate support for these kinds or document an effective alternative: ' + ', '.join(absent))
        if status.startswith('REPORTED_'):
            signal('INTERVIEW_NEEDS_CORROBORATION', ident,
                   'Retain the account and request a bounded walkthrough or concrete delivery example.')
        if status in {'RECORDED_ASSISTED', 'RECORDED_BLOCKED'}:
            signal('TASK_FRICTION_RECORDED', ident,
                   'Capture the dead end, assistance and task consequence; improve the aid and repeat this task.')
        scope_key = row.get('comparison_key', '')
        if scope_key and status.startswith(('RECORDED_', 'REPORTED_')):
            accounts[(row['group'], scope_key)].append({'task_id': ident,
                'outcome': outcome, 'evidence_type': etype, 'observed_on': row['observed_on']})
        task_results.append({'task_id': ident, 'group': row['group'],
            'task_name': row['task_name'], 'criticality': row['criticality'],
            'evidence_type': etype, 'recorded_result': outcome, 'assessment': status,
            'linked_documents': [{'doc_id': d['doc_id'], 'reference': d['reference'],
                                  'discovery': d['state']} for d in found],
            'unresolved_document_ids': missing})
    disagreements = []
    for (group, key), records in sorted(accounts.items()):
        if len({r['outcome'] for r in records}) > 1:
            disagreements.append({'group': group, 'comparison_key': key, 'accounts': records})
            signal('DIVERGENT_TASK_ACCOUNTS', key,
                   'Confirm the same bounded occurrence and explain the different accounts; do not pick a preferred narrative.',
                   [r['task_id'] for r in records])
    signals.sort(key=lambda x: (x['entity_id'], x['code'], x['related_ids']))
    return {'schema': SCHEMA, 'context': context, 'as_of': as_of,
        'parameters': {'review_age_days': review_age_days},
        'limits': ['Supplied-record analysis; authenticity and export completeness are not established.',
                   'Recorded walkthrough means the evidence type supplied, not human research executed by this tool.',
                   'Review age is not content correctness; availability is not usability.',
                   'No maturity score, person rating, University finding, compliance or release approval.'],
        'inventory_records': sorted(docs, key=lambda r: r['doc_id']),
        'task_records': sorted(observations, key=lambda r: r['task_id']),
        'documents': documents, 'tasks': task_results, 'disagreements': disagreements,
        'follow_ups': signals,
        'summary': {'document_count': len(docs), 'task_count': len(observations),
                    'task_evidence_states': dict(sorted(Counter(t['assessment'] for t in task_results).items())),
                    'disagreement_count': len(disagreements), 'follow_up_count': len(signals)}}


def markdown(report: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        # Treat identifiers, notes and locators as passive text, never HTML/links.
        text = str(value if value is not None else 'UNKNOWN')
        for old, new in (('&', '&amp;'), ('<', '&lt;'), ('>', '&gt;'),
                         ('\\', '\\\\'), ('`', '\\`'), ('|', '\\|'),
                         ('[', '\\['), (']', '\\]'), ('\r', ' '), ('\n', ' / ')):
            text = text.replace(old, new)
        return text
    lines = ['# Documentation usability — ' + report['context'].upper(), '',
             'As of ' + report['as_of'] + '. No scores or approval decisions.', '']
    lines.extend('- ' + x for x in report['limits'])
    lines += ['', '## Document signals', '',
              '| Document | Group | Located state | Maintainer role | Review recency | Source locator |',
              '|---|---|---|---|---|---|']
    for d in report['documents']:
        lines.append('| ' + ' | '.join(cell(d[k]) for k in ('doc_id', 'group', 'discovery',
                     'maintainer_role', 'review_recency', 'source_reference')) + ' |')
    lines += ['', '## Recorded task evidence', '',
              '| Task | Group | Task name | Evidence type | Supplied result | As-of interpretation |',
              '|---|---|---|---|---|---|']
    for t in report['tasks']:
        lines.append('| ' + ' | '.join(cell(t[k]) for k in ('task_id', 'group', 'task_name',
                     'evidence_type', 'recorded_result', 'assessment')) + ' |')
    lines += ['', '## Follow-up questions', '']
    for f in report['follow_ups']:
        related = ' [' + ', '.join(f['related_ids']) + ']' if f['related_ids'] else ''
        lines.append('- ' + cell(f['entity_id'] + related) + ' — ' + f['code'] + ': ' + cell(f['follow_up']))
    if not report['follow_ups']:
        lines.append('No questions emitted for supplied rows; this does not establish complete coverage.')
    lines += ['', '## Preserved evidence', '',
              'report.json retains every original worksheet field, extra named column, source locator,',
              'task account and disagreement. The tables above are a view, not replacement evidence.', '']
    return '\n'.join(lines)


def write_bundle(directory: Path, report: dict[str, Any], inputs: dict[str, bytes]) -> None:
    outputs = {'report.json': json_bytes(report), 'report.md': markdown(report).encode('utf-8')}
    receipt = {'schema': 'uiowa048.bundle.v1', 'context': report['context'],
               'as_of': report['as_of'],
               'inputs': {k: {'sha256': digest(v), 'bytes': len(v)} for k, v in sorted(inputs.items())},
               'outputs': {k: {'sha256': digest(v), 'bytes': len(v)} for k, v in sorted(outputs.items())},
               'meaning': 'Exact captured input/output bytes; not authenticity or executable-source attestation.'}
    # mkdir is create-only. A preexisting file/directory/alias cannot be overwritten.
    # On an I/O failure, partial output may remain; success requires exit 0 + receipt.
    directory.mkdir(parents=False, exist_ok=False)
    for name, data in {**outputs, 'receipt.json': json_bytes(receipt)}.items():
        with (directory / name).open('xb') as stream:
            stream.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--review-age-days', type=int, default=180)
    parser.add_argument('--context', choices=['synthetic', 'supplied_records'], default='synthetic')
    parser.add_argument('--output', type=Path, required=True, help='NEW directory; parent must exist')
    args = parser.parse_args(argv)
    try:
        captured = {'inventory.csv': read_input(args.inventory), 'tasks.csv': read_input(args.tasks)}
        report = assess(parse_csv(captured['inventory.csv'], INVENTORY, 'inventory'),
                        parse_csv(captured['tasks.csv'], TASKS, 'tasks'), as_of=args.as_of,
                        review_age_days=args.review_age_days, context=args.context)
        write_bundle(args.output, report, captured)
        print(json.dumps(report['summary'], sort_keys=True))
        return 0
    except (InputError, OSError, UnicodeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
