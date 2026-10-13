#!/usr/bin/env python3
"""Compare the real canonical default's SeedBudget cache on retained inputs.

This acceptance consumer runs no interpreter or new game. Each mode gets a fresh
process and consumes four old, complete own-observation prefixes in one module.
The only comparator substitutions are the current uncached derivation or the
retained original SeedBudget class. Runtime source files are never changed.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = 'aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9'
SOURCE_COMMIT = '9db2f2f94666b3ca126f97ab98d28f9a3814de4f'
CASES = (
    ('evaluation/pilot-completion/9965001-p0-sell', 0),
    ('evaluation/sell-seed1-p1/9965001-p1-sell', 1),
    ('evaluation/sell-seed2/9965019-p0-sell', 0),
    ('evaluation/sell-seed2/9965019-p1-sell', 1),
)
MODES = ('cached', 'uncached', 'original')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(value):
    """Stable, type-labeled in-memory state; never deserialize executable objects."""
    if isinstance(value, Mapping):
        return {'mapping': sorted([[normalized(k), normalized(v)] for k, v in value.items()],
                                   key=lambda row: encoded(row[0]))}
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError('Unsupported state value: ' + type(value).__name__)


def load(path, name):
    # Execute the exact file, not a potentially stale timestamp-valid bytecode file.
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def check_sources(root, pins):
    actual = {}
    for name, record in pins['files'].items():
        path = root / name
        raw = path.read_bytes()
        require(len(raw) == record['bytes'] and digest(raw) == record['sha256'],
                'Source differs: ' + name)
        actual[name] = record
    return actual


def read_case(archive, prefix, seat):
    """Align existing before/after frames exactly as the original driver did."""
    result = json.loads(archive.read(prefix + '.json'))
    frames_raw = archive.read(prefix + '.frames.jsonl.gz')
    frames = [json.loads(row) for row in gzip.decompress(frames_raw).splitlines()]
    telemetry = [json.loads(row) for row in gzip.decompress(
        archive.read(prefix + '.telemetry.jsonl.gz')).splitlines()]
    require(result['status'] == 'complete' and result['failure'] is None, 'Incomplete original')
    require(result['candidate_seat'] == seat and result['steps'] == 719 and
            len(frames) == 720 and len(telemetry) == 719, 'Unexpected retained cell')
    trace = hashlib.sha256()
    packets = []
    for step in range(719):
        frame, after = frames[step], frames[step + 1]
        require(frame['frame'] == step and after['frame'] == step + 1, 'Frame order differs')
        actions = [state['action'] for state in after['state']]
        require(telemetry[step]['step'] == step and actions[seat] == telemetry[step]['action'],
                'Original telemetry differs')
        bank = [float(f['money']) for f in after['state'][0]['observation']['farms']]
        trace.update(encoded({'step': step, 'actions': actions, 'bank': bank}))
        # Only the selected player's observation and public configuration cross
        # the policy boundary. No frame.info or rival private state is passed.
        obs = copy.deepcopy(frame['state'][seat]['observation'])
        obs.update(step=step, remainingOverageTime=0)
        cfg = copy.deepcopy(frame['configuration'])
        require(cfg.get('seed') is None and obs['player'] == seat, 'Private seed/view mismatch')
        packets.append({'observation': obs, 'configuration': cfg,
                        'expected_original_action': copy.deepcopy(actions[seat])})
    trace.update(encoded([state['observation'] for state in frames[-1]['state']]))
    require(trace.hexdigest() == result['trace_sha256'], 'Original action/bank/terminal digest differs')
    require([s['reward'] for s in frames[-1]['state']] == result['scores'], 'Terminal differs')
    return packets, {'prefix': prefix, 'seat': seat, 'seed_provenance_only': result['seed'],
                     'frames_sha256': digest(frames_raw), 'original_trace_sha256': trace.hexdigest(),
                     'original_terminal_not_recomputed': result['scores']}


def semantic_state(actor):
    seller = actor.consumer
    return normalized({
        'route': actor.controller.cur,
        'planned': seller.planned,
        'pending': seller.pending,
        'previous': seller.previous,
        'observed_harvests': seller.observed_harvests,
        'seller_diagnostics': seller.diagnostics,
        'seed_events': actor.seed_budget.events,
        'seed_funding': actor.diagnostics.get('seed_funding'),
        'selected': actor.selected,
        'post': actor.post,
        'ready': actor.ready,
    })


def worker(args):
    root = args.root.resolve()
    pins = json.loads(args.pins.read_text())
    before = check_sources(root, pins)
    raw = args.evidence.read_bytes()
    require(digest(raw) == ARCHIVE_SHA, 'Wrong retained evidence ZIP')
    # All modes preload identically for instrumentation. No cold/start or speed
    # conclusion is based on these executions. The actual 1s guard remains active.
    sys.path.insert(0, str(root))
    runtime = load(root / 'titan_runtime.py', 'titan_runtime')
    entry = load(root / 'main.py', 'trace_cache_entry')
    budget_path = root / 'reference/integrated-selected/alder/seed_budget.py'
    budget = runtime.load('_titan_seed_budget', budget_path, cache=True)
    budget._DERIVED_CACHE.clear()
    derived_calls = []
    real_derive = budget._derive
    def counted_derive(routes):
        derived_calls.append(1)
        return real_derive(routes)
    budget._derive = counted_derive
    if args.mode == 'uncached':
        budget._derived = counted_derive
    elif args.mode == 'original':
        old_raw = args.original.read_bytes()
        require(digest(old_raw) == '455024a4179a95ad597492e1f4b94de7bd3bfe7a3a88fd0dce46001f629ec3cd',
                'Original ALDER comparator differs')
        budget.SeedBudget = load(args.original.resolve(), 'trace_cache_original').SeedBudget
    import scheduler
    actual_parent = scheduler.parent.Agent.act
    parent_count = 0
    def count_parent(self, obs):
        nonlocal parent_count
        parent_count += 1
        return actual_parent(self, obs)
    scheduler.parent.Agent.act = count_parent
    init_records = []
    budgets = []
    original_init = budget.SeedBudget.__init__
    def count_init(self, routes):
        original_init(self, routes)
        require(self.events == [], 'New event history is not empty')
        init_records.append({'events_empty_at_init': True,
            'derived_tables_reused': bool(budgets and self.suffixes is budgets[0].suffixes),
            'prefix_table_reused': bool(budgets and self.prefix_lengths is budgets[0].prefix_lengths)})
        budgets.append(self)  # Retain references so object-id recycling cannot fake independence.
    budget.SeedBudget.__init__ = count_init
    cells = []
    with zipfile.ZipFile(args.evidence) as archive:
        manifest = json.loads(archive.read('MANIFEST.json'))['files']
        for name, record in manifest.items():
            data = archive.read(name)
            require(len(data) == record['bytes'] and digest(data) == record['sha256'], 'Input member differs: '+name)
        for prefix, seat in CASES:
            packets, cell = read_case(archive, prefix, seat)
            random.seed(20260907)
            previous_actor = entry._INSTANCE
            start_count = parent_count
            start_derivations = len(derived_calls)
            action_hash, state_hash = hashlib.sha256(), hashlib.sha256()
            row_hashes, original_differences, seed_event_steps, funding_steps = [], [], [], []
            actor = None
            for step, packet in enumerate(packets):
                obs, cfg = packet['observation'], packet['configuration']
                untouched = encoded({'observation': obs, 'configuration': cfg})
                old_calls = parent_count
                action = entry.agent(obs, cfg)
                require(parent_count - old_calls == 1, 'Not exactly one real producer call')
                require(encoded({'observation': obs, 'configuration': cfg}) == untouched, 'Caller input changed')
                require(entry._INSTANCE.diagnostics['status'] == 'completed', 'Incomplete current decision')
                require(entry._INSTANCE.features.seed and entry._INSTANCE.features.funding, 'Default seed/funding disabled')
                if step == 0:
                    actor = entry._INSTANCE
                    require(actor is not previous_actor, 'Step-zero did not reset actor')
                require(entry._INSTANCE is actor and actor.ready, 'Actor reset inside the prefix')
                a, s = encoded(action), encoded(semantic_state(actor))
                action_hash.update(a + b'\n');state_hash.update(s + b'\n')
                row_hashes.append({'step':step,'action':digest(a),'state':digest(s)})
                if action != packet['expected_original_action']:
                    original_differences.append(step)
                if actor.seed_budget.events and actor.seed_budget.events[-1]['step'] == step:
                    seed_event_steps.append(step)
                if actor.diagnostics.get('seed_funding') is not None:
                    funding_steps.append(step)
            cell.update(calls=len(packets), actual_parent_calls=parent_count-start_count,
                derivations=len(derived_calls)-start_derivations,
                actions_sha256=action_hash.hexdigest(), semantic_states_sha256=state_hash.hexdigest(),
                rows=row_hashes, seed_event_steps=seed_event_steps, funding_steps=funding_steps,
                seed_events=actor.seed_budget.events,
                original_frozen_action_difference_steps=original_differences,
                final_route=actor.controller.cur,
                derived_tables_sha256=digest(encoded(normalized((actor.seed_budget.suffixes, actor.seed_budget.prefix_lengths)))))
            cells.append(cell)
            print(json.dumps({'mode':args.mode,'prefix':prefix,'calls':cell['calls'],
                              'derivations':cell['derivations'],'original_differences':original_differences}),flush=True)
    require(len(budgets) == 4 and len({id(b.events) for b in budgets}) == 4, 'Mutable events are shared')
    require(all(cell['calls'] == 719 for cell in cells), 'Incomplete full prefix')
    require(check_sources(root, pins) == before, 'Runtime files changed')
    imported = {}
    for name, module in list(sys.modules.items()):
        path = getattr(module, '__file__', None)
        if path and Path(path).resolve().is_relative_to(root):
            relative = str(Path(path).resolve().relative_to(root))
            require(relative in before, 'Unpinned runtime import: ' + relative)
            imported[name] = relative
    report = {'mode':args.mode,'source_commit':pins['commit'],'source_scope':'exact default-only current source closure; not whole current archive',
        'source_files':before,'imported_runtime':imported,'input_zip_sha256':ARCHIVE_SHA,
        'manifest_files_verified':len(manifest),'cells':cells,'initializations':init_records,
        'total_calls':parent_count,'completed':True,'failures':[], 'new_games':0,
        'interpreter_calls':0,'timing_claim':False,'state_scope':'route, full SELL planned/pending/history/previous/diagnostics, seed events/funding, selected/post/ready; wall/CPU excluded'}
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')


def validate_reports(reports):
    """Require the complete declared matrix before comparing any paired rows."""
    require(isinstance(reports, dict) and set(reports) == set(MODES), 'Missing comparison mode')
    first = reports['cached']
    require(isinstance(first, dict), 'Malformed cached report')
    source = first.get('source_files')
    require(isinstance(source, dict) and source, 'Missing source binding')
    source_ref = first.get('source_commit')
    require(isinstance(source_ref, str) and len(source_ref) == 40 and
            all(c in '0123456789abcdef' for c in source_ref), 'Invalid source ref')
    expected_calls = 719 * len(CASES)
    for mode in MODES:
        report = reports[mode]
        require(isinstance(report, dict) and report.get('mode') == mode, 'Wrong report mode')
        require(report.get('completed') is True and report.get('failures') == [], 'Incomplete worker report')
        require(report.get('source_files') == source and report.get('source_commit') == source_ref,
                'Comparison source identity differs')
        require(report.get('input_zip_sha256') == ARCHIVE_SHA, 'Wrong retained input binding')
        require(type(report.get('total_calls')) is int and report['total_calls'] == expected_calls,
                'Wrong complete parent-call count')
        cells = report.get('cells')
        require(isinstance(cells, list) and len(cells) == len(CASES), 'Incomplete or extra comparison cells')
        initializations = report.get('initializations')
        require(isinstance(initializations, list) and len(initializations) == len(CASES) and
                all(isinstance(row, dict) and row.get('events_empty_at_init') is True
                    for row in initializations), 'Incomplete fresh-event initialization record')
        for cell, (prefix, seat) in zip(cells, CASES):
            require(isinstance(cell, dict) and cell.get('prefix') == prefix and
                    type(cell.get('seat')) is int and cell['seat'] == seat, 'Wrong comparison cell identity')
            require(type(cell.get('calls')) is int and cell['calls'] == 719 and
                    type(cell.get('actual_parent_calls')) is int and cell['actual_parent_calls'] == 719,
                    'Incomplete comparison cell calls')
            rows = cell.get('rows')
            require(isinstance(rows, list) and len(rows) == 719, 'Incomplete per-decision evidence')
            for step, row in enumerate(rows):
                require(isinstance(row, dict) and type(row.get('step')) is int and row['step'] == step,
                        'Noncontiguous per-decision evidence')
                for field in ('action', 'state'):
                    value = row.get(field)
                    require(isinstance(value, str) and len(value) == 64 and
                            all(c in '0123456789abcdef' for c in value), 'Invalid per-decision digest')


def compare(reports):
    validate_reports(reports)
    base = reports['cached']
    checks = []
    for mode in ('uncached','original'):
        other = reports[mode]
        require(other['completed'] and other['source_files'] == base['source_files'], 'Source/mode incomplete')
        for a,b in zip(base['cells'],other['cells']):
            require(a['prefix'] == b['prefix'] and a['rows'] == b['rows'], 'Action/state comparison differs: '+mode+' '+a['prefix'])
            require(a['derived_tables_sha256'] == b['derived_tables_sha256'], 'Derived tables differ')
            checks.append({'mode':mode,'prefix':a['prefix'],'action_state_pairs':len(a['rows']),'matched':True})
    require(sum(c['derivations'] for c in base['cells']) == 1, 'Expected one cached derivation')
    require(sum(c['derivations'] for c in reports['uncached']['cells']) == 4, 'Expected four uncached derivations')
    require([r['derived_tables_reused'] for r in base['initializations']] == [False,True,True,True], 'Cache reuse not exercised')
    return {'complete':True,'checks':checks,'matched_action_state_pairs':sum(r['action_state_pairs'] for r in checks),
        'actual_parent_calls':sum(r['total_calls'] for r in reports.values()),
        'cached_derivations':1,'uncached_derivations':4,'fresh_mutable_event_lists_per_mode':4,
        'new_games':0,'interpreter_calls':0,'timing_claim':False,
        'limits':'Four fixed observation prefixes from two old development regimes, not fresh games or on-policy current outcomes. No cancellation, optional history/ordered modes, whole-archive validation or latency result.'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--evidence',type=Path,required=True)
    ap.add_argument('--pins',type=Path,default=HERE/'SOURCE-PINS.json')
    ap.add_argument('--original',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--mode',choices=MODES)
    args=ap.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.mode:
        worker(args);return
    reports={}
    for mode in MODES:
        out=args.output.with_name(args.output.stem+'-'+mode+'.json')
        command=[sys.executable,'-B',str(Path(__file__).resolve()),'--root',str(args.root.resolve()),
                 '--evidence',str(args.evidence.resolve()),'--pins',str(args.pins.resolve()),
                 '--original',str(args.original.resolve()),'--output',str(out.resolve()),'--mode',mode]
        process=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                               env={**os.environ,'PYTHONHASHSEED':'20260907','PYTHONDONTWRITEBYTECODE':'1'},timeout=90)
        out.with_suffix('.log').write_text(process.stdout)
        require(process.returncode==0,'Worker failed; retained log: '+str(out.with_suffix('.log')))
        reports[mode]=json.loads(out.read_text())
    summary=compare(reports)
    summary.update(source_commit=reports['cached']['source_commit'],input_zip_sha256=ARCHIVE_SHA,
                   report_sha256={m:digest(args.output.with_name(args.output.stem+'-'+m+'.json').read_bytes()) for m in MODES},
                   python=sys.version)
    args.output.write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary,sort_keys=True))

if __name__=='__main__':
    main()
