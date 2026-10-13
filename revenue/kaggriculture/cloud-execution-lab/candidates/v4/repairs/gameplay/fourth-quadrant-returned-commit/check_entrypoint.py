# SPDX-License-Identifier: Apache-2.0
"""Isolated actual main.py::agent opening parity; no quadrant engagement claim."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from compose import compose, git_blob

PINS = {
    'SOURCE.json': '8dafbc57595a09eaa8b67e7fc061e60cbcdacc74',
    'main.py': '4a8cf7bcda1f0fea231a144692cb84a779a9e73e',
    'titan_runtime.py': 'b952c9c228ecbde592bf3d2df01638677abb0d24',
    'TITAN-CONFIG.json': '3a3bef83899d3010fad623b628d9e95d9978111b',
    'fourth_quadrant.py': '57ffe172a5a5ebf5b57132319731aa367b9dc7f5',
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec); sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


def worker(package, arm, enabled):
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix='landreturn-opening-') as tmp:
        root = Path(tmp) / 'package'
        shutil.copytree(package, root, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        if arm == 'repaired':
            (root / 'fourth_quadrant.py').write_bytes(compose((root / 'fourth_quadrant.py').read_bytes()))
        features = json.loads((root / 'TITAN-CONFIG.json').read_text())
        features['fourth_quadrant'] = enabled
        (root / 'TITAN-CONFIG.json').write_text(json.dumps(features))
        sys.path.insert(0, str(root))
        entry = load('landreturn_entry', root / 'main.py')
        loader = load('landreturn_loader', root / 'checks/reference/evaluator/loader.py')
        engine, _ = loader.get_engine(root / 'checks/reference/engine')
        records = []
        for seat in (0, 1):
            cfg = loader.Struct({k: v.get('default') if isinstance(v, dict) else v
                                 for k, v in engine.specification['configuration'].items()})
            cfg.seed = 91811
            env = loader.Struct(configuration=cfg, done=False, info={})
            state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0)
                     for _ in range(2)]
            engine.interpreter(state, env)
            for step in range(8):
                for s in state: s.observation.step = step
                output = entry.agent(copy.deepcopy(state[seat].observation), cfg)
                status = entry._INSTANCE.diagnostics.get('status') if entry._INSTANCE else 'no_instance'
                if status != 'completed':
                    raise RuntimeError('opening did not complete: ' + str(status))
                quadrant = entry._INSTANCE.quadrant
                if quadrant is not None and (quadrant.plan is not None or quadrant.events):
                    raise RuntimeError('opening unexpectedly engaged quadrant')
                state[seat].action = output
                state[1-seat].action = engine.starter_agent(copy.deepcopy(state[1-seat].observation))
                engine.interpreter(state, env)
                records.append({'seat': seat, 'step': step, 'action': output, 'status': status,
                                'observations': [copy.deepcopy(s.observation) for s in state]})
        return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--worker', choices=['original', 'repaired'])
    parser.add_argument('--enabled', action='store_true')
    args = parser.parse_args()
    for name, pin in PINS.items():
        if git_blob((args.package / name).read_bytes()) != pin:
            parser.exit(2, 'source drift: ' + name + '\n')
    manifest = json.loads((args.package / 'SOURCE.json').read_text())['runtime']
    for name, item in manifest.items():
        data = (args.package / name).read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            parser.exit(2, 'package member drift: ' + name + '\n')
    if args.worker:
        args.receipt.write_text(json.dumps(worker(args.package, args.worker, args.enabled), sort_keys=True) + '\n')
        return 0
    results = {}; matrices = {}
    with tempfile.TemporaryDirectory() as tmp:
        for enabled in (False, True):
            for arm in ('original', 'repaired'):
                out = Path(tmp) / f'{arm}-{enabled}.json'
                command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + [
                    str(Path(__file__)), '--package', str(args.package.resolve()),
                    '--worker', arm, '--receipt', str(out)] + (['--enabled'] if enabled else [])
                run = subprocess.run(command, capture_output=True, text=True, timeout=40)
                if run.returncode != 0:
                    parser.exit(1, run.stdout + run.stderr)
                records = json.loads(out.read_text())
                key = f'{arm}:fourth_quadrant={enabled}'
                matrices[key] = records
                results[key] = {'callbacks': len(records), 'completed': sum(r['status']=='completed' for r in records),
                                'trace_sha256': hashlib.sha256(out.read_bytes()).hexdigest()}
            if matrices[f'original:fourth_quadrant={enabled}'] != matrices[f'repaired:fourth_quadrant={enabled}']:
                parser.exit(1, 'native opening action/state parity failure\n')
    receipt = {'source_pins': PINS, 'optimization': sys.flags.optimize,
               'runner_blob': git_blob(Path(__file__).read_bytes()), 'arms': results,
               'callbacks': sum(x['callbacks'] for x in results.values()), 'authenticated_runtime_members': len(manifest),
               'parity': True, 'scope': 'actual current main/runtime full dependencies, eight opening callbacks per seat; no fourth-quadrant engagement or full-game/economic gate'}
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
