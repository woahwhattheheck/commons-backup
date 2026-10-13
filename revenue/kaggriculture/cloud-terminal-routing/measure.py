"""Paired terminal-routing experiments through the existing official evaluator.

Passive hooks record actual transitions. Policies run in separate, network-denied
processes. This script never uploads, uses Kaggle credentials, or spends money.
"""
from __future__ import annotations
import argparse
import collections
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--seeds', required=True)
    parser.add_argument('--seats', default='0,1')
    parser.add_argument('--opponents', default='arlene,apex')
    parser.add_argument('--variant', choices=['control', 'candidate'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Refusing to overwrite an existing experimental record')
    ev = load(HERE.parent / 'cloud-eval/evaluate.py', 't05_evaluator')
    engine, engine_hashes = ev.get_engine(args.engine_dir)
    runtime = args.runtime.resolve()
    candidate = runtime / ('arlene-adapter.py' if args.variant == 'control' else 't05-adapter.py')
    record = {'variant': args.variant, 'engine_ref': ev.ENGINE_REF,
              'engine_sha256': engine_hashes,
              'evaluator_sha256': digest(ev.__file__),
              'measurement_sha256': digest(__file__),
              'policy_sha256': digest(HERE / 'terminal.py'),
              'entry_sha256': digest(HERE / 'main.py'),
              'parent_sha256': digest(HERE.parent / 'cloud-frontier-policy/next-panel/vendor/arlene.py'),
              'runtime_manifest': json.loads((runtime / 'manifest.json').read_text()),
              'method': 'Unmodified official interpreter with passive hooks; existing process-isolated cloud-eval.play. Fresh complete games, paired by seed/opponent/seat. No hosted rating claim.',
              'games': []}
    original_interpreter = engine.interpreter
    original_commit = engine._commit_unit
    original_unit = engine._apply_unit_action
    for seed in map(int, args.seeds.split(',')):
        for opponent in args.opponents.split(','):
            for seat in map(int, args.seats.split(',')):
                current = {'step': -1, 'farms': {}}
                sales = [collections.Counter(), collections.Counter()]
                cash = [collections.Counter(), collections.Counter()]
                overflow = [collections.Counter(), collections.Counter()]
                history = []
                final = {}
                prefix = hashlib.sha256()
                def commit(op, item, price, farm, private, *a, **kw):
                    result = original_commit(op, item, price, farm, private, *a, **kw)
                    if result and op == 'SELL' and current['step'] >= 698:
                        i = current['farms'][id(farm)]
                        sales[i][item] += 1
                        cash[i][item] += price
                    return result
                def unit(farm, private, index, action, *a, **kw):
                    before = copy.deepcopy(private) if current['step'] >= 698 and action and action[0] == 'DROP' else None
                    result = original_unit(farm, private, index, action, *a, **kw)
                    if before is not None and index < len(before['inventories']):
                        i = current['farms'][id(farm)]
                        for item, n in before['inventories'][index].items():
                            carried_after = private['inventories'][index].get(item, 0)
                            deposited = private['shed'].get(item, 0) - before['shed'].get(item, 0)
                            lost = n - carried_after - deposited
                            if lost > 0:
                                overflow[i][item] += lost
                    return result
                def interpreter(state, env):
                    if state[0].observation.get('farms'):
                        current['farms'] = {id(f): i for i, f in enumerate(state[0].observation.farms)}
                        current['step'] = state[0].observation.get('step', 0)
                        if current['step'] < 698:
                            prefix.update(ev.encoded({'step': current['step'], 'observations': [s.observation for s in state], 'actions': [s.action for s in state]}))
                        else:
                            history.append({'step': current['step'],
                                            'observation': copy.deepcopy(state[seat].observation),
                                            'action': copy.deepcopy(state[seat].action)})
                    result = original_interpreter(state, env)
                    if all(s.status == 'DONE' for s in state):
                        final.update(farms=copy.deepcopy(state[0].observation.farms),
                                     private=[copy.deepcopy(s.observation.private) for s in state])
                    return result
                engine.interpreter, engine._commit_unit, engine._apply_unit_action = interpreter, commit, unit
                rival = runtime / (opponent + '-adapter.py')
                pair = [str(candidate), str(rival)] if seat == 0 else [str(rival), str(candidate)]
                game = ev.play(engine, pair, args.engine_dir, ev.LOADER, seed, seat)
                game.update(opponent=opponent, prefix_sha256=prefix.hexdigest(),
                            terminal_sales_units=sales, terminal_sales_cash=cash,
                            terminal_drop_loss=overflow, terminal=final, final_day=history)
                record['games'].append(game)
                record['summary'] = ev.summarize(record['games'])
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
                print(json.dumps({k: game[k] for k in ('seed', 'opponent', 'candidate_seat', 'status', 'scores', 'failure')}), flush=True)
    print(json.dumps(record['summary']), flush=True)


if __name__ == '__main__':
    main()
