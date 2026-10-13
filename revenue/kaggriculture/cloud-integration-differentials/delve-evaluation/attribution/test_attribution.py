"""New consumer/treatment checks; use saved states, never a scored game panel."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import unittest

import ablation_agent as agent
import attribute as a


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['DELVE_ATTR_TEST_PACKAGE'])
        cls.ev = a.load('delve_attr_test_eval', root/'source/tree/revenue/kaggriculture/cloud-eval/evaluate.py')
        cls.engine, _ = cls.ev.get_engine(root/'engine/engine', prepare=False)
        summary = json.loads((root/'evaluation/SUMMARY.json').read_text())
        cell = next(c for c in summary['cells'] if (c['seed'], c['player']) == (9965019, 0))
        path = (root/'evaluation'/cell['arms']['funded']['result_path']).with_suffix('.frames.jsonl.gz')
        cls.rows = a.read_rows(path)
        cls.originals = {k: getattr(cls.engine, k) for k in ('_commit_unit', '_do_hire', '_do_buy_land')}

    def tearDown(self):
        for name, value in self.originals.items():
            self.assertIs(getattr(self.engine, name), value)

    def test_baseline_full_state_and_cash(self):
        before = copy.deepcopy(self.rows[716:])
        result = a.replay(self.engine, self.ev, self.rows, 0, start=716, require_match=True)
        self.assertEqual(result['exact_post_states'], 3)
        self.assertEqual(result['cash_residual'], [0, 0])
        self.assertEqual(result['terminal'], [77678, 77208])
        self.assertEqual(self.rows[716:], before)

    def test_position_does_not_rewrite_shared_or_private_state(self):
        for position in (0, 1):
            result = a.replay(self.engine, self.ev, self.rows, position, start=716, require_match=True)
            self.assertEqual(result['terminal_state'], self.rows[-1]['state'])

    def test_incomplete_input(self):
        rows = self.rows[:-1]
        with self.assertRaisesRegex(ValueError, 'complete two-player'):
            a.replay(self.engine, self.ev, rows, 0, start=716)

    def test_invalid_position(self):
        for value in (True, -1, 2, 0.0, '0'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                a.replay(self.engine, self.ev, self.rows, value, start=716)

    def test_invalid_start(self):
        for value in (True, -1, 719, 716.0, '716'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                a.replay(self.engine, self.ev, self.rows, 0, start=value)

    def test_edits_must_be_in_suffix(self):
        for step in (True, 0, 719, 716.0):
            with self.subTest(step=step), self.assertRaises(ValueError):
                a.replay(self.engine, self.ev, self.rows, 0, start=716, insertions={step: ('MILK', 1)})

    def test_valid_sale_shape(self):
        for item, quantity in (('', 1), (None, 1), ('MILK', True), ('MILK', 0), ('MILK', 1.0)):
            with self.subTest(item=item, quantity=quantity), self.assertRaises(ValueError):
                a.replay(self.engine, self.ev, self.rows, 0, start=716, insertions={718: (item, quantity)})

    def test_valid_queue_shape(self):
        for queue in ('SELL', {'MILK': 2}, [None]):
            with self.subTest(queue=queue), self.assertRaises(ValueError):
                a.replay(self.engine, self.ev, self.rows, 0, start=716, market_overrides={718: queue})

    def test_baseline_cannot_contain_intervention(self):
        with self.assertRaisesRegex(ValueError, 'Baseline comparison'):
            a.replay(self.engine, self.ev, self.rows, 0, start=716,
                     insertions={718: ('MILK', 1)}, require_match=True)

    def test_full_slot_append_preserves_source_and_hooks(self):
        before = copy.deepcopy(self.rows[360:362])
        with self.assertRaisesRegex(ValueError, 'No appended market slot'):
            a.replay(self.engine, self.ev, self.rows, 0, start=360, insertions={360: ('MILK', 2)})
        self.assertEqual(self.rows[360:362], before)

    def test_oversized_override_restores_hooks(self):
        with self.assertRaisesRegex(ValueError, 'exceeds slot count'):
            a.replay(self.engine, self.ev, self.rows, 0, start=716,
                     market_overrides={718: [[] for _ in range(11)]})

    def test_literal_same_queue_is_exact(self):
        queue = copy.deepcopy(self.rows[719]['state'][0]['action']['market'])
        result = a.replay(self.engine, self.ev, self.rows, 0, start=716, market_overrides={718: queue})
        self.assertEqual(result['exact_post_states'], 3)
        self.assertEqual(result['terminal_state'], self.rows[-1]['state'])

    def test_full_state_recording(self):
        result = a.replay(self.engine, self.ev, self.rows, 0, start=716,
                          require_match=True, record_states=True)
        self.assertEqual(len(result['counterfactual_states']), 3)
        self.assertEqual(result['counterfactual_states'][-1]['state'], self.rows[-1]['state'])

    def test_failed_reconciliation_restores_hooks(self):
        rows = self.rows[:]
        rows[-1] = copy.deepcopy(rows[-1])
        rows[-1]['state'][0]['reward'] += 1
        with self.assertRaisesRegex(AssertionError, 'baseline fails'):
            a.replay(self.engine, self.ev, rows, 0, start=716, require_match=True)


class TreatmentTests(unittest.TestCase):
    def setUp(self):
        self.action = {'farmer': ['PASS'], 'hands': [['WATER']],
                       'market': [['SELL', 'MILK', 3], ['BUY_SEED', 'WHEAT', 11], ['HIRE']]}

    def test_other_steps_unchanged_and_detached(self):
        out, report = agent.intervene(self.action, 359, 'joint')
        self.assertEqual(out, self.action)
        self.assertIsNot(out, self.action)
        self.assertFalse(report['applied'])

    def test_suppress_preserves_slots_and_workers(self):
        before = copy.deepcopy(self.action)
        out, report = agent.intervene(self.action, 360, 'suppress360')
        self.assertEqual(out['market'], [[], *before['market'][1:]])
        self.assertEqual(out['farmer'], before['farmer'])
        self.assertEqual(out['hands'], before['hands'])
        self.assertTrue(report['applied'])
        self.assertEqual(self.action, before)

    def test_suppress_mismatched_selected_queue_is_unchanged(self):
        self.action['market'][0][2] = 4
        out, report = agent.intervene(self.action, 360, 'suppress360')
        self.assertEqual(out, self.action)
        self.assertFalse(report['applied'])

    def test_due_appends_only_when_a_slot_exists(self):
        out, report = agent.intervene(self.action, 381, 'due381')
        self.assertEqual(out['market'], self.action['market']+[['SELL', 'MILK', 2]])
        self.assertTrue(report['applied'])
        out, report = agent.intervene(self.action, 381, 'due381', maximum=3)
        self.assertEqual(out, self.action)
        self.assertFalse(report['applied'])

    def test_joint_has_only_the_two_declared_edits(self):
        for step in (360, 381):
            _, report = agent.intervene(self.action, step, 'joint')
            self.assertTrue(report['applied'])
        for step in (359, 361, 380, 382, 718):
            out, report = agent.intervene(self.action, step, 'joint')
            self.assertEqual(out, self.action)
            self.assertFalse(report['applied'])

    def test_undefined_treatment(self):
        with self.assertRaises(ValueError):
            agent.intervene(self.action, 360, 'other')


if __name__ == '__main__':
    unittest.main()
