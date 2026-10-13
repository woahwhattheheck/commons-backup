"""Offline assessment of assertion-specific run records; never executes a check."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

LEVELS = ('unit', 'integration', 'contract', 'end-to-end', 'user-acceptance')
STATES = ('SUPPORTED', 'OPEN_FAILURE', 'UNTESTED', 'UNCERTAIN', 'OUT_OF_SCOPE')


class InputError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise InputError(message)


def text(value, name):
    require(isinstance(value, str) and bool(value.strip()), name + ': nonempty text required')
    return value


def day(value, name):
    try:
        result = date.fromisoformat(value)
        require(result.isoformat() == value, name + ': use YYYY-MM-DD')
        return result
    except (ValueError, TypeError) as exc:
        raise InputError(name + ': invalid date') from exc


def ids(rows, name):
    require(isinstance(rows, list), name + ': list required')
    result = {}
    for row in rows:
        require(isinstance(row, dict), name + ': object required')
        key = text(row.get('id'), name + '.id')
        require(key not in result, name + ': duplicate id ' + key)
        result[key] = row
    return result


def strings(values, name):
    require(isinstance(values, list), name + ': list required')
    for value in values:
        text(value, name)
    require(len(set(values)) == len(values), name + ': duplicate entries')


def effort(value, name):
    require(value is None or (type(value) is int and value >= 0), name + ': nonnegative integer minutes or null required')


def analyze(packet):
    require(isinstance(packet, dict) and packet.get('schema') == 'uiowa-testing-portfolio/v1', 'unsupported schema')
    require(type(packet.get('synthetic')) is bool, 'synthetic must be boolean')
    as_of = day(packet.get('as_of'), 'as_of')
    revision = text(packet.get('required_revision'), 'required_revision')
    age = packet.get('max_age_days')
    require(type(age) is int and age >= 0, 'max_age_days must be a nonnegative integer')
    require(type(packet.get('impact_known')) is bool, 'impact_known must be boolean')
    strings(packet.get('changed_components'), 'changed_components')
    behaviors = ids(packet.get('behaviors'), 'behaviors')
    assertions = ids(packet.get('assertions'), 'assertions')
    checks = ids(packet.get('checks'), 'checks')
    runs = ids(packet.get('runs'), 'runs')
    improvements = ids(packet.get('improvements'), 'improvements')
    require(bool(behaviors) and bool(assertions), 'at least one behavior and assertion required')
    for b in behaviors.values():
        for field in ('service', 'statement'):
            text(b.get(field), 'behavior.' + field)
        strings(b.get('components'), 'behavior.components')
    for a in assertions.values():
        require(a.get('behavior_id') in behaviors, a['id'] + ': unknown behavior')
        require(a.get('level') in LEVELS, a['id'] + ': unknown level')
        require(type(a.get('required')) is bool and type(a.get('inventory_complete')) is bool, a['id'] + ': boolean scope/inventory required')
        for field in ('statement', 'passing_establishes', 'passing_does_not_establish', 'source_locator'):
            text(a.get(field), a['id'] + '.' + field)
        if not a['required']:
            text(a.get('scope_reason'), a['id'] + '.scope_reason')
    for c in checks.values():
        require(c.get('assertion_id') in assertions, c['id'] + ': unknown assertion')
        require(c.get('behavior_id') == assertions[c['assertion_id']]['behavior_id'], c['id'] + ': behavior/assertion binding mismatch')
        require(c.get('level') == assertions[c['assertion_id']]['level'], c['id'] + ': level/assertion binding mismatch')
        for field in ('boundary', 'owner_role', 'trigger', 'source_locator'):
            text(c.get(field), c['id'] + '.' + field)
        require(c.get('equivalence_key') is None or isinstance(c['equivalence_key'], str), c['id'] + ': equivalence_key must be text or null')
        effort(c.get('effort_minutes'), c['id'] + '.effort_minutes')
    evaluated_runs = []
    for r in sorted(runs.values(), key=lambda r: (r.get('observed_on', ''), r['id'])):
        require(r.get('check_id') in checks, r['id'] + ': unknown check')
        c = checks[r['check_id']]
        for field in ('assertion_id', 'behavior_id'):
            require(r.get(field) == c[field], r['id'] + ': run/check ' + field + ' mismatch')
        observed = day(r.get('observed_on'), r['id'] + '.observed_on')
        require(observed <= as_of, r['id'] + ': observation is after as_of')
        text(r.get('revision'), r['id'] + '.revision')
        require(r.get('result') in ('pass', 'fail', 'blocked', 'unknown'), r['id'] + ': invalid result')
        strings(r.get('artifacts'), r['id'] + '.artifacts')
        require(bool(r['artifacts']), r['id'] + ': at least one artifact locator required')
        resolution = r.get('resolution')
        if resolution is not None:
            require(r['result'] == 'fail' and isinstance(resolution, dict), r['id'] + ': only failures have resolutions')
            resolved = day(resolution.get('resolved_on'), r['id'] + '.resolved_on')
            require(observed <= resolved <= as_of, r['id'] + ': resolution outside observation/as_of window')
            text(resolution.get('source_locator'), r['id'] + '.resolution.source_locator')
            text(resolution.get('disposition'), r['id'] + '.resolution.disposition')
        reasons = []
        if r['revision'] != revision:
            reasons.append('REVISION_MISMATCH')
        if (as_of - observed).days > age:
            reasons.append('STALE')
        if r['result'] != 'pass':
            reasons.append('NOT_PASS')
        evaluated_runs.append({**r, 'supporting': not reasons, 'support_reasons': reasons,
                               'open_failure': r['result'] == 'fail' and resolution is None})
    by_assertion = defaultdict(list)
    checks_by_assertion = defaultdict(list)
    for r in evaluated_runs:
        by_assertion[r['assertion_id']].append(r)
    for c in checks.values():
        checks_by_assertion[c['assertion_id']].append(c)
    results = []
    for a in assertions.values():
        local = by_assertion[a['id']]
        supported = [r['id'] for r in local if r['supporting']]
        failures = [r['id'] for r in local if r['open_failure']]
        inventory = checks_by_assertion[a['id']]
        state = ('OUT_OF_SCOPE' if not a['required'] else 'OPEN_FAILURE' if failures else
                 'SUPPORTED' if supported else 'UNTESTED' if not inventory and a['inventory_complete'] else 'UNCERTAIN')
        results.append({**a, 'service': behaviors[a['behavior_id']]['service'], 'state': state,
                        'check_ids': sorted(c['id'] for c in inventory), 'supporting_run_ids': supported,
                        'open_failure_run_ids': failures,
                        'unsupported_run_ids': [r['id'] for r in local if not r['supporting']]})
    duplicates = defaultdict(list)
    for c in checks.values():
        if c.get('equivalence_key'):
            duplicates[(c['assertion_id'], c['level'], c['boundary'], c['equivalence_key'])].append(c['id'])
    duplicate_candidates = [{'assertion_id': k[0], 'level': k[1], 'boundary': k[2],
                             'declared_equivalence_key': k[3], 'check_ids': sorted(v)}
                            for k, v in sorted(duplicates.items()) if len(v) > 1]
    open_checks = {r['check_id'] for r in evaluated_runs if r['open_failure']}
    selected = []
    for c in sorted(checks.values(), key=lambda c: c['id']):
        reasons = []
        if not packet['impact_known']:
            reasons.append('IMPACT_UNKNOWN')
        elif set(behaviors[c['behavior_id']]['components']) & set(packet['changed_components']):
            reasons.append('CHANGED_COMPONENT')
        if c['id'] in open_checks:
            reasons.append('UNRESOLVED_FAILURE')
        if reasons:
            selected.append({'check_id': c['id'], 'reasons': reasons, 'effort_minutes': c['effort_minutes']})
    gains = {'low': 0, 'medium': 1, 'high': 2}
    proposals = []
    for item in improvements.values():
        strings(item.get('assertion_ids'), item['id'] + '.assertion_ids')
        require(bool(item['assertion_ids']) and all(a in assertions for a in item['assertion_ids']), item['id'] + ': unknown/empty assertion_ids')
        require(item.get('expected_gain') in ('low', 'medium', 'high', 'unknown'), item['id'] + ': unknown gain category')
        effort(item.get('effort_minutes'), item['id'] + '.effort_minutes')
        for field in ('action', 'rationale', 'source_locator'):
            text(item.get(field), item['id'] + '.' + field)
        proposals.append({**item, 'comparison_state': 'UNKNOWN_ASSUMPTIONS' if item['expected_gain'] == 'unknown' or item['effort_minutes'] is None else 'ASSESSED', 'dominated_by': []})
    for p in proposals:
        if p['comparison_state'] == 'UNKNOWN_ASSUMPTIONS':
            continue
        for q in proposals:
            if q['comparison_state'] == 'UNKNOWN_ASSUMPTIONS' or set(q['assertion_ids']) != set(p['assertion_ids']):
                continue
            if gains[q['expected_gain']] >= gains[p['expected_gain']] and q['effort_minutes'] <= p['effort_minutes'] and (gains[q['expected_gain']] > gains[p['expected_gain']] or q['effort_minutes'] < p['effort_minutes']):
                p['dominated_by'].append(q['id'])
    summary = {state: sum(a['state'] == state for a in results) for state in STATES}
    summary.update(supplied_runs=len(runs), supporting_runs=sum(r['supporting'] for r in evaluated_runs),
                   open_failures=sum(r['open_failure'] for r in evaluated_runs), assertions=len(assertions))
    matrix = [{'behavior_id': b, 'level': level, 'assertion_ids': [a['id'] for a in results if a['behavior_id'] == b and a['level'] == level],
               'states': dict(Counter(a['state'] for a in results if a['behavior_id'] == b and a['level'] == level))}
              for b in behaviors for level in LEVELS]
    return {'schema': 'uiowa-testing-portfolio-report/v1', 'synthetic': packet['synthetic'], 'input': packet,
            'boundary': 'Assessment of supplied assertion-specific records. Locators and declared resolutions are not independently authenticated. No tests are executed and no release is authorized.',
            'summary': summary, 'assertions': results, 'runs': evaluated_runs, 'matrix': matrix,
            'duplicate_candidates': duplicate_candidates,
            'regression_selection': {'checks': selected, 'known_effort_minutes': sum(c['effort_minutes'] or 0 for c in selected),
                                     'unknown_effort_check_ids': [c['check_id'] for c in selected if c['effort_minutes'] is None],
                                     'boundary': 'Selection proposal only, including every unresolved failure. No budget silently removes checks.'},
            'improvements': proposals}


def import_source(path, revision, as_of, required_revision, synthetic):
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    rows = list(reader)
    require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)), 'duplicate source CSV headers')
    expected = {'service', 'behavior', 'test_level', 'coverage_state', 'passing_establishes', 'passing_does_not_establish', 'portfolio_note'}
    require(bool(rows) and all(set(r) == expected and all(v is not None for v in r.values()) for r in rows), 'invalid source portfolio columns')
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    source = {'revision': revision, 'path': str(path), 'git_blob': blob, 'sha256': hashlib.sha256(raw).hexdigest(),
              'raw_base64': base64.b64encode(raw).decode(), 'rows': rows}
    behaviors, keys, assertions = [], {}, []
    for index, row in enumerate(rows, 1):
        key = (row['service'], row['behavior'])
        if key not in keys:
            keys[key] = 'B%02d' % (len(keys) + 1)
            behaviors.append({'id': keys[key], 'service': key[0], 'statement': key[1], 'components': []})
        assertions.append({'id': 'A%02d' % index, 'behavior_id': keys[key], 'level': row['test_level'],
                           'required': True, 'inventory_complete': False, 'statement': row['behavior'],
                           'passing_establishes': row['passing_establishes'], 'passing_does_not_establish': row['passing_does_not_establish'],
                           'source_locator': f'git:{revision}:{blob}#data-row-{index}', 'reported_coverage': row['coverage_state']})
    return {'schema': 'uiowa-testing-portfolio/v1', 'synthetic': synthetic, 'as_of': as_of,
            'required_revision': required_revision, 'max_age_days': 30, 'impact_known': False,
            'changed_components': [], 'behaviors': behaviors, 'assertions': assertions,
            'checks': [], 'runs': [], 'improvements': [], 'source': source}


def csv_report(report):
    f = io.StringIO(newline='')
    keys = ['id', 'behavior_id', 'service', 'level', 'state', 'statement', 'supporting_run_ids', 'open_failure_run_ids', 'source_locator']
    w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n'); w.writeheader()
    for a in report['assertions']:
        w.writerow({k: '; '.join(a[k]) if isinstance(a[k], list) else a[k] for k in keys})
    return f.getvalue()


def markdown(report):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    out = ['# Testing portfolio', '', '**SYNTHETIC EXAMPLE**' if report['synthetic'] else '**SUPPLIED RECORDS**', '', report['boundary'], '',
           '| Assertion state | Count |', '|---|---:|']
    out += [f'| {state} | {report["summary"][state]} |' for state in STATES]
    out += ['', f'Supplied runs: {report["summary"]["supplied_runs"]}. Current supporting runs: {report["summary"]["supporting_runs"]}. Unresolved failures: {report["summary"]["open_failures"]}.', '',
            '| Assertion | Service | Level | State | Supporting runs | Open failures |', '|---|---|---|---|---|---|']
    out += ['| ' + ' | '.join(cell(x) for x in (a['id'], a['service'], a['level'], a['state'], ', '.join(a['supporting_run_ids']), ', '.join(a['open_failure_run_ids']))) + ' |' for a in report['assertions']]
    out += ['', '## Regression selection', '', report['regression_selection']['boundary'], '']
    out += ['- ' + cell(c['check_id']) + ': ' + ', '.join(c['reasons']) for c in report['regression_selection']['checks']]
    out += ['', f'Known estimated effort: {report["regression_selection"]["known_effort_minutes"]} minutes. Unknown effort: ' + (', '.join(report['regression_selection']['unknown_effort_check_ids']) or 'none') + '.', '', '## Duplicate candidates', '']
    out += ['- ' + ', '.join(d['check_ids']) + ': same declared assertion, layer, boundary and equivalence key. Confirm failure-mode independence before consolidation.' for d in report['duplicate_candidates']] or ['None declared.']
    out += ['', '## Improvement assumptions', '', 'Qualitative gain categories are analyst assumptions. Dominance is compared only for identical assertion sets; it is not a confidence score.', '', '| Proposal | Gain | Minutes | State | Dominated by |', '|---|---|---:|---|---|']
    out += ['| ' + ' | '.join(cell(x) for x in (p['id'], p['expected_gain'], 'unknown' if p['effort_minutes'] is None else p['effort_minutes'], p['comparison_state'], ', '.join(p['dominated_by']))) + ' |' for p in report['improvements']]
    return '\n'.join(out) + '\n'


def load_json(path):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'duplicate JSON key: ' + k); result[k] = v
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(InputError('nonfinite JSON: ' + value)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    imp = commands.add_parser('import-source', help='Retain the published 045 CSV as reported coverage, without inventing runs')
    imp.add_argument('path', type=Path); imp.add_argument('--source-revision', required=True)
    imp.add_argument('--as-of', required=True); imp.add_argument('--required-revision', required=True)
    nature = imp.add_mutually_exclusive_group(required=True)
    nature.add_argument('--synthetic', action='store_true', dest='synthetic')
    nature.add_argument('--supplied-records', action='store_false', dest='synthetic')
    cmd = commands.add_parser('analyze'); cmd.add_argument('path', type=Path)
    cmd.add_argument('--format', choices=('json', 'csv', 'markdown'), default='markdown')
    args = p.parse_args()
    try:
        if args.command == 'import-source':
            packet = import_source(args.path, args.source_revision, args.as_of, args.required_revision, args.synthetic)
            analyze(packet)
            print(json.dumps(packet, ensure_ascii=False, indent=2)); return 0
        report = analyze(load_json(args.path))
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == 'json' else csv_report(report) if args.format == 'csv' else markdown(report), end='\n' if args.format == 'json' else '')
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        print('portfolio: ' + str(exc), file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
