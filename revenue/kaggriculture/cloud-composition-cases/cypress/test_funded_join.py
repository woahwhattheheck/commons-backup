# SPDX-License-Identifier: Apache-2.0
"""Execute the funded-seed join through the real integrated producer and seller.

Only this suite is collected. The unchanged existing test helper supplies the
pinned official engine and constructed observations, not its old test methods.
No completed panel, held example or full game is replayed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--lab', type=Path, default=ROOT / 'cloud-execution-lab')
PARSER.add_argument('--funding-dir', type=Path,
                    default=ROOT / 'cloud-integration-differentials')
PARSER.add_argument('--json-output', type=Path)
ARGS, UNUSED = PARSER.parse_known_args()
LAB = ARGS.lab.resolve()
FUNDING = ARGS.funding_dir.resolve()
sys.path.insert(0, str(LAB))
sys.path.insert(0, str(FUNDING))
import integrated_selected as I
import seed_funding as CEDAR
from test_ordered_selected_sell import OrderedSelectedSellTests, action

RECEIPTS: list[dict] = []
TRANSITIONS = 0


class FundedJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OrderedSelectedSellTests.setUpClass()
        cls.helper = OrderedSelectedSellTests()
        cls.engine = cls.helper.engine

    def case(self, selected, *, seat=0, step=100, cash=1000, hires=12,
             seeds=0, future=None, shed=None, carried=None, callback=CEDAR.select_seed_queue,
             use_default=False, sell=True, seed=True):
        state, env = self.helper.helper.fixture(step=step, cash=100000,
                                                shops=['FARMERS_MARKET'])
        obs = state[seat].observation
        positions = self.engine._shed_access_tiles(10)
        farm = obs['farms'][seat]
        farm['farmer'] = list(positions[0])
        farm['hands'] = [list(positions[1])]
        farm['money'] = cash
        farm['hires_today'] = hires
        obs['private']['shed'] = copy.deepcopy(shed or {})
        obs['private']['inventories'] = copy.deepcopy(carried or [{}, {}])
        obs['private']['seeds']['WHEAT'] = seeds
        kwargs = {'sell': sell, 'seed': seed}
        if not use_default:
            kwargs['seed_queue_selector'] = callback
        obj = I.make_agent(**kwargs)
        route = [action() for _ in range(720)]
        route[step] = copy.deepcopy(selected)
        for at, decision in (future or {}).items():
            route[at] = copy.deepcopy(decision)
        obj.controller.R = {'funded_case': route}
        obj.controller.cur = 'funded_case'
        obj.budget = I.budget_module.SeedBudget(obj.controller.R)
        return obj, obs, env.configuration, state, env

    def advance(self, state, env, selected, *, seat=0, step=100, rival=None):
        global TRANSITIONS
        state, env = copy.deepcopy((state, env))
        for index, row in enumerate(state):
            row.observation['step'] = step
            row.action = copy.deepcopy(selected if index == seat else (rival or action()))
        self.engine.interpreter(state, env)
        TRANSITIONS += 1
        return state, env

    def assert_nonseed_equal(self, before, after, seat, savings):
        own_before = before[seat].observation
        own_after = after[seat].observation
        cash_before = own_before['farms'][seat]['money']
        cash_after = own_after['farms'][seat]['money']
        self.assertEqual(cash_after - cash_before, savings)
        farms_before = copy.deepcopy(own_before['farms'])
        farms_after = copy.deepcopy(own_after['farms'])
        farms_before[seat].pop('money')
        farms_after[seat].pop('money')
        self.assertEqual(farms_after, farms_before)
        private_before = copy.deepcopy(own_before['private'])
        private_after = copy.deepcopy(own_after['private'])
        private_before.pop('seeds')
        private_after.pop('seeds')
        self.assertEqual(private_after, private_before)
        self.assertEqual(own_after['market'], own_before['market'])
        self.assertEqual(own_after['town'], own_before['town'])
        self.assertEqual(after[1-seat].observation['private'], before[1-seat].observation['private'])
        return cash_before, cash_after

    def test_funded_hire_real_budget_projection_and_market_both_seats(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        future = {t: action(['PLANT', 'WHEAT']) for t in (101, 102, 103)}
        for seat in (0, 1):
            with self.subTest(seat=seat):
                obj, obs, cfg, state, env = self.case(selected, seat=seat, future=future)
                saved = copy.deepcopy((obs, cfg, selected))
                with patch.object(obj.production, 'act', side_effect=AssertionError('second producer')):
                    out = obj.transform(obs, cfg, selected)
                self.assertEqual(out['market'], [['BUY_SEED', 'WHEAT', 3], ['HIRE']])
                self.assertEqual(obj.diagnostics['seed_reason'], 'funded_economic_order')
                report = obj.diagnostics['seed_funding']
                self.assertEqual(report['status'], 'certified')
                self.assertEqual(report['seed_cash_reduction'], 140)
                self.assertEqual(obj.last_seeded, out)
                self.assertIsNotNone(obj.last_packet)
                self.assertEqual(obj.last_packet['post_unit_observation']['private']['seeds']['WHEAT'], 0)
                self.assertEqual((obs, cfg, selected), saved)
                baseline, _ = self.advance(state, env, selected, seat=seat)
                funded, _ = self.advance(state, env, out, seat=seat)
                cash_before, cash_after = self.assert_nonseed_equal(baseline, funded, seat, 140)
                self.assertEqual(funded[seat].observation['private']['seeds']['WHEAT'], 3)
                RECEIPTS.append({'case': 'funded_budget_seller', 'seat': seat,
                                 'own_cash_before': cash_before, 'own_cash_after': cash_after,
                                 'retained_seeds': 3, 'non_seed_state_equal': True,
                                 'diagnostics': copy.deepcopy(obj.diagnostics)})

    def test_certificate_receives_post_plant_state_once(self):
        selected = action(['PLANT', 'WHEAT'], market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        callback = Mock(wraps=CEDAR.select_seed_queue)
        obj, obs, cfg, state, env = self.case(selected, seeds=1,
                                             future={101: action(['PLANT', 'WHEAT'])},
                                             callback=callback)
        x, y = obs['farms'][0]['farmer']
        obs['farms'][0]['tiles'][y][x] = None
        out = obj.transform(obs, cfg, selected)
        self.assertEqual(callback.call_count, 1)
        self.assertEqual(callback.call_args.args[1]['private']['seeds']['WHEAT'], 0)
        self.assertEqual(out['market'][0], ['BUY_SEED', 'WHEAT', 1])
        self.assertEqual(out['farmer'], selected['farmer'])
        baseline, _ = self.advance(state, env, selected)
        funded, _ = self.advance(state, env, out)
        self.assert_nonseed_equal(baseline, funded, 0, 160)
        self.assertEqual(funded[0].observation['private']['seeds']['WHEAT'], 1)
        RECEIPTS.append({'case': 'post_plant_certificate', 'callback_calls': 1,
                         'post_unit_seeds': 0, 'retained': 1, 'cash_delta': 160})

    def test_underfunded_queue_keeps_original_and_records_rejection(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        obj, obs, cfg, state, env = self.case(selected, cash=300)
        out = obj.transform(obs, cfg, selected)
        self.assertEqual(out, selected)
        self.assertEqual(obj.diagnostics['seed_reason'], 'later_economic_order')
        self.assertEqual(obj.diagnostics['seed_funding']['status'], 'not_certified')
        correct, _ = self.advance(state, env, out)
        unsafe, _ = self.advance(state, env, action(market=[[], ['HIRE']]))
        self.assertEqual(correct[0].observation['farms'][0]['money'], 130)
        self.assertEqual(unsafe[0].observation['farms'][0]['money'], 67)
        self.assertEqual(len(unsafe[0].observation['farms'][0]['hands']),
                         len(correct[0].observation['farms'][0]['hands']) + 1)
        RECEIPTS.append({'case': 'underfunded_negative', 'original_cash': 130,
                         'uncertified_reduction_cash': 67, 'original_preserved': True})

    def test_default_and_explicit_none_keep_existing_behavior(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        outputs = []
        for use_default in (True, False):
            obj, obs, cfg, _, _ = self.case(selected, callback=None, use_default=use_default)
            outputs.append(obj.transform(obs, cfg, selected))
            self.assertEqual(obj.diagnostics['seed_reason'], 'later_economic_order')
        self.assertEqual(outputs, [selected, selected])

    def test_seed_disabled_never_calls_certificate(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        callback = Mock(side_effect=AssertionError('disabled seed callback'))
        obj, obs, cfg, _, _ = self.case(selected, seed=False, callback=callback)
        self.assertEqual(obj.transform(obs, cfg, selected), selected)
        callback.assert_not_called()
        self.assertEqual(obj.diagnostics['seed_reason'], 'disabled')

    def test_extra_current_plant_is_not_reauthorized_by_funding(self):
        routed = action(market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        selected = copy.deepcopy(routed)
        selected['farmer'] = ['PLANT', 'WHEAT']
        callback = Mock(side_effect=AssertionError('demand-ineligible callback'))
        obj, obs, cfg, _, _ = self.case(routed, seeds=1, callback=callback)
        x, y = obs['farms'][0]['farmer']
        obs['farms'][0]['tiles'][y][x] = None
        out = obj.transform(obs, cfg, selected)
        self.assertEqual(out['market'][0], selected['market'][0])
        self.assertEqual(obj.diagnostics['seed_reason'], 'selected_plant_requests_exceed_route')
        callback.assert_not_called()

    def test_no_seed_edit_never_calls_certificate(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 1], ['HIRE']])
        callback = Mock(side_effect=AssertionError('no-edit callback'))
        obj, obs, cfg, _, _ = self.case(selected, future={101: action(['PLANT', 'WHEAT'])},
                                        callback=callback)
        self.assertEqual(obj.transform(obs, cfg, selected), selected)
        callback.assert_not_called()

    def test_no_dependent_order_uses_existing_alder_path(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17]])
        callback = Mock(side_effect=AssertionError('unneeded callback'))
        obj, obs, cfg, _, _ = self.case(selected, callback=callback)
        self.assertEqual(obj.transform(obs, cfg, selected)['market'], [[]])
        self.assertEqual(obj.diagnostics['seed_reason'], 'applied')
        callback.assert_not_called()

    def test_positive_product_purchase_remains_unresolved(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17], ['BUY_PRODUCT', 'WHEAT', 1]])
        obj, obs, cfg, _, _ = self.case(selected)
        out = obj.transform(obs, cfg, selected)
        self.assertEqual(out, selected)
        self.assertEqual(obj.diagnostics['seed_funding']['status'], 'not_certified')
        self.assertIn('paired-flow', obj.diagnostics['seed_funding']['reason'])

    def test_parent_control_still_uses_join_and_has_no_seller_call(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        obj, obs, cfg, _, _ = self.case(selected, sell=False)
        with patch.object(obj.execution.seller, 'transform', side_effect=AssertionError('seller in parent')):
            out = obj.transform(obs, cfg, selected)
        self.assertEqual(out['market'], [[], ['HIRE']])
        self.assertEqual(obj.diagnostics['status'], 'parent_control')
        self.assertEqual(obj.diagnostics['seed_funding']['status'], 'certified')

    def test_failed_certificate_preserves_explicit_fallback_without_retry(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        callback = Mock(side_effect=TypeError('funding-body-marker'))
        obj, obs, cfg, _, _ = self.case(selected, callback=callback)
        fallback = action(market=[['BUY_SEED', 'WHEAT', 17]])
        out = obj.transform(obs, cfg, selected, fallback_action=fallback)
        self.assertEqual(out, fallback)
        self.assertEqual(callback.call_count, 1)
        self.assertIn('funding-body-marker', obj.diagnostics['reason'])
        out['market'].clear()
        self.assertTrue(fallback['market'])

    def test_truncated_acquisition_does_not_invent_funding_cost(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        obj, obs, cfg, state, env = self.case(selected, cash=170)
        cfg['maxMarketOrdersPerTurn'] = 1
        out = obj.transform(obs, cfg, selected)
        self.assertEqual(out['market'], [[], ['HIRE']])
        self.assertEqual(obj.diagnostics['seed_funding']['original_fixed_cost_upper_bound'], 170)
        baseline, _ = self.advance(state, env, selected)
        funded, _ = self.advance(state, env, out)
        self.assert_nonseed_equal(baseline, funded, 0, 170)
        RECEIPTS.append({'case': 'truncated_hire', 'cash_delta': 170, 'hire_executed': False})

    def test_terminal_place_sale_and_funded_queue_both_seats(self):
        selected = action(['PLACE', 'CARROT', 1], market=[['BUY_SEED', 'WHEAT', 17],
                                                        ['HIRE'], ['SELL', 'CARROT', 1]])
        for seat in (0, 1):
            with self.subTest(seat=seat):
                obj, obs, cfg, state, env = self.case(selected, seat=seat, step=718,
                                                      carried=[{'CARROT': 1}, {}])
                out = obj.transform(obs, cfg, selected)
                self.assertEqual(out['farmer'], selected['farmer'])
                self.assertEqual(out['market'], [[], ['HIRE'], ['SELL', 'CARROT', 1]])
                self.assertEqual(obj.last_packet['post_unit_observation']['private']['shed']['CARROT'], 1)
                baseline, _ = self.advance(state, env, selected, seat=seat, step=718)
                funded, _ = self.advance(state, env, out, seat=seat, step=718)
                self.assert_nonseed_equal(baseline, funded, seat, 170)
                self.assertEqual(funded[seat].observation['private']['shed']['CARROT'], 0)
                RECEIPTS.append({'case': 'terminal_place_sale', 'seat': seat, 'cash_delta': 170,
                                 'carrot_sold': 1, 'unit_stage_count': obj.diagnostics['selected_unit_stages']})

    def test_actual_parent_called_once_with_funding_enabled_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                state, env = self.helper.helper.fixture(step=0, cash=1000)
                obs = copy.deepcopy(state[seat].observation)
                obs.pop('step', None)
                started = time.perf_counter()
                obj = I.make_agent(seed_queue_selector=CEDAR.select_seed_queue)
                with patch.object(obj.controller, 'act', wraps=obj.controller.act) as parent:
                    out = obj.act(obs, env.configuration)
                self.assertEqual(parent.call_count, 1)
                self.assertEqual(out['farmer'], obj.last_selected['farmer'])
                self.assertEqual(out['hands'], obj.last_selected['hands'])
                RECEIPTS.append({'case': 'actual_parent_funding_enabled', 'seat': seat,
                                 'parent_calls': parent.call_count,
                                 'constructor_plus_first_action_s': time.perf_counter() - started})

    def test_callback_inputs_and_return_are_detached(self):
        selected = action(market=[['BUY_SEED', 'WHEAT', 17], ['HIRE']])
        returned = {}
        def selector(mechanics, post, original, proposed, configuration):
            chosen, report = CEDAR.select_seed_queue(mechanics, post, original, proposed, configuration)
            post['private']['seeds']['WHEAT'] = 9999
            original['market'].clear()
            proposed['market'].clear()
            configuration['boardSize'] = 1
            returned.update(action=chosen, report=report)
            return chosen, report
        obj, obs, cfg, _, _ = self.case(selected, callback=selector)
        saved = copy.deepcopy((obs, cfg, selected))
        out = obj.transform(obs, cfg, selected)
        self.assertEqual(out['market'], [[], ['HIRE']])
        self.assertEqual((obs, cfg, selected), saved)
        self.assertEqual(obj.last_packet['post_unit_observation']['private']['seeds']['WHEAT'], 0)
        returned['action']['market'].clear()
        returned['report']['status'] = 'mutated_after_return'
        self.assertEqual(obj.last_seeded['market'], [[], ['HIRE']])
        self.assertEqual(obj.diagnostics['seed_funding']['status'], 'certified')

    def test_published_variant_constructs_same_single_parent(self):
        path = FUNDING / 'funded_main.py'
        spec = importlib.util.spec_from_file_location('cypress_funded_entry', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        obj = module.make_agent()
        self.assertIsInstance(obj, I.IntegratedSelectedAgent)
        state, env = self.helper.helper.fixture(step=0, cash=1000)
        with patch.object(obj.controller, 'act', wraps=obj.controller.act) as parent:
            out = obj.act(state[0].observation, env.configuration)
        self.assertEqual(parent.call_count, 1)
        self.assertIsInstance(out, dict)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FundedJoinTests)
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    source_paths = [Path(__file__).resolve(), LAB / 'integrated_selected.py',
                    FUNDING / 'seed_funding.py', FUNDING / 'funded_main.py',
                    LAB / 'reference/integrated-selected/alder/seed_budget.py',
                    LAB / 'selected_action_sell.py', LAB / 'ordered_selected_sell.py',
                    LAB / 'reference/ordered-feasibility/atlas/projection.py',
                    LAB / 'reference/engine/kaggriculture.py']
    sources = {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path):
               {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'bytes': path.stat().st_size} for path in source_paths}
    report = {'test_methods': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'successful': result.wasSuccessful(),
              'wall_s': time.perf_counter() - started, 'official_transitions': TRANSITIONS,
              'full_games': 0, 'new_game_seeds': 0,
              'scope': 'constructed joined-path states and actual parent first calls; not policy strength',
              'sources': sources, 'cases': RECEIPTS,
              'workflow_run': os.environ.get('GITHUB_RUN_ID'),
              'workflow_attempt': os.environ.get('GITHUB_RUN_ATTEMPT')}
    if ARGS.json_output:
        ARGS.json_output.parent.mkdir(parents=True, exist_ok=True)
        ARGS.json_output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return not result.wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(main())
