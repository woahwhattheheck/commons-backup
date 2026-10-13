# SPDX-License-Identifier: Apache-2.0
"""Source-pinned EOD market externality probe; not a policy or runtime installer.

The router dependency is ONLY the official PRODUCTS constant. Full H3c and EOD
helper bytes and the full official interpreter execute; no router/native-agent
integration, natural engagement, or whole-game performance is claimed.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import types
from typing import Any, Callable

PINS = {
    'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
    'r04_eod_capacity_rescue.py': '9ad4092453e2332b0914f90ca89791b18f2229c2',
    'h3c_goose_eod_cap_rescue.py': '79c3fd029054a2db5931609db06f6b9aa4d4be3c',
}
NEUTRAL_MARKET = frozenset(('HIRE', 'BUY_LAND', 'BUY_SEED'))
BUYABLE_PRODUCTS = frozenset(('WHEAT', 'FERTILIZER'))


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def authenticated(path: Path) -> bytes:
    data = path.read_bytes()
    expected = PINS.get(path.name)
    if expected is None or git_blob(data) != expected:
        raise ValueError(f'source pin mismatch: {path}')
    return data


@contextlib.contextmanager
def module_bindings(bindings):
    missing = object()
    previous = {name: sys.modules.get(name, missing) for name in bindings}
    sys.modules.update(bindings)
    try:
        yield
    finally:
        for name, old in previous.items():
            if old is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def module_from_bytes(name, data, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    with module_bindings({name: module}):
        exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def floor_envelope(engine, observation, parent, candidate, configuration):
    """Public-only sufficient certificate for ZERO incremental market supply.

    Requires an already-validated whole-vector rescue of cargo-neutral work.
    It is NOT a substitute for that helper's private-state/legality guards.
    For an extra SELL at raw slot j and quantity q, prior rival BUY_PRODUCT rows
    can withdraw at most capacity*j units; before its last quote the concurrent
    rival row can withdraw at most q-1 more. Non-buyable products cannot have a
    rival withdrawal at all. Check EVERY integer inventory in that envelope,
    not just the observed price or a monotonic-price assumption.
    """
    def reject(reason):
        return {'certified': False, 'reason': reason, 'rows': []}
    if not all(isinstance(x, dict) for x in (observation, parent, candidate, configuration)):
        return reject('mapping_required')
    cap = configuration.get('shedCapacity')
    limit = configuration.get('maxMarketOrdersPerTurn')
    if type(cap) is not int or cap != 100 or type(limit) is not int or limit != 10:
        return reject('standard_capacity_and_raw_limit_required')
    before, after = parent.get('market'), candidate.get('market')
    if not isinstance(before, list) or not isinstance(after, list):
        return reject('market_lists_required')
    if not len(before) < len(after) <= limit or after[:len(before)] != before:
        return reject('append_only_executable_rescue_required')
    if parent.get('farmer') != candidate.get('farmer') or parent.get('hands') != candidate.get('hands'):
        return reject('unit_action_change')
    for row in before:
        if not isinstance(row, list) or (row and (not isinstance(row[0], str) or row[0] not in NEUTRAL_MARKET)):
            return reject('nonneutral_prefix')
    market = observation.get('market')
    if not isinstance(market, dict) or not isinstance(market.get('inventory'), dict):
        return reject('public_inventory_required')
    rows = []
    seen = set()
    for slot, row in enumerate(after[len(before):], start=len(before)):
        if not isinstance(row, list) or len(row) != 3 or row[0] != 'SELL':
            return reject('sell_vector_required')
        _, product, quantity = row
        if not isinstance(product, str) or product not in engine.PRODUCTS or product in seen:
            return reject('unique_known_products_required')
        if type(quantity) is not int or not 0 < quantity <= cap:
            return reject('bounded_positive_quantity_required')
        seen.add(product)
        inventory = market['inventory'].get(product)
        if type(inventory) is not int:
            return reject('integer_public_inventory_required')
        withdrawals = cap * slot + quantity - 1 if product in BUYABLE_PRODUCTS else 0
        try:
            prices = [engine.market_price(product, inventory - d, market.get('params'))
                      for d in range(withdrawals + 1)]
        except (TypeError, ValueError, KeyError, OverflowError, ZeroDivisionError):
            return reject('price_evaluation_failed')
        rows.append({'product': product, 'quantity': quantity, 'raw_slot': slot,
                     'withdrawal_bound': withdrawals, 'minimum_inventory': inventory - withdrawals,
                     'maximum_sale_price': max(prices)})
    return {'certified': all(row['maximum_sale_price'] == 1 for row in rows),
            'reason': 'all_quotes_floor' if all(row['maximum_sale_price'] == 1 for row in rows)
                      else 'floor_can_break', 'rows': rows}


class Harness:
    """Execute real initialized interpreter transitions with constructed states."""
    def __init__(self, engine_dir: Path, overlay_dir: Path):
        paths = {name: (engine_dir if name in ('kaggriculture.py', 'kaggriculture.json', 'utils.py')
                        else overlay_dir) / name for name in PINS}
        data = {name: authenticated(path) for name, path in paths.items()}
        self.sources = {name: {'git_blob': git_blob(b), 'sha256': hashlib.sha256(b).hexdigest(),
                               'bytes': len(b)} for name, b in data.items()}
        # Only the upstream seed helper is needed from utils; its actual AST is
        # compiled from authenticated bytes, not replaced by a bespoke RNG.
        tree = ast.parse(data['utils.py'])
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'resolve_episode_seed')
        ns = {'Any': Any, 'Callable': Callable, 'random': random}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(paths['utils.py']), 'exec'), ns)
        package = types.ModuleType('kaggle_environments')
        utils = types.ModuleType('kaggle_environments.utils')
        utils.resolve_episode_seed = ns['resolve_episode_seed']
        with module_bindings({'kaggle_environments': package, 'kaggle_environments.utils': utils}):
            self.engine = module_from_bytes('eod_official_engine', data['kaggriculture.py'], paths['kaggriculture.py'])
        # The engine reads its adjacent JSON at import. Check it again so a changed
        # specification is a hard failure, never a silently different experiment.
        if paths['kaggriculture.json'].read_bytes() != data['kaggriculture.json']:
            raise ValueError('engine specification changed during import')
        self.h3c = module_from_bytes('eod_h3c_fixture', data['h3c_goose_eod_cap_rescue.py'], paths['h3c_goose_eod_cap_rescue.py'])
        self.constants = types.ModuleType('r04_full_router')
        self.constants.PRODUCTS = tuple(self.engine.PRODUCTS)
        self.bindings = {'h3c_goose_eod_cap_rescue': self.h3c, 'r04_full_router': self.constants}
        with module_bindings(self.bindings):
            self.lane = module_from_bytes('eod_rescue_fixture', data['r04_eod_capacity_rescue.py'], paths['r04_eod_capacity_rescue.py'])
        self.interpreter_calls = 0

    def pair(self, *, seat=0, product='FERTILIZER', inventory=10493, quantity=8,
             slot=0, rival_kind='buy100', seed=20260911, cargo=None, shed=None):
        if type(seat) is not int or seat not in (0, 1) or type(slot) is not int or not 0 <= slot <= 9:
            raise ValueError('invalid paired cell')
        e = self.engine
        cfg = Struct({k: (v.get('default') if isinstance(v, dict) else v)
                      for k, v in e.specification['configuration'].items()})
        cfg.seed = seed
        env = Struct(configuration=cfg, done=False, info={})
        state = [Struct(observation=Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        e.interpreter(state, env)
        self.interpreter_calls += 1
        for i, s in enumerate(state):
            s.observation.step = 119
            s.observation.day, s.observation.hour = 4, 23
            s.observation.farms[i]['money'] = 1000000
        obs = state[seat].observation
        obs.market['inventory'][product] = inventory
        e._refresh_prices(obs.market)
        obs.private['shed'] = copy.deepcopy(shed if shed is not None else {product: 100})
        obs.private['inventories'] = copy.deepcopy(cargo if cargo is not None else [{product: quantity}])
        obs.farms[seat]['hands'] = [[4, 5] for _ in obs.private['inventories'][1:]]
        rival = 1 - seat
        if rival_kind == 'pass':
            orders = []
        elif rival_kind in ('buy1', 'buy8', 'buy100'):
            orders = [['BUY_PRODUCT', product, int(rival_kind[3:])]]
        elif rival_kind == 'delayed_buy':
            orders = [[] for _ in range(slot)] + [['BUY_PRODUCT', product, 100]]
        elif rival_kind == 'sell100':
            state[rival].observation.private['shed'] = {product: 100}
            orders = [['SELL', product, 100]]
        elif rival_kind == 'roundtrip':
            orders = [['BUY_PRODUCT', product, 100], ['SELL', product, 100]] * 5
        else:
            raise ValueError('unknown rival profile')
        parent = {'farmer': ['PASS'], 'hands': [['PASS'] for _ in obs.farms[seat]['hands']],
                  'market': [[] for _ in range(slot)]}
        before = copy.deepcopy((parent, obs, cfg))
        with module_bindings(self.bindings):
            candidate = self.lane.apply_eod_capacity_rescue(parent, obs, cfg, enabled=True)
            if self.lane.apply_eod_capacity_rescue(parent, obs, cfg, enabled=False) is not parent:
                raise AssertionError('OFF identity lost')
        if (parent, obs, cfg) != before:
            raise AssertionError('helper mutated input')
        certificate = floor_envelope(e, obs, parent, candidate, cfg)
        states = []
        for action in (parent, candidate):
            st, en = copy.deepcopy((state, env))
            st[seat].action = copy.deepcopy(action)
            st[rival].action = {'farmer': ['PASS'], 'hands': [], 'market': copy.deepcopy(orders)}
            e.interpreter(st, en)
            self.interpreter_calls += 1
            states.append(st)
        off, on = states
        banks = lambda st: [st[0].observation.farms[i]['money'] for i in range(2)]
        old, new = banks(off), banks(on)
        own_delta, rival_delta = new[seat] - old[seat], new[rival] - old[rival]
        farms_off, farms_on = copy.deepcopy(off[0].observation.farms), copy.deepcopy(on[0].observation.farms)
        for farm in farms_off + farms_on:
            farm.pop('money', None)
        result = {'seat': seat, 'seed': seed, 'step': 119, 'product': product,
                  'public_inventory': inventory, 'observed_price': obs.market['prices'][product],
                  'quantity': quantity, 'raw_slot': slot, 'rival_profile': rival_kind,
                  'rival_orders': orders, 'parent_action': parent, 'candidate_action': candidate,
                  'active': candidate is not parent, 'delta_own': own_delta, 'delta_rival': rival_delta,
                  'delta_margin': own_delta - rival_delta, 'off_cash': old, 'on_cash': new,
                  'private_equal': [off[i].observation.private == on[i].observation.private for i in range(2)],
                  'farm_without_money_equal': farms_off == farms_on,
                  'town_equal': off[0].observation.town == on[0].observation.town,
                  'market_equal': off[0].observation.market == on[0].observation.market,
                  'off_product_supply': off[0].observation.market['inventory'][product],
                  'on_product_supply': on[0].observation.market['inventory'][product],
                  'certificate': certificate}
        if not all(result['private_equal']) or not result['farm_without_money_equal'] or not result['town_equal']:
            raise AssertionError(f'private/environment conservation failed: {result}')
        if certificate['certified']:
            rescued = sum(row['quantity'] for row in certificate['rows'])
            if not result['market_equal'] or rival_delta != 0 or own_delta != rescued:
                raise AssertionError(f'false floor certificate: {result}')
        return result


def run_matrix(harness):
    """Predeclared synthetic grid; all cells retained, including negative margins."""
    cases = []
    profiles = [('FERTILIZER', n) for n in (10492, 10493, 10494, 10500, 10593, 11400)]
    profiles += [('WHEAT', 10000), ('MILK', 12000), ('STRAWBERRY', 12000)]
    for seat in (0, 1):
        for product, inventory in profiles:
            for quantity in (1, 2, 8, 20):
                for slot in (0, 1, 9):
                    for rival_kind in ('pass', 'buy100', 'delayed_buy', 'sell100', 'roundtrip'):
                        cases.append(harness.pair(seat=seat, product=product, inventory=inventory,
                                                  quantity=quantity, slot=slot, rival_kind=rival_kind))
    negative = [c for c in cases if c['delta_margin'] < 0]
    certified = [c for c in cases if c['certificate']['certified']]
    return {'sources': harness.sources, 'scope': 'constructed one-turn helper/interpreter pairs, NOT natural or full-game evidence',
            'router_binding': 'PRODUCTS constant only, from authenticated official engine',
            'cells': len(cases), 'interpreter_calls': harness.interpreter_calls,
            'negative_margin_cells': len(negative), 'certified_cells': len(certified),
            'certified_false_positives': 0, 'worst_delta_margin': min(c['delta_margin'] for c in cases),
            'cases': cases}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--overlay-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_matrix(Harness(args.engine_dir, args.overlay_dir))
        payload = json.dumps(report, sort_keys=True, indent=2) + '\n'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + f'.{os.getpid()}.tmp')
        try:
            temporary.write_text(payload, encoding='utf-8')
            os.replace(temporary, args.output)
        finally:
            temporary.unlink(missing_ok=True)
        print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, sort_keys=True))
        return 0
    except (OSError, ValueError, AssertionError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
