#!/usr/bin/env python3
"""Six fictional preparation cases through Kelvin's actual UIOWA-107 analyzer.

No live records, scheduling, new scoring formula or automatic option choice.
The retained fixture is pinned; edited what-ifs are explicit, separate copies.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import continuity

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / 'fixtures' / 'ris_deadline_scenario.json'
FIXTURE_BLOB = '889aaff4f90658091902db0249161bff66a935a4'
SOURCE_NAMES = ('continuity.py', 'intervals.py', 'rehearse.py')
CASES = (
    ('baseline', 'Retained scenario; no evidence has been collected', {}),
    ('wait-bounded', 'Assume IAM wait is 0-2 hours; temporary capacity remains unconfirmed',
     {'ASM-002': (0, 2)}),
    ('capacity-added', 'Also assume 16 usable temporary hours; this is not staffing approval',
     {'ASM-002': (0, 2), 'ASM-006': (16, 16)}),
    ('peak-window', 'Assume only 8-12 usable analyst hours during the reporting peak',
     {'ASM-002': (0, 2), 'ASM-003': (8, 12)}),
    ('capacity-unknown', 'Remove the capacity observation; keep it unknown rather than zero',
     {'ASM-003': (None, None)}),
    ('long-wait-peak', 'Assume 20-24 hours of IAM wait and 8-12 usable analyst hours',
     {'ASM-002': (20, 24), 'ASM-003': (8, 12)}),
)


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def describe(data: bytes) -> dict:
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'git_blob': blob_id(data)}


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, indent=2) + '\n').encode('utf-8')


def build_cases(base: dict) -> list:
    """Only change the named assumptions; retain every other source field."""
    answer = []
    for name, question, changes in CASES:
        scenario = copy.deepcopy(base)
        by_id = {a['id']: a for a in scenario['assumptions']}
        changed = []
        for aid, (low, high) in changes.items():
            row = by_id[aid]
            before = copy.deepcopy(row)
            row.update(low=low, high=high,
                       basis='UNKNOWN' if low is None else 'ASSUMED',
                       stated_by='fictional what-if; not an observed or approved input',
                       source_ref=None)
            changed.append({'assumption_id': aid, 'before': before, 'after': copy.deepcopy(row)})
        answer.append({'case': name, 'question': question, 'changes': changed,
                       'scenario': scenario})
    return answer


def summarize(cases: list) -> dict:
    rows = []
    for case in cases:
        analysis = continuity.Analysis(case['scenario'])
        output = analysis.as_dict()
        rows.append({'case': case['case'], 'question': case['question'],
                     'changes': case['changes'],
                     'verdicts': {r['option_id']: r['verdict'] for r in analysis.results},
                     'options': analysis.results,
                     'unresolved_assumptions': output['unresolved_assumptions'],
                     'comparisons': output['comparisons']})
    return {'schema': 'uiowa107-preparation-rehearsal/v1', 'synthetic': True,
            'authority': 'FICTIONAL_REHEARSAL_ONLY',
            'interpretation': 'Scenario arithmetic only; not a chosen option, observed capacity, or commitment.',
            'cases': rows}


def render_summary(summary: dict) -> str:
    lines = ['# Research-deadline preparation rehearsal', '',
             '**All six cases are fictional. No calendar, staffing, or change decision is made.**', '',
             '| Case | Proceed A | Defer B | Rehearse C | Add capacity D | Unknown inputs |',
             '| --- | --- | --- | --- | --- | --- |']
    for row in summary['cases']:
        verdicts = [row['verdicts'][oid] for oid in ('OPT-A', 'OPT-B', 'OPT-C', 'OPT-D')]
        lines.append('| ' + ' | '.join([row['case']] + verdicts +
                      [', '.join(row['unresolved_assumptions']) or 'none; assumptions still are not observations']) + ' |')
    lines += ['', '## What the comparisons establish', '',
              'Bounding the IAM wait does not identify a uniquely preferable option. The wait-bounded case',
              'makes C fit the stated capacity, while A and D still overlap it. Adding an explicitly assumed',
              '16 usable hours makes D fit too; D has not become lower-exposure than A.',
              'In the unknown-capacity case even B is NOT_DETERMINED despite retaining lower in-window exposure.',
              'FITS does not certify rollback feasibility, deferral authority, funding, downstream impact,',
              'or the appropriateness of adding elapsed wait to labor effort.', '',
              '## Read each case', '']
    for row in summary['cases']:
        lines += [f"### {row['case']}", '', row['question'], '',
                  f"Read `{row['case']}/input.json` and `{row['case']}/continuity_report.md`.",
                  'The complete original option exclusions and evidence questions remain in the report.', '']
    return '\n'.join(lines)


def run(outdir: Path) -> dict:
    """Create a new bundle. Refuse any existing destination, including symlinks.

    Partial new output is retained with .incomplete on failure; this is not an
    atomic filesystem transaction or protection from adversarial directory moves.
    """
    source = {name: (HERE / name).read_bytes() for name in SOURCE_NAMES}
    fixture = FIXTURE.read_bytes()
    if blob_id(fixture) != FIXTURE_BLOB:
        raise ValueError('retained fictional fixture has changed; reconcile its case contract before replay')
    cases = build_cases(json.loads(fixture))
    summary = summarize(cases)  # Reject bad arithmetic before creating output.
    summary_bytes = encoded(summary)
    outdir.mkdir(parents=True, exist_ok=False)
    marker = outdir / '.incomplete'
    marker.write_text('Preparation rehearsal did not complete. Do not treat partial output as success.\n', encoding='utf-8')
    for case in cases:
        folder = outdir / case['case']
        folder.mkdir()
        (folder / 'input.json').write_bytes(encoded(case['scenario']))
        analysis = continuity.Analysis(case['scenario'])
        continuity.write_csv(analysis, folder / 'continuity_options.csv')
        continuity.write_evidence_csv(analysis, folder / 'evidence_requests.csv')
        (folder / 'continuity_analysis.json').write_bytes(encoded(analysis.as_dict()))
        (folder / 'continuity_report.md').write_text(continuity.render_markdown(analysis), encoding='utf-8')
    (outdir / 'summary.json').write_bytes(summary_bytes)
    (outdir / 'START_HERE.md').write_text(render_summary(summary), encoding='utf-8')
    if FIXTURE.read_bytes() != fixture or any((HERE / n).read_bytes() != b for n, b in source.items()):
        raise ValueError('source changed during rehearsal; partial output is not a successful run')
    files = {p.relative_to(outdir).as_posix(): describe(p.read_bytes())
             for p in sorted(outdir.rglob('*')) if p.is_file() and p != marker}
    manifest = {'schema': 'uiowa107-preparation-bundle/v1', 'status': 'COMPLETE',
                'synthetic': True, 'authority': 'FICTIONAL_REHEARSAL_ONLY',
                'fixture': describe(fixture),
                'source_files': {n: describe(b) for n, b in sorted(source.items())},
                'files': files,
                'scope': 'Exact component execution, not hosted CI, separate specialist-engine integration, or University evidence.'}
    (outdir / 'manifest.json').write_bytes(encoded(manifest))
    marker.unlink()
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True, help='new, nonexistent output directory')
    args = parser.parse_args(argv)
    try:
        summary = run(args.outdir)
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    print(f"completed {len(summary['cases'])} fictional cases; read {args.outdir / 'START_HERE.md'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
