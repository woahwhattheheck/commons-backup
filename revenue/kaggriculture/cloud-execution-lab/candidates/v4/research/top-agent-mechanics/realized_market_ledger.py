# SPDX-License-Identifier: Apache-2.0
"""Offline realized-order oracle. Never import this into a playing agent.

Executes the unmodified pinned interpreter, temporarily observing primitive
calls. Raw market positions are preserved. Both private states are oracle-only.
Use a dedicated engine module in one thread; hooks are restored even on errors.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any

PINS = {
    'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}
LOADER_PIN = 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e'
HOOKS = ('_process_market', '_parse_order', '_commit_unit', '_do_hire', '_do_buy_land')


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def authenticate(engine_dir: Path, loader_path: Path) -> dict[str, str]:
    """Fail before import/network on missing or changed reference bytes."""
    files = [(engine_dir / name, pin) for name, pin in PINS.items()]
    files.append((loader_path, LOADER_PIN))
    found = {}
    for path, expected in files:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'reference hash mismatch: {path.name}')
        found[path.name] = actual
    return found


def load_engine(engine_dir: Path, loader_path: Path):
    authenticate(engine_dir, loader_path)
    spec = importlib.util.spec_from_file_location('_realized_loader', loader_path)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    engine, _ = loader.get_engine(engine_dir)
    return engine, loader


def new_game(engine, loader, seed: int, **configuration):
    S = loader.Struct
    cfg = S({k: v.get('default') if isinstance(v, dict) else v
             for k, v in engine.specification['configuration'].items()})
    cfg.update(configuration)
    cfg.seed = seed
    env = S(configuration=cfg, done=False, info={})
    state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    return state, env


def _snapshot(farm, private, market):
    return {'cash': farm['money'], 'hands': len(farm['hands']),
            'hires_today': farm['hires_today'], 'land': len(farm['unlocked_quadrants']),
            'shed': dict(private['shed']), 'seeds': dict(private['seeds']),
            'market': dict(market['inventory'])}


def _delta(before, after):
    result = {}
    for key, value in before.items():
        if isinstance(value, dict):
            result[key] = {k: after[key].get(k, 0) - value.get(k, 0)
                           for k in sorted(value.keys() | after[key].keys())
                           if after[key].get(k, 0) != value.get(k, 0)}
        else:
            result[key] = after[key] - value
    return result


def _empty_delta():
    return {'cash': 0, 'hands': 0, 'hires_today': 0, 'land': 0,
            'shed': {}, 'seeds': {}, 'market': {}}


def _add(target, delta):
    for key, value in delta.items():
        if isinstance(value, dict):
            for k, n in value.items():
                target[key][k] = target[key].get(k, 0) + n
                if not target[key][k]:
                    del target[key][k]
        else:
            target[key] += value


class MarketLedger:
    """Observe one interpreter callback, without changing any game operation.

    Not thread-safe. Refuses nested observers and a second use of the object.
    A raised engine error yields no completed receipt, even if some units filled.
    """
    def __init__(self, engine):
        self.engine = engine
        self.rows = []
        self.events = []
        self.complete = False
        self._entered = False
        self._active = False
        self.before = None
        self.after = None
        self.step = None
        self.cap = None

    def __enter__(self):
        if self._entered or getattr(self.engine, '_realized_observer', None) is not None:
            raise RuntimeError('observer already used or engine already observed')
        self._entered = True
        self.original = {name: getattr(self.engine, name) for name in HOOKS}
        self.engine._realized_observer = self
        for name in HOOKS:
            setattr(self.engine, name, getattr(self, name))
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, function in self.original.items():
            setattr(self.engine, name, function)
        del self.engine._realized_observer
        self._active = False
        if exc_type is not None:
            self.complete = False
        return False

    def _process_market(self, state, env):
        if self._active or self.before is not None:
            raise RuntimeError('one market callback per observer')
        self._active = True
        self.step = state[0].observation.get('step', 0)
        self.cap = max(1, int(self.engine.get(env.configuration, 'maxMarketOrdersPerTurn', 10)))
        self.farms = state[0].observation.farms
        self.privates = [s.observation.private for s in state]
        self.market = state[0].observation.market
        self.current = {}
        self.seats = {id(f): i for i, f in enumerate(self.farms)}
        self.before = [self._snap(i) for i in range(2)]
        self.by_position = {}
        lengths = []
        for seat, s in enumerate(state):
            action = s.action if isinstance(s.action, dict) else {}
            raw = action.get('market', [])
            raw = raw if isinstance(raw, list) else []
            lengths.append(min(len(raw), self.cap))
            for slot, order in enumerate(raw):
                row = {'seat': seat, 'slot': slot, 'raw': copy.deepcopy(order),
                       'admitted': slot < self.cap, 'parsed': None,
                       'attempts': 0, 'filled': 0, 'delta': _empty_delta()}
                self.rows.append(row)
                self.by_position[slot, seat] = row
        self.parse_order = iter((slot, seat) for slot in range(max(lengths, default=0))
                                for seat in range(2) if slot < lengths[seat])
        try:
            result = self.original['_process_market'](state, env)
            if next(self.parse_order, None) is not None:
                raise RuntimeError('parser call coverage incomplete')
            self.after = [self._snap(i) for i in range(2)]
            self.complete = True
            return result
        finally:
            self._active = False

    def _snap(self, seat):
        return _snapshot(self.farms[seat], self.privates[seat], self.market)

    def _parse_order(self, raw):
        if not self._active:
            return self.original['_parse_order'](raw)
        position = next(self.parse_order)
        row = self.by_position[position]
        if raw != row['raw']:
            raise RuntimeError('parser call order mismatch')
        parsed = self.original['_parse_order'](raw)
        row['parsed'] = copy.deepcopy(parsed)
        self.current[position[1]] = row
        # Do not return our retained copy: engine mutates remaining in place.
        return parsed

    def _event(self, seat, before, filled, price=None):
        row = self.current[seat]
        delta = _delta(before, self._snap(seat))
        row['attempts'] += 1
        row['filled'] += int(filled)
        _add(row['delta'], delta)
        self.events.append({'seat': seat, 'slot': row['slot'], 'filled': bool(filled),
                            'price': price, 'delta': delta})

    def _commit_unit(self, op, item, price, farm, private, market, shed_capacity=100):
        if not self._active:
            return self.original['_commit_unit'](op, item, price, farm, private, market, shed_capacity)
        seat = self.seats[id(farm)]
        before = self._snap(seat)
        ok = self.original['_commit_unit'](op, item, price, farm, private, market, shed_capacity)
        self._event(seat, before, ok, price)
        return ok

    def _do_hire(self, farm, private, board_size, mult=1):
        if not self._active:
            return self.original['_do_hire'](farm, private, board_size, mult)
        seat = self.seats[id(farm)]
        before = self._snap(seat)
        result = self.original['_do_hire'](farm, private, board_size, mult)
        self._event(seat, before, len(farm['hands']) > before['hands'])
        return result

    def _do_buy_land(self, farm, board_size):
        if not self._active:
            return self.original['_do_buy_land'](farm, board_size)
        seat = self.seats[id(farm)]
        before = self._snap(seat)
        result = self.original['_do_buy_land'](farm, board_size)
        self._event(seat, before, len(farm['unlocked_quadrants']) > before['land'])
        return result

    def report(self):
        if not self.complete or self.after is None:
            raise RuntimeError('no completed market receipt')
        rows = copy.deepcopy(self.rows)
        for row in rows:
            parsed = row['parsed']
            row['requested'] = (parsed.get('remaining', 1) if parsed else None)
            row['status'] = ('clipped' if not row['admitted'] else 'invalid' if parsed is None
                             else 'no_attempt' if not row['attempts'] else 'failed' if not row['filled']
                             else 'filled' if row['filled'] == row['requested'] else 'partial')
        totals = [_empty_delta(), _empty_delta()]
        for row in rows:
            _add(totals[row['seat']], row['delta'])
        # Cash and private assets belong to a seat; market supply belongs to both.
        for seat in range(2):
            observed = _delta(self.before[seat], self.after[seat])
            for key in ('cash', 'hands', 'hires_today', 'land', 'shed', 'seeds'):
                if totals[seat][key] != observed[key]:
                    raise AssertionError(f'unaccounted market {key}, seat {seat}')
        joint = Counter(totals[0]['market'])
        joint.update(totals[1]['market'])
        observed_market = _delta(self.before[0], self.after[0])['market']
        if {k: v for k, v in joint.items() if v} != observed_market:
            raise AssertionError('unaccounted market supply')
        return {'schema': 'titan.realized-market.v1', 'step': self.step, 'cap': self.cap,
                'rows': rows, 'events': copy.deepcopy(self.events), 'totals': totals,
                'market_before': copy.deepcopy(self.before), 'market_after': copy.deepcopy(self.after)}


def audit_transition(engine, state, env):
    """Run actual full interpreter twice; reject altered state or environment.

    Leaves the supplied state/env unchanged. Engine exceptions propagate; they
    never become successful rows or successful parity receipts.
    """
    baseline, env_b = copy.deepcopy((state, env))
    candidate, env_c = copy.deepcopy((state, env))
    engine.interpreter(baseline, env_b)
    with MarketLedger(engine) as ledger:
        engine.interpreter(candidate, env_c)
    if baseline != candidate or env_b != env_c:
        raise AssertionError('instrumented full interpreter parity failed')
    report = ledger.report()
    report['full_state_sha256'] = digest([baseline, env_b])
    report['parity'] = True
    return candidate, env_c, report
