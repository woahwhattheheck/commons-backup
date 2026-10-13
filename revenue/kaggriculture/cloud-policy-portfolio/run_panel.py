# SPDX-License-Identifier: Apache-2.0
"""Paired full games through the unchanged process-isolated official evaluator."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import gzip
import hashlib
import json
from pathlib import Path
import time
from features import extract
from runtime import HERE, load


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_game(job):
    arm, opponent, seed, seat, directory, split = job
    out = Path(directory)
    game_id = f'{arm}-{opponent}-{seed}-seat{seat}'
    path = out / (game_id + '.json')
    if path.exists():
        return json.loads(path.read_text())
    ev = load(HERE / 'vendor/cloud-eval/evaluate.py', 't14_game_eval')
    engine, hashes = ev.get_engine(HERE / 'vendor/engine')
    original = engine.interpreter
    checkpoints = {}
    prefix = hashlib.sha256()
    trace_path = out / (game_id + '.jsonl.gz')
    with gzip.open(trace_path, 'wt') as trace:
        def observed(state, env):
            if not state[0].observation.get('farms'):
                return original(state, env)
            step = int(state[seat].observation['step'])
            obs = copy.deepcopy(dict(state[seat].observation))
            actions = [copy.deepcopy(s.action) for s in state]
            if step in (0, 360):
                checkpoints[str(step)] = {'features': extract(obs), 'observation': obs,
                    'observation_sha256': hashlib.sha256(encoded(obs)).hexdigest(),
                    'observed_at_step': step, 'available_before_action': True}
            if step < 360:
                prefix.update(encoded({'step': step, 'actions': actions}))
            result = original(state, env)
            cash = [float(s.observation.farms[i]['money']) for i, s in enumerate(state)]
            trace.write(json.dumps({'step': step, 'candidate_seat': seat, 'observation': obs,
                                    'actions': actions, 'post_cash': cash,
                                    'done': all(s.status == 'DONE' for s in state)}, separators=(',', ':')) + '\n')
            return result
        engine.interpreter = observed
        specs = [str(HERE / 'controls.py') + '::' + opponent] * 2
        specs[seat] = str(HERE / 'controls.py') + '::' + arm
        result = ev.play(engine, specs, HERE / 'vendor/engine', ev.LOADER, seed, seat)
    result.update(id=game_id, arm=arm, opponent=opponent, panel=split,
                  label_observed_at_step=718 if result['status'] == 'complete' else None,
                  checkpoints=checkpoints, prefix_before_360_sha256=prefix.hexdigest(),
                  trace_file=trace_path.name, trace_file_sha256=digest(trace_path),
                  engine_ref=ev.ENGINE_REF, engine_sha256=hashes,
                  evaluator_sha256=digest(ev.__file__), source_model_sha256=digest(HERE / 'model.json'))
    if result['status'] == 'complete':
        own, rival = result['scores'][seat], result['scores'][1-seat]
        result.update(own_cash=own, rival_cash=rival, margin=own-rival,
                      outcome='W' if own > rival else 'L' if own < rival else 'T')
    path.write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', nargs='+', type=int, required=True)
    parser.add_argument('--arms', nargs='+', default=['sell', 'carrot_sell'])
    parser.add_argument('--opponents', nargs='+', default=['arlene', 'apex', 'sale_cadence', 'crop_demand', 'labor_cadence'])
    parser.add_argument('--seats', nargs='+', type=int, default=[0, 1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--panel', choices=['development', 'validation', 'diagnostic'], required=True)
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = [(arm, rival, seed, seat, str(args.output.resolve()), args.panel)
            for seed in args.seeds for rival in args.opponents for seat in args.seats for arm in args.arms]
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_game, job) for job in jobs]
        for f in as_completed(futures):
            row = f.result()
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ('id', 'status', 'outcome', 'own_cash', 'rival_cash', 'failure', 'wall_seconds')}), flush=True)
    report = {'panel': args.panel, 'complete': all(r['status'] == 'complete' for r in rows),
              'games': sorted(rows, key=lambda r: r['id']), 'count': len(rows),
              'seeds': args.seeds, 'arms': args.arms, 'opponents': args.opponents}
    (args.output / 'panel.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
