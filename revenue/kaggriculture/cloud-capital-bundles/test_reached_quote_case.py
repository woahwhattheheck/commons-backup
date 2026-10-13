# SPDX-License-Identifier: Apache-2.0
"""Integration regressions; optional real input remains in private evidence."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import reached_quote_case as q

HERE = Path(__file__).resolve().parent


def example(deps):
    """Minimal constructed quotation input, not a physical reached-game state."""
    inventory = {p: 10000 for p in deps.mechanics.PRODUCTS}
    prices = {p: deps.mechanics.market_price(p, n) for p, n in inventory.items()}
    return {'step': 226, 'seat': 0, 'expected_action': {'never': 'model input'},
        'observation': {'step': 226, 'day': 9, 'hour': 10, 'player': 0,
            'farms': [{'money': 10000, 'hires_today': 0, 'unlocked_quadrants': ['NW']}
                      for _ in range(2)],
            'market': {'inventory': inventory, 'prices': prices},
            'private': {'inventories': [], 'shed': {}, 'seeds': {}},
            'town': {'unlocked_shops': ['BAKERY']}},
        'configuration': {'episodeSteps': 720, 'turnsPerDay': 24, 'seed': 99999}}


def specs():
    return [{'name': 'present_only'},
            {'name': 'declared_future', 'shop_additions': {'288': ['YARN_STORE']}}]


class ConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deps = q.load_dependencies()

    def run_case(self, row=None, scenarios=None, **kwargs):
        return q.compare_saved_input(example(self.deps) if row is None else row,
            specs() if scenarios is None else scenarios, self.deps,
            seconds=None, **kwargs)

    def test_no_agent_or_switch_callback(self):
        with (patch.object(self.deps.programs, 'Agent', side_effect=AssertionError('No actor')),
             patch.object(self.deps.hazel, 'choose_before_action', side_effect=AssertionError('No live switch'))):
            report = self.run_case()
        self.assertTrue(report['complete'])
        self.assertEqual(report['actor_calls'], 0)
        self.assertFalse(report['live_route_applied'])

    def test_original_pricing_and_ranking_functions_are_consumed(self):
        with (patch.object(self.deps.flow, 'evaluate_scenarios', wraps=self.deps.flow.evaluate_scenarios) as flow,
             patch.object(self.deps.date, 'DatedSelector', wraps=self.deps.date.DatedSelector) as date,
             patch.object(self.deps.hazel, 'quote_program', wraps=self.deps.hazel.quote_program) as quotes):
            self.run_case()
        self.assertEqual(flow.call_count, 1)
        self.assertEqual(date.call_count, 3)
        self.assertEqual(quotes.call_count, 2)

    def test_cash_rows_reconcile(self):
        result = self.run_case()
        self.assertEqual(result['reconciled_route_scenarios'], 4)
        self.assertTrue(all(v['complete'] for s in result['ranking']['scenarios']
                            for v in s['routes'].values()))

    def test_expected_action_and_seed_labels_do_not_influence_result(self):
        row = example(self.deps)
        initial = self.run_case(row)
        row['expected_action'] = {'market': [['SELL', 'WOOL', 99999]]}
        row['terminal_scores'] = [999999, 0]
        row['configuration']['seed'] = 44444
        self.assertEqual(self.run_case(row), initial)

    def test_input_and_scenario_mutation_absent(self):
        row, scenarios = example(self.deps), specs()
        before = copy.deepcopy((row, scenarios))
        self.run_case(row, scenarios)
        self.assertEqual((row, scenarios), before)

    def test_report_scenarios_do_not_alias_caller(self):
        scenarios = specs()
        report = self.run_case(scenarios=scenarios)
        report['scenario_specifications'][1]['shop_additions']['288'].append('BAKERY')
        self.assertEqual(scenarios, specs())

    def test_original_static_programs_are_not_changed(self):
        programs = self.deps.programs.routes()
        before = copy.deepcopy(programs)
        with patch.object(self.deps.programs, 'routes', return_value=programs):
            self.run_case()
        self.assertEqual(programs, before)

    def test_budget_exhaustion_does_not_rank_partial_vector(self):
        result = self.run_case(max_units=0)
        self.assertFalse(result['complete'])
        self.assertEqual(result['flow']['reason'], 'incomplete_budget')
        self.assertIsNone(result['ranking'])
        self.assertEqual(result['individual_rankings'], [])

    def test_seconds_budget_is_respected(self):
        result = q.compare_saved_input(example(self.deps), specs(), self.deps, seconds=0)
        self.assertFalse(result['complete'])
        self.assertEqual(result['flow']['reason'], 'incomplete_budget')

    def test_duplicate_scenario_identifiers_not_ranked(self):
        result = self.run_case(scenarios=[{'name': 'same'}, {'name': 'same'}])
        self.assertFalse(result['complete'])
        self.assertIsNone(result['ranking'])

    def test_no_implicit_scenario_or_calibrated_probability(self):
        for value in ([], [{'name': 'x', 'probability': .5}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_case(scenarios=value)

    def test_future_shop_is_not_moved_to_present(self):
        result = self.run_case(scenarios=[{'name': 'bad-date', 'shop_additions': {'226': ['YARN_STORE']}}])
        self.assertFalse(result['complete'])
        self.assertEqual(result['flow']['reason'], 'invalid_flow')

    def test_key_conversion_keeps_slots_and_duplicate_shops(self):
        values = [{'name': 'explicit', 'rival_orders': {'240': [['PASS'], ['SELL', 'WOOL', 8]]},
                   'shop_additions': {'288': ['BAKERY', 'BAKERY']}}]
        converted = q.make_scenarios(values, self.deps.flow)[0]
        self.assertEqual(converted.rival_orders[240][0], ['PASS'])
        self.assertEqual(converted.shop_additions[288], ['BAKERY', 'BAKERY'])
        with self.assertRaises(ValueError): q._steps({'0288': [], '288': []})
        for invalid in (True, 2.5, '2.5', '٢'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): q._steps({invalid: []})

    def test_wrong_clock_or_cross_seat_is_not_relabelled(self):
        for key, value in [('seat', 1), ('step', 225), ('seat', True)]:
            row = example(self.deps); row[key] = value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError): self.run_case(row)

    def test_other_checkpoint_needs_its_own_consumer(self):
        row = example(self.deps)
        row['step'] = row['observation']['step'] = 577
        row['observation'].update(day=24,hour=1)
        with self.assertRaises(ValueError): self.run_case(row)

    def test_cli_fresh_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'input.json').write_text(json.dumps(example(self.deps)))
            (root/'scenarios.json').write_text(json.dumps(specs()))
            command = [sys.executable, str(HERE/'reached_quote_case.py'), str(root/'input.json'),
                str(root/'scenarios.json'), '--output', str(root/'report.json')]
            run = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            original = (root/'report.json').read_bytes()
            repeated = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual((root/'report.json').read_bytes(), original)

    def test_cli_incomplete_report_has_distinct_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'input.json').write_text(json.dumps(example(self.deps)))
            (root/'scenarios.json').write_text(json.dumps(specs()))
            run = subprocess.run([sys.executable, str(HERE/'reached_quote_case.py'), str(root/'input.json'),
                str(root/'scenarios.json'), '--output', str(root/'report.json'), '--max-units', '0'],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 3)
            self.assertFalse(json.loads((root/'report.json').read_text())['complete'])

    @unittest.skipUnless(os.environ.get('OSPREY_QUOTE_INPUT') and os.environ.get('OSPREY_QUOTE_EXPECTED'),
                         'Set OSPREY_QUOTE_INPUT and OSPREY_QUOTE_EXPECTED for the retained observation')
    def test_retained_natural_input(self):
        row = json.loads(Path(os.environ['OSPREY_QUOTE_INPUT']).read_text())
        expected = json.loads(Path(os.environ['OSPREY_QUOTE_EXPECTED']).read_text())
        self.assertEqual(q.sha256(q.canonical(row['observation'])), expected['observation_sha256'])
        report = self.run_case(row)
        self.assertEqual(report['original_mark_choice'], expected['original_mark_choice'])
        self.assertEqual(report['ranking']['selected'], expected['joint_choice'])
        self.assertEqual([r['selected'] for r in report['individual_rankings']], expected['individual_choices'])
        self.assertEqual([[r['final_marked_cash'] for r in world] for world in report['flow']['rows']],
                         expected['final_cash_by_scenario_and_route'])
        self.assertEqual(report['flow']['unit_rounds'], expected['unit_rounds'])


if __name__ == '__main__':
    unittest.main()
