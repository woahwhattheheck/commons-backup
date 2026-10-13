"""Read the source trace strictly and describe elapsed intervals, never person-hours."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path

FIELDS = ('change_id,group,stage_order,stage_name,documented_expected,observed_activity,status,owner_role,handoff_from,handoff_to,queue_enter,work_start,work_end,queue_wait_hours,active_hours,evidence_ref,evidence_type,evidence_semantics,exception_type,gap_or_conflict,follow_up_question').split(',')


class InputError(ValueError):
    pass


def timestamp(value, location):
    if value == '':
        return None
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError('timezone offset required')
        return result
    except ValueError as exc:
        raise InputError(location + ': invalid offset-qualified timestamp') from exc


def hours(start, end):
    if start is None or end is None:
        return None
    delta = end - start
    return Fraction(delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds, 3600000000)


def scalar(value):
    return None if value is None else {'exact_hours': str(value), 'hours': float(value)}


def read_trace(path):
    raw = path.read_bytes()
    reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
    records = list(reader)
    if not records or records[0] != FIELDS:
        raise InputError('expected the exact 21-column trace header')
    stages = []
    identities = set()
    for number, values in enumerate(records[1:], 2):
        if len(values) != len(FIELDS):
            raise InputError(f'CSV record {number}: expected {len(FIELDS)} fields, found {len(values)}; no fields were shifted or discarded')
        row = dict(zip(FIELDS, values))
        try:
            order = int(row['stage_order'])
        except ValueError as exc:
            raise InputError(f'CSV record {number}: integer stage_order required') from exc
        if order < 1 or str(order) != row['stage_order']:
            raise InputError(f'CSV record {number}: positive canonical stage_order required')
        identity = (row['change_id'], row['group'], order)
        if identity in identities:
            raise InputError(f'CSV record {number}: duplicate change/group/stage identity')
        identities.add(identity)
        if not row['change_id'] or not row['group'] or not row['stage_name']:
            raise InputError(f'CSV record {number}: missing change, group or stage name')
        if row['status'] not in ('SUPPORTED', 'PARTIAL', 'UNKNOWN', 'CONFLICT'):
            raise InputError(f'CSV record {number}: unknown evidence status')
        times = {key: timestamp(row[key], f'CSV record {number}.{key}') for key in ('queue_enter', 'work_start', 'work_end')}
        ordered = [value for value in times.values() if value is not None]
        if any(a > b for a, b in zip(ordered, ordered[1:])):
            raise InputError(f'CSV record {number}: queue/work chronology is reversed')
        queue = hours(times['queue_enter'], times['work_start'])
        work = hours(times['work_start'], times['work_end'])
        notes = []
        for key, calculated in (('queue_wait_hours', queue), ('active_hours', work)):
            if row[key] == '':
                continue
            try:
                declared = Fraction(row[key])
                if declared < 0:
                    raise ValueError('negative interval')
            except (ValueError, ZeroDivisionError) as exc:
                raise InputError(f'CSV record {number}.{key}: nonnegative finite number required') from exc
            if calculated is None:
                notes.append(key + ': stated interval has no complete timestamp pair')
            elif abs(declared - calculated) > Fraction(1, 200):
                notes.append(key + ': stated value differs from timestamp result by more than 0.005 hours')
        stages.append({'source_record': number, 'source': row, 'queue': scalar(queue), 'work_span': scalar(work),
                       'timing_state': 'COMPLETE_TIMESTAMPS' if all(v is not None for v in times.values()) else 'INCOMPLETE_TIMESTAMPS',
                       'diagnostics': notes})
    if not stages:
        raise InputError('trace must contain at least one stage')
    return raw, stages


def summarize(stages):
    changes = {}
    for stage in stages:
        key = (stage['source']['change_id'], stage['source']['group'])
        changes.setdefault(key, []).append(stage)
    output = []
    for (change, group), members in changes.items():
        queues = [Fraction(s['queue']['exact_hours']) for s in members if s['queue'] is not None]
        work = [Fraction(s['work_span']['exact_hours']) for s in members if s['work_span'] is not None]
        starts = [timestamp(s['source']['queue_enter'], 'queue_enter') for s in members if s['source']['queue_enter']]
        ends = [timestamp(s['source']['work_end'], 'work_end') for s in members if s['source']['work_end']]
        output.append({'change_id': change, 'group': group, 'stage_count': len(members),
                       'status_counts': dict(Counter(s['source']['status'] for s in members)),
                       'known_queue_sum': scalar(sum(queues, Fraction(0))), 'known_work_span_sum': scalar(sum(work, Fraction(0))),
                       'missing_queue_stage_count': len(members)-len(queues), 'missing_work_stage_count': len(members)-len(work),
                       'observed_endpoint_span': scalar(hours(min(starts), max(ends))) if starts and ends else None})
    return output


def analyze(path, advance_hours, synthetic):
    raw, stages = read_trace(path)
    try:
        advance = Fraction(advance_hours)
        if advance < 0 or (advance * 3600000000).denominator != 1:
            raise ValueError('nonnegative microsecond-representable value required')
    except (ValueError, ZeroDivisionError) as exc:
        raise InputError('invalid triage advance hours') from exc
    scenario = {'name': 'Advance triage and hand its result forward; later work remains fixed', 'advance_hours': str(advance), 'stages': []}
    if advance:
        groups = {(s['source']['change_id'], s['source']['group']) for s in stages}
        if len(groups) != 1:
            raise InputError('triage scenario requires exactly one supplied change/group')
        by_order = {int(s['source']['stage_order']): s for s in stages}
        if 2 not in by_order or 3 not in by_order:
            raise InputError('triage scenario requires stages 2 and 3')
        triage, following = by_order[2], by_order[3]
        if triage['source']['stage_name'] != 'Triage' or triage['timing_state'] != 'COMPLETE_TIMESTAMPS':
            raise InputError('stage 2 must be a fully timestamped Triage stage')
        if Fraction(triage['queue']['exact_hours']) < advance:
            raise InputError('triage advance exceeds its observed queue interval')
        if following['source']['queue_enter'] != triage['source']['work_end']:
            raise InputError('scenario requires stage 3 queue entry to equal observed triage end')
        delta = timedelta(microseconds=int(advance * 3600000000))
        new_rows = []
        for stage in stages:
            row = dict(stage['source'])
            order = int(row['stage_order'])
            if order == 2:
                for key in ('work_start', 'work_end'):
                    row[key] = (timestamp(row[key], key)-delta).isoformat()
            if order == 3:
                row['queue_enter'] = (timestamp(row['queue_enter'], 'queue_enter')-delta).isoformat()
            q = hours(timestamp(row['queue_enter'], 'queue_enter'), timestamp(row['work_start'], 'work_start'))
            w = hours(timestamp(row['work_start'], 'work_start'), timestamp(row['work_end'], 'work_end'))
            new_rows.append({**stage, 'source': row, 'queue': scalar(q), 'work_span': scalar(w)})
        scenario['stages'] = new_rows
    else:
        scenario['stages'] = stages
    scenario['summary'] = summarize(scenario['stages'])
    return {'schema': 'uiowa-change-trace-report/v1', 'synthetic': synthetic,
            'boundary': 'Supplied trace. Elapsed calendar intervals are not person-hours. Missing stage timing and evidence stay unknown. The scenario changes timing assumptions, not evidence statuses.',
            'source': {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                       'git_blob': hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),
                       'raw_base64': base64.b64encode(raw).decode()},
            'stages': stages, 'summary': summarize(stages), 'scenario': scenario}


def markdown(report):
    def value(v):
        return 'UNKNOWN' if v is None else f'{v["hours"]:.6f}'
    def cell(v):
        return str(v).replace('|', '\\|').replace('\n', ' ')
    out = ['# Change trace timing and evidence', '', '**SYNTHETIC**' if report['synthetic'] else '**SUPPLIED RECORDS**', '', report['boundary'], '',
           '| Stage | Name | Evidence status | Queue hours | Work span hours | Scenario queue hours |', '|---|---|---|---:|---:|---:|']
    for s, scenario in zip(report['stages'], report['scenario']['stages']):
        row=s['source'];out.append('| '+' | '.join(cell(v) for v in (row['stage_order'],row['stage_name'],row['status'],value(s['queue']),value(s['work_span']),value(scenario['queue'])))+' |')
    out += ['', '## Observed endpoints and missing intervals', '']
    for item, scenario in zip(report['summary'], report['scenario']['summary']):
        out += [f'- {cell(item["change_id"])}: observed endpoint span {value(item["observed_endpoint_span"])} hours; scenario {value(scenario["observed_endpoint_span"])} hours.',
                f'- Known queue sum {value(item["known_queue_sum"])} hours; known work-span sum {value(item["known_work_span_sum"])} hours. Missing queue stages: {item["missing_queue_stage_count"]}; missing work spans: {item["missing_work_stage_count"]}.']
    out += ['', 'These are sums of supplied intervals and observed endpoints, not a complete critical-path model or a staffing-effort estimate. Overlapping stages could make sums exceed elapsed journey time.', '', '## Unresolved evidence and follow-up', '']
    for stage in report['stages']:
        row=stage['source']
        if row['gap_or_conflict'] or row['follow_up_question']:
            out += ['- Stage '+row['stage_order']+' ('+row['status']+'): '+cell(row['gap_or_conflict'])+' '+cell(row['follow_up_question'])]
    return '\n'.join(out)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('path',type=Path)
    p.add_argument('--advance-triage-hours',default='0');p.add_argument('--format',choices=('json','markdown'),default='markdown')
    nature=p.add_mutually_exclusive_group(required=True)
    nature.add_argument('--synthetic',action='store_true',dest='synthetic')
    nature.add_argument('--supplied-records',action='store_false',dest='synthetic')
    args=p.parse_args()
    try:
        report=analyze(args.path,args.advance_triage_hours,args.synthetic)
        print(json.dumps(report,ensure_ascii=False,indent=2) if args.format=='json' else markdown(report),end='\n' if args.format=='json' else '')
        return 0
    except (OSError,UnicodeError,ValueError,csv.Error) as exc:
        print('change-trace: '+str(exc),file=sys.stderr);return 2


if __name__=='__main__':
    raise SystemExit(main())
