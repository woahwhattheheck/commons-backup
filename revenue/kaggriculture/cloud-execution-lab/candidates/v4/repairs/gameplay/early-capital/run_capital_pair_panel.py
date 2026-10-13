#!/usr/bin/env python3
"""Pinned native-fixture paired games; consumes the existing isolated evaluator.

Development evidence only. No repository mutation, network, Actions, default
activation, or claim of current-main/hosted equivalence. All variant trees are
copies under a new output directory and differ in early_capital.py alone.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import statistics
import sys

PINS = {
    'main.py': '4a8cf7bcda1f0fea231a144692cb84a779a9e73e',
    'titan_runtime.py': 'b952c9c228ecbde592bf3d2df01638677abb0d24',
    'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
    'operating_stock.py': '781aa90da0d85d0ba23c665e29d6087d182c085e',
    'TITAN-CONFIG.json': '3a3bef83899d3010fad623b628d9e95d9978111b',
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
}
CAPITAL = {'control': '1161859ac5af617eca65aec3f732b5c1396cad37',
           'candidate': 'c87f1d1c9d7b416c5316837634f7e721c85811fa'}
EVALUATOR = '1fb6b655bb4ca1e1684be165a8ef513e2e6c2325'
LOADER = '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5'


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def check(path: Path, expected: str) -> None:
    got = blob(path)
    if got != expected:
        raise ValueError(f'Exact source mismatch: {path}: {got} != {expected}')


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def inventory(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): blob(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def verify_single_delta(control: dict, candidate: dict) -> None:
    if set(control) != set(candidate):
        raise ValueError('Variant path sets differ')
    changed = [p for p in control if control[p] != candidate[p]]
    if changed != ['early_capital.py']:
        raise ValueError(f'Expected only early_capital.py delta, got {changed}')


def write_observer(path: Path, root: Path, destination: Path) -> None:
    # Observation is after the native call. The returned action is never edited.
    # Complete action hashes are checked against an uninstrumented replay below.
    path.write_text('''from pathlib import Path
import hashlib
import json
import sys
sys.path.insert(0, ROOT)
import main as native
ROWS = []
def agent(observation, configuration=None):
    returned = native.agent(observation, configuration)
    instance = native._INSTANCE
    diagnostics = {} if instance is None else instance.diagnostics
    ROWS.append({'step': int(observation['step']),
                 'status': diagnostics.get('status'),
                 'fallback_stage': diagnostics.get('fallback_stage'),
                 'capital': diagnostics.get('early_capital'),
                 'action': returned})
    # Freeze retained receipts even if the producer later reuses its objects.
    ROWS[-1] = json.loads(json.dumps(ROWS[-1], allow_nan=False))
    if int(observation['step']) == int((configuration or {}).get('episodeSteps', 720))-2:
        Path(DESTINATION).write_text(json.dumps(ROWS, separators=(',', ':'), allow_nan=False)+'\\n')
    return returned
'''.replace('ROOT', repr(str(root))).replace('DESTINATION', repr(str(destination))))


def summarize_pairs(plan: list[dict], results: list[dict]) -> dict:
    keyed = {(r['variant'], r['opponent'], r['seed'], r['candidate_seat']): r
             for r in results}
    if len(keyed) != len(results):
        raise ValueError('Duplicate result cell')
    expected = {(r['variant'], r['opponent'], r['seed'], r['seat']) for r in plan}
    if set(keyed) != expected:
        raise ValueError('Missing/unplanned result cell')
    paired = []
    for opponent, seed, seat in sorted({k[1:] for k in expected}):
        old, new = [keyed[(v, opponent, seed, seat)] for v in CAPITAL]
        complete = old['status'] == new['status'] == 'complete'
        row = {'opponent': opponent, 'seed': seed, 'seat': seat,
               'complete': complete, 'control_failure': old.get('failure'),
               'candidate_failure': new.get('failure')}
        if complete:
            own = new['scores'][seat] - old['scores'][seat]
            rival = new['scores'][1-seat] - old['scores'][1-seat]
            old_margin = old['scores'][seat] - old['scores'][1-seat]
            new_margin = new['scores'][seat] - new['scores'][1-seat]
            row.update(delta_own=own, delta_rival=rival, delta_margin=own-rival,
                       control_margin=old_margin, candidate_margin=new_margin,
                       new_loss=old_margin >= 0 and new_margin < 0,
                       lost_win=old_margin > 0 and new_margin <= 0)
        paired.append(row)
    complete = [p for p in paired if p['complete']]
    return {'pairs': paired, 'planned_pairs': len(paired),
            'complete_pairs': len(complete), 'incomplete_pairs': len(paired)-len(complete),
            'mean_delta_own': statistics.mean(p['delta_own'] for p in complete) if complete else None,
            'mean_delta_rival': statistics.mean(p['delta_rival'] for p in complete) if complete else None,
            'mean_delta_margin': statistics.mean(p['delta_margin'] for p in complete) if complete else None,
            'new_losses': sum(p['new_loss'] for p in complete),
            'lost_wins': sum(p['lost_win'] for p in complete)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seeds', default='17,101')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--max-cells', type=int, default=0, help='Pause after this many newly executed games; 0 runs all')
    parser.add_argument('--game-timeout', type=float, default=120)
    args = parser.parse_args()
    seeds = [int(s) for s in args.seeds.split(',')]
    if not seeds or len(seeds) != len(set(seeds)):
        parser.error('Seeds must be a nonempty distinct list')
    if args.max_cells < 0:
        parser.error('max-cells must be nonnegative')
    if not math.isfinite(args.game_timeout) or args.game_timeout <= 0 or args.game_timeout > 600:
        parser.error('game-timeout must be in (0, 600]')
    fixture = args.fixture.resolve(strict=True)
    for rel, sha in PINS.items():
        check(fixture/rel, sha)
    check(args.control, CAPITAL['control'])
    check(args.candidate, CAPITAL['candidate'])
    evaluator_path = fixture/'checks/reference/evaluator/evaluate.py'
    loader = fixture/'checks/reference/evaluator/loader.py'
    engine_dir = fixture/'checks/reference/engine'
    check(evaluator_path, EVALUATOR)
    check(loader, LOADER)
    spec = importlib.util.spec_from_file_location('capital_existing_evaluator', evaluator_path)
    evaluator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = evaluator
    spec.loader.exec_module(evaluator)
    evaluator.verify_sources(engine_dir)
    # Resumption requires the same pinned plan and immutable source trees.
    out = args.output.resolve()
    if out == fixture or fixture in out.parents:
        parser.error('Output must be outside the input fixture')
    if args.resume and not (out/'PLAN.json').is_file():
        parser.error('resume requires an existing PLAN.json')
    if not args.resume:
        out.mkdir(parents=True, exist_ok=False)
    original_manifest = inventory(fixture)
    roots, manifests = {}, {}
    for variant, source in [('control', args.control), ('candidate', args.candidate)]:
        root = out/variant
        if not args.resume:
            shutil.copytree(fixture, root, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            shutil.copyfile(source, root/'early_capital.py')
        roots[variant] = root
        manifests[variant] = inventory(root)
    verify_single_delta(manifests['control'], manifests['candidate'])
    # Alternate variant execution order between cells; identical exact opponent
    # source and role RNG within each pair. This is a DEVELOPMENT panel.
    plan = []
    for op in ('official_starter', 'native_control'):
        for seed in seeds:
            for seat in (0, 1):
                for variant in (tuple(CAPITAL) if seat == 0 else tuple(reversed(CAPITAL))):
                    plan.append({'variant': variant, 'opponent': op, 'seed': seed, 'seat': seat})
    metadata = {'schema': 'titan-capital-native-paired/v1', 'scope': 'development_native_fixture',
                'fixture_tree': original_manifest, 'fixture_tree_sha256': digest(original_manifest),
                'variant_trees': manifests,
                'variant_tree_sha256': {v: digest(m) for v,m in manifests.items()},
                'sole_source_delta': 'early_capital.py', 'plan': plan,
                'agent_rng_seed': 20260907, 'engine_ownership': 'serial',
                'game_timeout': args.game_timeout, 'action_rpc_timeout': 1.0,
                'python': sys.version, 'runner_blob': blob(Path(__file__)),
                'no_current_main_claim': True, 'no_promotion': True}
    if args.resume:
        if json.loads((out/'PLAN.json').read_text()) != metadata:
            raise ValueError('Plan, runner, fixture, or variant tree drift on resume')
    else:
        dump(out/'PLAN.json', metadata)  # Written before any game outcome.
    plan_digest = digest(metadata)
    new_cells = 0

    def execute(cell: dict, *, observed: bool = True) -> dict | None:
        nonlocal new_cells
        variant, op, seed, seat = [cell[k] for k in ('variant','opponent','seed','seat')]
        label = f'{variant}-{op}-{seed}-{seat}' + ('' if observed else '-uninstrumented')
        saved = out/(label+'-result.json')
        if saved.exists():
            result = json.loads(saved.read_text())
            expected = {'variant':variant, 'opponent':op, 'seed':seed, 'candidate_seat':seat, 'observed':observed, 'plan_sha256':plan_digest}
            if any(result.get(k) != v for k,v in expected.items()):
                raise ValueError('Saved result does not match planned cell: '+label)
            telemetry_record = result.get('telemetry')
            if observed and result.get('status') == 'complete':
                if not isinstance(telemetry_record, dict):
                    raise ValueError('Completed observed cell lacks telemetry: '+label)
                expected_path = label+'-actions.json'
                if telemetry_record.get('path') != expected_path:
                    raise ValueError('Unexpected telemetry path: '+label)
                check(out/expected_path, telemetry_record['blob'])
            return result  # Retain failures; never silently retry them.
        if args.max_cells and new_cells >= args.max_cells:
            return None
        new_cells += 1
        root = roots[variant]
        observer = out/(label+'-observer.py')
        telemetry = out/(label+'-actions.json')
        write_observer(observer, root, telemetry)
        own = str(observer) if observed else str(root/'main.py')
        other = 'official_starter' if op == 'official_starter' else str(roots['control']/'main.py')
        engine, _ = evaluator.get_engine(engine_dir, loader)
        pair = [own, other] if seat == 0 else [other, own]
        result = evaluator.play(engine, pair, engine_dir, loader, seed, seat,
                                rng_seed=20260907, game_timeout=args.game_timeout)
        result.update(variant=variant, opponent=op, observed=observed, plan_sha256=plan_digest)
        if observed and telemetry.exists():
            rows = json.loads(telemetry.read_text())
            capital = [r['capital'] for r in rows if isinstance(r.get('capital'), dict)]
            reasons = {}
            for report in capital:
                reason = report.get('reason')
                reasons[reason] = reasons.get(reason, 0)+1
            result['telemetry'] = {'path': telemetry.name, 'blob': blob(telemetry),
                                   'callbacks': len(rows), 'capital_callbacks': len(capital),
                                   'capital_changed': sum(bool(r.get('changed')) for r in capital),
                                   'capital_reasons': reasons,
                                   'fallback_callbacks': sum(r['status'] == 'deadline_fallback' for r in rows)}
        else:
            result['telemetry'] = None
        if observed and result['status'] == 'complete' and result['telemetry'] is None:
            raise ValueError('Completed observed game did not write its terminal telemetry')
        dump(out/(label+'-result.json'), result)
        print(json.dumps({k:result[k] for k in ('variant','opponent','seed','candidate_seat','status','scores','failure')},sort_keys=True),flush=True)
        return result

    # Serial ownership prevents global engine/module/RNG races. Unfinished cells
    # are explicit, and a failed finished cell is retained rather than retried.
    results = []
    for cell in plan:
        result = execute(cell)
        if result is None:
            dump(out/'PROGRESS.json', {'plan_sha256':plan_digest, 'status':'partial',
                  'completed_cell_records':len(results), 'planned_cell_records':len(plan),
                  'observer_parity_complete':False})
            return 3
        results.append(result)
    parity = []
    for variant in CAPITAL:
        first = next(c for c in plan if c['variant'] == variant)
        actual = next(r for r in results if (r['variant'],r['opponent'],r['seed'],r['candidate_seat']) ==
                      (variant,first['opponent'],first['seed'],first['seat']))
        plain = execute(first, observed=False)
        if plain is None:
            dump(out/'PROGRESS.json', {'plan_sha256':plan_digest, 'status':'partial',
                  'completed_cell_records':len(results), 'planned_cell_records':len(plan),
                  'observer_parity_complete':False})
            return 3
        parity.append({'variant':variant,
                       'same_complete_trace_and_scores': actual['status'] == plain['status'] == 'complete'
                        and actual['scores'] == plain['scores'] and actual['trace_sha256'] == plain['trace_sha256'],
                       'observed_trace':actual['trace_sha256'], 'plain_trace':plain['trace_sha256']})
    stable = inventory(fixture) == original_manifest and all(inventory(roots[v]) == m for v,m in manifests.items())
    report = {'plan_sha256':digest(metadata), 'results':results,
              'paired':summarize_pairs(plan, results), 'observer_parity':parity,
              'source_trees_unchanged':stable, 'scope':'development fixture; not current-main promotion'}
    dump(out/'RESULTS.json',report)
    dump(out/'PROGRESS.json', {'plan_sha256':plan_digest,'status':'complete','completed_cell_records':len(results),'planned_cell_records':len(plan),'observer_parity_complete':True})
    return int(not stable or report['paired']['incomplete_pairs'] > 0 or
               not all(p['same_complete_trace_and_scores'] for p in parity))

if __name__ == '__main__':
    raise SystemExit(main())
