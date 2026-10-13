# SPDX-License-Identifier: Apache-2.0
"""Shadow-census existing CF1 against an authenticated native TITAN package.

This is a local exploration driver, not the Kaggle runner or an economic gate.
It never executes the legacy materializer or submits the shadow action. Raw
hand and market rows go unchanged to the original interpreter: overlong hand
PLANT rows can affect atomic seed admission even without an executable actor.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
ARCHIVE_SHA256 = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
HELPER_BLOB = 'ef6ab6e795375cf84c5dc7d0bcd43f979bbd0af8'
DEFAULT_SEEDS = (9172031, 9172033, 9172037, 9172041)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def authenticate(root, helper):
    """Verify the whole 109-file declared package before importing any of it."""
    root, helper = Path(root).resolve(), Path(helper)
    raw = (root / 'SOURCE.json').read_bytes()
    if digest(raw) != SOURCE_SHA256:
        raise ValueError('SOURCE.json is not the pinned current-package manifest')
    source = json.loads(raw)
    members = source['runtime']
    if len(members) != 109:
        raise ValueError('unexpected runtime member count')
    pins = {}
    for relative, expected in sorted(members.items()):
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('member is a symlink or escapes runtime: ' + relative)
        data = path.read_bytes()
        if len(data) != expected['bytes'] or digest(data) != expected['sha256']:
            raise ValueError('runtime member mismatch: ' + relative)
        pins[relative] = {'bytes': len(data), 'sha256': digest(data), 'git_blob': git_blob(data)}
    for path in root.rglob('*.py'):
        if path.relative_to(root).as_posix() not in members:
            raise ValueError('undeclared Python source: ' + str(path))
    raw_helper = helper.read_bytes()
    if helper.is_symlink() or git_blob(raw_helper) != HELPER_BLOB:
        raise ValueError('CF1 helper is not the existing canonical donor')
    return {'source_manifest_sha256': SOURCE_SHA256,
            'mapped_archive_sha256': ARCHIVE_SHA256,
            'archive_bytes_checked': False,
            'runtime_members_checked': len(pins), 'members': pins,
            'helper_git_blob': HELPER_BLOB, 'helper_sha256': digest(raw_helper)}


def load_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError('cannot load ' + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def shadow(helper, action, obs, cfg):
    """Execute exact helper ON/OFF, but never change the returned parent action."""
    before = canonical([action, obs, cfg])
    if helper.apply_cow_fert_salvage(action, obs, cfg) is not action:
        raise ValueError('CF1 default-OFF identity violated')
    target = helper.apply_cow_fert_salvage.__code__
    lines = []
    old = sys.getprofile()

    def profiler(frame, event, value):
        if frame.f_code is target and event == 'return':
            lines.append(frame.f_lineno)

    try:
        sys.setprofile(profiler)
        transformed = helper.apply_cow_fert_salvage(action, obs, cfg, enabled=True, completed_service=False)
    finally:
        sys.setprofile(old)
    if canonical([action, obs, cfg]) != before:
        raise ValueError('CF1 shadow mutated parent action, observation or configuration')
    if len(lines) != 1:
        raise ValueError('CF1 return-line observation incomplete')
    return transformed, lines[0]


def observation_census(helper, obs, action):
    """Descriptive counts, never alternate CF1 admission logic."""
    counts = Counter(callbacks=1)
    farm = obs['farms'][obs['player']]
    tiles = farm['tiles']
    positions = [farm['farmer'], *farm['hands']]
    rows = [action.get('farmer', ['PASS']), *action.get('hands', [])]
    extras = action.get('hands', [])[len(farm['hands']):]
    if extras:
        counts['extra_hand_callbacks'] = 1
        counts['extra_hand_rows'] = len(extras)
        counts['extra_hand_plant_rows'] = sum(isinstance(r, list) and len(r) >= 2
                                              and r[0] == 'PLANT' for r in extras)
    cows = [t for row in tiles for t in row
            if isinstance(t, dict) and t.get('animal') == 'COW']
    counts['cow_tile_callbacks'] = len(cows)
    counts['cow_callbacks'] = int(bool(cows))
    eod = obs['step'] <= 695 and obs['step'] % 24 == 23
    if eod:
        counts['eligible_hour_callbacks'] = 1
        counts['eligible_hour_cow_tiles'] = len(cows)
        counts['ready_cow_tiles_at_eligible_hour'] = sum(
            helper._ready_cow(tile, obs['step'] // 24) for tile in cows)
        for position, command in zip(positions, rows):
            x, y = position
            tile = tiles[y][x]
            verb = command[0] if isinstance(command, list) and command else '<empty>'
            counts['eligible_hour_verb:' + str(verb)] += 1
            if isinstance(tile, dict) and tile.get('animal') == 'COW':
                counts['eligible_hour_cow_verb:' + str(verb)] += 1
                if verb == 'HARVEST':
                    counts['cow_harvest_rows_at_eligible_hour'] += 1
                    counts['ready_cow_harvest_rows_at_eligible_hour'] += int(
                        helper._ready_cow(tile, obs['step'] // 24))
    return counts


def execute_cell(root, helper_path, seed, seat):
    authentication = authenticate(root, helper_path)
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    helper = load_at('_cf1_exact_helper', helper_path)
    loader = load_at('_cf1_exact_loader', root / 'checks/reference/evaluator/loader.py')
    engine, _ = loader.get_engine(root / 'checks/reference/engine')
    parent = load_at('_cf1_native_parent', root / 'main.py')
    cfg = loader.Struct({key: value.get('default') if isinstance(value, dict) else value
                         for key, value in engine.specification['configuration'].items()})
    cfg.seed = seed
    if not helper._standard(cfg):
        raise ValueError('official default configuration is outside CF1 guard')
    env = loader.Struct(configuration=cfg, done=False, info={})
    state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    if env.info.get('seed') != seed or cfg.get('seed') is not None:
        raise ValueError('official seed resolution/scrubbing contract failed')
    counts, returns, statuses = Counter(shadow_activations=0), Counter(), Counter()
    daily, witnesses, extra_first = [], [], None
    action_tape = hashlib.sha256()
    started = time.perf_counter()
    for step in range(cfg.episodeSteps):
        # Both policies receive only preturn public state and their own private state.
        for i, player_state in enumerate(state):
            player_state.observation.step = step
            obs = copy.deepcopy(player_state.observation)
            if i == seat:
                action = parent.agent(obs, cfg)
                if not isinstance(action, dict):
                    raise ValueError('parent returned a non-dict action')
                instance = parent._INSTANCE
                status = (getattr(instance, 'diagnostics', {}) or {}).get('status', 'no_instance')
                statuses[status] += 1
                # The helper sees the complete returned action. No row truncation.
                transformed, line = shadow(helper, action, obs, cfg)
                returns[str(line)] += 1
                current = observation_census(helper, obs, action)
                counts.update(current)
                action_tape.update((canonical({'step': step, 'action': action}) + '\n').encode())
                if current['extra_hand_rows'] and extra_first is None:
                    extra_first = {'step': step, 'public_hands': len(obs['farms'][seat]['hands']),
                                   'action': copy.deepcopy(action)}
                if transformed is not action:
                    counts['shadow_activations'] += 1
                    witnesses.append({'seed': seed, 'seat': seat, 'step': step,
                                      'observation': copy.deepcopy(obs), 'parent_action': copy.deepcopy(action),
                                      'shadow_action': transformed, 'return_line': line})
                if step <= 695 and step % 24 == 23:
                    farm = obs['farms'][seat]
                    daily.append({'step': step, 'counts': dict(current), 'return_line': line,
                                  'parent_action': copy.deepcopy(action),
                                  'positions': [farm['farmer'], *farm['hands']],
                                  'private': copy.deepcopy(obs['private']),
                                  'actor_tiles': [copy.deepcopy(farm['tiles'][y][x])
                                                  for x, y in [farm['farmer'], *farm['hands']]],
                                  'ready_cow_sites': [dict(x=x, y=y, tile=copy.deepcopy(tile))
                                      for y, row in enumerate(farm['tiles']) for x, tile in enumerate(row)
                                      if helper._ready_cow(tile, step // 24)],
                                  'money': farm['money']})
                # Deliberately submit ONLY the unmodified action returned by the parent.
                player_state.action = action
            else:
                player_state.action = engine.starter_agent(obs)
        engine.interpreter(state, env)
        if any(s.status == 'DONE' for s in state):
            env.done = True
            break
    bank = [s.reward for s in state]
    complete = step == 718 and all(s.status == 'DONE' for s in state)
    if any(not isinstance(x, (float, int)) or not math.isfinite(x) for x in bank):
        raise ValueError('nonfinite final bank')
    return {'schema': 1, 'seed': seed, 'seat': seat, 'opponent': 'official_starter',
            'mode': 'shadow_only_parent_actions_submitted', 'complete': complete,
            'python': platform.python_version(), 'optimized': sys.flags.optimize,
            'counts': dict(counts), 'return_lines': dict(returns),
            'parent_statuses': dict(statuses), 'final_status': [s.status for s in state],
            'final_step': step, 'bank': bank, 'own_cash': bank[seat], 'rival_cash': bank[1-seat],
            'margin': bank[seat] - bank[1-seat], 'action_tape_sha256': action_tape.hexdigest(),
            'elapsed_seconds': time.perf_counter() - started,
            'resolved_episode_seed': env.info['seed'], 'agent_configuration_seed': cfg.get('seed'),
            'source_manifest_sha256': authentication['source_manifest_sha256'],
            'helper_git_blob': HELPER_BLOB, 'eligible_hour_details': daily,
            'first_extra_hand_witness': extra_first, 'activation_witnesses': witnesses}


def reduce_panel(plan, cells):
    expected = {(row['seed'], row['seat']) for row in plan['cells']}
    if not expected or len(expected) != len(plan['cells']):
        raise ValueError('empty or duplicate planned cells')
    seen, errors = set(), []
    counts, returns, statuses = Counter(), Counter(), Counter()
    compact = []
    for row in cells:
        key = (row.get('seed'), row.get('seat'))
        if key not in expected or key in seen:
            raise ValueError('unexpected or duplicate result cell')
        seen.add(key)
        if 'error' in row:
            errors.append({'seed': key[0], 'seat': key[1], 'reason': 'execution_error', 'error': row['error']})
            continue
        if (row.get('source_manifest_sha256') != SOURCE_SHA256
                or row.get('helper_git_blob') != HELPER_BLOB
                or row.get('opponent') != 'official_starter'
                or row.get('mode') != 'shadow_only_parent_actions_submitted'
                or row.get('resolved_episode_seed') != key[0]
                or row.get('agent_configuration_seed') is not None):
            errors.append({'seed': key[0], 'seat': key[1], 'reason': 'provenance_or_mode'})
            continue
        if (row.get('complete') is not True or row.get('counts', {}).get('callbacks') != 719
                or row.get('final_step') != 718 or row.get('final_status') != ['DONE', 'DONE']):
            errors.append({'seed': key[0], 'seat': key[1], 'reason': 'incomplete', 'error': row.get('error')})
            continue
        counts.update(row['counts']); returns.update(row['return_lines']); statuses.update(row['parent_statuses'])
        compact.append({k: row[k] for k in ['seed', 'seat', 'own_cash', 'rival_cash', 'margin',
                                           'action_tape_sha256', 'counts', 'parent_statuses']})
    missing = sorted(expected - seen)
    complete = not missing and not errors and len(compact) == len(expected)
    return {'schema': 1, 'panel_complete': complete, 'expected_cells': len(expected),
            'completed_cells': len(compact), 'missing_cells': missing, 'errors': errors,
            'verdict': ('INCOMPLETE' if not complete else
                        'PARK_ON_THIS_PANEL' if not counts['shadow_activations'] else
                        'ENGAGED_NEEDS_PAIRED_ECONOMICS'),
            'counts': dict(counts), 'return_lines': dict(returns), 'parent_statuses': dict(statuses),
            'cells': compact, 'limits': ['official_starter only; not opponent-diverse',
                       'shadow actions never executed; no CF1 economic gain measured',
                       'native current package, not legacy R04 or hosted Kaggle',
                       'zero engagement is limited to this named panel']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory; never overwrite evidence')
    parser.add_argument('--seeds', type=int, nargs='+', default=list(DEFAULT_SEEDS))
    parser.add_argument('--seats', type=int, choices=(0, 1), nargs='+', default=[0, 1])
    parser.add_argument('--cell', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    helper = Path(__file__).with_name('r04_cow_fert_salvage.py')
    try:
        if args.cell:
            seed, seat = map(int, args.cell.split(':'))
            if seat not in (0, 1):
                raise ValueError('invalid seat')
            row = execute_cell(args.runtime, helper, seed, seat)
            with args.output.open('x') as stream:
                stream.write(json.dumps(row, sort_keys=True, indent=2, allow_nan=False) + '\n')
            return 0 if row['complete'] else 2
        if len(set(args.seeds)) != len(args.seeds) or len(set(args.seats)) != len(args.seats):
            raise ValueError('duplicate seed or seat')
        auth = authenticate(args.runtime, helper)
        args.output.mkdir(parents=True, exist_ok=False)
        plan = {'schema': 1, 'kind': 'exploratory_natural_engagement', 'opponent': 'official_starter',
                'cells': [{'seed': seed, 'seat': seat} for seed in args.seeds for seat in args.seats],
                'authentication': auth, 'python': platform.python_version(), 'optimized': sys.flags.optimize,
                'driver_sha256': digest(Path(__file__).read_bytes())}
        (args.output / 'PLAN.json').write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n')
        cells = []
        for cell in plan['cells']:
            seed, seat = cell['seed'], cell['seat']
            file = args.output / f'cell-{seed}-{seat}.json'
            command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + [
                str(Path(__file__).resolve()), '--runtime', str(args.runtime.resolve()),
                '--output', str(file.resolve()), '--cell', f'{seed}:{seat}']
            try:
                proc = subprocess.run(command, text=True, capture_output=True, timeout=120)
                (args.output / f'cell-{seed}-{seat}.log').write_text(proc.stdout + proc.stderr)
                if proc.returncode != 0 or not file.is_file():
                    raise RuntimeError(f'cell subprocess exited {proc.returncode}: {proc.stderr[-1500:]}')
                row = json.loads(file.read_text())
            except (subprocess.TimeoutExpired, RuntimeError, OSError, ValueError) as error:
                row = {**cell, 'complete': False, 'error': str(error)}
                if not file.exists():
                    file.write_text(json.dumps(row, indent=2) + '\n')
            cells.append(row)
            print(canonical({'seed': seed, 'seat': seat, 'complete': row.get('complete'),
                             'counts': row.get('counts'), 'error': row.get('error')}), flush=True)
        result = reduce_panel(plan, cells)
        result['plan_sha256'] = digest((args.output / 'PLAN.json').read_bytes())
        (args.output / 'RESULTS.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        print(canonical({'verdict': result['verdict'], 'counts': result['counts']}), flush=True)
        return 0 if result['panel_complete'] else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('CF1 census error: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
