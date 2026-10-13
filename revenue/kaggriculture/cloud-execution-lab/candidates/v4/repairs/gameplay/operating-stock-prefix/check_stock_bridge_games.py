# SPDX-License-Identifier: Apache-2.0
"""One isolated full native game; consumes stock_bridge's exact peer modules.

No source downloads or hosted uploads. Output is exclusive. Run baseline/plain,
baseline/shadow, composed/shadow, and composed/release as distinct processes.
All raw action rows, including surplus hands and dead market slots, reach the
unmodified official interpreter. No test-driver action sanitization is allowed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
import time

from stock_bridge import StockProbe, blob, compose, peers, ENGINE

ENGINE_INPUTS = {
    'kaggriculture.py': ENGINE,
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def run(source: Path, seed: int, seat: int, variant: str, probe_mode: str, *, gameplay=None, stock_off=False):
    if variant not in ('baseline', 'composed') or probe_mode not in ('plain', 'shadow', 'release'):
        raise ValueError('unsupported isolated variant')
    if seat not in (0, 1):
        raise ValueError('seat must be 0 or 1')
    if any(name in sys.modules for name in ('titan_runtime', 'operating_stock', 'scheduler')):
        raise ValueError('native modules already imported; use a fresh process')
    source = source.resolve()
    engine_root = source / 'checks/reference/engine'
    for name, expected in ENGINE_INPUTS.items():
        if blob((engine_root / name).read_bytes()) != expected:
            raise ValueError('engine input drift: ' + name)
    dependency_map = {str(p.relative_to(source)): blob(p.read_bytes()) for p in sorted(source.rglob('*'))
                      if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    peer_modules = peers(gameplay)
    # All composition occurs in an ephemeral test copy, never a production path.
    with tempfile.TemporaryDirectory(prefix='titan-stockbridge-test-') as temporary:
        root = Path(temporary) / 'runtime'
        shutil.copytree(source, root, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        composition = None
        if variant == 'composed':
            stock_bytes, runtime_bytes, composition = compose(
                (root/'operating_stock.py').read_bytes(), (root/'titan_runtime.py').read_bytes(), gameplay)
            (root/'operating_stock.py').write_bytes(stock_bytes)
            (root/'titan_runtime.py').write_bytes(runtime_bytes)
        if stock_off:
            config = json.loads((root/'TITAN-CONFIG.json').read_text())
            config['operating_stock'] = False
            (root/'TITAN-CONFIG.json').write_text(json.dumps(config))
        sys.path.insert(0, str(root))
        loader = load(root/'checks/reference/evaluator/loader.py', '_stockbridge_engine_loader')
        engine, engine_hashes = loader.get_engine(root/'checks/reference/engine')
        main = load(root/'main.py', '_stockbridge_main')
        import operating_stock as stock
        probe = StockProbe(peer_modules['terminal'], release=probe_mode == 'release')
        context = nullcontext() if probe_mode == 'plain' else probe.installed(stock)
        cfg = loader.Struct({key: value.get('default') if isinstance(value, dict) else value
                             for key, value in engine.specification['configuration'].items()})
        cfg.seed = seed
        random.seed(seed)
        env = loader.Struct(configuration=cfg, done=False, info={})
        state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        engine.interpreter(state, env)
        trace = hashlib.sha256()
        statuses, terminal = Counter(), []
        calls = []
        started = time.perf_counter()
        with context:
            for step in range(int(cfg.episodeSteps)):
                for player, current in enumerate(state):
                    current.observation.step = step
                    visible = deepcopy(current.observation)
                    if player == seat:
                        begin = time.perf_counter()
                        current.action = main.agent(visible, cfg)
                        calls.append(time.perf_counter()-begin)
                        instance = main._INSTANCE
                        diagnostic = instance.diagnostics if instance is not None else {}
                        statuses[str(diagnostic.get('status', 'instance_absent'))] += 1
                        if 672 <= step <= 694:
                            terminal.append({'step': step, 'action': deepcopy(current.action),
                                'status': diagnostic.get('status'),
                                'feed_stock': deepcopy(diagnostic.get('feed_stock')),
                                'operating_stock': deepcopy(diagnostic.get('operating_stock'))})
                    else:
                        current.action = engine.starter_agent(visible)
                action = deepcopy([s.action for s in state])
                engine.interpreter(state, env)
                frame = {'step': step, 'actions': action, 'observations': [s.observation for s in state],
                         'status': [s.status for s in state], 'rewards': [s.reward for s in state]}
                trace.update(json_bytes(frame) + b'\n')
                if any(s.status == 'DONE' for s in state):
                    env.done = True
                    break
        return {
            'schema': 'titan-stockbridge-game/v1', 'variant': variant, 'probe_mode': probe_mode,
            'operating_stock_off_test_control': stock_off, 'seed': seed, 'seat': seat,
            'opponent': 'pinned official starter', 'steps': step+1, 'status': [s.status for s in state],
            'bank': [s.reward for s in state], 'margin': state[seat].reward-state[1-seat].reward,
            'full_raw_action_and_state_sha256': trace.hexdigest(),
            'native_statuses': dict(statuses), 'helper_call_counts': dict(probe.counts),
            'helper_events': probe.events, 'terminal_returned_action_window': terminal,
            'elapsed_seconds': time.perf_counter()-started, 'max_call_seconds': max(calls),
            'composition': composition, 'engine_sha256': engine_hashes,
            'source_map': dependency_map, 'source_map_sha256': hashlib.sha256(json_bytes(dependency_map)).hexdigest(),
            'executed_main_blob': blob((root/'main.py').read_bytes()),
            'executed_runtime_blob': blob((root/'titan_runtime.py').read_bytes()),
            'executed_stock_blob': blob((root/'operating_stock.py').read_bytes()),
            'executed_config_blob': blob((root/'TITAN-CONFIG.json').read_bytes()),
            'scope': 'Full archived native entrypoint and pinned interpreter, NOT latest-main/all-lane or hosted evidence',
            'promotion_authorized': False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--gameplay', type=Path)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--seat', type=int, choices=(0, 1), required=True)
    parser.add_argument('--variant', choices=('baseline', 'composed'), required=True)
    parser.add_argument('--probe', choices=('plain', 'shadow', 'release'), default='shadow')
    parser.add_argument('--stock-off', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Claim exclusive result path before spending compute, never clobber receipts.
    with args.output.open('x') as stream:
        result = run(args.source, args.seed, args.seat, args.variant, args.probe,
                     gameplay=args.gameplay, stock_off=args.stock_off)
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('variant', 'probe_mode', 'seed', 'seat', 'steps',
        'bank', 'margin', 'native_statuses', 'helper_call_counts', 'elapsed_seconds')}), flush=True)


if __name__ == '__main__':
    main()
