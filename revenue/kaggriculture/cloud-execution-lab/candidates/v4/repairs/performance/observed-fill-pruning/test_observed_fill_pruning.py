# SPDX-License-Identifier: Apache-2.0
"""Current-source differential, small-state exhaustive and lifecycle checks.

Run: python test_observed_fill_pruning.py --baseline PATH [--receipt PATH]
The baseline must be the externally supplied production observed_fills.py,
not a copy reconstructed by the checker or imported from the repair payload.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

import oracle
import repair_observed_fill_pruning as repair_module

BASELINE = None
ORIGINAL = None
CANDIDATE = None
SOURCE = None
OUTPUT = None
COUNTS = {'exhaustive_cases': 0, 'random_cases': 0}


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def semantic(result):
    kept = {key: result[key] for key in ('status', 'reason', 'orders', 'cash_receipts')}
    if result['status'] in ('reconciled', 'ambiguous'):
        kept.update({key: result[key] for key in
                     ('compatible_states', 'method', 'non_shed_orders_inferred')})
    return kept


def case(before=None, market=None, after=None, capacity=100, slots=10, deposits=()):
    return dict(post_unit_shed={} if before is None else before,
                submitted_action={'market': [] if market is None else market},
                next_shed={} if after is None else after,
                configuration={'shedCapacity': capacity, 'maxMarketOrdersPerTurn': slots},
                after_market_deposits=deposits)


class RepairContract(unittest.TestCase):
    def test_01_exact_external_source_custody(self):
        self.assertEqual(repair_module.git_blob(SOURCE), repair_module.PREDECESSOR_BLOB)

    def test_02_materialization_is_idempotent(self):
        self.assertEqual(repair_module.repair(OUTPUT), OUTPUT)

    def test_03_unrelated_peer_bytes_preserved(self):
        prefix = b'# unrelated peer prelude\n'
        suffix = b'\nPEER_RECEIPT = 77\n'
        self.assertEqual(repair_module.repair(prefix + SOURCE + suffix), prefix + OUTPUT + suffix)

    def test_04_target_drift_is_not_overwritten(self):
        altered = SOURCE.replace(b'capacity, limit, _ = _config(configuration)',
                                 b'capacity, limit, _ = _config(configuration or {})')
        with self.assertRaises(ValueError):
            repair_module.repair(altered)

    def test_05_duplicate_target_is_rejected(self):
        with self.assertRaises(ValueError):
            repair_module.repair(SOURCE + b'\ndef reconcile_shed_fills():\n    return 0\n')

    def test_06_async_target_is_rejected(self):
        with self.assertRaises(ValueError):
            repair_module.repair(SOURCE.replace(b'def reconcile_shed_fills(', b'async def reconcile_shed_fills('))

    def test_07_nonbytes_rejected(self):
        with self.assertRaises(TypeError):
            repair_module.repair(SOURCE.decode())

    def test_08_only_target_ast_changes(self):
        left, right = ast.parse(SOURCE), ast.parse(OUTPUT)
        self.assertEqual(len(left.body), len(right.body))
        for a, b in zip(left.body, right.body):
            if isinstance(a, ast.FunctionDef) and a.name == repair_module.FUNCTION:
                self.assertEqual(ast.dump(a.args), ast.dump(b.args))
            else:
                self.assertEqual(ast.dump(a), ast.dump(b))

    def test_09_non_target_bytes_stay_exact(self):
        a, b, _ = repair_module._span(SOURCE)
        x, y, _ = repair_module._span(OUTPUT)
        self.assertEqual(SOURCE[:a], OUTPUT[:x])
        self.assertEqual(SOURCE[b:], OUTPUT[y:])


class DependencyContract(unittest.TestCase):
    def test_32_changed_parser_requires_review(self):
        altered = SOURCE.replace(b'op = order[0]', b'op = order[0].upper()')
        with self.assertRaises(ValueError):
            repair_module.repair(altered)

    def test_33_changed_cap_requires_review_even_when_already_patched(self):
        altered = OUTPUT.replace(b'MAX_SLOT_UNITS = 99_999', b'MAX_SLOT_UNITS = 99_998')
        with self.assertRaises(ValueError):
            repair_module.repair(altered)

    def test_34_changed_payload_is_detected(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/'replacement'
            path.write_bytes(b'def reconcile_shed_fills():\n    return None\n')
            with patch.object(repair_module, 'PAYLOAD', path):
                with self.assertRaises(ValueError):
                    repair_module.repair(SOURCE)


class Reconciliation(unittest.TestCase):
    def agree(self, data, *, oracle_check=True):
        before = deepcopy(data)
        baseline = ORIGINAL.reconcile_shed_fills(**data)
        candidate = CANDIDATE.reconcile_shed_fills(**data)
        self.assertEqual(semantic(baseline), semantic(candidate), data)
        if oracle_check:
            self.assertEqual(semantic(oracle.reconcile(data)), semantic(candidate), data)
        self.assertEqual(data, before)
        return candidate

    def test_10_two_high_capacity_buys_recover_exact_fills(self):
        data = case(market=[['BUY_PRODUCT', 'WHEAT', 100], ['BUY_PRODUCT', 'FERTILIZER', 100]],
                    after={'WHEAT': 50, 'FERTILIZER': 50})
        original = ORIGINAL.reconcile_shed_fills(**data)
        candidate = CANDIDATE.reconcile_shed_fills(**data)
        self.assertEqual(original['reason'], 'state_budget_exceeded')
        self.assertEqual(candidate['status'], 'reconciled')
        self.assertEqual(candidate['transitions'], 2)
        self.assertEqual(candidate['peak_states'], 1)
        self.assertEqual([(r['fill_min'], r['fill_max']) for r in candidate['orders']], [(50, 50), (50, 50)])
        self.assertIsNone(candidate['cash_receipts'])
        self.assertEqual(semantic(oracle.reconcile(data)), semantic(candidate))

    def test_11_genuine_buy_sell_ambiguity_retained(self):
        result = self.agree(case(market=[['BUY_PRODUCT', 'WHEAT', 6], ['SELL', 'WHEAT', 6]], capacity=6))
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual([(r['fill_min'], r['fill_max']) for r in result['orders']], [(0, 6), (0, 6)])

    def test_12_state_limit_still_applies(self):
        data = case(market=[['BUY_PRODUCT', 'WHEAT', 100], ['SELL', 'WHEAT', 100]])
        result = CANDIDATE.reconcile_shed_fills(**data, max_states=3)
        self.assertEqual(result['reason'], 'state_budget_exceeded')
        self.assertEqual(result['orders'], [])

    def test_13_transition_limit_still_applies(self):
        data = case(market=[['BUY_PRODUCT', 'WHEAT', 100], ['SELL', 'WHEAT', 100]])
        result = CANDIDATE.reconcile_shed_fills(**data, max_transitions=5)
        self.assertEqual(result['reason'], 'transition_budget_exceeded')
        self.assertEqual(result['orders'], [])

    def test_14_raw_suffix_slots_are_unchanged(self):
        data = case(market=[[], ['BUY_PRODUCT', 'WHEAT', 2], ['SELL', 'WHEAT', 2],
                            None, ['HIRE'], ['BUY_PRODUCT', 'FERTILIZER', '9']],
                    after={'WHEAT': 2}, capacity=3, slots=2)
        result = self.agree(data)
        self.assertEqual(len(result['orders']), 6)
        self.assertEqual(result['orders'][2]['kind'], 'ignored')
        self.assertEqual(result['orders'][2]['fill_max'], 0)

    def test_15_zero_config_slots_uses_existing_one_slot_contract(self):
        self.agree(case(market=[['BUY_PRODUCT', 'WHEAT', 2], ['SELL', 'WHEAT', 2]],
                        after={'WHEAT': 1}, capacity=3, slots=0))

    def test_16_ordered_overflow_deposits_keep_ambiguity(self):
        result = self.agree(case(market=[['BUY_PRODUCT', 'WHEAT', 2]],
                                after={'WHEAT': 3}, capacity=3,
                                deposits=[{'WHEAT': 3, 'FERTILIZER': 3}]))
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual(result['orders'][0]['fill_max'], 2)

    def test_17_reversed_deposit_order_changes_evidence(self):
        result = self.agree(case(market=[['BUY_PRODUCT', 'WHEAT', 2]],
                                after={'FERTILIZER': 3}, capacity=3,
                                deposits=[{'FERTILIZER': 3, 'WHEAT': 3}]))
        self.assertEqual(result['status'], 'reconciled')
        self.assertEqual(result['orders'][0]['fill_max'], 0)

    def test_18_missing_deposit_evidence_remains_unknown(self):
        for value in (None, 'unknown', [{} , {'WHEAT': -1}]):
            data = case(deposits=value)
            self.assertEqual(ORIGINAL.reconcile_shed_fills(**data), CANDIDATE.reconcile_shed_fills(**data))

    def test_19_invalid_inputs_do_not_become_receipts(self):
        variants = [case(before={'WHEAT': -1}), case(after={'WHEAT': True}),
                    case(capacity=-1), case(capacity='bad'), case(before={'WHEAT': 1.0})]
        for data in variants:
            self.assertEqual(ORIGINAL.reconcile_shed_fills(**data), CANDIDATE.reconcile_shed_fills(**data))
        for key in ('max_states', 'max_transitions'):
            for value in (False, 0, -1, 1.5):
                self.assertEqual(ORIGINAL.reconcile_shed_fills(**case(), **{key: value}),
                                 CANDIDATE.reconcile_shed_fills(**case(), **{key: value}))

    def test_20_non_shed_orders_keep_unknown_fill(self):
        result = self.agree(case(market=[['HIRE'], ['BUY_SEED', 'WHEAT', 2], ['BUY_LAND'],
                                        ['BUY_ANIMAL', 'SHEEP', 2]], after={'SHEEP': 1}, capacity=3))
        self.assertTrue(all(row['fill_min'] is None for row in result['orders'][:3]))
        self.assertFalse(result['non_shed_orders_inferred'])

    def test_21_parser_edges_preserve_semantics(self):
        rows = [['BUY_PRODUCT', 'WHEAT', '2'], ['SELL', 'WHEAT', True],
                ['BUY_PRODUCT', 'FERTILIZER', 'x'], ['SELL', ['bad'], 3],
                ['BUY_ANIMAL', 'COW', 1.9], ['WHAT'], [], None, ['SELL', 'WHEAT', 0]]
        self.agree(case(market=rows, after={'WHEAT': 1, 'COW': 1}, capacity=4))

    def test_22_per_slot_maximum_is_not_relaxed(self):
        self.agree(case(before={'WHEAT': 100005}, market=[['SELL', 'WHEAT', 100005]],
                        after={'WHEAT': 6}, capacity=200000))
        result = CANDIDATE.reconcile_shed_fills(**case(market=[['BUY_PRODUCT', 'WHEAT', 100001]],
                                                      after={'WHEAT': 100000}, capacity=200000))
        self.assertEqual(result['reason'], 'observed_shed_not_explained')

    def test_23_initial_overcapacity_matches_reference(self):
        self.agree(case(before={'WHEAT': 8}, market=[['SELL', 'WHEAT', 5], ['BUY_PRODUCT', 'FERTILIZER', 3]],
                        after={'WHEAT': 3, 'FERTILIZER': 1}, capacity=4))

    def test_24_no_purchase_fast_path_preserves_work_counters(self):
        data = case(before={'WHEAT': 4, 'WOOL': 2}, market=[[], ['SELL', 'WHEAT', 2], ['SELL', 'WOOL', 5]],
                    after={'WHEAT': 2}, capacity=6)
        self.assertEqual(ORIGINAL.reconcile_shed_fills(**data), CANDIDATE.reconcile_shed_fills(**data))

    def test_25_unknown_market_does_not_invent_operations(self):
        for action in (None, [], {'market': None}, {'market': 'BUY'}, {'market': [['SELL'], [[]]]}):
            data = case(before={'WHEAT': 2}, after={'WHEAT': 2})
            data['submitted_action'] = action
            self.agree(data)

    def test_26_full_sale_verdict_preserved(self):
        data = case(market=[['BUY_PRODUCT', 'WHEAT', 4], ['SELL', 'WHEAT', 3]],
                    after={'WHEAT': 1}, capacity=5)
        result = self.agree(data)
        for slot in range(-1, 4):
            for quantity in (-1, 0, 1, 3, True):
                self.assertEqual(ORIGINAL.full_sale_verdict(result, slot, quantity),
                                 CANDIDATE.full_sale_verdict(result, slot, quantity))


class LedgerLifecycle(unittest.TestCase):
    def exercise(self, module, player, *, eod=False, deposits=None):
        ledger = module.ObservedFillLedger()
        step = 23 if eod else 5
        before = {'step': step, 'player': player}
        action = {'market': [['BUY_PRODUCT', 'WHEAT', 4], ['SELL', 'WHEAT', 2]]}
        binding = ledger.record(before, {'shedCapacity': 5}, action,
                                post_unit_shed={}, post_unit_inventories=deposits)
        action['market'][0][2] = 99  # The recorded action is a detached snapshot.
        same = ledger.observe({'step': step, 'player': player, 'private': {'shed': {}}})
        other = ledger.observe({'step': step + 1, 'player': 1-player, 'private': {'shed': {}}})
        after = ledger.observe({'step': step + 1, 'player': player, 'private': {'shed': {'WHEAT': 1}}})
        no_pending = ledger.observe({'step': step + 2, 'player': player, 'private': {'shed': {}}})
        return binding, same, other, semantic(after), no_pending

    def test_27_both_seats_binding_and_duplicate_observations(self):
        for player in (0, 1):
            self.assertEqual(self.exercise(ORIGINAL, player), self.exercise(CANDIDATE, player))

    def test_28_end_of_day_known_and_unknown_carry(self):
        for deposits in (None, [], [{'WHEAT': 1}, {'FERTILIZER': 3}]):
            self.assertEqual(self.exercise(ORIGINAL, 0, eod=True, deposits=deposits),
                             self.exercise(CANDIDATE, 0, eod=True, deposits=deposits))

    def test_29_nonadjacent_observation_does_not_infer(self):
        for module in (ORIGINAL, CANDIDATE):
            ledger = module.ObservedFillLedger()
            ledger.record({'step': 3, 'player': 0}, {}, {'market': []}, post_unit_shed={})
            result = ledger.observe({'step': 5, 'player': 0, 'private': {'shed': {}}})
            self.assertEqual(result['reason'], 'nonadjacent_observation')


class Differential(unittest.TestCase):
    def compare(self, data):
        original = ORIGINAL.reconcile_shed_fills(**data)
        candidate = CANDIDATE.reconcile_shed_fills(**data)
        expected = oracle.reconcile(data)
        self.assertEqual(semantic(original), semantic(expected), data)
        self.assertEqual(semantic(candidate), semantic(expected), data)

    def test_30_exhaustive_small_state_grid(self):
        ops = [[], ['HIRE'], ['BUY_PRODUCT', 'WHEAT', 2], ['BUY_PRODUCT', 'FERTILIZER', 2],
               ['SELL', 'WHEAT', 2], ['SELL', 'FERTILIZER', 2], ['BUY_ANIMAL', 'COW', 1]]
        stocks = [{'WHEAT': w, 'FERTILIZER': f} for w in range(3) for f in range(3-w)]
        queues = [[]] + [[o] for o in ops] + list(map(list, itertools.product(ops, repeat=2)))
        deposits = [(), [{'WHEAT': 2, 'FERTILIZER': 1}], [{'FERTILIZER': 1, 'WHEAT': 2}]]
        for before, queue, after, dep in itertools.product(stocks, queues, stocks, deposits):
            self.compare(case(before, queue, after, capacity=2, deposits=dep))
            COUNTS['exhaustive_cases'] += 1

    def test_31_seeded_random_three_way_differential(self):
        rng = random.Random(20260911031)
        products = ['WHEAT', 'FERTILIZER', 'WOOL', 'COW']
        for i in range(4000):
            capacity = rng.randrange(1, 7)
            before = {item: rng.randrange(3) for item in products}
            queue = []
            for _ in range(rng.randrange(0, 6)):
                operation = rng.choice(['SELL', 'BUY_PRODUCT', 'BUY_ANIMAL', 'BUY_SEED', 'HIRE', 'PASS'])
                item = rng.choice(products)
                queue.append([operation, item, rng.choice([1, 2, 3, '2', 0, -1])])
            if i % 7 == 0:
                queue.insert(rng.randrange(len(queue)+1), None)
            slots = rng.randrange(0, 7)
            deposits = [] if i % 3 else [{key: rng.randrange(3) for key in rng.sample(products, 4)}]
            _, paths = oracle.paths(before, {'market': queue}, capacity, slots)
            if i % 4:
                stock, _ = rng.choice(paths)
                after = oracle.deposited(stock, deposits, capacity)
            else:
                after = {item: rng.randrange(4) for item in products}
            self.compare(case(before, queue, after, capacity, slots, deposits))
            COUNTS['random_cases'] += 1


def main():
    global BASELINE, ORIGINAL, CANDIDATE, SOURCE, OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    BASELINE = args.baseline
    SOURCE = BASELINE.read_bytes()
    OUTPUT = repair_module.repair(SOURCE)
    with tempfile.TemporaryDirectory(prefix='titan-fill-prune-') as work:
        materialized = Path(work)/'observed_fills.py'
        materialized.write_bytes(OUTPUT)
        ORIGINAL = load_file('_external_original_observed_fills', BASELINE)
        CANDIDATE = load_file('_materialized_candidate_observed_fills', materialized)
        suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
               'optimized': not __debug__, 'baseline_blob': repair_module.git_blob(SOURCE),
               'candidate_blob': repair_module.git_blob(OUTPUT), **COUNTS,
               'boundary': 'Inference component only; no official-interpreter or game-economics claim.'}
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n')
    print(json.dumps(receipt, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
