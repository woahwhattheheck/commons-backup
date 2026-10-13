# SPDX-License-Identifier: Apache-2.0
"""T08 full-game arms using the unchanged existing official evaluator."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--arm', required=True)
    p.add_argument('--seeds', required=True)
    p.add_argument('--engine-dir', type=Path, required=True)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location('t08_eval', HERE.parent/'cloud-eval/evaluate.py')
    ev = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ev
    spec.loader.exec_module(ev)
    engine, hashes = ev.get_engine(a.engine_dir)
    candidate = str(HERE/'arms'/f'{a.arm}.py')
    report = {'arm': a.arm, 'engine_ref': ev.ENGINE_REF, 'engine_sha256': hashes,
              'evaluator_sha256': ev.sha256(ev.__file__),
              'source_files': {str(f.relative_to(HERE)): ev.sha256(f)
                               for f in sorted(HERE.rglob('*.py'))}, 'games': []}
    if a.output.exists():
        raise ValueError('Refusing to overwrite an existing panel')
    for seed in map(int, a.seeds.split(',')):
        for opponent in ('arlene', 'apex'):
            other = str(a.runtime/(opponent+'-adapter.py'))
            for seat in (0, 1):
                pair = [candidate, other] if seat == 0 else [other, candidate]
                game = ev.play(engine, pair, a.engine_dir, ev.LOADER, seed, seat)
                game['opponent'] = opponent
                report['games'].append(game)
                report['summary'] = ev.summarize(report['games'])
                a.output.parent.mkdir(parents=True, exist_ok=True)
                a.output.write_text(json.dumps(report, indent=2)+'\n')
                print(json.dumps({'arm': a.arm, 'seed': seed, 'opponent': opponent,
                                  'seat': seat, 'game': game}), flush=True)

if __name__ == '__main__':
    main()
