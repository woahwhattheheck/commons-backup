"""Offline receipts for executed market rows in the pinned Kaggriculture engine.

Runs the original interpreter and observes its original mutation functions. No
quantity/request/daily-balance estimator stands in for an executed fill. This is
an analysis tool with both players' private state, never a live-agent feature.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterator

ENGINE_BLOB = '3c202c7ee921da239356789e266b694635103fc4'
SCHEMA = 'titan.market-fill-ledger.v1'
MAP_FIELDS = ('shed', 'seeds', 'market_inventory')
SCALAR_FIELDS = ('money', 'hands', 'hires_today', 'quadrants')
FUNCTIONS = ('_process_market', '_parse_order', '_commit_unit', '_do_hire', '_do_buy_land', '_town_consume', '_end_of_day')


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _resources(farm: dict, private: dict, market: dict) -> dict:
    return {'money': farm['money'], 'hands': len(farm['hands']),
            'hires_today': farm['hires_today'], 'quadrants': len(farm['unlocked_quadrants']),
            'shed': dict(private['shed']), 'seeds': dict(private['seeds']),
            'market_inventory': dict(market['inventory'])}


def _delta(before: dict, after: dict) -> dict:
    out = {key: after[key] - before[key] for key in SCALAR_FIELDS}
    for key in MAP_FIELDS:
        out[key] = {item: after[key].get(item, 0) - before[key].get(item, 0)
                    for item in sorted(before[key].keys() | after[key].keys())
                    if after[key].get(item, 0) != before[key].get(item, 0)}
    return out


def _empty_delta() -> dict:
    return {**dict.fromkeys(SCALAR_FIELDS, 0), **{key: {} for key in MAP_FIELDS}}


def _add_delta(total: dict, part: dict) -> None:
    for key in SCALAR_FIELDS:
        total[key] += part[key]
    for key in MAP_FIELDS:
        for item, value in part[key].items():
            total[key][item] = total[key].get(item, 0) + value
            if total[key][item] == 0:
                del total[key][item]


class MarketFillLedger:
    """One-transition observer. Use one isolated engine module per process.

    Not thread-safe; the module-scoped observer lease rejects nested use. Original
    functions are restored even if the official interpreter raises. The caller
    owns serialization / provenance of replay observations; actions alone do not
    recreate the hidden stock of a historical match.
    """
    def __init__(self, engine: Any):
        source = Path(engine.__file__).read_bytes()
        if git_blob(source) != ENGINE_BLOB:
            raise ValueError('market-fill ledger requires the exact pinned official engine')
        self.engine = engine
        self.original = {name: getattr(engine, name) for name in FUNCTIONS}
        for name, fn in self.original.items():
            if (not hasattr(fn, '__code__') or fn.__code__.co_name != name
                    or Path(fn.__code__.co_filename).resolve() != Path(engine.__file__).resolve()):
                raise ValueError('engine mutation function is already wrapped: ' + name)
        self.records: dict[tuple[int, int], dict] = {}
        self.state = None
        self.env = None
        self.report: dict = {'schema': SCHEMA, 'engine_blob': ENGINE_BLOB,
                            'status': 'not_run', 'rows': [], 'phases': [],
                            'private_analysis_only': True}
        self.market_calls = 0

    def _snapshot(self) -> list[dict]:
        obs = self.state[0].observation
        return [_resources(farm, self.state[seat].observation.private, obs.market)
                for seat, farm in enumerate(obs.farms)]

    def _caller_key(self, frame: Any) -> tuple[int, int]:
        if frame.f_code is not self.original['_process_market'].__code__:
            raise RuntimeError('unexpected official market callsite')
        return int(frame.f_locals['player_id']), int(frame.f_locals['i'])

    def _record_delta(self, key: tuple[int, int], before: dict, after: dict) -> None:
        _add_delta(self.records[key]['delta'], _delta(before, after))

    def _market(self, state: list, env: Any) -> Any:
        self.market_calls += 1
        if self.market_calls != 1:
            raise RuntimeError('one ledger must be used for exactly one transition')
        self.state, self.env = state, env
        cap = max(1, int(self.engine.get(env.configuration, 'maxMarketOrdersPerTurn', 10)))
        self.report.update(step=state[0].observation.get('step', 0), effective_cap=cap)
        for seat, row in enumerate(state):
            action = row.action if isinstance(row.action, dict) else {}
            market = action.get('market', [])
            market = market if isinstance(market, list) else []
            for slot, raw in enumerate(market):
                verb = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], str) else None
                item = raw[1] if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], str) else None
                self.records[seat, slot] = {
                    'seat': seat, 'raw_slot': slot, 'raw': deepcopy(raw),
                    'verb': verb, 'item': item, 'in_cap': slot < cap,
                    'parsed': False, 'requested_units': None, 'attempts': 0,
                    'filled_units': 0, 'failed_attempts': 0, 'quote_counts': {},
                    'fill_price_counts': {}, 'failed_attempt_state': None, 'delta': _empty_delta(),
                    'outcome': 'not_reached' if slot < cap else 'over_cap',
                }
        before = self._snapshot()
        result = self.original['_process_market'](state, env)
        after = self._snapshot()
        per_seat = [_empty_delta(), _empty_delta()]
        aggregate_market: dict[str, int] = {}
        for (seat, _), row in self.records.items():
            _add_delta(per_seat[seat], row['delta'])
            for item, value in row['delta']['market_inventory'].items():
                aggregate_market[item] = aggregate_market.get(item, 0) + value
            if row['parsed']:
                n = row['requested_units']
                row['outcome'] = ('filled' if row['filled_units'] == n else
                                  'partial' if row['filled_units'] else 'unfilled')
        aggregate_market = {k: v for k, v in aggregate_market.items() if v}
        observed = [_delta(a, b) for a, b in zip(before, after)]
        for seat in (0, 1):
            for field in SCALAR_FIELDS + ('shed', 'seeds'):
                if per_seat[seat][field] != observed[seat][field]:
                    raise RuntimeError(f'unreconciled market mutation: seat={seat} field={field}')
        if any(observed[seat]['market_inventory'] != aggregate_market for seat in (0, 1)):
            raise RuntimeError('unreconciled shared market inventory')
        self.report['market_delta'] = observed
        self.report['rows'] = list(self.records.values())
        self.report['market_reconciled'] = True
        return result

    def _parse(self, order: Any) -> Any:
        key = self._caller_key(sys._getframe(1))
        row = self.records[key]
        result = self.original['_parse_order'](order)
        if result is None:
            row['outcome'] = 'invalid'
        else:
            row['parsed'] = True
            row['requested_units'] = result.get('remaining', 1)
        return result

    def _commit(self, op: str, item: str, price: int, farm: dict,
                private: dict, market: dict, shed_capacity: int = 100) -> bool:
        key = self._caller_key(sys._getframe(1))
        before = _resources(farm, private, market)
        ok = self.original['_commit_unit'](op, item, price, farm, private, market, shed_capacity)
        after = _resources(farm, private, market)
        row = self.records[key]
        row['attempts'] += 1
        row['filled_units'] += int(bool(ok))
        row['failed_attempts'] += int(not ok)
        if not ok:
            row['failed_attempt_state'] = {'money': before['money'],
                'shed_total': sum(before['shed'].values()), 'shed_capacity': shed_capacity,
                'available_item': before['shed'].get(item, 0), 'quoted_price': price}
        quote = str(price)
        row['quote_counts'][quote] = row['quote_counts'].get(quote, 0) + 1
        if ok:
            row['fill_price_counts'][quote] = row['fill_price_counts'].get(quote, 0) + 1
        self._record_delta(key, before, after)
        return ok

    def _atomic(self, name: str, key: tuple[int, int], args: tuple) -> Any:
        seat = key[0]
        private = self.state[seat].observation.private
        market = self.state[0].observation.market
        before = _resources(args[0], private, market)
        result = self.original[name](*args)
        after = _resources(args[0], private, market)
        field = 'hands' if name == '_do_hire' else 'quadrants'
        filled = after[field] - before[field]
        row = self.records[key]
        row['attempts'] += 1
        row['filled_units'] += filled
        row['failed_attempts'] += int(not filled)
        if not filled:
            row['failed_attempt_state'] = {'money': before['money'], 'hires_today': before['hires_today'],
                                           'quadrants': before['quadrants']}
        if filled:
            price = str(before['money'] - after['money'])
            row['fill_price_counts'][price] = row['fill_price_counts'].get(price, 0) + 1
        self._record_delta(key, before, after)
        return result

    def _hire(self, *args: Any) -> Any:
        return self._atomic('_do_hire', self._caller_key(sys._getframe(1)), args)

    def _land(self, *args: Any) -> Any:
        return self._atomic('_do_buy_land', self._caller_key(sys._getframe(1)), args)

    def _phase(self, name: str, args: tuple) -> Any:
        before = self._snapshot()
        result = self.original[name](*args)
        after = self._snapshot()
        self.report['phases'].append({'phase': name, 'delta': [_delta(a, b) for a, b in zip(before, after)]})
        return result

    def _town(self, *args: Any) -> Any:
        return self._phase('_town_consume', args)

    def _eod(self, *args: Any) -> Any:
        return self._phase('_end_of_day', args)

    @contextmanager
    def installed(self) -> Iterator['MarketFillLedger']:
        e = self.engine
        if getattr(e, '_fill_ledger_active', False):
            raise RuntimeError('nested market-fill observation on the same engine')
        if any(getattr(e, name) is not fn for name, fn in self.original.items()):
            raise RuntimeError('engine functions changed after observer construction')
        e._fill_ledger_active = True
        replacements = dict(zip(FUNCTIONS, (self._market, self._parse, self._commit,
                                           self._hire, self._land, self._town, self._eod)))
        try:
            for name, fn in replacements.items():
                setattr(e, name, fn)
            yield self
        finally:
            for name, fn in self.original.items():
                setattr(e, name, fn)
            delattr(e, '_fill_ledger_active')

    def run(self, state: list, env: Any) -> dict:
        if self.report['status'] != 'not_run':
            raise RuntimeError('a transition ledger cannot be reused')
        if len(state) != 2:
            raise ValueError('this official market is a two-seat interpreter')
        self.state, self.env = state, env
        self.report['status'] = 'running'
        try:
            with self.installed():
                self.engine.interpreter(state, env)
        except BaseException as error:
            self.report.update(status='engine_or_observer_exception', exception_type=type(error).__name__,
                               rows=list(self.records.values()))
            raise
        self.report['status'] = 'complete' if self.market_calls else 'no_market_transition'
        return self.report


def audit_transition(engine: Any, state: list, env: Any) -> tuple[list, Any, dict]:
    """Return an audited successor, leaving both inputs unmodified.

    Run a pristine twin on an independent deep copy with the SAME complete raw
    action vectors; full state and environment equality is mandatory. Costs are
    outside agent-call timing. No shortened / reconstructed market is executed.
    """
    observed, observed_env = deepcopy((state, env))
    pristine, pristine_env = deepcopy((state, env))
    ledger = MarketFillLedger(engine)
    report = ledger.run(observed, observed_env)
    engine.interpreter(pristine, pristine_env)
    if observed != pristine or observed_env != pristine_env:
        raise RuntimeError('market observer changed the official interpreter result')
    report['pristine_state_env_equal'] = True
    report['successor_sha256'] = fingerprint([observed, observed_env])
    return observed, observed_env, report


def summarize(receipts: list[dict]) -> dict:
    """Aggregate by seat, verb and item, retaining submission and fill denominators."""
    groups: dict[tuple, dict] = {}
    for receipt in receipts:
        if receipt['status'] != 'complete' or not receipt.get('market_reconciled'):
            raise ValueError('only completed reconciled market transitions may be summarized')
        for row in receipt['rows']:
            key = row['seat'], row['verb'], row['item']
            group = groups.setdefault(key, {'seat': key[0], 'verb': key[1], 'item': key[2],
                'submitted_rows': 0, 'admitted_rows': 0, 'parsed_rows': 0,
                'filled_rows': 0, 'requested_units_in_cap': 0, 'filled_units': 0,
                'cash_delta': 0, 'outcomes': {}})
            group['submitted_rows'] += 1
            group['admitted_rows'] += int(row['in_cap'])
            group['parsed_rows'] += int(row['parsed'])
            group['filled_rows'] += int(row['filled_units'] > 0)
            group['requested_units_in_cap'] += row['requested_units'] or 0
            group['filled_units'] += row['filled_units']
            group['cash_delta'] += row['delta']['money']
            outcome = row['outcome']
            group['outcomes'][outcome] = group['outcomes'].get(outcome, 0) + 1
    return {'schema': SCHEMA, 'transitions': len(receipts),
            'groups': sorted(groups.values(), key=lambda row: (row['seat'], str(row['verb']), str(row['item'])))}
