"""Regression: terminal market slots are occurrences, not Python object identities.

Uses the existing admission/official-engine test harness. No game panel is run.
Set TITAN_ADMISSION_SOURCE to exercise an exact older runtime against this suite.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
TARGET = Path(os.environ.get('TITAN_ADMISSION_SOURCE', HERE / 'terminal_admission.py')).resolve()
spec = importlib.util.spec_from_file_location('terminal_admission', TARGET)
admission = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = admission
spec.loader.exec_module(admission)

import test_terminal_admission as fixture

RECORDS = []
COUNTS = {'queue_comparisons': 0, 'full_transform_comparisons': 0,
          'official_terminal_transitions': 0}


def node(shed):
    return admission._Node({}, {'shed': copy.deepcopy(shed)}, [['PASS']])


def liquidate(queue, shed, limit=10):
    selected = {'farmer': ['PASS'], 'hands': [], 'market': queue}
    return admission._liquidate(fixture.engine, selected, node(shed),
                               {'maxMarketOrdersPerTurn': limit})


def stable_report(report):
    """Elapsed wall time is not part of action/receipt correspondence."""
    return {key: value for key, value in report.items() if key != 'elapsed_s'}


class OrderOccurrenceTests(unittest.TestCase):
    def test_first_shared_sale_keeps_full_quantity(self):
        order = ['SELL', 'WOOL', 100]
        actual = liquidate([order, order], {'WOOL': 3})
        self.assertEqual(actual['market'], [['SELL', 'WOOL', 3], ['SELL', 'WOOL', 0]])
        self.assertIsNot(actual['market'][0], actual['market'][1])
        self.assertEqual(order, ['SELL', 'WOOL', 100])

    def test_nonadjacent_occurrences_preserve_market_positions(self):
        wool = ['SELL', 'WOOL', 9]
        actual = liquidate([wool, ['BUY_SEED', 'WHEAT', 0], wool,
                            ['SELL', 'MILK', 9]], {'WOOL': 3, 'MILK': 2})
        self.assertEqual(actual['market'], [
            ['SELL', 'WOOL', 3], ['BUY_SEED', 'WHEAT', 0],
            ['SELL', 'WOOL', 0], ['SELL', 'MILK', 2]])

    def test_three_shared_occurrences_zero_only_later_slots(self):
        order = ['SELL', 'MILK', 12]
        actual = liquidate([order] * 3, {'MILK': 5})
        self.assertEqual([row[2] for row in actual['market']], [5, 0, 0])
        self.assertEqual(len({id(row) for row in actual['market']}), 3)

    def test_multiple_interleaved_alias_groups(self):
        milk, wool = ['SELL', 'MILK', 9], ['SELL', 'WOOL', 9]
        actual = liquidate([milk, wool, milk, wool], {'MILK': 2, 'WOOL': 3})
        self.assertEqual(actual['market'], [
            ['SELL', 'MILK', 2], ['SELL', 'WOOL', 3],
            ['SELL', 'MILK', 0], ['SELL', 'WOOL', 0]])

    def test_market_limit_truncates_before_occurrence_edits(self):
        order = ['SELL', 'WOOL', 100]
        for limit in (1, 2, 3):
            with self.subTest(limit=limit):
                actual = liquidate([order] * 4, {'WOOL': 2}, limit)
                self.assertEqual(actual['market'],
                                 [['SELL', 'WOOL', 2]] + [['SELL', 'WOOL', 0]] * (limit - 1))
        self.assertEqual(order, ['SELL', 'WOOL', 100])

    def test_untouched_non_sale_aliases_stay_detached_and_shared(self):
        order = ['BUY_SEED', 'WHEAT', 0, {'note': ['unchanged']}]
        actual = liquidate([order, order], {})
        self.assertEqual(actual['market'], [order, order])
        self.assertIs(actual['market'][0], actual['market'][1])
        self.assertIsNot(actual['market'][0], order)
        actual['market'][0][3]['note'].append('output-only')
        self.assertEqual(order[3]['note'], ['unchanged'])

    def test_sale_extra_fields_are_deeply_detached(self):
        order = ['SELL', 'WOOL', 9, {'note': ['unchanged']}]
        actual = liquidate([order, order], {'WOOL': 2})
        self.assertEqual([row[2] for row in actual['market']], [2, 0])
        actual['market'][0][3]['note'].append('first-only')
        self.assertEqual(actual['market'][1][3]['note'], ['unchanged'])
        self.assertEqual(order[3]['note'], ['unchanged'])

    def test_empty_stock_and_appended_product_remain_consistent(self):
        order = ['SELL', 'WOOL', 9]
        actual = liquidate([order, order], {'WOOL': 0, 'WHEAT': 2})
        self.assertEqual(actual['market'], [
            ['SELL', 'WOOL', 0], ['SELL', 'WOOL', 0], ['SELL', 'WHEAT', 2]])

    def test_queue_matrix_matches_json_value_semantics(self):
        for product, quantity, repeats, limit in itertools.product(
                ('WHEAT', 'MILK', 'WOOL'), (0, 1, 3), (2, 3, 4), (1, 2, 4)):
            with self.subTest(product=product, quantity=quantity, repeats=repeats, limit=limit):
                order = ['SELL', product, 100]
                queue = [order] * repeats
                serialized = json.loads(json.dumps(queue))
                before = copy.deepcopy(queue)
                actual = liquidate(queue, {product: quantity}, limit)
                expected = liquidate(serialized, {product: quantity}, limit)
                COUNTS['queue_comparisons'] += 1
                self.assertEqual(actual, expected)
                self.assertEqual(queue, before)
                self.assertIs(queue[0], queue[-1])

    def test_full_transform_matches_engine_and_json_both_positions(self):
        for player, capacity, repeats in itertools.product((0, 1), (2, 3), (2, 3)):
            with self.subTest(player=player, capacity=capacity, repeats=repeats):
                states, env = fixture.setup_case(
                    capacity=capacity, carried=[{'WHEAT': capacity}, {'WOOL': capacity}], player=player)
                order = ['SELL', 'WOOL', 100]
                selected = {'farmer': ['DROP'], 'hands': [['DROP']],
                            'market': [order] * repeats + [['SELL', 'WHEAT', 100]]}
                before = json.dumps([states, env, selected], sort_keys=True)
                hypotheses = fixture.scenarios(capacity)
                actual, report = fixture.solve(states, env, selected, player, scenarios=hypotheses)
                expected, reference = fixture.solve(
                    states, env, json.loads(json.dumps(selected)), player, scenarios=hypotheses)
                COUNTS['full_transform_comparisons'] += 1
                # Collect all three interpreter outcomes before comparison so the old
                # failing runtime still retains complete original/repaired witnesses.
                outcomes = []
                for scenario, row in zip(hypotheses, report['scenarios']):
                    result = {'scenario': scenario.name, 'report': row, 'actions': {}}
                    for label, choice in (('original', selected),
                                          ('control', report['same_workers_liquidation_action']),
                                          ('selected', actual)):
                        cash, final = fixture.transition(states, env, choice, scenario, player)
                        COUNTS['official_terminal_transitions'] += 1
                        result['actions'][label] = {
                            'cash_delta': cash,
                            'own_farm': copy.deepcopy(final[player].observation.farms[player]),
                            'own_private': copy.deepcopy(final[player].observation.private),
                            'market': copy.deepcopy(final[player].observation.market)}
                        self.assertEqual(cash, [row[label + '_own'], row[label + '_rival']])
                    outcomes.append(result)
                RECORDS.append({'player': player, 'capacity': capacity, 'repeats': repeats,
                                'input': copy.deepcopy(states[player].observation),
                                'configuration': dict(env.configuration), 'original': selected,
                                'actual': actual, 'json_value_control': expected,
                                'report': stable_report(report),
                                'json_value_report': stable_report(reference), 'outcomes': outcomes})
                self.assertEqual(before, json.dumps([states, env, selected], sort_keys=True))
                self.assertIs(selected['market'][0], selected['market'][1])
                self.assertTrue(report['changed'])
                self.assertEqual(actual, expected)
                self.assertEqual(stable_report(report), stable_report(reference))

    def test_nonterminal_fallback_preserves_original_aliases(self):
        states, env = fixture.setup_case()
        states[0].observation.step = 717
        order = ['SELL', 'WOOL', 100]
        selected = {'farmer': ['DROP'], 'hands': [['DROP']], 'market': [order, order]}
        actual, report = fixture.solve(states, env, selected)
        self.assertEqual(actual, selected)
        self.assertIs(actual['market'][0], actual['market'][1])
        self.assertIsNot(actual['market'][0], order)
        self.assertEqual(report['reason'], 'nonterminal')

    def test_order_identity_does_not_change_complete_interpreter(self):
        for player in (0, 1):
            with self.subTest(player=player):
                states, env = fixture.setup_case(carried=[{}, {}], shed={'WOOL': 3}, player=player)
                order = ['SELL', 'WOOL', 2]
                selected = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': [order, order]}
                for scenario in fixture.scenarios():
                    left = fixture.transition(states, env, selected, scenario, player)
                    right = fixture.transition(states, env, json.loads(json.dumps(selected)), scenario, player)
                    COUNTS['official_terminal_transitions'] += 2
                    self.assertEqual(left, right)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OrderOccurrenceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report_path = os.environ.get('TITAN_OCCURRENCE_REPORT')
    if report_path:
        data = TARGET.read_bytes()
        report = {'source': {'sha256': hashlib.sha256(data).hexdigest(),
                             'git_blob': hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()},
                  'engine_hashes': fixture.ENGINE_HASHES,
                  'test_methods': result.testsRun, 'failures': len(result.failures),
                  'errors': len(result.errors), 'skipped': len(result.skipped),
                  'success': result.wasSuccessful(), 'counts': COUNTS,
                  'records': RECORDS, 'full_games': 0, 'game_seeds': []}
        Path(report_path).write_text(json.dumps(report, indent=2) + '\n')
    sys.exit(0 if result.wasSuccessful() else 1)
