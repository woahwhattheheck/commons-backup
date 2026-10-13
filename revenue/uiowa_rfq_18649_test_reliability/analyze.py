#!/usr/bin/env python3
"""Offline test-run evidence analysis. Outcomes are signals, not defect diagnoses."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

FIELDS = (
    'run_id', 'group', 'service', 'test_id', 'revision', 'environment',
    'data_version', 'attempt', 'outcome', 'failure_kind', 'failure_signature',
    'queued_at', 'started_at', 'finished_at', 'triage', 'triage_ref', 'source_ref',
)
OUTCOMES = {'pass', 'fail', 'error', 'skipped', 'cancelled'}
TRIAGE = {'unreviewed', 'confirmed_flaky', 'confirmed_defect', 'confirmed_infrastructure'}
EXECUTED = {'pass', 'fail', 'error'}
FAILED = {'fail', 'error'}


class InputError(ValueError):
    """A structural error that would make the evidence ambiguous."""


def timestamp(value: str, field: str, issues: list[str]) -> datetime | None:
    if not value:
        issues.append(f'missing:{field}')
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.utcoffset() is None:
            raise ValueError('timezone required')
        return stamp
    except ValueError:
        issues.append(f'invalid:{field}')
        return None


def parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), strict=True)
    if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise InputError('Missing or duplicate CSV column names')
    if set(reader.fieldnames) != set(FIELDS):
        missing = sorted(set(FIELDS) - set(reader.fieldnames))
        extra = sorted(set(reader.fieldnames) - set(FIELDS))
        raise InputError(f'CSV schema mismatch; missing={missing}, extra={extra}')
    rows, seen = [], set()
    for raw in reader:
        line = reader.line_num
        if None in raw or any(v is None for v in raw.values()):
            raise InputError(f'CSV line {line}: wrong number of fields')
        row = {k: v.strip() for k, v in raw.items()}
        for field in ('run_id', 'group', 'service', 'test_id', 'source_ref'):
            if not row[field]:
                raise InputError(f'CSV line {line}: {field} is required')
        attempt = row['attempt']
        if not attempt.isascii() or not attempt.isdecimal() or int(attempt) < 1:
            raise InputError(f'CSV line {line}: attempt must be a positive integer')
        row['attempt'] = int(attempt)
        row['triage'] = row['triage'] or 'unreviewed'
        if row['outcome'] not in OUTCOMES:
            raise InputError(f'CSV line {line}: unsupported outcome {row["outcome"]!r}')
        if row['failure_kind'] not in {'', 'test', 'infrastructure', 'unknown'}:
            raise InputError(f'CSV line {line}: unsupported failure_kind')
        if row['outcome'] not in FAILED and (row['failure_kind'] or row['failure_signature']):
            raise InputError(f'CSV line {line}: failure fields require fail/error outcome')
        if row['triage'] not in TRIAGE:
            raise InputError(f'CSV line {line}: unsupported triage')
        if row['triage'] != 'unreviewed' and not row['triage_ref']:
            raise InputError(f'CSV line {line}: confirmed triage requires triage_ref')
        row['key'] = tuple(row[k] for k in ('group', 'service', 'run_id', 'test_id'))
        identity = (*row['key'], row['attempt'])
        if identity in seen:
            raise InputError(f'CSV line {line}: duplicate test attempt {identity!r}')
        seen.add(identity)
        row['line'] = line
        row['issues'] = []
        row['times'] = {k: timestamp(row[k], k, row['issues'])
                        for k in ('queued_at', 'started_at', 'finished_at')}
        for earlier, later in (('queued_at', 'started_at'), ('started_at', 'finished_at'),
                               ('queued_at', 'finished_at')):
            a, b = row['times'][earlier], row['times'][later]
            if a is not None and b is not None and b < a:
                row['issues'].append(f'reversed:{earlier}:{later}')
        rows.append(row)
    return rows


def elapsed(row: dict, start: str, end: str) -> float | None:
    # A contradictory clock invalidates all durations on that row, not just one pair.
    if row['outcome'] not in EXECUTED or any(x.startswith('reversed:') for x in row['issues']):
        return None
    a, b = row['times'][start], row['times'][end]
    return (b - a).total_seconds() if a is not None and b is not None else None


def distribution(values: list[float | None]) -> dict:
    known = sorted(v for v in values if v is not None)
    return {
        'eligible_count': len(values), 'observed_count': len(known),
        'unavailable_count': len(values) - len(known),
        'total_observed_seconds': round(sum(known), 6),
        'mean_seconds': round(mean(known), 6) if known else None,
        'p50_seconds': round(median(known), 6) if known else None,
        'p95_seconds': known[math.ceil(.95 * len(known)) - 1] if known else None,
        'p95_method': 'nearest-rank; descriptive only, not an SLA or population estimate',
    }


def rate(numerator: int, denominator: int) -> dict:
    return {'numerator': numerator, 'denominator': denominator,
            'fraction': numerator / denominator if denominator else None}


def cohort(rows: list[dict]) -> dict:
    rows = sorted(rows, key=lambda r: r['attempt'])
    first, last = rows[0], rows[-1]
    issues = sorted({issue for row in rows for issue in row['issues']})
    complete = [r['attempt'] for r in rows] == list(range(1, len(rows) + 1))
    if not complete:
        issues.append('attempt_history_incomplete')
    signatures = {tuple(r[k] for k in ('revision', 'environment', 'data_version')) for r in rows}
    comparable = complete and len(signatures) == 1 and all(next(iter(signatures)))
    if not all(all(sig) for sig in signatures):
        issues.append('comparison_context_missing')
    if len(signatures) > 1:
        issues.append('comparison_context_changed')
    # Retries should be sequential; overlapping/reversed exported attempts are not a valid chain.
    chronology_ok = True
    for left, right in zip(rows, rows[1:]):
        end, start = left['times']['finished_at'], right['times']['started_at']
        if end is not None and start is not None and start < end:
            chronology_ok = False
            issues.append('attempt_chronology_conflict')
    comparable = comparable and chronology_ok
    outcomes = [r['outcome'] for r in rows]
    failures = [r for r in rows if r['outcome'] in FAILED]
    pure_test = all(r['outcome'] in {'pass', 'fail'} for r in rows) and all(
        r['failure_kind'] == 'test' for r in failures)
    if not failures:
        pattern = ('incomplete_execution' if not complete else
                   'first_pass' if outcomes == ['pass'] else
                   'passes_with_extra_attempts' if set(outcomes) == {'pass'} else 'incomplete_execution')
    elif any(r['failure_kind'] == 'infrastructure' or r['outcome'] == 'error' for r in failures):
        pattern = 'infrastructure_or_execution_error'
    elif not comparable or not pure_test:
        pattern = 'unresolved_failure'
    elif first['outcome'] == 'fail' and last['outcome'] == 'pass':
        pattern = 'retry_recovered_unconfirmed'
    elif len(rows) >= 2 and set(outcomes) == {'fail'} and len(
            {r['failure_signature'] for r in rows}) == 1 and first['failure_signature']:
        pattern = 'repeated_test_failure_unconfirmed'
    else:
        pattern = 'unresolved_failure'
    confirmed = sorted({r['triage'] for r in rows if r['triage'] != 'unreviewed'})
    triage = confirmed[0] if len(confirmed) == 1 else 'conflicting' if confirmed else 'unreviewed'
    if triage == 'conflicting':
        issues.append('conflicting_triage')
    feedback = None
    if complete and chronology_ok and last['outcome'] in EXECUTED and not any(
            x.startswith('reversed:') for x in issues):
        a, b = first['times']['queued_at'], last['times']['finished_at']
        if a is not None and b is not None:
            if b >= a:
                feedback = (b - a).total_seconds()
            else:
                issues.append('logical_feedback_clock_conflict')
    executed = [r for r in rows if r['outcome'] in EXECUTED]
    return {
        'key': dict(zip(('group', 'service', 'run_id', 'test_id'), first['key'])),
        'observed_attempts': len(rows), 'attempt_numbers': [r['attempt'] for r in rows],
        'history_complete_from_attempt_one': complete, 'comparison_context_stable': bool(comparable),
        'outcomes': outcomes, 'observed_pattern': pattern, 'reported_triage': triage,
        'comparison_contexts': [dict(zip(('revision', 'environment', 'data_version'), sig))
                                for sig in sorted(signatures)],
        'failure_signatures': sorted({r['failure_signature'] for r in failures if r['failure_signature']}),
        'triage_refs': sorted({r['triage_ref'] for r in rows if r['triage_ref']}),
        'source_refs': sorted({r['source_ref'] for r in rows}),
        'first_failure_eligible': first['attempt'] == 1 and first['outcome'] in EXECUTED,
        'initial_failure': first['attempt'] == 1 and first['outcome'] in FAILED,
        'recovery_eligible': bool(comparable and pure_test and first['outcome'] == 'fail'),
        'logical_feedback_seconds': feedback,
        'queue': distribution([elapsed(r, 'queued_at', 'started_at') for r in executed]),
        'execution': distribution([elapsed(r, 'started_at', 'finished_at') for r in executed]),
        'retry_execution': distribution([elapsed(r, 'started_at', 'finished_at') for r in executed
                                         if r['attempt'] > 1]),
        'data_issues': sorted(set(issues)),
    }


def summarize(rows: list[dict], items: list[dict]) -> dict:
    executed = [r for r in rows if r['outcome'] in EXECUTED]
    terminal = [c for c in items if c['outcomes'][-1] in EXECUTED]
    return {
        'attempt_count': len(rows), 'logical_test_count': len(items),
        'outcome_counts': dict(sorted(Counter(r['outcome'] for r in rows).items())),
        'pattern_counts': dict(sorted(Counter(c['observed_pattern'] for c in items).items())),
        'triage_counts': dict(sorted(Counter(c['reported_triage'] for c in items).items())),
        'first_attempt_failure_rate': rate(sum(c['initial_failure'] for c in items),
                                           sum(c['first_failure_eligible'] for c in items)),
        'observed_final_pass_rate': rate(sum(c['outcomes'][-1] == 'pass' for c in terminal), len(terminal)),
        'observed_test_retry_recovery_rate': rate(
            sum(c['observed_pattern'] == 'retry_recovered_unconfirmed' for c in items),
            sum(c['recovery_eligible'] for c in items)),
        'queue': distribution([elapsed(r, 'queued_at', 'started_at') for r in executed]),
        'execution': distribution([elapsed(r, 'started_at', 'finished_at') for r in executed]),
        'logical_feedback': distribution([c['logical_feedback_seconds'] for c in items]),
        'retry_execution': distribution([elapsed(r, 'started_at', 'finished_at') for r in executed
                                         if r['attempt'] > 1]),
    }


def analyze(rows: list[dict], *, queue_threshold: float = 300,
            feedback_threshold: float = 1800, synthetic: bool = False) -> dict:
    for threshold in (queue_threshold, feedback_threshold):
        if not math.isfinite(threshold) or threshold < 0:
            raise InputError('Thresholds must be finite, nonnegative seconds')
    groups = defaultdict(list)
    for row in rows:
        groups[row['key']].append(row)
    items = [cohort(groups[key]) for key in sorted(groups)]
    investigations = []
    questions = {
        'retry_recovered_unconfirmed': (2, 'Did code, runner, dependencies or test data change? Compare retained logs before calling this flaky.'),
        'repeated_test_failure_unconfirmed': (1, 'Does the same assertion reproduce on a controlled rerun? Distinguish a product defect from a deterministic test defect.'),
        'infrastructure_or_execution_error': (1, 'Is this a runner/shared-service incident or a test setup exception? Correlate logs before attributing the cause.'),
        'unresolved_failure': (1, 'What missing context or failure evidence would distinguish a defect, instability and an environment change?'),
        'incomplete_execution': (3, 'Was the check intentionally skipped/cancelled, or is completion evidence missing?'),
        'passes_with_extra_attempts': (3, 'Why were passing checks rerun? Is the original failing attempt absent from this export?'),
    }
    for item in items:
        def add(kind: str, priority: int, question: str, impact: float = 0) -> None:
            investigations.append({'priority': priority, 'kind': kind, 'key': item['key'],
                                   'question': question, 'observed_impact_seconds': impact,
                                   'source_refs': item['source_refs'],
                                   'triage_refs': item['triage_refs']})
        pattern = item['observed_pattern']
        if item['reported_triage'] == 'conflicting':
            add('conflicting_triage', 1, 'Which source resolves the conflicting triage decisions? Preserve both pending review.')
        elif item['reported_triage'] == 'confirmed_defect':
            add('reported_confirmed_defect', 1, 'What is the linked defect disposition and retest evidence? Confirmation is reported by the source, not verified by this calculator.')
        elif item['reported_triage'] == 'confirmed_flaky':
            add('reported_confirmed_flaky', 2, 'What corrective work and repeatable validation address the linked flakiness diagnosis? Do not count a retry pass as a fix.')
        elif item['reported_triage'] == 'confirmed_infrastructure':
            add('reported_confirmed_infrastructure', 1, 'What infrastructure correction and follow-up evidence close the linked incident?')
        elif pattern in questions:
            priority, question = questions[pattern]
            add(pattern, priority, question, item['retry_execution']['total_observed_seconds'])
        if item['data_issues']:
            add('evidence_completeness', 2, 'Resolve: ' + ', '.join(item['data_issues']) + '. Missing evidence is not a zero duration or a low maturity score.')
        queue_p95 = item['queue']['p95_seconds']
        if queue_p95 is not None and queue_p95 > queue_threshold:
            add('queue_delay', 2, 'Is runner capacity, concurrency policy or dependency waiting responsible for this observed queue?', queue_p95)
        feedback = item['logical_feedback_seconds']
        if feedback is not None and feedback > feedback_threshold:
            add('feedback_delay', 2, 'Where does end-to-end feedback wait: queue, execution or between retries?', feedback)
    investigations.sort(key=lambda x: (x['priority'], -x['observed_impact_seconds'],
                                       tuple(x['key'].values()), x['kind']))
    scoped = []
    for group, service in sorted({(r['group'], r['service']) for r in rows}):
        subset_rows = [r for r in rows if (r['group'], r['service']) == (group, service)]
        subset_items = [c for c in items if (c['key']['group'], c['key']['service']) == (group, service)]
        scoped.append({'group': group, 'service': service, **summarize(subset_rows, subset_items)})
    stamps = [t for row in rows for t in row['times'].values() if t is not None]
    return {
        'schema': 'tjlabs-test-reliability/v1', 'synthetic': synthetic,
        'authority': 'Analysis of supplied export only; not University findings, maturity scores, confirmed availability, or release approval.',
        'coverage': {'observed_start': min(stamps).isoformat() if stamps else None,
                     'observed_end': max(stamps).isoformat() if stamps else None,
                     'completeness': 'unknown; export boundaries, omitted runs and missing attempts require source confirmation'},
        'thresholds_seconds': {'queue': queue_threshold, 'feedback': feedback_threshold,
                               'meaning': 'local investigation triggers, not industry benchmarks or SLAs'},
        'summary': summarize(rows, items), 'by_service': scoped, 'cohorts': items,
        'investigations': investigations,
        'row_issues': [{'line': r['line'], 'source_ref': r['source_ref'], 'issues': r['issues']}
                       for r in rows if r['issues']],
    }


def markdown(report: dict) -> str:
    def cell(value: object) -> str:
        return html.escape(str(value), quote=True).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
    summary = report['summary']
    lines = ['# Test reliability and feedback investigation', '',
             '**SYNTHETIC EXERCISE**' if report['synthetic'] else '**SUPPLIED EXPORT — NOT UNIVERSITY FINDINGS**',
             '', report['authority'], '',
             f"Observed: {summary['attempt_count']} attempts / {summary['logical_test_count']} logical test chains.",
             f"Input SHA-256: `{report.get('input_sha256', 'not supplied through CLI')}`", '',
             'Rates apply only to exported, eligible observations. A retry recovery is not a confirmed flaky test.', '',
             '| Metric | Numerator | Denominator | Fraction |', '|---|---:|---:|---:|']
    for name in ('first_attempt_failure_rate', 'observed_final_pass_rate', 'observed_test_retry_recovery_rate'):
        item = summary[name]
        fraction = 'unknown' if item['fraction'] is None else f"{item['fraction']:.4f}"
        lines.append(f"| {name} | {item['numerator']} | {item['denominator']} | {fraction} |")
    lines += ['', '| Latency | Observed / eligible | p50 seconds | p95 seconds |', '|---|---:|---:|---:|']
    for name in ('queue', 'execution', 'logical_feedback', 'retry_execution'):
        value = summary[name]
        lines.append(f"| {name} | {value['observed_count']} / {value['eligible_count']} | {value['p50_seconds']} | {value['p95_seconds']} |")
    lines += ['', 'p95 uses nearest rank. Null durations are unavailable, never zero; small samples are descriptive only.',
              '', '## Prioritized investigation questions', '',
              '| Priority | Group / service / run / test | Signal | Question | Source references |', '|---:|---|---|---|---|']
    for item in report['investigations']:
        values = (item['priority'], ' / '.join(item['key'].values()), item['kind'], item['question'],
                  '; '.join(item['source_refs'] + item['triage_refs']))
        lines.append('| ' + ' | '.join(cell(v) for v in values) + ' |')
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_path', type=Path)
    parser.add_argument('--format', choices=('json', 'markdown'), default='json')
    parser.add_argument('--queue-threshold', type=float, default=300)
    parser.add_argument('--feedback-threshold', type=float, default=1800)
    parser.add_argument('--synthetic', action='store_true', help='Label an explicitly fictional input collection')
    args = parser.parse_args(argv)
    try:
        payload = args.csv_path.read_bytes()
        report = analyze(parse_csv(payload.decode('utf-8-sig')), queue_threshold=args.queue_threshold,
                         feedback_threshold=args.feedback_threshold, synthetic=args.synthetic)
        report['input_sha256'] = hashlib.sha256(payload).hexdigest()
        output = markdown(report) if args.format == 'markdown' else json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n'
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        print(f'Input error: {exc}', file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
