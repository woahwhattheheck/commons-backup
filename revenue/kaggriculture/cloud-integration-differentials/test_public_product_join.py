# SPDX-License-Identifier: Apache-2.0
"""New public-product callback in the existing actual integrated agent.

Constructed caller inputs and exact pinned dependencies; no game initialization,
policy panel, hidden seed, or replacement integration implementation.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
import unittest

import seed_funding as F
import test_public_product_funding as M

I = None
RECORDS = []
PARENT_CALLS = 0
REACHED = None
REACHED_SHA = '0ad5d66dcb1a4e441eec842d8174e3806379d8a669ebd83a703395bd58957810'
INTEGRATED_SHA = 'dd6b0b52575ad95a975695d372546ebfbdcb829065574d9c94eab5085a44a9fe'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def make_input(seat=0, *, cash=10000, seeds=5, step=600, inventory=10000):
    state = M.fixture(money=cash, seat=seat, inventory=inventory)
    state['privates'][seat]['seeds'] = {'WHEAT': seeds}
    obs = M.observation(state)
    obs.update(step=step, day=step // 24, hour=step % 24, town={'unlocked_shops': []})
    return state, obs


def selected(product='WHEAT', quantity=3, seed_quantity=17):
    return M.action([['BUY_SEED', 'WHEAT', seed_quantity],
                     ['BUY_PRODUCT', product, quantity], ['HIRE']])


class ProductJoinTests(unittest.TestCase):
    def join(self, obs, action, *, callback=F.select_public_seed_queue,
             config=None, fallback=None, full_act=False, case='join'):
        global PARENT_CALLS
        cfg = dict(config or {})
        before = deepcopy((obs, action, cfg, fallback))
        policy = I.make_agent(seed_queue_selector=callback, horizon=1)
        calls, units = [], []
        original_parent = policy.controller.act
        original_units = I.atlas._units

        def parent(o):
            calls.append(1)
            return original_parent(o)

        def unit_stage(*args, **kwargs):
            units.append(args[4])
            return original_units(*args, **kwargs)

        policy.controller.act = parent
        I.atlas._units = unit_stage
        try:
            if full_act:
                out = policy.act(obs, cfg)
            else:
                out = policy.transform(obs, cfg, action, fallback_action=fallback)
        finally:
            I.atlas._units = original_units
        PARENT_CALLS += len(calls)
        self.assertEqual((obs, action, cfg, fallback), before)
        self.assertEqual(len(calls), 1 if full_act else 0)
        now = I.absolute_step(obs, cfg)
        self.assertEqual(units.count(now), 1)
        self.assertEqual(policy.diagnostics.get('selected_unit_stages'), 1)
        self.assertEqual(policy.diagnostics.get('parent_calls_in_transform'), 0)
        RECORDS.append({'case': case, 'seat': obs['player'], 'input_sha256': digest(obs),
                        'configuration': cfg, 'selected_action': action,
                        'output': out, 'diagnostics': policy.diagnostics,
                        'parent_calls': len(calls), 'current_unit_stages': units.count(now),
                        'all_projected_unit_steps': units, 'caller_inputs_unchanged': True})
        return policy, out

    def test_funded_product_hire_callback_and_fixed_control_both_seats(self):
        for seat in (0, 1):
            initial, obs = make_input(seat)
            action = selected()
            policy, out = self.join(obs, action, case='funded-product-hire')
            report = policy.diagnostics['seed_funding']
            self.assertEqual(report['status'], 'certified')
            self.assertEqual(report['seed_cash_reduction'], 140)
            self.assertEqual(out['market'], [['BUY_SEED', 'WHEAT', 3],
                                              ['BUY_PRODUCT', 'WHEAT', 3], ['HIRE']])
            self.assertEqual(out, policy.last_seeded)
            control, old = self.join(obs, action, callback=F.select_seed_queue,
                                     case='fixed-only-control')
            self.assertEqual(old, action)
            self.assertEqual(control.diagnostics['seed_funding']['status'], 'not_certified')
            baseline, _ = M.execute(initial, action, M.action([]))
            changed, _ = M.execute(initial, out, M.action([]))
            self.assertEqual(M.without(baseline['farms'][seat], 'money'),
                             M.without(changed['farms'][seat], 'money'))
            self.assertEqual(M.without(baseline['privates'][seat], 'seeds'),
                             M.without(changed['privates'][seat], 'seeds'))
            self.assertEqual(baseline['market'], changed['market'])
            self.assertEqual(baseline['farms'][1-seat], changed['farms'][1-seat])
            self.assertEqual(baseline['privates'][1-seat], changed['privates'][1-seat])
            self.assertEqual(changed['farms'][seat]['money'] - baseline['farms'][seat]['money'], 140)
            RECORDS[-2]['paired_market'] = {
                'baseline_money': baseline['farms'][seat]['money'],
                'callback_money': changed['farms'][seat]['money'],
                'non_seed_state_equal': True, 'own_cash_delta': 140,
                'rival_cash_delta': 0}

    def test_seller_still_requires_its_separate_buy_product_bound(self):
        _, obs = make_input()
        policy, out = self.join(obs, selected(), case='seller-fallback-preserves-funded-queue')
        self.assertEqual(policy.diagnostics['status'], 'fallback')
        self.assertIn('Caller cash bound required for BUY_PRODUCT', policy.diagnostics['reason'])
        self.assertEqual(policy.diagnostics['seed_reason'], 'funded_economic_order')
        self.assertEqual(out, policy.last_seeded)
        self.assertIsNotNone(policy.last_packet['arrival_contract'])
        self.assertEqual(policy.last_packet['projection']['observed_step'], 600)

    def test_negative_inventory_underfunding_keeps_the_original_queue(self):
        for seat in (0, 1):
            _, obs = make_input(seat, cash=4300, seeds=8, inventory=0)
            action = M.action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'FERTILIZER', 2]])
            policy, out = self.join(obs, action, config={'shedCapacity': 10},
                                    case='negative-inventory-retained')
            report = policy.diagnostics['seed_funding']
            self.assertEqual(out, action)
            self.assertEqual(report['status'], 'not_certified')
            self.assertEqual(report['original_total_cost_upper_bound'], 4308)
            self.assertEqual(report['public_product_bounds'][0]['quote_inventory_lower_bound'], -22)
            self.assertEqual(policy.diagnostics['seed_reason'], 'later_economic_order')

    def test_current_drop_is_projected_once_and_callback_receives_post_unit_state(self):
        for seat in (0, 1):
            _, obs = make_input(seat)
            obs['private']['inventories'][0] = {'WHEAT': 2}
            action = selected(); action['farmer'] = ['DROP']
            seen = []
            def callback(m, post, base, proposed, cfg):
                seen.append(deepcopy(post))
                return F.select_public_seed_queue(m, post, base, proposed, cfg)
            policy, out = self.join(obs, action, callback=callback, case='post-unit-drop')
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0]['private']['shed']['WHEAT'], 2)
            self.assertEqual(seen[0]['private']['inventories'][0], {})
            self.assertEqual(policy.last_packet['post_unit_observation']['private'], seen[0]['private'])
            self.assertEqual(out['farmer'], ['DROP'])
            self.assertEqual(out['market'][0], ['BUY_SEED', 'WHEAT', 3])

    def test_extra_selected_plant_keeps_existing_demand_boundary(self):
        _, obs = make_input()
        action = selected(); action['farmer'] = ['PLANT', 'WHEAT']
        calls = []
        def callback(*args):
            calls.append(1)
            return F.select_public_seed_queue(*args)
        policy, out = self.join(obs, action, callback=callback, case='extra-plant')
        self.assertEqual(calls, [])
        self.assertEqual(policy.diagnostics['seed_reason'], 'selected_plant_requests_exceed_route')
        self.assertEqual(out, action)
        self.assertNotIn('seed_funding', policy.diagnostics)

    def test_unknown_bound_and_explicit_fallback_survive_the_join(self):
        _, obs = make_input()
        del obs['market']['inventory']['WHEAT']
        policy, out = self.join(obs, selected(), case='missing-visible-inventory')
        self.assertEqual(policy.diagnostics['seed_funding']['status'], 'not_certified')
        self.assertEqual(out, selected())
        _, obs = make_input()
        fallback = M.action([['PASS']])
        policy, out = self.join(obs, selected(), fallback=fallback, case='explicit-caller-fallback')
        self.assertEqual(policy.diagnostics['seed_funding']['status'], 'certified')
        self.assertEqual(out, fallback)
        self.assertEqual(policy.last_seeded['market'][0], ['BUY_SEED', 'WHEAT', 3])

    def test_actual_cold_parent_call_matches_default_without_duplicate_invocation(self):
        for seat in (0, 1):
            _, obs = make_input(seat, step=0)
            obs['farms'][seat]['hands'] = []
            obs['farms'][seat]['hires_today'] = 0
            obs['private']['inventories'] = [{}]
            obs.pop('step')
            _, candidate = self.join(obs, {}, full_act=True, case='actual-parent-public')
            _, control = self.join(obs, {}, callback=None, full_act=True, case='actual-parent-default')
            self.assertEqual(candidate, control)


    def test_integral_float_product_funding_works_in_the_actual_join(self):
        for seat in (0, 1):
            _, obs = make_input(seat, cash=10000.0)
            policy, out = self.join(obs, selected(), case='integral-float-product-hire')
            report = policy.diagnostics['seed_funding']
            self.assertEqual(report['status'], 'certified')
            self.assertEqual(report['seed_cash_reduction'], 140)
            self.assertEqual(out['market'][0], ['BUY_SEED', 'WHEAT', 3])
            self.assertEqual(policy.diagnostics['status'], 'fallback')
            _, obs = make_input(seat, cash=4300.0, seeds=8, inventory=0)
            action = M.action([['BUY_SEED', 'WHEAT', 10], ['BUY_PRODUCT', 'FERTILIZER', 2]])
            policy, out = self.join(obs, action, config={'shedCapacity': 10},
                                    case='integral-float-underfunded-product')
            self.assertEqual(out, action)
            self.assertEqual(policy.diagnostics['seed_funding']['reason'],
                             'original_queue_needs_additional_cash')

    def test_public_callback_on_recorded_float_cash_with_labeled_product_counterfactual(self):
        # Reuse real recorded observations, not a reconstructed controller state.
        # The product order and one-seed reduction are NEW financial test inputs,
        # not claimed recorded actions or proof that one fewer seed is sufficient.
        for case in REACHED['cases']:
            post = deepcopy(case['observation']); cfg = case['configuration']
            seat = post['player']; source_action = case['selected']
            I.atlas._units(I.m, post['farms'][seat], post['private'], source_action,
                case['step'], cfg['boardSize'], cfg['turnsPerDay'], cfg['shedCapacity'],
                lossless=False, events=[], excluded=set(), omissions=[])
            self.assertIsInstance(post['farms'][seat]['money'], float)
            base = deepcopy(source_action)
            base['market'][0] = ['BUY_PRODUCT', 'WHEAT', 1]
            proposed = deepcopy(base)
            slot = next(i for i,o in enumerate(proposed['market']) if o and o[0] == 'BUY_SEED')
            proposed['market'][slot][2] -= 1
            original = deepcopy((post, base, proposed, cfg))
            chosen, report = F.select_public_seed_queue(I.m, post, base, proposed, cfg)
            self.assertEqual(report['status'], 'certified')
            self.assertEqual(report['seed_cash_reduction'], 10)
            self.assertEqual(chosen, proposed)
            self.assertGreater(report['product_cost_upper_bound'], 0)
            fixed, fixed_report = F.select_seed_queue(I.m, post, base, proposed, cfg)
            self.assertEqual(fixed, base)
            self.assertEqual(fixed_report['status'], 'not_certified')
            self.assertEqual((post, base, proposed, cfg), original)
            RECORDS.append({'case': 'recorded-cash-product-counterfactual',
                'source_witness_sha256': REACHED_SHA, 'source_step': case['step'],
                'source_observation_sha256': digest(case['observation']),
                'observed_float_cash': post['farms'][seat]['money'],
                'post_unit_observation_sha256': digest(post), 'selected_action': base,
                'proposed_action': proposed, 'output': chosen, 'diagnostics': report,
                'controller_calls': 0, 'current_unit_stages': 1,
                'input_changes': 'slot0 BUY_PRODUCT WHEAT1 and proposal seed quantity minus1',
                'scope': 'Recorded state; changed test queue. No demand proof or market/game execution.',
                'caller_inputs_unchanged': True})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integrated-root', type=Path, required=True)
    parser.add_argument('--engine-source', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--reached-file', type=Path, required=True)
    args = parser.parse_args()
    root = args.integrated_root.resolve()
    actual = hashlib.sha256((root / 'integrated_selected.py').read_bytes()).hexdigest()
    if actual != INTEGRATED_SHA:
        raise SystemExit('Use the exact PR10015 callback integration; do not silently change the target.')
    sys.path.insert(0, str(root))
    I = importlib.import_module('integrated_selected')
    M.K = M.load_engine(args.engine_source)
    raw_reached = args.reached_file.read_bytes()
    if hashlib.sha256(raw_reached).hexdigest() != REACHED_SHA:
        raise SystemExit('Recorded input does not match DELVE original witness.')
    REACHED = json.loads(raw_reached)
    start = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProductJoinTests))
    report = {'schema': 'cedar-public-product-join-v1', 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'successful': result.wasSuccessful(), 'elapsed_s': time.perf_counter()-start,
              'integrated_sha256': actual, 'callback_sha256': hashlib.sha256(Path(F.__file__).read_bytes()).hexdigest(),
              'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'engine_sha256': M.ENGINE_SHA, 'market_calls': M.MARKET_CALLS,
              'actual_parent_calls': PARENT_CALLS, 'full_games': 0, 'game_seeds': [],
              'reached_witness_sha256': REACHED_SHA, 'direct_reached_post_unit_calls': 2,
              'scope': 'Constructed selected-action joins and cold first calls; not reached full-game evidence.',
              'cases': RECORDS,
              'failure_details': [{'test': str(t), 'detail': d} for t,d in result.failures],
              'error_details': [{'test': str(t), 'detail': d} for t,d in result.errors]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('cases','failure_details','error_details')},indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
