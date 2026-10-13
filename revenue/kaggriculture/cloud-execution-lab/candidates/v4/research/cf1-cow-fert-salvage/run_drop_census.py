# SPDX-License-Identifier: Apache-2.0
"""Execute the CF1 DROP proposal on exact R01 tapes without a runtime materializer.

This is an explicitly HISTORICAL FIXED-TAPE panel, not current TITAN or a field
strength test. The engine, reference tapes, helper, opponents and panel plan are
pinned in output. Every activated action gets a full same-state engine check;
OFF/ON games continue separately to expose later cash/capacity effects.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

from check_eod_drop_fert import Struct, git_blob, load_engine, load_helper, normal_state

TAPES_BLOB = 'a43289b9cc5e34a2481fddf652762a7d92f427ef'
ENGINE_BLOB = '3c202c7ee921da239356789e266b694635103fc4'
DEFAULT_SEEDS = [9600803, 9600821, 9600823, 9600841, 9600847, 9600863, 9600871, 9600893]


def load_tapes(path):
    """Use the existing exact R01 decoder; do not create another tape format."""
    path = Path(path)
    if git_blob(path.read_bytes()) != TAPES_BLOB:
        raise ValueError('R01 source identity mismatch')
    spec = importlib.util.spec_from_file_location('kestrel_exact_r01_tapes', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_tapes()


def _dumps(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def prove_local(engine, state, env, proposed, seat):
    baseline, candidate = copy.deepcopy(state), copy.deepcopy(state)
    candidate[seat].action = copy.deepcopy(proposed)
    base_env, cand_env = copy.deepcopy(env), copy.deepcopy(env)
    engine.interpreter(baseline, base_env)
    engine.interpreter(candidate, cand_env)
    base, cand = normal_state(baseline), normal_state(candidate)
    delta = cand[seat].observation.private['shed']['FERTILIZER'] - base[seat].observation.private['shed']['FERTILIZER']
    cand[seat].observation.private['shed']['FERTILIZER'] -= 1
    if delta != 1 or cand != base or cand_env != base_env:
        raise ValueError('accepted proposal violates full-state +1-fertilizer certificate')


def play(engine, helper, tape, seed, seat, opponent, enabled):
    cfg = Struct({key: value.get('default') if isinstance(value, dict) else value
                  for key, value in engine.specification['configuration'].items()})
    cfg.seed = seed
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    trace = hashlib.sha256()
    activations = []
    counts = {'callbacks': 0, 'eod_callbacks': 0, 'colocated_harvest_water_pairs': 0}
    rival_agent = engine.agents[opponent]
    for step, authored in enumerate(tape):
        for entry in state:
            entry.observation.step = step
        state[seat].action = copy.deepcopy(authored)
        state[1-seat].action = rival_agent(copy.deepcopy(state[1-seat].observation))
        observation = state[seat].observation
        farm = observation.farms[seat]
        positions = [farm['farmer'], *farm['hands']]
        units = [authored.get('farmer', ['PASS']), *authored.get('hands', [])]
        counts['callbacks'] += 1
        if step % 24 == 23:
            counts['eod_callbacks'] += 1
        for h, row in enumerate(units[:len(positions)]):
            if row != ['HARVEST']:
                continue
            for w in range(h+1, min(len(units), len(positions))):
                if units[w] == ['WATER'] and positions[h] == positions[w]:
                    counts['colocated_harvest_water_pairs'] += 1
        original = state[seat].action
        before = copy.deepcopy(original)
        proposed = helper.apply_eod_drop_fert_salvage(original, observation, cfg, enabled=enabled)
        if original != before or (not enabled and proposed is not original):
            raise ValueError('input mutation or nonidentity OFF path')
        if proposed is not original:
            if proposed.get('market') != original.get('market'):
                raise ValueError('proposal changed market')
            after_units = [proposed['farmer'], *proposed['hands']]
            changed = [i for i, pair in enumerate(zip(units, after_units)) if pair[0] != pair[1]]
            if len(changed) != 1:
                raise ValueError('proposal did not change exactly one unit')
            actor = changed[0]
            prove_local(engine, state, env, proposed, seat)
            x, y = positions[actor]
            activations.append({'step': step, 'actor': actor, 'position': [x, y],
                                'from': units[actor], 'to': after_units[actor],
                                'cow_fed': farm['tiles'][y][x]['fed_today'],
                                'cow_cared': farm['tiles'][y][x]['cared_today'],
                                'carried': dict(observation.private['inventories'][actor]),
                                'same_state_extra_fertilizer': 1})
        state[seat].action = proposed
        engine.interpreter(state, env)
        trace.update(_dumps({'step': step, 'actions': [s.action for s in state],
                             'cash': [f['money'] for f in state[0].observation.farms]}).encode())
    if len(tape) != 719 or any(s.status != 'DONE' for s in state):
        raise ValueError('incomplete episode')
    cash = [float(f['money']) for f in state[0].observation.farms]
    if not all(math.isfinite(value) for value in cash):
        raise ValueError('nonfinite cash')
    return {'own_cash': cash[seat], 'rival_cash': cash[1-seat],
            'margin': cash[seat]-cash[1-seat], 'activations': activations,
            'final_own_shed': dict(state[seat].observation.private['shed']),
            'counts': counts, 'trace_sha256': trace.hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--tapes', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('drop_continuation.py'))
    parser.add_argument('--seeds', default=','.join(map(str, DEFAULT_SEEDS)))
    parser.add_argument('--opponents', default='pass,starter')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        seeds = [int(value) for value in args.seeds.split(',')]
        opponents = args.opponents.split(',')
        if (not seeds or len(seeds) != len(set(seeds)) or any(seed < 0 for seed in seeds)
                or not opponents or len(opponents) != len(set(opponents))
                or any(op not in ('pass', 'starter') for op in opponents)):
            raise ValueError('invalid explicit panel')
        engine, helper = load_engine(args.engine_dir), load_helper(args.source)
        tapes = load_tapes(args.tapes)
        plan = {'schema': 'titan-cf1-drop-fixed-tape-panel/v1',
                'scope': 'historical_fixed_R01_tapes_NOT_current_runtime_NOT_field_strength',
                'engine_git_blob': ENGINE_BLOB, 'tapes_git_blob': TAPES_BLOB,
                'helper_git_blob': git_blob(args.source.read_bytes()),
                'original_cf1_git_blob': '3f6697c7825ea39b84a00767088eb52f2ba2903f',
                'runner_git_blob': git_blob(Path(__file__).read_bytes()),
                'python': sys.version, 'seeds': seeds, 'seats': [0, 1],
                'opponents': opponents, 'tapes': list(range(13)), 'episode_callbacks': 719}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        plan_path = args.output.with_suffix('.plan.json')
        plan_path.write_text(json.dumps(plan, indent=2, allow_nan=False)+'\n')
        results = []
        partial_path = args.output.with_suffix('.partial.jsonl')
        partial_path.write_text('')
        for opponent in opponents:
            for seed in seeds:
                for tape_id, tape in enumerate(tapes):
                    for seat in (0, 1):
                        baseline = play(engine, helper, tape, seed, seat, opponent, False)
                        candidate = play(engine, helper, tape, seed, seat, opponent, True)
                        results.append({'opponent': opponent, 'seed': seed, 'tape': tape_id, 'seat': seat,
                                        'baseline': baseline, 'candidate': candidate,
                                        'delta_own': candidate['own_cash']-baseline['own_cash'],
                                        'delta_rival': candidate['rival_cash']-baseline['rival_cash'],
                                        'delta_margin': candidate['margin']-baseline['margin']})
                        with partial_path.open('a') as progress:
                            progress.write(_dumps(results[-1])+'\n')
                print(f'completed opponent={opponent} seed={seed} pairs={len(results)}', flush=True)
        summary = {'paired_games': len(results), 'episodes': 2*len(results),
                   'callbacks': 2*719*len(results),
                   'activations': sum(len(row['candidate']['activations']) for row in results),
                   'activated_games': sum(bool(row['candidate']['activations']) for row in results),
                   'cash_improved_games': sum(row['delta_margin'] > 0 for row in results),
                   'cash_regressed_games': sum(row['delta_margin'] < 0 for row in results),
                   'min_delta_margin': min(row['delta_margin'] for row in results),
                   'max_delta_margin': max(row['delta_margin'] for row in results),
                   'sum_delta_margin': sum(row['delta_margin'] for row in results),
                   'baseline_colocated_harvest_water_pairs': sum(row['baseline']['counts']['colocated_harvest_water_pairs'] for row in results)}
        output = {'plan': plan, 'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                  'summary': summary, 'results': results,
                  'promotion': False, 'current_runtime_executed': False,
                  'caveat': 'PASS/starter are diagnostic opponents, not a competitive opponent field. A later evaluator needs current routed runtime and opponent-diverse held-out games.'}
        args.output.write_text(json.dumps(output, sort_keys=True, indent=2, allow_nan=False)+'\n')
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'CF1 DROP census failed: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
