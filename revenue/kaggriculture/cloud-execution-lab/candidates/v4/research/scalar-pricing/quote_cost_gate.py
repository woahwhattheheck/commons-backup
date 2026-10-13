# SPDX-License-Identifier: Apache-2.0
"""Offline, source-pinned scalar quote experiment. NOT a runtime plugin.

The snapshot arm intentionally has a narrower contract than native MarketPath:
its parameters are frozen and both branches are validated at construction.
Never use fixed-fixture parity as permission to install that arm in V4.
"""
from __future__ import annotations

import argparse
import copy
import cProfile
from functools import lru_cache
import gc
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import pstats
import random
import statistics
import sys
import time
from contextlib import contextmanager

NATIVE_PINS = {
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'selected_sell_core.py': 'f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3',
    'reference/decision/decision.py': '2931aa55831204fbb473ab85a6f5b81ec947fcf7',
}
ENGINE_PINS = {
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
    'checks/reference/evaluator/evaluate.py': '1fb6b655bb4ca1e1684be165a8ef513e2e6c2325',
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
}
MODES = ('native', 'amplitude_cache', 'snapshot', 'oracle_table')


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def verify(root: Path, pins: dict[str, str]) -> dict:
    result = {}
    for relative, expected in pins.items():
        data = (root / relative).read_bytes()
        actual = git_blob(data)
        if actual != expected:
            raise ValueError(f'source mismatch: {relative}: {actual} != {expected}')
        result[relative] = {'git_blob': actual, 'sha256': hashlib.sha256(data).hexdigest(),
                            'bytes': len(data)}
    return result


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_native(root: Path):
    root = Path(root).resolve()
    pins = verify(root, NATIVE_PINS)
    mechanics = _load(root / 'mechanics.py', 'prism_native_mechanics')
    sentinel = object()
    previous = sys.modules.get('mechanics', sentinel)
    try:
        sys.modules['mechanics'] = mechanics
        core = _load(root / 'selected_sell_core.py', 'prism_native_core')
    finally:
        if previous is sentinel:
            sys.modules.pop('mechanics', None)
        else:
            sys.modules['mechanics'] = previous
    if core.m is not mechanics:
        raise RuntimeError('native mechanics import isolation failed')
    return mechanics, core, pins


def load_engine(root: Path):
    root = Path(root).resolve()
    pins = verify(root, ENGINE_PINS)
    evaluator = _load(root / 'checks/reference/evaluator/evaluate.py', 'prism_existing_evaluator')
    engine, _ = evaluator.get_engine(root / 'checks/reference/engine',
                                     root / 'checks/reference/evaluator/loader.py')
    return engine, pins


def amplitude_quote(m, item, params):
    """Experimental live-parameter cache; not a general replacement contract.

    Keeps arithmetic order and typed scalar keys, and falls back on replacement
    of market_price or _shape AFTER construction. Arbitrary Python hooks, math
    monkeypatches and nonhashable custom parameters are outside this experiment.
    """
    original, shape = m.market_price, m._shape

    @lru_cache(maxsize=16, typed=True)
    def amplitude(func, base, width, target, gain):
        return target * base / shape(func, width, width)

    def quote(inventory):
        if m.market_price is not original or m._shape is not shape:
            return m.market_price(item, inventory, params)
        p = (params or m.MARKET_PARAMS)[item]
        base, origin, width = p['base'], p['I0'], p['T']
        if inventory < origin:
            func = p['below_func']
            amp = amplitude(func, base, width, p['below_target'], m.HINGE_GAIN)
            price = base + amp * shape(func, origin - inventory, width)
        else:
            func = p['above_func']
            amp = amplitude(func, base, width, p['above_target'], m.HINGE_GAIN)
            price = base - amp * shape(func, inventory - origin, width)
        return max(m.PRICE_FLOOR, int(round(price)))
    return quote


def snapshot_quote(m, item, params):
    """Immutable-curve MICROBENCH arm. Deliberately not native-compatible.

    No reassociation: target*base/denominator, then amp*shape, then base +/-.
    Eager branch normalization and frozen params are intentional negative controls.
    """
    p = copy.deepcopy((params or m.MARKET_PARAMS)[item])
    base, origin, width, floor = p['base'], p['I0'], p['T'], m.PRICE_FLOOR
    shape = m._shape
    below, above = p['below_func'], p['above_func']
    lower = p['below_target'] * base / shape(below, width, width)
    upper = p['above_target'] * base / shape(above, width, width)

    def quote(inventory):
        if inventory < origin:
            price = base + lower * shape(below, origin - inventory, width)
        else:
            price = base - upper * shape(above, inventory - origin, width)
        return max(floor, int(round(price)))
    return quote


def fixtures(m):
    """81 deterministic complete native optimizer inputs, not game episodes."""
    rows = []
    for item in m.PRODUCTS:
        for inventory in (9800, 10000, 10100):
            for rule in ('strict', 'expected_downside', 'minimax_regret'):
                rows.append(dict(item=item, quantity=20, inventory=inventory,
                    params=m._resolve_market_params({}), shops=['BAKERY', 'YARN_STORE'],
                    config={'townShopSellInterval': 4, 'townCenterSellInterval': 24,
                            'sellAcceptanceRule': rule, 'sellDownsideBound': 0},
                    now=120, dates=[120, 124, 132], reference=((132, 20),),
                    rival_quantity=20))
    return rows


@contextmanager
def quote_arm(core, mode, tables=None, *, record=False):
    """Patch one isolated research module only; restore even on interruption."""
    if mode not in MODES:
        raise ValueError(f'unknown arm: {mode}')
    original = core.MarketPath
    cursor = 0
    captured = []

    class Arm(original):
        def __init__(self, item, inventory, params, shops, config, now, end):
            nonlocal cursor
            super().__init__(item, inventory, params, shops, config, now, end)
            if record:
                table = {}
                captured.append(table)
                def raw(inv):
                    value = core.m.market_price(item, inv, params)
                    table[inv] = value
                    return value
            elif mode == 'amplitude_cache':
                raw = amplitude_quote(core.m, item, params)
            elif mode == 'snapshot':
                raw = snapshot_quote(core.m, item, params)
            elif mode == 'oracle_table':
                if tables is None or cursor >= len(tables):
                    raise ValueError('oracle requires the exact traced fixture table')
                # A missing inventory must raise, NEVER query/fill the oracle.
                raw = tables[cursor].__getitem__
            else:
                raw = lambda inv: core.m.market_price(item, inv, params)
            cursor += 1
            self.quote = lru_cache(maxsize=2048)(raw)
    try:
        if mode != 'native' or record:
            core.MarketPath = Arm
        yield captured
        if mode == 'oracle_table' and cursor != len(tables):
            raise ValueError('unused oracle tables: fixture/model count changed')
    finally:
        core.MarketPath = original


def run_panel(core, rows, mode='native', tables=None, *, record=False):
    results, traces = [], []
    with quote_arm(core, mode, tables, record=record) as captured:
        for row in rows:
            trace = []
            def capacity(plan):
                trace.append(tuple(plan))
                return True
            results.append(core.optimize_lot(**row, capacity_ok=capacity))
            traces.append(trace)
    return {'results': results, 'capacity_calls': traces}, captured


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def microbench(m, repetitions=7, count=10000):
    rng = random.Random(19091143)
    inventories = [rng.randrange(9000, 11001) for _ in range(count)]
    report = {}
    for item in m.PRODUCTS:
        funcs = {'native': lambda inv, item=item: m.market_price(item, inv),
                 'amplitude_cache': amplitude_quote(m, item, None),
                 'snapshot': snapshot_quote(m, item, None)}
        expected = [funcs['native'](inv) for inv in inventories]
        raw = {mode: [] for mode in funcs}
        for mode, func in funcs.items():
            if [func(inv) for inv in inventories] != expected:
                raise ValueError(f'microbench parity failed: {item}/{mode}')
        for rep in range(repetitions):
            order = list(funcs)
            order = order[rep % len(order):] + order[:rep % len(order)]
            for mode in order:
                started = time.perf_counter()
                total = sum(map(funcs[mode], inventories))
                elapsed = time.perf_counter() - started
                if total != sum(expected):
                    raise ValueError('microbench changed after parity check')
                raw[mode].append(elapsed)
        medians = {k: statistics.median(v) for k, v in raw.items()}
        report[item] = {'count': count, 'result_sha256': digest(expected),
                        'seconds': raw, 'median_seconds': medians,
                        'speedup_vs_native': {k: medians['native']/v for k,v in medians.items()}}
    return report


def experiment(root: Path, repetitions=7):
    if repetitions < 3:
        raise ValueError('at least three timing repetitions required')
    m, core, pins = load_native(root)
    rows = fixtures(m)
    before = copy.deepcopy(rows)
    baseline, _ = run_panel(core, rows)
    recorded, tables = run_panel(core, rows, record=True)
    if recorded != baseline:
        raise ValueError('recording changed complete optimizer/capacity output')
    for mode in MODES:
        result, _ = run_panel(core, rows, mode, tables)
        if result != baseline:
            raise ValueError(f'complete optimizer/capacity parity failed: {mode}')
    if rows != before:
        raise ValueError('fixture mutation')
    timings = {mode: [] for mode in MODES}
    for rep in range(repetitions):
        order = MODES[rep % len(MODES):] + MODES[:rep % len(MODES)]
        for mode in order:
            gc.collect()  # Outside timing; cyclic GC remains enabled during work.
            started = time.perf_counter()
            result, _ = run_panel(core, rows, mode, tables)
            elapsed = time.perf_counter() - started
            if result != baseline:
                raise ValueError(f'timed output drift: {mode}')
            timings[mode].append(elapsed)
    profiler = cProfile.Profile()
    profiler.enable()
    profiled, _ = run_panel(core, rows)
    profiler.disable()
    if profiled != baseline:
        raise ValueError('profiling changed output')
    stats = pstats.Stats(profiler)
    functions = []
    for (filename, line, name), (primitive, calls, own, cumulative, callers) in stats.stats.items():
        if name in ('optimize_lot', 'score', '_single', '_joint', 'sale_receipts', 'market_price'):
            functions.append({'file': str(Path(filename).relative_to(Path(root).resolve())),
                'line': line, 'name': name, 'calls': calls, 'self_seconds': own,
                'cumulative_seconds': cumulative})
    quote_time = sum(f['cumulative_seconds'] for f in functions if f['name'] == 'market_price')
    fraction = quote_time / stats.total_tt
    medians = {mode: statistics.median(values) for mode, values in timings.items()}
    return {'schema': 'prism-scalar-quote-experiment/v1',
        'disposition': 'NO_RUNTIME_INTEGRATION',
        'limits': ['Constructed optimizer fixtures; no full games or deadline evidence.',
                   'Snapshot arm freezes params and validates unused branches eagerly.',
                   'Oracle table uses baseline traces prepared OUTSIDE the timed region.',
                   'Profile fractions are instrumented cost attribution, not whole-agent bounds.',
                   'Microbench closures are warm; full optimizer timing includes per-model setup.',
                   'No source transformation, feature key, production or archive modification.'],
        'python': sys.version, 'platform': platform.platform(), 'optimized': bool(sys.flags.optimize),
        'source_files': pins, 'fixture_sha256': digest(rows), 'fixtures': len(rows),
        'complete_output_sha256': digest(baseline), 'full_output_and_capacity_parity': True,
        'oracle_tables': len(tables), 'oracle_entries': sum(map(len, tables)),
        'repetitions': repetitions, 'optimizer_seconds': timings, 'optimizer_median_seconds': medians,
        'optimizer_speedup_vs_native': {k: medians['native']/v for k,v in medians.items()},
        'profile': {'total_seconds': stats.total_tt, 'functions': functions,
                    'scalar_quote_fraction': fraction,
                    'profile_only_zero_quote_cost_speedup': 1/(1-fraction)},
        'microbench': microbench(m, repetitions)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repetitions', type=int, default=7)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; choose a new evidence path')
    data = experiment(args.native_root, args.repetitions)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    print(json.dumps({k:data[k] for k in ('disposition','fixtures','full_output_and_capacity_parity',
                                         'optimizer_speedup_vs_native')}, sort_keys=True))


if __name__ == '__main__':
    main()
