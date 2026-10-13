"""Pinned offline native-entrypoint fill census; no network or policy edits."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from market_fill_ledger import audit_transition, fingerprint, git_blob, summarize

PINS = {'engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
        'engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
        'engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
        'evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5'}
MANIFEST_SHA = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
ARCHIVE_SHA = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'

class Struct(dict):
    def __getattr__(self, key):
        try: return self[key]
        except KeyError: raise AttributeError(key) from None
    def __setattr__(self, key, value): self[key] = value

def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None: raise ValueError('cannot load '+str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def load_engine(native):
    reference = Path(native)/'checks/reference'
    for name, expected in PINS.items():
        if git_blob((reference/name).read_bytes()) != expected:
            raise ValueError('reference input mismatch: '+name)
    loader = load_file(reference/'evaluator/loader.py', '_fillproof_pinned_loader')
    engine, _ = loader.get_engine(reference/'engine')
    return engine

def world(engine, seed=17, step=1, **overrides):
    config = {k: (v.get('default') if isinstance(v, dict) else v)
              for k, v in engine.specification['configuration'].items()}
    config.update(seed=seed, **overrides)
    env = Struct(configuration=Struct(config), done=False, info={})
    state = [Struct(observation=Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    for item in state:
        item.observation.step = step
        item.observation.day = step // config['turnsPerDay']
        item.observation.hour = step % config['turnsPerDay']
    return state, env

def verify_native(native, manifest, archive):
    manifest_bytes = Path(manifest).read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA:
        raise ValueError('source manifest mismatch')
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest() != ARCHIVE_SHA:
        raise ValueError('checked archive mismatch')
    runtime = json.loads(manifest_bytes)['runtime']
    for name, record in runtime.items():
        data = (Path(native)/name).read_bytes()
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('native file mismatch: '+name)
    if len(runtime) != 109: raise ValueError('unexpected runtime manifest size')
    return {'archive_sha256': ARCHIVE_SHA, 'manifest_sha256': MANIFEST_SHA, 'verified_runtime_files': len(runtime)}

def play(native, seed, seat):
    engine = load_engine(native)
    main = load_file(Path(native)/'main.py', '_fillproof_native_main')
    state, env = world(engine, seed, step=0)
    receipts, statuses, timings = [], {}, []
    traces = {'actions': hashlib.sha256(), 'states': hashlib.sha256(), 'receipts': hashlib.sha256()}
    for step in range(int(env.configuration.episodeSteps)-1):
        for player in (0, 1):
            obs = deepcopy(state[player].observation)
            obs.step = step
            state[player].observation.step = step
            if player == seat:
                start = time.perf_counter()
                action = main.agent(obs, deepcopy(env.configuration))
                timings.append(time.perf_counter()-start)
                status = getattr(main._INSTANCE, 'diagnostics', {}).get('status', 'missing')
                statuses[status] = statuses.get(status, 0)+1
            else:
                action = engine.starter_agent(obs)
            state[player].action = deepcopy(action)
        traces['actions'].update((fingerprint([row.action for row in state])+'\n').encode())
        state, env, receipt = audit_transition(engine, state, env)
        if receipt['status'] != 'complete': raise RuntimeError('game skipped market transition')
        receipts.append(receipt)
        traces['states'].update((receipt['successor_sha256']+'\n').encode())
        traces['receipts'].update((fingerprint(receipt)+'\n').encode())
    if any(row.status != 'DONE' for row in state): raise RuntimeError('incomplete native game')
    summary = summarize(receipts)
    initial_money = float(env.configuration.startingMoney)
    for player in (0,1):
        ledger_cash = sum(g['cash_delta'] for g in summary['groups'] if g['seat'] == player)
        if initial_money + ledger_cash != state[player].reward:
            raise RuntimeError('whole-game cash does not reconcile to all market rows')
    hours = [0]*int(env.configuration.turnsPerDay)
    phases = {}
    for receipt in receipts:
        for row in receipt['rows']:
            if row['seat'] != seat or row['verb'] not in ('HIRE','BUY_PRODUCT','SELL'): continue
            if row['verb'] == 'HIRE': hours[receipt['step'] % len(hours)] += row['filled_units']
            phase = 'early' if receipt['step'] < 240 else 'middle' if receipt['step'] < 480 else 'late'
            key = (phase,row['verb'],row['item'])
            group = phases.setdefault(key, {'phase':phase, 'verb':row['verb'], 'item':row['item'],
                'submitted_rows':0,'filled_units':0,'cash_delta':0})
            group['submitted_rows'] += 1
            group['filled_units'] += row['filled_units']
            group['cash_delta'] += row['delta']['money']
    interesting = [dict(step=r['step'], **row) for r in receipts for row in r['rows']
                   if row['seat'] == seat and row['verb'] in ('HIRE','BUY_PRODUCT','SELL')
                   and (row['outcome'] != 'filled' or (row['verb'] == 'HIRE' and r['step'] % 24 == 23))]
    return {'scope': 'checked-published-native-archive, not composed V4 or top-team replay',
        'seed': seed, 'native_seat': seat, 'opponent': 'pinned official starter',
        'callbacks': len(receipts), 'official_interpreter_calls': 1+2*len(receipts),
        'full_state_env_pristine_twins_equal': len(receipts), 'statuses': statuses,
        'scores_by_seat': [row.reward for row in state], 'summary': summary,
        'whole_game_market_cash_reconciles': True, 'native_hourly_hire_fills': hours,
        'native_phase_groups': sorted(phases.values(),key=lambda x:(x['phase'],x['verb'],str(x['item']))),
        'action_trace_sha256': traces['actions'].hexdigest(),
        'state_trace_sha256': traces['states'].hexdigest(),
        'receipt_trace_sha256': traces['receipts'].hexdigest(),
        'native_call_max_seconds': max(timings),
        'nonfull_or_eod_hire_witnesses': interesting}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=17)
    parser.add_argument('--seat', type=int, choices=(0,1), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    custody = verify_native(args.native, args.manifest, args.archive)
    result = {'custody': custody, **play(args.native, args.seed, args.seat)}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n')
    print(json.dumps({'output': str(args.output), 'callbacks': result['callbacks'],
                     'statuses': result['statuses'], 'scores': result['scores_by_seat']}, sort_keys=True))

if __name__ == '__main__': main()
