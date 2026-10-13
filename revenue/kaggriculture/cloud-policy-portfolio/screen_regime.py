# SPDX-License-Identifier: Apache-2.0
"""Collect a missing PUBLIC checkpoint regime without observing match outcomes."""
import argparse
import copy
import json
from pathlib import Path
from features import extract
from runtime import HERE, load


def screen(seed):
    ev = load(HERE / 'vendor/cloud-eval/evaluate.py', 't14_screen_eval')
    engine, _ = ev.get_engine(HERE / 'vendor/engine')
    original = engine.interpreter
    evidence = {'seed': seed, 'observed_through_step': 360, 'terminal_label': None, 'early_yarn': False}
    def stop_at_checkpoint(state, env):
        if state[0].observation.get('farms'):
            obs = state[0].observation
            if int(obs['step']) == 226:
                evidence['early_yarn'] = 'YARN_STORE' in obs['town']['unlocked_shops']
            if int(obs['step']) == 360:
                evidence['observation'] = copy.deepcopy(dict(obs))
                evidence['features'] = extract(obs)
                # Stop before applying this action. Configuration keeps the
                # full 720-step horizon so common-prefix actions stay unchanged.
                raise StopIteration('T14 development screening checkpoint')
        return original(state, env)
    engine.interpreter = stop_at_checkpoint
    result = ev.play(engine, [str(HERE / 'controls.py')+'::sell', str(HERE / 'controls.py')+'::arlene'],
                     HERE / 'vendor/engine', ev.LOADER, seed, 0)
    expected = result.get('failure', {}).get('error') == 'StopIteration: T14 development screening checkpoint'
    if not expected:
        raise RuntimeError('Screen did not reach its specified checkpoint: ' + str(result['failure']))
    f = evidence['features']
    evidence['target'] = evidence['early_yarn'] and f['shop_FARMERS_MARKET'] > 0 and f['price_CARROT'] < 42
    evidence['full_game'] = False
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first', type=int, required=True)
    parser.add_argument('--count', type=int, default=16)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in range(args.first, args.first + args.count):
        row = screen(seed)
        rows.append(row)
        args.output.write_text(json.dumps({'status': 'screening', 'rows': rows}, indent=2)+'\n')
        print(seed, row['target'], flush=True)
        if row['target']:
            break
    args.output.write_text(json.dumps({'status': 'complete', 'selection_uses': 'checkpoint features only',
        'selected_seed': rows[-1]['seed'] if rows[-1]['target'] else None, 'rows': rows}, indent=2)+'\n')


if __name__ == '__main__':
    main()
