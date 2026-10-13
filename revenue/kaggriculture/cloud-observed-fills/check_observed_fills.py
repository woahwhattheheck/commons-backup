# SPDX-License-Identifier: Apache-2.0
"""Offline callable checks, with existing pinned engine/loader supplied explicitly."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from observed_fills import ObservedFillLedger, full_sale_verdict, reconcile_shed_fills

ENGINE_HASHES = {
    'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}
ENGINE = LOADER = None
CASES = []


def action(*orders):
    return {'farmer': ['PASS'], 'hands': [], 'market': list(orders)}


def obs(step, shed, player=0, **extra):
    return dict(step=step, day=step // 24, hour=step % 24, player=player,
                private={'shed': deepcopy(shed)}, **extra)


class UnitChecks(unittest.TestCase):
    def reconcile(self, before, queue, after, **kw):
        return reconcile_shed_fills(before, action(*queue), after, **kw)

    def test_full_sale_and_cash_not_inferred(self):
        r = self.reconcile({'EGG': 4}, [['SELL', 'EGG', 4]], {'EGG': 0})
        self.assertEqual(r['status'], 'reconciled')
        self.assertIs(full_sale_verdict(r, 0, 4), True)
        self.assertIsNone(r['cash_receipts'])

    def test_stock_clipping_and_repeated_sales(self):
        r = self.reconcile({'EGG': 4}, [['SELL', 'EGG', 3], ['SELL', 'EGG', 3]], {})
        self.assertEqual([(x['fill_min'], x['fill_max']) for x in r['orders']], [(3, 3), (1, 1)])
        self.assertIs(full_sale_verdict(r, 1, 3), False)

    def test_buy_sell_roundtrip_ambiguous(self):
        r = self.reconcile({}, [['BUY_PRODUCT', 'WHEAT', 1], ['SELL', 'WHEAT', 1]], {})
        self.assertEqual(r['status'], 'ambiguous')
        self.assertEqual([(x['fill_min'], x['fill_max']) for x in r['orders']], [(0, 1), (0, 1)])
        self.assertIsNone(full_sale_verdict(r, 1, 1))

    def test_observed_purchase_then_sale(self):
        r = self.reconcile({}, [['BUY_PRODUCT', 'WHEAT', 4], ['SELL', 'WHEAT', 2]], {'WHEAT': 1})
        self.assertEqual([(x['fill_min'], x['fill_max']) for x in r['orders']], [(3, 3), (2, 2)])

    def test_shared_capacity_across_products(self):
        r = self.reconcile({'EGG': 99}, [['BUY_PRODUCT', 'WHEAT', 2], ['BUY_ANIMAL', 'COW', 1]],
                           {'EGG': 99, 'COW': 1})
        self.assertEqual([x['fill_max'] for x in r['orders']], [0, 1])

    def test_market_slot_limit(self):
        r = self.reconcile({'EGG': 2}, [['HIRE'], ['SELL', 'EGG', 2]], {'EGG': 2},
                           configuration={'maxMarketOrdersPerTurn': 1})
        self.assertEqual(r['orders'][1]['kind'], 'ignored')
        self.assertIs(full_sale_verdict(r, 1, 2), False)

    def test_deposits_are_after_sale_not_before(self):
        r = self.reconcile({'EGG': 1}, [['SELL', 'EGG', 2]], {'EGG': 2},
                           after_market_deposits=[{'EGG': 2}])
        self.assertEqual(r['orders'][0]['fill_max'], 1)
        self.assertIs(full_sale_verdict(r, 0, 2), False)

    def test_ordered_deposits_at_capacity(self):
        before = {'EGG': 100}
        queue = [['SELL', 'EGG', 1]]
        r = self.reconcile(before, queue, {'EGG': 99, 'MILK': 1},
                           after_market_deposits=[{'MILK': 1, 'WOOL': 1}])
        self.assertEqual(r['status'], 'reconciled')
        reverse = self.reconcile(before, queue, {'EGG': 99, 'MILK': 1},
                                 after_market_deposits=[{'WOOL': 1, 'MILK': 1}])
        self.assertEqual(reverse['reason'], 'observed_shed_not_explained')

    def test_deposit_can_hide_buy_amount(self):
        r = self.reconcile({}, [['BUY_PRODUCT', 'WHEAT', 2]], {'WHEAT': 2},
                           configuration={'shedCapacity': 2}, after_market_deposits=[{'WHEAT': 2}])
        self.assertEqual(r['status'], 'ambiguous')
        self.assertEqual((r['orders'][0]['fill_min'], r['orders'][0]['fill_max']), (0, 2))

    def test_contradiction_unknown(self):
        r = self.reconcile({'EGG': 1}, [['SELL', 'EGG', 1]], {'EGG': 1})
        self.assertEqual(r['reason'], 'observed_shed_not_explained')
        self.assertIsNone(full_sale_verdict(r, 0, 1))

    def test_state_and_transition_budgets(self):
        kw = dict(post_unit_shed={}, submitted_action=action(['BUY_PRODUCT', 'WHEAT', 100], ['SELL', 'WHEAT', 100]), next_shed={})
        self.assertEqual(reconcile_shed_fills(**kw, max_states=2)['reason'], 'state_budget_exceeded')
        self.assertEqual(reconcile_shed_fills(**kw, max_transitions=2)['reason'], 'transition_budget_exceeded')

    def test_invalid_inputs_unknown(self):
        for before in ({'EGG': -1}, {'EGG': 1.0}, {'EGG': True}, None):
            with self.subTest(before=before):
                self.assertEqual(self.reconcile(before, [], {})['reason'], 'invalid_input')
        self.assertEqual(self.reconcile({}, [], {}, after_market_deposits=None)['reason'],
                         'after_market_deposits_unknown')

    def test_non_shed_orders_not_claimed(self):
        r = self.reconcile({}, [['BUY_SEED', 'WHEAT', 2], ['HIRE'], ['BUY_LAND']], {})
        self.assertTrue(all(x['fill_min'] is None for x in r['orders']))
        self.assertFalse(r['non_shed_orders_inferred'])

    def test_malformed_and_string_quantity(self):
        r = self.reconcile({'EGG': 2}, [None, ['SELL', 'EGG', '2'], ['SELL', 'EGG', 0]], {})
        self.assertEqual([x['fill_max'] for x in r['orders']], [0, 2, 0])

    def test_full_verdict_binds_slot_and_quantity(self):
        r = self.reconcile({'EGG': 2}, [['SELL', 'EGG', 2]], {})
        self.assertIsNone(full_sale_verdict(r, 1, 2))
        self.assertIsNone(full_sale_verdict(r, 0, 1))
        self.assertIsNone(full_sale_verdict(r, True, 2))

    def test_inputs_not_mutated(self):
        args = [ {'EGG': 2}, action(['SELL', 'EGG', 1]), {'EGG': 2} ]
        deposits = [{'EGG': 1}]
        old = deepcopy((args, deposits))
        reconcile_shed_fills(*args, after_market_deposits=deposits)
        self.assertEqual((args, deposits), old)

    def test_ledger_adjacent_and_retry(self):
        ledger = ObservedFillLedger()
        binding = ledger.record(obs(7, {'EGG': 2}), {}, action(['SELL', 'EGG', 2]), post_unit_shed={'EGG': 2})
        self.assertEqual(ledger.observe(obs(7, {'EGG': 2}))['status'], 'pending')
        r = ledger.observe(obs(8, {}))
        self.assertIs(full_sale_verdict(r, 0, 2), True)
        self.assertEqual(r['binding']['action_sha256'], binding['action_sha256'])
        self.assertEqual(ledger.observe(obs(8, {}))['reason'], 'no_pending_action')

    def test_ledger_final_action_detached_and_replaced(self):
        ledger = ObservedFillLedger()
        a = action(['SELL', 'EGG', 2])
        ledger.record(obs(7, {}), {}, a, post_unit_shed={'EGG': 2})
        a['market'][0][2] = 1
        r = ledger.observe(obs(8, {}))
        self.assertIs(full_sale_verdict(r, 0, 2), True)
        ledger.record(obs(7, {}), {}, action(['SELL', 'EGG', 2]), post_unit_shed={'EGG': 2})
        ledger.record(obs(7, {}), {}, a, post_unit_shed={'EGG': 2})
        self.assertIs(full_sale_verdict(ledger.observe(obs(8, {'EGG': 1})), 0, 1), True)

    def test_ledger_time_gap_player_and_clock(self):
        ledger = ObservedFillLedger()
        ledger.record(obs(7, {}), {}, action(), post_unit_shed={})
        self.assertEqual(ledger.observe(obs(8, {}, 1))['reason'], 'different_player')
        self.assertIsNotNone(ledger.pending)
        self.assertEqual(ledger.observe(obs(9, {}))['reason'], 'nonadjacent_observation')
        inconsistent = obs(7, {}); inconsistent['hour'] = 8
        with self.assertRaises(ValueError):
            ledger.record(inconsistent, {}, action(), post_unit_shed={})

    def test_ledger_missing_step_uses_day_hour(self):
        a, b = obs(7, {}), obs(8, {})
        del a['step']; del b['step']
        ledger = ObservedFillLedger()
        ledger.record(a, {}, action(), post_unit_shed={})
        self.assertEqual(ledger.observe(b)['status'], 'reconciled')

    def test_ledger_eod_requires_exact_inventories(self):
        ledger = ObservedFillLedger()
        ledger.record(obs(23, {}), {}, action(['SELL', 'EGG', 1]), post_unit_shed={'EGG': 1})
        self.assertEqual(ledger.observe(obs(24, {'EGG': 1}))['reason'], 'after_market_deposits_unknown')
        ledger.record(obs(23, {}), {}, action(['SELL', 'EGG', 1]), post_unit_shed={'EGG': 1},
                      post_unit_inventories=[{'EGG': 1}])
        self.assertIs(full_sale_verdict(ledger.observe(obs(24, {'EGG': 1})), 0, 1), True)

    def test_terminal_718_is_not_eod_deposit(self):
        ledger = ObservedFillLedger()
        ledger.record(obs(718, {}), {}, action(['SELL', 'EGG', 2]), post_unit_shed={'EGG': 1},
                      post_unit_inventories=[{'EGG': 1}])
        r = ledger.observe(obs(719, {}))
        self.assertIs(full_sale_verdict(r, 0, 2), False)

    def test_iteration_ceiling(self):
        r = self.reconcile({'EGG': 100001}, [['SELL', 'EGG', 100001]], {'EGG': 2},
                           configuration={'shedCapacity': 200000})
        self.assertEqual(r['orders'][0]['fill_max'], 99999)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'input.json'
            p.write_text(json.dumps(dict(post_unit_shed={'EGG': 1}, submitted_action=action(['SELL', 'EGG', 1]), next_shed={})))
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('observed_fills.py')), str(p)],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)['status'], 'reconciled')


class OfficialMarketChecks(unittest.TestCase):
    def run_case(self, name, seat, before, orders, *, rival_orders=(), rival_shed=None,
                 money=1000, capacity=100, slots=10, deposits=(), floor=False):
        e, S = ENGINE, LOADER.Struct
        farms = [e._new_farm(10, money), e._new_farm(10, money)]
        privates = [e._new_private(), e._new_private()]
        privates[seat]['shed'].update(before)
        privates[1-seat]['shed'].update(rival_shed or {})
        privates[seat]['inventories'] = deepcopy(list(deposits)) or [{}]
        market = e._new_market()
        if floor:
            market['inventory']['STRAWBERRY'] = 20000
        state = [S(observation=S(player=i, farms=farms, private=privates[i], market=market,
                                 town=e._new_town(), day=0, hour=17, step=17),
                   action=deepcopy(action(*(orders if i == seat else rival_orders))), status='ACTIVE', reward=0)
                 for i in (0, 1)]
        cfg = S(boardSize=10, shedCapacity=capacity, maxMarketOrdersPerTurn=slots, farmHandCostMult=1)
        env = S(configuration=cfg, done=False, info={})
        control = deepcopy(state)
        e._process_market(control, env)
        own_queue = state[seat].action['market']
        own_positions = {id(x): i for i, x in enumerate(own_queue)}
        observed_fills = [0] * len(own_queue)
        current_slot = [None]
        original_parse, original_commit = e._parse_order, e._commit_unit
        def parse(order):
            if id(order) in own_positions:
                current_slot[0] = own_positions[id(order)]
            return original_parse(order)
        def commit(op, item, price, farm, private, shared_market, shed_capacity=100):
            ok = original_commit(op, item, price, farm, private, shared_market, shed_capacity)
            if ok and farm is farms[seat]:
                observed_fills[current_slot[0]] += 1
            return ok
        # Evaluation-only tracing delegates every call to the actual functions.
        # The uninstru­mented control must have exactly the same complete state.
        e._parse_order, e._commit_unit = parse, commit
        try:
            e._process_market(state, env)
        finally:
            e._parse_order, e._commit_unit = original_parse, original_commit
        self.assertEqual(state, control)
        if deposits:
            e._drop_inventories_to_shed(privates[seat], capacity)
        start = time.perf_counter()
        r = reconcile_shed_fills(before, state[seat].action, privates[seat]['shed'], cfg,
                                 after_market_deposits=deposits)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertIn(r['status'], ('reconciled', 'ambiguous'))
        for row, actual in zip(r['orders'], observed_fills):
            if row['kind'] in ('sell', 'buy', 'ignored'):
                self.assertLessEqual(row['fill_min'], actual)
                self.assertGreaterEqual(row['fill_max'], actual)
        CASES.append({'name': name, 'seat': seat, 'orders': deepcopy(orders),
                      'actual_fills': observed_fills, 'result': r,
                      'elapsed_ms': round(elapsed_ms, 6),
                      'post_market_cash': farms[seat]['money'],
                      'traced_matches_uninstrumented': True})
        return r, state

    def test_exact_and_short_sales(self):
        for seat in (0, 1):
            for quantity in (1, 2, 4):
                with self.subTest(seat=seat, quantity=quantity):
                    r, _ = self.run_case('stock-short-sale', seat, {'EGG': 2}, [['SELL', 'EGG', quantity]])
                    self.assertIs(full_sale_verdict(r, 0, quantity), quantity <= 2)

    def test_ordered_repeated_sales_and_truncation(self):
        for seat in (0, 1):
            for slots in (1, 2, 3):
                self.run_case('ordered-sales', seat, {'EGG': 3},
                              [['HIRE'], ['SELL', 'EGG', 2], ['SELL', 'EGG', 2]], slots=slots)

    def test_buys_cash_and_joint_capacity(self):
        for seat in (0, 1):
            for money in (0, 25, 1000):
                for capacity in (1, 3):
                    self.run_case('unknown-purchase-budget', seat, {},
                        [['BUY_PRODUCT', 'WHEAT', 2], ['BUY_ANIMAL', 'COW', 1], ['SELL', 'WHEAT', 1]],
                        money=money, capacity=capacity)

    def test_rival_paired_quotes_need_no_rival_state(self):
        for seat in (0, 1):
            for rival in ([['BUY_PRODUCT', 'WHEAT', 3]], [['SELL', 'WHEAT', 3]], []):
                self.run_case('paired-rival', seat, {'WHEAT': 3},
                              [['BUY_PRODUCT', 'WHEAT', 2], ['SELL', 'WHEAT', 4]],
                              rival_orders=rival, rival_shed={'WHEAT': 3}, money=70)

    def test_floor_sale_not_visible_in_shared_inventory(self):
        for seat in (0, 1):
            r, state = self.run_case('floor-sale', seat, {'STRAWBERRY': 3},
                                    [['SELL', 'STRAWBERRY', 3]], floor=True)
            self.assertEqual(state[seat].observation.market['inventory']['STRAWBERRY'], 20000)
            self.assertIs(full_sale_verdict(r, 0, 3), True)

    def test_actual_eod_clipping_and_order(self):
        for seat in (0, 1):
            for deposits in ([{'MILK': 2}, {'WOOL': 2}], [{'WOOL': 2}, {'MILK': 2}]):
                self.run_case('eod-whole-ordered-deposits', seat, {'EGG': 100},
                              [['SELL', 'EGG', 3]], deposits=deposits)

    def test_roundtrip_true_ambiguity_at_two_cash_levels(self):
        for seat in (0, 1):
            for money in (0, 1000):
                r, _ = self.run_case('roundtrip-ambiguity', seat, {},
                                    [['BUY_PRODUCT', 'WHEAT', 1], ['SELL', 'WHEAT', 1]], money=money)
                self.assertEqual(r['status'], 'ambiguous')
                self.assertIsNone(full_sale_verdict(r, 1, 1))

    def test_seed_storage_and_atomic_costs_not_inferred(self):
        for seat in (0, 1):
            self.run_case('seed-hire-land-not-cash-receipts', seat, {'EGG': 3},
                          [['SELL', 'EGG', 3], ['BUY_SEED', 'CARROT', 2], ['HIRE'], ['BUY_LAND']])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-loader', type=Path, required=True)
    parser.add_argument('--engine-cache', type=Path, required=True)
    parser.add_argument('--json-output', type=Path, required=True)
    args = parser.parse_args()
    actual = {name: hashlib.sha256((args.engine_cache/name).read_bytes()).hexdigest()
              for name in ENGINE_HASHES}
    if actual != ENGINE_HASHES:
        raise SystemExit('Existing engine cache does not match the tested official source pin.')
    global ENGINE, LOADER
    spec = importlib.util.spec_from_file_location('observed_fills_existing_loader', args.engine_loader)
    LOADER = importlib.util.module_from_spec(spec); spec.loader.exec_module(LOADER)
    ENGINE, returned_hashes = LOADER.get_engine(args.engine_cache)
    if returned_hashes != ENGINE_HASHES:
        raise SystemExit('Loader returned different source hashes.')
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'component': 'cloud-observed-fills', 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'success': result.wasSuccessful(),
              'engine_ref': '28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c',
              'engine_sha256': actual,
              'runtime_sha256': hashlib.sha256(Path(__file__).with_name('observed_fills.py').read_bytes()).hexdigest(),
              'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'loader_sha256': hashlib.sha256(args.engine_loader.read_bytes()).hexdigest(),
              'official_market_cases': len(CASES),
              'uninstrumented_control_executions': len(CASES),
              'full_games': 0, 'policy_selection_changed': False,
              'max_warm_reconciliation_ms': max((r['elapsed_ms'] for r in CASES), default=None),
              'cases': CASES}
    args.json_output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
