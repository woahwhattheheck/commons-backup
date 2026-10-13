"""Additional official-engine tests for the offline hosted-loss witnesses."""
import copy
from pathlib import Path
import unittest

import diagnostics as d
import market_witnesses as w
import test_diagnostics as fixtures


class MarketWitnessTests(unittest.TestCase):
    observation = fixtures.DiagnosticsTests.observation
    replay = fixtures.DiagnosticsTests.replay

    @classmethod
    def setUpClass(cls):
        fixtures.DiagnosticsTests.setUpClass()
        for name in ('tm', 'ev', 'engine', 'cfg'):
            setattr(cls, name, getattr(fixtures.DiagnosticsTests, name))

    def test_ranking_uses_own_view_and_preserves_nonprefix_slots(self):
        obs = self.observation()
        obs['farms'][1] = None
        obs['private']['shed'].update(WOOL=12, STRAWBERRY=18, MILK=12)
        obs['market']['inventory'].update(WOOL=10011, STRAWBERRY=10057, MILK=10015)
        action = {'farmer': ['PASS'], 'market': [
            ['SELL','STRAWBERRY',18], ['SELL','MILK',12], ['SELL','WOOL',12],
            ['HIRE'], ['SELL','WHEAT',8], ['BUY_SEED','WHEAT',2]]}
        original = copy.deepcopy((obs, action))
        alt, scores = w.impact_order(obs, action, self.engine, self.cfg)
        self.assertEqual(alt['market'][0], ['SELL','WOOL',12])
        self.assertEqual(alt['market'][3:], action['market'][3:])
        self.assertEqual(sorted(alt['market'][:3]), sorted(action['market'][:3]))
        self.assertEqual(len(scores), 3)
        self.assertEqual((obs, action), original)

    def test_quantity_is_bounded_by_owned_shed_and_floor_has_zero_risk(self):
        obs = self.observation()
        obs['private']['shed'].update(WOOL=3, STRAWBERRY=1)
        obs['market']['inventory'].update(WOOL=20000, STRAWBERRY=20000)
        action = {'market': [['SELL','WOOL',99], ['SELL','STRAWBERRY',30]]}
        alt, scores = w.impact_order(obs, action, self.engine, self.cfg)
        self.assertEqual([s['owned_quantity'] for s in scores], [3,1])
        self.assertEqual([s['mirrored_lot_receipt_risk'] for s in scores], [0,0])
        self.assertEqual(alt, action)

    def test_buy_first_means_no_reordering(self):
        obs = self.observation()
        action = {'market': [['BUY_SEED','WHEAT',1], ['SELL','WOOL',2]]}
        alt, scores = w.impact_order(obs, action, self.engine, self.cfg)
        self.assertEqual(alt, action)
        self.assertEqual(scores, [])

    def test_unused_seed_purchase_cut_is_cash_with_no_other_change(self):
        obs = self.observation()
        replay = self.replay(obs, [{'market': [['BUY_SEED','WHEAT',4]]}, {}])
        original = copy.deepcopy(replay)
        result = w.carry_path(replay, 0, {240: {'market': [['BUY_SEED','WHEAT',2]]}}, self.engine, self.ev, trace_module=self.tm)
        self.assertEqual(result['status'], 'RECORDED_PATH_EQUIVALENT_EXCEPT_CASH_AND_SEEDS')
        self.assertEqual(result['relative_cash_gain'], 20)
        self.assertEqual(result['terminal_seed_delta'], {'WHEAT': -2})
        self.assertEqual(result['compared_transitions'], 1)
        self.assertEqual(replay, original)

    def test_underbuy_rejected_when_later_planting_changes(self):
        obs = self.observation(step=30)
        obs['private']['seeds']['WHEAT'] = 0
        first = self.replay(obs, [{'market': [['BUY_SEED','WHEAT',1]]}, {}])
        next_obs = self.tm.observations(first['steps'][-1])[0]
        second = self.replay(next_obs, [{'farmer': ['PLANT','WHEAT']}, {}])
        replay = {**first, 'steps': first['steps']+[second['steps'][-1]]}
        result = w.carry_path(replay, 0, {30: {'market': [['BUY_SEED','WHEAT',0]]}}, self.engine, self.ev, trace_module=self.tm)
        self.assertEqual(result['status'], 'NONFINANCIAL_DIVERGENCE')
        self.assertEqual(result['action_step'], 31)
        self.assertFalse(result['checks']['farm_0'])
        self.assertNotIn('relative_cash_gain', result)

    def test_corrupt_baseline_cannot_claim_path_gain(self):
        replay = self.replay(self.observation(), [{'market': [['BUY_SEED','WHEAT',4]]}, {}])
        replay['steps'][-1][0]['observation']['farms'][0]['money'] += 1
        result = w.carry_path(replay, 0, {240: {}}, self.engine, self.ev, trace_module=self.tm)
        self.assertEqual(result['status'], 'BASELINE_MISMATCH')
        self.assertNotIn('relative_cash_gain', result)

    def test_zero_only_yield_key_is_not_a_quantity_divergence(self):
        replay = self.replay(self.observation(), [{}, {}])
        trace = self.tm.analyze(replay, self.engine, self.ev)
        trace['opening'][0]['held_yield']['EGG'] = 0
        trace['transitions'][0]['farms_after'][0]['held_yield']['EGG'] = 0
        report = d.summarize_trace(trace, 0)
        self.assertIsNone(report['first_observed_differences']['held_yield'])
        trace['transitions'][0]['farms_after'][0]['held_yield']['EGG'] = 1
        report = d.summarize_trace(trace, 0)
        self.assertEqual(report['first_observed_differences']['held_yield']['frame'], 1)

    def test_fractional_player_indices_are_errors(self):
        for player in (0.0, 1.0, '0', None):
            with self.assertRaises(ValueError):
                d._seat(player)

    def test_public_seed_enables_exact_random_boundary_comparison(self):
        replay = self.replay(self.observation(step=239), [{'market': [['BUY_SEED','WHEAT',4]]}, {}])
        replay['info']['seed'] = 0  # Actual fixture used the official default 0.
        result = w.carry_path(replay, 0, {239: {'market': [['BUY_SEED','WHEAT',2]]}}, self.engine, self.ev, trace_module=self.tm)
        self.assertEqual(result['status'], 'RECORDED_PATH_EQUIVALENT_EXCEPT_CASH_AND_SEEDS')
        self.assertTrue(result['seed_available_for_offline_engine'])
        self.assertEqual(result['excluded_random_boundaries'], [])
        self.assertEqual(result['relative_cash_gain'], 20)

    def test_outside_tape_or_empty_replacements_are_errors(self):
        replay = self.replay(self.observation(), [{}, {}])
        for changes in ({}, {241: {}}):
            with self.assertRaises(ValueError):
                w.carry_path(replay, 0, changes, self.engine, self.ev, trace_module=self.tm)


if __name__ == '__main__':
    unittest.main()
