# SPDX-License-Identifier: Apache-2.0
"""Independent D4 whole-native field census; no policy or activation code.

Use the pinned GitHub workflow ZIP (artifact 10175943272). Each game imports an
independently extracted native main.py in a fresh process. Only frozen_selected.py
may differ, and only when its SHA256 is supplied explicitly. Market instrumentation
runs after the agent's own deadline context and is checked against an uninstrumented
full interpreter transition at EVERY step. This is not the hosted Kaggle runner.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import statistics
import sys
import tarfile
import tempfile
import time
import zipfile

ZIP_SHA = '3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8'
ARCHIVE_SHA = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
ARCHIVE_MEMBER = 'checked-package/exports/titan-current.tar.gz'
ITEM = 'STRAWBERRY'
ENGINE_BLOBS = {
    'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def unpack(artifact, root, candidate=None, candidate_sha=None):
    """Authenticate ALL bytes before importing executable source; extract regulars only."""
    raw = Path(artifact).read_bytes()
    require(sha(raw) == ZIP_SHA, 'artifact SHA256 mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        packed = archive.read(ARCHIVE_MEMBER)
    require(sha(packed) == ARCHIVE_SHA, 'native archive SHA256 mismatch')
    original = {}
    with tarfile.open(fileobj=io.BytesIO(packed), mode='r:gz') as archive:
        for entry in archive.getmembers():
            path = Path(entry.name)
            require(not path.is_absolute() and '..' not in path.parts, 'unsafe member')
            require(entry.isfile(), 'non-regular member')
            require(entry.name not in original, 'duplicate member')
            data = archive.extractfile(entry).read()
            original[entry.name] = sha(data)
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    require(len(original) == 110, 'unexpected package member count')
    if candidate is not None:
        data = Path(candidate).read_bytes()
        require(candidate_sha is not None and sha(data) == candidate_sha,
                'candidate SHA256 mismatch or absent')
        compile(data, 'candidate-frozen-selected', 'exec')
        (root / 'frozen_selected.py').write_bytes(data)
    materialized = {name: sha((root / name).read_bytes()) for name in original}
    changed = [name for name in original if original[name] != materialized[name]]
    require(changed == ([] if candidate is None or candidate_sha == original['frozen_selected.py']
                        else ['frozen_selected.py']), 'unexpected runtime delta')
    return {'original_members': original, 'materialized_members': materialized,
            'changed': changed, 'runtime_members_excluding_SOURCE': 109,
            'original_manifest_sha256': sha(encoded(original)),
            'materialized_manifest_sha256': sha(encoded(materialized))}


def authored_dates(route, now, last, checkpoints, cap):
    """Census only: raw capped, positive authored same-day STRAWBERRY sell dates.

    This deliberately does NOT certify that inventory stays available, a cash
    schedule remains feasible, or selling early is profitable. No mutation.
    """
    end = min(last, (now // 24 + 1) * 24 - 1, len(route) - 1)
    for step in checkpoints:
        if now < step <= end:
            end = step - 1
    result = []
    for step in range(now + 9, end + 1):
        rows = route[step].get('market', [])
        if not isinstance(rows, list):
            continue
        quantity = sum(row[2] for row in rows[:max(1, int(cap))]
                       if isinstance(row, list) and len(row) >= 3
                       and row[:2] == ['SELL', ITEM]
                       and type(row[2]) is int and row[2] > 0)
        if quantity:
            result.append([step, quantity])
    return result


class MarketAudit:
    """Pass-through official market observer, independently parity-checked each turn."""
    def __init__(self, engine, seat):
        self.engine, self.seat = engine, seat
        self.market, self.commit = engine._process_market, engine._commit_unit
        self.farm = None
        self.record = {}

    def process(self, state, env):
        self.farm = state[0].observation.farms[self.seat]
        self.record = {'post_units_stock': state[self.seat].observation.private['shed'].get(ITEM, 0),
                       'fill_units': 0, 'fill_cash': 0}
        return self.market(state, env)

    def unit(self, op, item, price, farm, private, market, shed_capacity=100):
        result = self.commit(op, item, price, farm, private, market, shed_capacity)
        if result and farm is self.farm and op == 'SELL' and item == ITEM:
            self.record['fill_units'] += 1
            self.record['fill_cash'] += price
        return result

    def transition(self, state, env):
        pristine_state, pristine_env = copy.deepcopy((state, env))
        rng = random.getstate()
        self.engine.interpreter(pristine_state, pristine_env)
        reference_rng = random.getstate()
        random.setstate(rng)
        self.engine._process_market, self.engine._commit_unit = self.process, self.unit
        try:
            self.engine.interpreter(state, env)
        finally:
            self.engine._process_market, self.engine._commit_unit = self.market, self.commit
        require(encoded([state, env]) == encoded([pristine_state, pristine_env]),
                'instrumentation changed full official state or environment')
        require(random.getstate() == reference_rng, 'instrumentation changed RNG')
        return dict(self.record)


def game(args):
    require('titan_runtime' not in sys.modules, 'run each native game in a fresh process')
    with tempfile.TemporaryDirectory(prefix='berry-native-') as scratch:
        root = Path(scratch)
        identity = unpack(args.artifact, root, args.candidate, args.candidate_sha)
        sys.path.insert(0, str(root))
        engine_root = root / 'checks/reference/engine'
        for name, expected in ENGINE_BLOBS.items():
            require(blob((engine_root / name).read_bytes()) == expected, 'engine pin: ' + name)
        loader = load(root / 'checks/reference/evaluator/loader.py', 'berry_loader')
        engine, _ = loader.get_engine(engine_root)  # all required files authenticated above
        cfg = loader.Struct({key: value.get('default') if isinstance(value, dict) else value
                             for key, value in engine.specification['configuration'].items()})
        cfg.seed = args.seed
        env = loader.Struct(configuration=cfg, done=False, info={})
        state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0)
                 for _ in range(2)]
        engine.interpreter(state, env)
        main = load(root / 'main.py', 'berry_native_main')
        audit = MarketAudit(engine, args.seat)
        rows, durations = [], []
        own = args.seat
        for step in range(int(cfg.episodeSteps)):
            for s in state:
                s.observation.step = step
            own_obs = copy.deepcopy(state[own].observation)
            before = time.perf_counter()
            action = main.agent(copy.deepcopy(own_obs), copy.deepcopy(cfg))
            durations.append(time.perf_counter() - before)
            require(isinstance(action, dict), 'non-dict native action')
            require(isinstance(action.get('farmer'), list), 'invalid farmer')
            require(isinstance(action.get('hands'), list), 'invalid hands')
            require(isinstance(action.get('market'), list), 'invalid market')
            state[own].action = action
            state[1-own].action = engine.starter_agent(copy.deepcopy(state[1-own].observation))
            instance = main._INSTANCE
            consumer = getattr(instance, 'consumer', None)
            diagnostics = copy.deepcopy(getattr(consumer, 'diagnostics', {}))
            controller = getattr(instance, 'controller', None)
            route = [] if controller is None else controller.R[controller.cur]
            scheduler = sys.modules.get('scheduler')
            checkpoints = [] if scheduler is None else [r[0] for r in scheduler.parent.DECISIONS]
            future = authored_dates(route, step, int(cfg.episodeSteps)-2, checkpoints,
                                    cfg.maxMarketOrdersPerTurn)
            record = audit.transition(state, env)
            row = {'step': step, 'action_sha256': sha(encoded(action)),
                   'state_sha256': sha(encoded([state, env])),
                   'held_before_agent': own_obs.private['shed'].get(ITEM, 0),
                   'price': own_obs.market['prices'].get(ITEM), 'authored_beyond_8': future,
                   'extra_hand_rows': max(0, len(action['hands'])-len(own_obs.farms[own]['hands'])),
                   'dead_market_rows': max(0, len(action['market'])-max(1, int(cfg.maxMarketOrdersPerTurn))),
                   'status': getattr(instance, 'diagnostics', {}).get('status'),
                   'horizon': diagnostics.get('horizon'),
                   'selected_market': copy.deepcopy((getattr(instance, 'selected', None) or {}).get('market', [])),
                   'strawberry_evaluations': [r for r in diagnostics.get('evaluations', [])
                                              if r.get('item') == ITEM], **record}
            if record['post_units_stock'] > 0 or future or row['strawberry_evaluations']:
                row['market'] = copy.deepcopy(action['market'])
            rows.append(row)
            if any(s.status == 'DONE' for s in state):
                env.done = True
                break
        require(len(rows) == int(cfg.episodeSteps)-1, 'incomplete game')
        require([s.status for s in state] == ['DONE', 'DONE'], 'not terminal')
        report = {'seed': args.seed, 'seat': own, 'opponent': 'official_starter',
                  'identity': identity, 'callbacks': len(rows),
                  'official_transitions_including_shadow': len(rows)*2,
                  'official_initializations': 1,
                  'bank': [s.reward for s in state],
                  'margin': state[own].reward-state[1-own].reward,
                  'fallbacks': sum(r['status'] != 'completed' for r in rows),
                  'strawberry': {'held_before_callbacks': sum(r['held_before_agent'] > 0 for r in rows),
                                 'post_units_callbacks': sum(r['post_units_stock'] > 0 for r in rows),
                                 'authored_beyond8_callbacks': sum(bool(r['authored_beyond_8']) for r in rows),
                                 'joint_stock_future_callbacks': sum(r['post_units_stock'] > 0 and bool(r['authored_beyond_8']) for r in rows),
                                 'filled_units': sum(r['fill_units'] for r in rows),
                                 'realized_receipts': sum(r['fill_cash'] for r in rows)},
                  'action_trace_sha256': sha(encoded([r['action_sha256'] for r in rows])),
                  'state_trace_sha256': sha(encoded([r['state_sha256'] for r in rows])),
                  'max_call_seconds': max(durations), 'median_call_seconds': statistics.median(durations),
                  'rows': rows}
        report['funnel'] = funnel(rows)
        validate_report(report)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_bytes(encoded(report) + b'\n')
        print(json.dumps({k: v for k, v in report.items() if k not in ('identity', 'rows')}), flush=True)
        return report


def funnel(rows):
    """Disjoint labels where useful; these counts are NOT an admission certificate."""
    stock = [r for r in rows if r['post_units_stock'] > 0]
    window = [r for r in stock if 12*24 <= r['step'] < 19*24]
    overlap = [r for r in stock if r['authored_beyond_8']]
    uncovered = []
    for row in overlap:
        evaluations = row['strawberry_evaluations']
        if evaluations and any(e['quantity'] > sum(q for _, q in e.get('reference', []))
                               for e in evaluations):
            uncovered.append(row['step'])
    return {'stock_callbacks': len(stock), 'old_midgame_stock_callbacks': len(window),
            'old_midgame_price180_callbacks': sum(r['price'] >= 180 for r in window),
            'stock_and_beyond8_callbacks': len(overlap),
            'stock_and_beyond8_inside_old_window': sum(12*24 <= r['step'] < 19*24 for r in overlap),
            'unallocated_reference_overlap_steps': uncovered,
            'overlap_steps': [r['step'] for r in overlap]}


def validate_report(report):
    rows = report['rows']
    require(report['callbacks'] == 719 and len(rows) == 719, 'incomplete report rows')
    require([r['step'] for r in rows] == list(range(719)), 'nonsequential report')
    require(report['official_transitions_including_shadow'] == 1438, 'missing shadow coverage')
    require(report['fallbacks'] == sum(r['status'] != 'completed' for r in rows),
            'fallback summary inconsistent')
    require(report['action_trace_sha256'] == sha(encoded([r['action_sha256'] for r in rows])),
            'action digest inconsistent')
    require(report['state_trace_sha256'] == sha(encoded([r['state_sha256'] for r in rows])),
            'state digest inconsistent')
    require(len(report['bank']) == 2 and report['seat'] in (0, 1), 'bad seats')
    require(report['margin'] == report['bank'][report['seat']]-report['bank'][1-report['seat']],
            'margin arithmetic inconsistent')
    require(report['strawberry']['filled_units'] == sum(r['fill_units'] for r in rows),
            'sale quantity inconsistent')
    require(report['strawberry']['realized_receipts'] == sum(r['fill_cash'] for r in rows),
            'sale receipts inconsistent')
    identity = report['identity']
    for field in ('original', 'materialized'):
        members = identity[field+'_members']
        require(len(members) == 110, 'source member coverage incomplete')
        require(sha(encoded(members)) == identity[field+'_manifest_sha256'], 'source digest inconsistent')
    changed = [name for name in identity['original_members']
               if identity['original_members'][name] != identity['materialized_members'].get(name)]
    require(changed in ([], ['frozen_selected.py']), 'unauthorized native delta')
    require(changed == identity['changed'], 'misreported native delta')
    encoded(report)  # reject nonfinite values in any nested receipt


def compare(left, right):
    validate_report(left)
    validate_report(right)
    require(left['identity']['original_members'] == right['identity']['original_members'],
            'different native foundations')
    require((left['seed'], left['seat']) == (right['seed'], right['seat']), 'unpaired games')
    require(left['callbacks'] == right['callbacks'], 'unequal game coverage')
    require(left['fallbacks'] == right['fallbacks'] == 0, 'deadline-contaminated comparison')
    changed = [a['step'] for a, b in zip(left['rows'], right['rows'])
               if a['action_sha256'] != b['action_sha256']]
    return {'seed': left['seed'], 'seat': left['seat'], 'action_changes': changed,
            'delta_margin': right['margin']-left['margin'],
            'delta_own': right['bank'][right['seat']]-left['bank'][left['seat']],
            'delta_rival': right['bank'][1-right['seat']]-left['bank'][1-left['seat']],
            'same_state_trace': left['state_trace_sha256'] == right['state_trace_sha256'],
            'same_action_trace': left['action_trace_sha256'] == right['action_trace_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--candidate-sha')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=17)
    parser.add_argument('--seat', type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    if (args.candidate is None) != (args.candidate_sha is None):
        parser.error('--candidate and --candidate-sha must be supplied together')
    game(args)


if __name__ == '__main__':
    main()
