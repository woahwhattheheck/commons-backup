# SPDX-License-Identifier: Apache-2.0
"""Parity and bounded-work checks for selected SELL's per-ledger consumption cache.

No games or seed discovery. Optional benchmarks are descriptive, not CI thresholds.
The reference is the unchanged pre-cache feasible method, executed with the same
seller helpers and optimizer as the candidate. See LEDGER-SCHEDULE.md.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import platform
import statistics
import sys
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / 'fixtures' / 'ledger_feasible_0364fa0a.py'
REFERENCE_SHA256 = 'cc6018bdf0a5daa559969395a386baac9a4d7f2aec50a698091ad6ea03101a2f'
OLD = NEW = ENGINE = EV = None
COUNTS = {'feasibility_comparisons': 0, 'transform_comparisons': 0,
          'ordered_capacity_comparisons': 0, 'official_market_calls': 0}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f'Cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def setup(lab):
    global OLD, NEW
    sys.path.insert(0, str(lab.resolve()))
    NEW = load(lab / 'selected_action_sell.py', 'ledger_schedule_candidate')
    OLD = load(lab / 'selected_action_sell.py', 'ledger_schedule_reference')
    if sha(REFERENCE) != REFERENCE_SHA256:
        raise ValueError('The retained pre-cache reference has changed')
    # Bind the exact original method to an independent class/module, so the
    # complete transform uses one reference ledger without patching the candidate.
    exec(compile(REFERENCE.read_text(), str(REFERENCE), 'exec'), OLD.__dict__)
    OLD.ProjectionLedger = type('ReferenceLedger', (OLD.ProjectionLedger,),
                                {'feasible': OLD.feasible})


def packet(q=12, now=667, horizon=8, item='MILK', buys=False, pending=0, seat=0):
    farm = {'money': 10000, 'tiles': [[None]], 'hires_today': 2,
            'unlocked_quadrants': ['NW']}
    obs = {'step': now, 'day': now // 24, 'hour': now % 24, 'player': seat,
           'farms': [copy.deepcopy(farm), copy.deepcopy(farm)],
           'market': {'inventory': {p: 10000 for p in NEW.m.PRODUCTS}},
           'town': {'unlocked_shops': ['BAKERY', 'PIZZA_SHOP', 'YARN_STORE']}}
    action = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', item, q]]}
    shed = {item: q, 'WHEAT': 2}
    end = min(718, now + horizon)
    projection = {'observed_step': now, 'end_step': end, 'stock_events': [],
                  'future_market': {end: [['SELL', item, q]]}}
    reservations = {}
    if buys and now + 2 <= end:
        projection['future_market'][now + 2] = [
            ['BUY_PRODUCT', 'WHEAT', 1], ['BUY_PRODUCT', 'FERTILIZER', 1], ['HIRE']]
        reservations = {'stock': {'WHEAT': 1}, 'order_cost_bounds': [
            {'step': now + 2, 'slot': slot, 'max_cash_cost': 100} for slot in (0, 1)]}
    contract = {'observed_step': now, 'capacity_events': []}
    if pending:
        contract['capacity_events'].append({
            'owner': 'test-producer', 'errand_id': 'lot', 'step': min(end, now + 2),
            'phase': 'after_market', 'pending_capacity_units': pending,
            'units_total': pending, 'guaranteed_stock_units': 0, 'contingent': True})
    options = {'post_unit_shed': shed, 'projection': projection,
               'arrival_contract': contract, 'reservations': reservations,
               'fallback_action': {'farmer': ['PASS'], 'hands': [], 'market': []}}
    return [obs, {}, action, options]


def ledger(module, args):
    obs, cfg, action, kw = args
    return module.ProjectionLedger(obs, cfg, action, kw['post_unit_shed'],
        kw['projection'], kw['arrival_contract'], kw['reservations'], 8)


def outcome(fn):
    try:
        return ('return', fn())
    except Exception as exc:
        return ('raise', type(exc).__name__, str(exc))


def compare_ledgers(test, args, plans, item='MILK'):
    a, b = ledger(OLD, copy.deepcopy(args)), ledger(NEW, copy.deepcopy(args))
    for plan in plans:
        test.assertEqual(outcome(lambda: a.feasible(item, plan)),
                         outcome(lambda: b.feasible(item, plan)))
        COUNTS['feasibility_comparisons'] += 1
    return a, b


def compare_transforms(test, args):
    outputs, diagnostics, paths = [], [], []
    for module in (OLD, NEW):
        policy = module.SelectedActionSell()
        calls = []
        original = module.ProjectionLedger.feasible
        def record(self, item, plan):
            value = original(self, item, plan)
            calls.append((item, tuple(plan), value))
            return value
        with patch.object(module.ProjectionLedger, 'feasible', record):
            outputs.append(policy.transform(*args[:3], **args[3]))
        diagnostics.append(copy.deepcopy(policy.diagnostics))
        paths.append(calls)
    test.assertEqual(outputs[0], outputs[1])
    test.assertEqual(diagnostics[0], diagnostics[1])
    test.assertEqual(paths[0], paths[1])
    COUNTS['transform_comparisons'] += 1
    COUNTS['ordered_capacity_comparisons'] += len(paths[0])
    return outputs[1]


class LedgerScheduleTests(unittest.TestCase):
    def test_reference_integrity(self):
        self.assertEqual(sha(REFERENCE), REFERENCE_SHA256)

    def test_plan_lattice(self):
        for now, q, horizon, item, pending in itertools.product(
                (17, 23, 667, 717, 718), (1, 5, 20), (0, 1, 4, 8),
                ('MILK', 'CARROT', 'WOOL'), (0, 12)):
            args = packet(q=q, now=now, horizon=horizon, item=item, pending=pending)
            end = args[3]['projection']['end_step']
            plans = [((now, first), (end, q-first)) if end != now else ((now, first),)
                     for first in sorted({0, q//2, q})]
            compare_ledgers(self, args, plans, item)

    def test_operating_buy_cash_and_price_bounds(self):
        for cash, inventory, bound, now in itertools.product(
                (0, 20, 500, 10000), (-20, 0, 20, 10000), (0, 30, 300), (17, 23)):
            args = packet(buys=True, now=now)
            args[0]['farms'][0]['money'] = cash
            args[0]['market']['inventory']['WHEAT'] = inventory
            args[3]['reservations']['order_cost_bounds'][0]['max_cash_cost'] = bound
            compare_ledgers(self, args, [((now, 0),), ((now, 12),)])

    def test_literal_empty_lot_queues(self):
        for now, cash, queue in itertools.product((17, 718), (0, 100, 10000), (
                [], [['HIRE']], [['BUY_SEED', 'WHEAT', 2], ['HIRE']],
                [['BUY_ANIMAL', 'GOOSE', 2]], [['BUY_LAND'], ['BUY_LAND']],
                [['SELL', 'WHEAT', 2]], [['SELL', 'WHEAT', 1], ['HIRE']])):
            args = packet(q=0, now=now)
            args[0]['farms'][0]['money'] = cash
            args[2]['market'] = copy.deepcopy(queue)
            args[3]['reservations'] = {'stock': {'WHEAT': 1},
                'cash': [{'step': now, 'phase': 'after_market', 'minimum': 100}]}
            compare_ledgers(self, args, [()], None)
            compare_transforms(self, args)

    def test_ordered_transfers_and_whole_lot_capacity(self):
        args = packet(q=10, now=17, horizon=2)
        args[3]['post_unit_shed'] = {'MILK': 10, 'WHEAT': 90}
        events = [{'step': 18, 'phase': 'before_market', 'product': 'EGG', 'quantity_delta': 10},
                  {'step': 18, 'phase': 'before_market', 'product': 'WHEAT', 'quantity_delta': -10}]
        for phase, reverse in itertools.product(('before_market', 'after_market'), (False, True)):
            rows = copy.deepcopy(events[::-1] if reverse else events)
            for row in rows:
                row['phase'] = phase
            args[3]['projection']['stock_events'] = rows
            compare_ledgers(self, args, [((17, n), (19, 10-n)) for n in (0, 1, 10)])
            compare_transforms(self, args)

    def test_consumption_is_once_per_reached_product_date(self):
        args = packet(now=17, horizon=4)
        counts = []
        for module in (OLD, NEW):
            target = ledger(module, copy.deepcopy(args))
            with patch.object(module, 'absorption', wraps=module.absorption) as fn:
                for _ in range(20):
                    self.assertTrue(target.feasible(None, ()))
                counts.append(fn.call_count)
        self.assertEqual(counts, [20*5*9, 5*9])

    def test_early_return_does_not_evaluate_consumption(self):
        for now in (17, 718):
            args = packet(now=now, q=0)
            args[3]['reservations'] = {'stock': {'WHEAT': 3}}
            target = ledger(NEW, args)
            with patch.object(NEW, 'absorption', side_effect=AssertionError('unreached')) as fn:
                self.assertFalse(target.feasible(None, ()))
                self.assertEqual(fn.call_count, 0)
            self.assertFalse(hasattr(target, '_flow_consumed'))

    def test_terminal_does_not_evaluate_postfinal_consumption(self):
        args = packet(now=718)
        target = ledger(NEW, args)
        with patch.object(NEW, 'absorption', side_effect=AssertionError('postfinal')) as fn:
            self.assertTrue(target.feasible(None, ()))
            self.assertEqual(fn.call_count, 0)
        self.assertFalse(hasattr(target, '_flow_consumed'))

    def test_cache_never_populates_unreached_future(self):
        args = packet(now=17, horizon=8)
        args[3]['projection']['stock_events'] = [
            {'step': 19, 'phase': 'before_market', 'product': 'EGG', 'quantity_delta': 101}]
        target = ledger(NEW, args)
        self.assertFalse(target.feasible(None, ()))
        self.assertEqual(set(target._flow_consumed), {17, 18})

    def test_shop_and_interval_changes_invalidate(self):
        args = packet(now=17, horizon=4, buys=True)
        a, b = compare_ledgers(self, args, [()], None)
        changes = [lambda x: x.obs['town']['unlocked_shops'].append('FARMERS_MARKET'),
                   lambda x: x.obs['town']['unlocked_shops'].clear(),
                   lambda x: x.config.update(townShopSellInterval=3),
                   lambda x: x.config.update(townCenterSellInterval='2'),
                   lambda x: x.obs['town'].update(unlocked_shops=('BAKERY', 'BAKERY'))]
        for change in changes:
            old_cache = b._flow_consumed
            change(a); change(b)
            self.assertEqual(a.feasible(None, ()), b.feasible(None, ()))
            self.assertIsNot(b._flow_consumed, old_cache)
            for t, values in b._flow_consumed.items():
                self.assertEqual(values, tuple((p, NEW.absorption(p, t,
                    b.obs['town']['unlocked_shops'], b.config)) for p in b.obs['market']['inventory']))

    def test_inventory_values_are_not_cached(self):
        args = packet(now=17, horizon=4, buys=True)
        args[3]['reservations']['order_cost_bounds'][0]['max_cash_cost'] = 2
        a, b = compare_ledgers(self, args, [()], None)
        original = b._flow_consumed
        for inventory in (10000, 1, -20, 10000):
            for x in (a, b):
                x.obs['market']['inventory']['WHEAT'] = inventory
            self.assertEqual(a.feasible(None, ()), b.feasible(None, ()))
            self.assertIs(b._flow_consumed, original)

    def test_inventory_keys_and_range_invalidate(self):
        args = packet(now=17, horizon=4)
        a, b = compare_ledgers(self, args, [()], None)
        changes = [lambda x: x.obs['market']['inventory'].pop('MELON'),
                   lambda x: x.obs['market']['inventory'].update(EXTRA=3),
                   lambda x: setattr(x, 'end', 22),
                   lambda x: setattr(x, 'now', 18)]
        for change in changes:
            old_cache = b._flow_consumed
            change(a); change(b)
            self.assertEqual(a.feasible(None, ()), b.feasible(None, ()))
            self.assertIsNot(old_cache, b._flow_consumed)

    def test_changed_absorption_function_invalidates(self):
        target = ledger(NEW, packet(now=17, horizon=4))
        target.feasible(None, ())
        original = target._flow_consumed
        fn = NEW.absorption
        with patch.object(NEW, 'absorption', side_effect=lambda *a: fn(*a)+3) as changed:
            target.feasible(None, ())
            self.assertEqual(changed.call_count, 45)
            self.assertIsNot(original, target._flow_consumed)
            self.assertTrue(all(q >= 3 for rows in target._flow_consumed.values() for p, q in rows))

    def test_partial_exception_does_not_cache_a_date(self):
        args = packet(now=17, horizon=0)
        target = ledger(NEW, args)
        fn = NEW.absorption
        def failing(product, *rest):
            if product == 'TOMATO':
                raise ValueError('consumption witness')
            return fn(product, *rest)
        with patch.object(NEW, 'absorption', side_effect=failing):
            for _ in range(2):
                self.assertEqual(outcome(lambda: target.feasible(None, ())),
                    ('raise', 'ValueError', 'consumption witness'))
                self.assertEqual(target._flow_consumed, {})
        self.assertTrue(target.feasible(None, ()))

    def test_nonstandard_shops_keep_legacy_return_or_error(self):
        for shops, now in itertools.product((None, 'BAKERY', {}, ['BAKERY', []]), (17, 20)):
            args = packet(now=now, horizon=0)
            args[0]['town']['unlocked_shops'] = copy.deepcopy(shops)
            compare_ledgers(self, args, [()], None)

    def test_mutable_market_override_and_reservations_still_execute(self):
        args = packet(now=17, horizon=4)
        a, b = compare_ledgers(self, args, [((17, 12),)])
        counts = [0, 0]
        for i, target in enumerate((a, b)):
            def market(this, step, item, quantity, stock, i=i):
                counts[i] += 1
                return copy.deepcopy(this.future.get(step, []))
            target.market = types.MethodType(market, target)
        for minimum in (0, 10001, 0):
            for target in (a, b):
                target.cash_min[(17, 'after_market')] = minimum
                target.future[18] = [['HIRE']]
            self.assertEqual(a.feasible('MILK', ()), b.feasible('MILK', ()))
        self.assertEqual(counts[0], counts[1])

    def test_ledger_instances_do_not_share_cache_or_mutate_inputs(self):
        args = packet()
        before = copy.deepcopy(args)
        a, b = ledger(NEW, args), ledger(NEW, args)
        a.feasible(None, ()); b.feasible(None, ())
        self.assertEqual(args, before)
        self.assertEqual(a._flow_consumed, b._flow_consumed)
        self.assertIsNot(a._flow_consumed, b._flow_consumed)

    def test_full_transform_actions_diagnostics_and_capacity_order(self):
        for q, now, buys, seat in itertools.product((1, 12, 40), (17, 23, 667, 718), (False, True), (0, 1)):
            args = packet(q=q, now=now, buys=buys, seat=seat, pending=4)
            before = copy.deepcopy(args)
            compare_transforms(self, args)
            self.assertEqual(args, before)

    def test_history_and_retry_actions_are_identical(self):
        policies = [OLD.SelectedActionSell(), NEW.SelectedActionSell()]
        for now in (667, 667, 668, 669, 17):
            args = packet(now=now)
            args[0]['farms'][1]['tiles'] = [[{'kind': 'PLANT', 'crop': 'CARROT', 'yield_units': max(0, 680-now)}]]
            results = [p.transform(*args[:3], **args[3]) for p in policies]
            self.assertEqual(*results)
            self.assertEqual(policies[0].diagnostics, policies[1].diagnostics)
            self.assertEqual(policies[0].observed_harvests, policies[1].observed_harvests)
            COUNTS['transform_comparisons'] += 1

    def test_official_market_output_parity(self):
        if ENGINE is None:
            self.skipTest('Supply --engine-cache and --evaluator for existing offline engine')
        for seat, q, buys in itertools.product((0, 1), (1, 12, 40), (False, True)):
            args = packet(q=q, buys=buys, seat=seat)
            farms = [ENGINE._new_farm(10, 10000) for _ in range(2)]
            args[0]['farms'] = copy.deepcopy(farms)
            outputs = []
            for module in (OLD, NEW):
                action = module.SelectedActionSell().transform(*args[:3], **args[3])
                private = [ENGINE._new_private() for _ in range(2)]
                private[seat]['shed'].update(args[3]['post_unit_shed'])
                private[1-seat]['shed']['MILK'] = 6
                market = ENGINE._new_market()
                market['inventory'] = copy.deepcopy(args[0]['market']['inventory'])
                ENGINE._refresh_prices(market)
                shared = EV.structify({'farms': copy.deepcopy(farms), 'market': market})
                state = [EV.Struct(observation=EV.Struct(farms=shared.farms, market=shared.market,
                          private=EV.structify(private[i])), action=action if i == seat else
                          {'market': [['SELL', 'MILK', 6]]}) for i in range(2)]
                ENGINE._process_market(state, EV.Struct(configuration=EV.Struct()))
                outputs.append(copy.deepcopy(state))
                COUNTS['official_market_calls'] += 1
            self.assertEqual(*outputs)


def benchmark(samples=7, iterations=6):
    families = [('empty', packet(q=0)), ('small', packet(q=1, horizon=2)),
                ('medium', packet(q=12, pending=4)), ('large', packet(q=40, pending=4)),
                ('operating_buys', packet(q=40, pending=4, buys=True)),
                ('terminal', packet(q=40, now=718))]
    rows = []
    for name, args in families:
        expected = OLD.SelectedActionSell().transform(*args[:3], **args[3])
        assert NEW.SelectedActionSell().transform(*args[:3], **args[3]) == expected
        times = {'reference': [], 'candidate': []}
        for sample in range(samples):
            pairs = [('reference', OLD), ('candidate', NEW)]
            if sample % 2:
                pairs.reverse()
            for label, module in pairs:
                started = time.perf_counter()
                for _ in range(iterations):
                    module.SelectedActionSell().transform(*args[:3], **args[3])
                times[label].append((time.perf_counter()-started)/iterations)
        a, b = statistics.median(times['reference']), statistics.median(times['candidate'])
        rows.append({'workload': name, 'samples': samples, 'calls_per_sample': iterations,
                     'reference_seconds_per_call': a, 'candidate_seconds_per_call': b,
                     'time_reduction_fraction': 1-b/a, 'raw_seconds_per_call': times})
    return rows


def main():
    global ENGINE, EV
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab', type=Path, default=HERE.parent/'cloud-execution-lab')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--engine-cache', type=Path)
    parser.add_argument('--evaluator', type=Path)
    parser.add_argument('--engine-loader', type=Path)
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--samples', type=int, default=7)
    parser.add_argument('--iterations', type=int, default=6)
    options = parser.parse_args()
    if options.samples < 1 or options.iterations < 1:
        parser.error('samples and iterations must be positive')
    if bool(options.engine_cache) != bool(options.evaluator):
        parser.error('Supply both --engine-cache and --evaluator, or neither')
    setup(options.lab)
    engine_hashes = None
    if options.engine_cache:
        EV = load(options.evaluator.resolve(), 'ledger_schedule_evaluator')
        kwargs = {'prepare': False}
        if options.engine_loader:
            kwargs['loader'] = options.engine_loader.resolve()
        ENGINE, engine_hashes = EV.get_engine(options.engine_cache.resolve(), **kwargs)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LedgerScheduleTests))
    report = {'python': platform.python_version(), 'platform': platform.platform(),
              'test_methods': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'successful': result.wasSuccessful(),
              'sources_sha256': {str(p.relative_to(options.lab)): sha(p) for p in (
                  options.lab/'selected_action_sell.py', options.lab/'selected_sell_core.py',
                  options.lab/'mechanics.py', options.lab/'reference/decision/decision.py')},
              'reference_method_sha256': sha(REFERENCE), 'engine_sha256': engine_hashes,
              'counts': COUNTS, 'full_games': 0, 'game_seeds': [],
              'scope': 'synthetic source-parity and native market cases; not whole-agent/game timing'}
    if options.benchmark and result.wasSuccessful():
        report['benchmark'] = benchmark(options.samples, options.iterations)
    if options.report:
        options.report.parent.mkdir(parents=True, exist_ok=True)
        options.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
