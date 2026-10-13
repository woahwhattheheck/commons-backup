#!/usr/bin/env python3
"""Independent FWD-BUY census contract. No gameplay or economics execution.

Usage: python [-O] test_fwd_census_engine_contract.py DECODER.py [--engine ENGINE.py]
The optional engine adapter tests raw-slot/order grammar with stubbed commits;
it is not a full-game evaluator and cannot establish profit or activation rates.
"""
from __future__ import annotations
import argparse
import ast
import copy
import importlib.util
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError('cannot load decoder')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('decoder', type=Path)
PARSER.add_argument('--engine', type=Path)
ARGS, UNITTEST_ARGS = PARSER.parse_known_args()
D = load(ARGS.decoder, '_decoder_under_test')


def action(rows=None):
    return {'market': [] if rows is None else rows}


def buy(product='WHEAT', quantity=1):
    return ['BUY_PRODUCT', product, quantity]


def report(*tape):
    return D.analyze([list(tape)], require_shape=False)


class CensusContract(unittest.TestCase):
    def test_official_sell_blocks_prior_candidate_for_both_products(self):
        for product in ('WHEAT', 'FERTILIZER'):
            with self.subTest(product=product):
                result = report(action(), action([['SELL', product, 1]]), action([buy(product)]))
                self.assertIsNone(result['records'][0]['candidate_step'])

    def test_same_product_buy_blocks(self):
        result = report(action(), action([buy()]), action([buy()]))
        self.assertIsNone(result['records'][1]['candidate_step'])

    def test_other_product_sale_does_not_steal_nearest_slot(self):
        result = report(action([['SELL', 'MILK', 1]]), action([buy()]))
        self.assertEqual(result['records'][0]['candidate_step'], 0)

    def test_cap_boundary_ninth_tenth_and_eleventh_raw_slots(self):
        for prefix in (8, 9, 10, 11):
            with self.subTest(prefix=prefix):
                result = report(action([[] for _ in range(prefix)] + [buy()]))
                self.assertEqual(result['summary']['total_positive_exact_buys'], int(prefix < 10))
                if prefix < 10:
                    self.assertEqual(result['records'][0]['later_market_row'], prefix)

    def test_dead_suffix_hire_does_not_block_search_across_full_step(self):
        result = report(action(), action([[] for _ in range(10)] + [['HIRE']]), action([buy()]))
        self.assertEqual(result['records'][0]['candidate_step'], 0)
        self.assertEqual(result['records'][0]['gap'], 2)

    def test_dead_suffix_same_product_sale_does_not_block(self):
        result = report(action(), action([[] for _ in range(10)] + [['SELL', 'WHEAT', 2]]), action([buy()]))
        self.assertEqual(result['records'][0]['candidate_step'], 0)

    def test_full_prefix_cannot_receive_an_appended_buy(self):
        result = report(action([[] for _ in range(10)]), action([buy()]))
        self.assertIsNone(result['records'][0]['candidate_step'])

    def test_source_callback_hire_buy_atomicity(self):
        result = report(action(), action([['HIRE'], buy('FERTILIZER')]))
        self.assertIsNone(result['records'][0]['candidate_step'])

    def test_source_callback_all_hard_barriers(self):
        for row in (['BUY_LAND'], ['BUY_SEED', 'WHEAT', 1], ['BUY_ANIMAL', 'COW', 1]):
            with self.subTest(row=row):
                result = report(action(), action([row, buy()]))
                self.assertIsNone(result['records'][0]['candidate_step'])

    def test_source_callback_same_product_sale_dependency(self):
        result = report(action(), action([['SELL', 'WHEAT', 2], buy()]))
        self.assertIsNone(result['records'][0]['candidate_step'])

    def test_source_callback_prior_same_product_buy_dependency(self):
        result = report(action(), action([buy(), buy()]))
        self.assertIsNone(result['records'][0]['candidate_step'])
        self.assertIsNone(result['records'][1]['candidate_step'])

    def test_companion_guard_is_intentionally_conservative_on_later_hire(self):
        result = report(action(), action([buy(), ['HIRE']]))
        self.assertIsNone(result['records'][0]['candidate_step'])

    def test_raw_indices_survive_empty_prefix_rows(self):
        result = report(action(), action([[], [], buy()]))
        self.assertEqual(result['records'][0]['later_market_row'], 2)
        self.assertEqual(result['records'][0]['candidate_step'], 0)

    def test_exact_buy_rejects_unhashable_or_nonstring_products(self):
        for product in ([], {}, None, 1, True):
            with self.subTest(product=product):
                self.assertIsNone(D.exact_buy(['BUY_PRODUCT', product, 1]))

    def test_exact_buy_rejects_quantity_coercions(self):
        for quantity in (False, True, 0, -1, 1.0, '1', None):
            with self.subTest(quantity=quantity):
                self.assertIsNone(D.exact_buy(['BUY_PRODUCT', 'WHEAT', quantity]))

    def test_gap_histogram_and_day_boundary(self):
        tape = [action() for _ in range(25)]
        tape[24] = action([buy()])
        result = D.analyze([tape], require_shape=False)
        self.assertEqual(result['summary']['same_day_candidates'], 0)
        self.assertEqual(result['summary']['prior_day_candidates'], 1)
        self.assertEqual(result['summary']['gap_histogram'], {'1': 1})
        self.assertEqual(result['summary']['max_gap'], 1)

    def test_no_runtime_or_economic_proof_is_fabricated(self):
        row = report(action(), action([buy()]))['records'][0]
        for key in ('cash_affordability', 'shed_capacity', 'opponent_market_effect'):
            self.assertEqual(row[key], 'NEEDS_RUNTIME_PROOF')

    def test_input_nonmutation_and_determinism(self):
        tape = [action(), action([[], buy('FERTILIZER', 3)])]
        frozen = copy.deepcopy(tape)
        first = D.analyze([tape], require_shape=False)
        second = D.analyze([tape], require_shape=False)
        self.assertEqual(tape, frozen)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_production_shape_rejected_unless_exact(self):
        for tapes in ([], [[]], [[action()] for _ in range(13)]):
            with self.subTest(count=len(tapes)):
                with self.assertRaises(ValueError):
                    D.analyze(tapes)
        correct = [[action() for _ in range(719)] for _ in range(13)]
        result = D.analyze(correct)
        self.assertEqual(result['summary']['tape_count'], 13)
        self.assertEqual(result['summary']['total_positive_exact_buys'], 0)

    def test_frozen_tape_identity_remains_pinned(self):
        self.assertEqual(D.EXPECTED_BLOB, 'a43289b9cc5e34a2481fddf652762a7d92f427ef')

    def test_self_test_rejects_wrong_results_even_under_python_optimized(self):
        saved = D.analyze
        D.analyze = lambda *args, **kwargs: {'summary': {'total_positive_exact_buys': 999, 'max_gap': 1}, 'records': []}
        try:
            with self.assertRaises((AssertionError, ValueError, RuntimeError)):
                D.self_test()
        finally:
            D.analyze = saved


@unittest.skipUnless(ARGS.engine, 'supply --engine for frozen-interpreter grammar checks')
class EngineGrammarContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = ARGS.engine.read_bytes()
        engine_blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if engine_blob != '3c202c7ee921da239356789e266b694635103fc4':
            raise ValueError('wrong pinned engine: ' + engine_blob)
        tree = ast.parse(raw)
        names = {'_process_market', '_parse_order'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        if {n.name for n in nodes} != names:
            raise ValueError('engine grammar functions not found')
        cls.code = compile(ast.Module(body=nodes, type_ignores=[]), str(ARGS.engine), 'exec')

    def execute_rows(self, rows):
        events = []
        namespace = {
            'get': lambda config, name, default: getattr(config, name, default),
            'FARM_HAND_COST_MULT': 1,
            'PRODUCTS': {'WHEAT', 'FERTILIZER', 'MILK'},
            'CROPS': {}, 'ANIMALS': {},
            'market_price': lambda *args: 5,
            '_refresh_prices': lambda market: None,
            '_do_hire': lambda *args: events.append('HIRE'),
            '_do_buy_land': lambda *args: events.append('BUY_LAND'),
        }
        def commit(op, *args):
            events.append(op)
            return True
        namespace['_commit_unit'] = commit
        exec(self.code, namespace)
        market = {'inventory': {'WHEAT': 100, 'FERTILIZER': 100, 'MILK': 100}}
        farms = [{}, {}]
        state = [SimpleNamespace(action=action(r), observation=SimpleNamespace(
            market=market, farms=farms, private={})) for r in (rows, [])]
        env = SimpleNamespace(configuration=SimpleNamespace(maxMarketOrdersPerTurn=10))
        namespace['_process_market'](state, env)
        return events

    def test_engine_recognizes_sell_not_sell_product(self):
        self.assertEqual(self.execute_rows([['SELL', 'WHEAT', 1]]), ['SELL'])
        self.assertEqual(self.execute_rows([['SELL_PRODUCT', 'WHEAT', 1]]), [])

    def test_engine_uses_uncompacted_raw_ten_row_prefix(self):
        self.assertEqual(self.execute_rows([[] for _ in range(9)] + [buy()]), ['BUY_PRODUCT'])
        self.assertEqual(self.execute_rows([[] for _ in range(10)] + [buy()]), [])
        self.assertEqual(self.execute_rows([[] for _ in range(10)] + [['HIRE']]), [])

    def test_engine_preserves_source_hire_before_buy(self):
        self.assertEqual(self.execute_rows([['HIRE'], buy('FERTILIZER')]), ['HIRE', 'BUY_PRODUCT'])


if __name__ == '__main__':
    unittest.main(argv=[__file__, *UNITTEST_ARGS])
