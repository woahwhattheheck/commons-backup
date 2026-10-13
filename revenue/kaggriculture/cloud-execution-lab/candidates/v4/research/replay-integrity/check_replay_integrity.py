"""Offline behavior tests; all engine cases use the complete pinned interpreter."""
from __future__ import annotations
import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import unittest

from tape_integrity import (FrozenTape, MarketRecorder, ReplayError, TapeAudit,
                            encoded, first_difference, observation_parts)
import run_counterfactual_probe as probe

BINDING = {"engine_blob": probe.ENGINE_PIN, "seed": 9922023,
           "configuration": {"episodeSteps": 720, "maxMarketOrdersPerTurn": 10},
           "policy_rng_seeds": [9000, 9001]}
COUNTS = {"official_interpreter_calls": 0, "randomized_full_transition_pairs": 0}


def observation(seat=0):
    return {"player": seat, "farms": [
        {"money": 3000, "farmer": [0, 0], "hands": [], "tiles": [[None]]},
        {"money": 3000, "farmer": [0, 0], "hands": [], "tiles": [[None]]}],
        "private": {"shed": {"WHEAT": 3}, "inventories": [{}], "seeds": {"WHEAT": 1}},
        "market": {"inventory": {"WHEAT": 10000}, "prices": {"WHEAT": 25}},
        "town": {"unlocked_shops": []}, "step": 0, "day": 0, "hour": 0}


def raw_action():
    return {"farmer": ["PASS"], "hands": [["PLANT", "WHEAT"]],
            "market": [[], ["SELL", "WHEAT", 0], ["HIRE"]] + [[]] * 8 + [["SELL", "WHEAT", 9]],
            "future": {"unrecognized": [1, {"retain": True}]}}


def frame(step=0):
    return {"step": step, "actions": [raw_action(), raw_action()],
            "before": [observation(0), observation(1)],
            "after": [observation(0), observation(1)], "receipts": [{}, {}],
            "status": ["ACTIVE", "ACTIVE"], "rewards": [0, 0]}


def tape(frames=None, seat=0):
    return FrozenTape([frame()] if frames is None else frames, seat,
                      expected_binding=BINDING, actual_binding=deepcopy(BINDING))


class CustodyTests(unittest.TestCase):
    def test_strict_json_rejects_nonfinite(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value), self.assertRaises(ReplayError): encoded({'q': value})

    def test_binding_mismatch_rejected(self):
        for key, value in [('seed', 7), ('engine_blob', 'x'), ('configuration', {}), ('policy_rng_seeds', [1, 2])]:
            actual = deepcopy(BINDING); actual[key] = value
            with self.subTest(key=key), self.assertRaises(ReplayError):
                FrozenTape([frame()], 0, expected_binding=BINDING, actual_binding=actual)

    def test_seat_contract(self):
        for seat in (True, False, -1, 2, 0.0, '0', None):
            with self.subTest(seat=seat), self.assertRaises(ReplayError): tape(seat=seat)

    def test_empty_tape_rejected(self):
        with self.assertRaises(ReplayError): tape([])

    def test_noncontiguous_tape_rejected(self):
        for frames in ([frame(1)], [frame(0), frame(2)], [frame(0), frame(0)], [frame(False)]):
            with self.subTest(frames=len(frames)), self.assertRaises(ReplayError): tape(frames)

    def test_two_raw_action_objects_required(self):
        for actions in ([{}], [{}, []], [{}, {}, {}], None):
            f = frame(); f['actions'] = actions
            with self.subTest(actions=actions), self.assertRaises(ReplayError): tape([f])

    def test_raw_prefix_and_surplus_hands_not_normalized(self):
        expected = raw_action(); t = tape(); got = t.action(0)
        self.assertEqual(encoded(got), encoded(expected))
        self.assertEqual(len(got['market']), 12)
        self.assertEqual(len(got['hands']), 1)
        self.assertEqual(got['market'][0], [])
        self.assertIn('future', got)

    def test_input_tape_detached(self):
        f = frame(); t = tape([f]); f['actions'][0]['future']['unrecognized'][1]['retain'] = False
        self.assertTrue(t.action(0)['future']['unrecognized'][1]['retain'])

    def test_returned_actions_detached_from_later_callbacks(self):
        action = raw_action()
        a, b = frame(0), frame(1); a['actions'][0] = action; b['actions'][0] = action
        t = tape([a, b]); first = t.action(0); first['future']['unrecognized'][1]['retain'] = False
        self.assertTrue(t.action(1)['future']['unrecognized'][1]['retain']); t.finish()

    def test_callback_sequence_rejected(self):
        t = tape([frame(0), frame(1)])
        for step in (1, -1, True, 0.0):
            with self.subTest(step=step), self.assertRaises(ReplayError): t.action(step)
        t.action(0)
        with self.assertRaises(ReplayError): t.action(0)
        t.action(1); t.finish()

    def test_no_implicit_pass_on_exhaustion(self):
        t = tape(); t.action(0)
        with self.assertRaises(ReplayError): t.action(1)

    def test_early_game_termination_rejected(self):
        t = tape([frame(), frame(1)]); t.action(0)
        with self.assertRaises(ReplayError): t.finish()


class AuditTests(unittest.TestCase):
    def test_exact_control_has_zero_differences(self):
        for seat in (0, 1):
            a = TapeAudit(seat)
            for step in range(3):
                f = frame(step); a.observe(f, deepcopy(f))
            self.assertEqual(a.report()['changed_callbacks'], {}); self.assertEqual(a.next_step, 3)

    def test_changed_replayed_action_rejected(self):
        for field in ('farmer', 'hands', 'market', 'future'):
            left, right = frame(), frame(); right['actions'][0].pop(field)
            with self.subTest(field=field), self.assertRaises(ReplayError): TapeAudit(0).observe(left, right)

    def test_rival_action_can_change_without_own_tape_change(self):
        left, right = frame(), frame(); right['actions'][1] = {'farmer': ['NORTH']}
        audit = TapeAudit(0); audit.observe(left, right)
        self.assertEqual(audit.report()['changed_callbacks'], {})

    def test_cash_separate_from_private_production(self):
        left, right = frame(), frame(); right['before'][0]['farms'][0]['money'] -= 1
        audit = TapeAudit(0); audit.observe(left, right)
        self.assertEqual(audit.report()['changed_callbacks'], {'input/own_money': 1})

    def test_shed_divergence_not_confused_with_market(self):
        left, right = frame(), frame(); right['before'][0]['private']['shed']['WHEAT'] = 0
        audit = TapeAudit(0); audit.observe(left, right)
        self.assertEqual(audit.report()['changed_callbacks'], {'input/own_production': 1})
        self.assertEqual(audit.report()['first']['input/own_production']['path'], '$.private.shed.WHEAT')

    def test_first_witness_is_earliest_not_latest(self):
        audit = TapeAudit(0)
        for step in range(3):
            left, right = frame(step), frame(step)
            right['before'][0]['market']['prices']['WHEAT'] = 30 + step
            audit.observe(left, right)
        self.assertEqual(audit.report()['changed_callbacks']['input/market'], 3)
        self.assertEqual(audit.report()['first']['input/market']['actual'], 30)
        self.assertEqual(audit.report()['first']['input/market']['step'], 0)

    def test_execution_and_status_differences_detected(self):
        left, right = frame(), frame()
        right['receipts'][0]['HIRE'] = {'attempts': 1, 'filled': 0, 'cash_delta': 0}
        right['status'][0] = 'DONE'
        audit = TapeAudit(0); audit.observe(left, right)
        self.assertEqual(audit.report()['changed_callbacks'], {'execution/market': 1, 'status': 1})

    def test_post_transition_production_difference_detected(self):
        left, right = frame(), frame(); right['after'][0]['farms'][0]['hands'].append([0, 1])
        audit = TapeAudit(0); audit.observe(left, right)
        self.assertEqual(audit.report()['changed_callbacks'], {'output/own_production': 1})

    def test_seat_one_is_not_seat_zero(self):
        left, right = frame(), frame(); right['after'][1]['private']['shed']['WHEAT'] = 7
        audit = TapeAudit(1); audit.observe(left, right)
        self.assertIn('output/own_production', audit.report()['first'])
        self.assertEqual(audit.report()['first']['output/own_production']['actual'], 7)

    def test_missing_private_or_mismatched_player_rejected(self):
        for change in ({'player': 1}, {'player': True}, {'private': None}, {'farms': []}):
            obs = observation(); obs.update(change)
            with self.subTest(change=change), self.assertRaises(ReplayError): observation_parts(obs, 0)

    def test_audit_sequence_and_bool_reference_rejected(self):
        for ref, actual in ((frame(1), frame(1)), (frame(0), frame(1)), (frame(False), frame(0))):
            with self.subTest(ref=ref['step'], actual=actual['step']), self.assertRaises(ReplayError):
                TapeAudit(0).observe(ref, actual)

    def test_detached_snapshots_and_reports(self):
        obs = observation(); parts = observation_parts(obs, 0); parts['own_production']['private']['shed']['WHEAT'] = 99
        self.assertEqual(obs['private']['shed']['WHEAT'], 3)
        left, right = frame(), frame(); right['before'][0]['town']['unlocked_shops'].append('X')
        audit = TapeAudit(0); audit.observe(left, right); report = audit.report()
        report['first'].clear(); self.assertTrue(audit.report()['first'])

    def test_missing_key_is_not_null(self):
        self.assertFalse(first_difference({}, {'x': None})['reference_present'])

    def test_type_and_length_and_depth_witnesses(self):
        self.assertEqual(first_difference(True, 1)['reference_type'], 'bool')
        self.assertEqual(first_difference([1], [1, 2])['path'], '$.length')
        self.assertTrue(first_difference({'x': 1}, {'x': 2}, budget=0)['depth_limited'])
        self.assertIsNone(first_difference({'x': 1}, {'x': 1}, budget=0))

    def test_signed_zero_is_custody_difference(self):
        self.assertIsNotNone(first_difference(-0.0, 0.0))
        left, right = frame(), frame()
        left['before'][0]['farms'][0]['money'] = -0.0; right['before'][0]['farms'][0]['money'] = 0.0
        audit = TapeAudit(0); audit.observe(left, right)
        self.assertEqual(audit.report()['changed_callbacks'], {'input/own_money': 1})

    def test_observe_has_no_side_effects(self):
        left, right = frame(), frame(); saved = encoded([left, right])
        TapeAudit(0).observe(left, right); self.assertEqual(encoded([left, right]), saved)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['TITAN_NATIVE_ROOT']).resolve()
        cls.bound = probe.authenticate(cls.root); cls.ev = probe.import_evaluator(cls.root)
        cls.engine, _ = cls.ev.get_engine(cls.root/'checks/reference/engine', cls.root/'checks/reference/evaluator/loader.py')

    def new(self, seed=9922023):
        ev, engine = self.ev, self.engine
        cfg = ev.Struct({k: v.get('default') if isinstance(v, dict) else v for k, v in engine.specification['configuration'].items()})
        cfg.seed = seed
        env = ev.Struct(configuration=cfg, done=False, info={})
        state = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        engine.interpreter(state, env); COUNTS['official_interpreter_calls'] += 1
        self.assertIsNone(cfg.get('seed'))
        for s in state: s.observation.step = 0
        return state, env

    def run_turn(self, state, env, observed=True):
        if observed:
            with MarketRecorder(self.engine, state) as rec:
                returned = self.engine.interpreter(state, env)
            receipts = rec.receipts
        else:
            returned = self.engine.interpreter(state, env); receipts = None
        COUNTS['official_interpreter_calls'] += 1
        self.assertIs(returned, state)
        return receipts

    def test_package_authenticates_109_members(self):
        self.assertEqual(self.bound['authenticated_runtime_members'], 109)
        self.assertEqual(self.bound['engine_blob'], probe.ENGINE_PIN)

    def test_unaffordable_buy_is_attempt_not_fill(self):
        for seat in (0, 1):
            state, env = self.new(); state[seat].observation.farms[seat]['money'] = 0
            state[seat].action = {'market': [['BUY_PRODUCT', 'WHEAT', 1000]]}
            rec = self.run_turn(state, env)
            self.assertEqual(rec[seat]['BUY_PRODUCT:WHEAT'], {'attempts': 1, 'filled': 0, 'cash_delta': 0})
            self.assertEqual(state[seat].observation.private['shed'].get('WHEAT', 0), 0)

    def test_unsupported_buy_never_reaches_commit(self):
        for seat in (0, 1):
            state, env = self.new(); state[seat].action = {'market': [['BUY_PRODUCT', 'MILK', 10]]}
            rec = self.run_turn(state, env); self.assertNotIn('BUY_PRODUCT:MILK', rec[seat])
            self.assertEqual(state[seat].observation.farms[seat]['money'], 3000)

    def test_partial_fill_matches_stock_and_cash(self):
        for seat in (0, 1):
            state, env = self.new(); farm = state[seat].observation.farms[seat]
            farm['money'] = 40; state[seat].action = {'market': [['BUY_PRODUCT', 'WHEAT', 1000]]}
            rec = self.run_turn(state, env)[seat]['BUY_PRODUCT:WHEAT']
            self.assertEqual(rec['filled'], state[seat].observation.private['shed']['WHEAT'])
            self.assertGreater(rec['filled'], 0); self.assertLess(rec['filled'], 1000)
            self.assertEqual(rec['attempts'], rec['filled'] + 1)
            self.assertEqual(rec['cash_delta'], farm['money'] - 40)

    def test_hire_calls_are_not_hires_when_no_cash(self):
        for seat in (0, 1):
            state, env = self.new(); farm = state[seat].observation.farms[seat]
            farm['money'] = 0; state[seat].action = {'market': [['HIRE'], ['HIRE'], ['HIRE']]}
            rec = self.run_turn(state, env)[seat]['HIRE']
            self.assertEqual(rec, {'attempts': 3, 'filled': 0, 'cash_delta': 0})
            self.assertEqual(farm['hands'], [])

    def test_hire_actual_success_count(self):
        for seat in (0, 1):
            state, env = self.new(); farm = state[seat].observation.farms[seat]
            state[seat].action = {'market': [['HIRE'], ['HIRE'], ['HIRE']]}
            rec = self.run_turn(state, env)[seat]['HIRE']
            self.assertEqual(rec['filled'], len(farm['hands'])); self.assertEqual(rec['filled'], 3)
            self.assertEqual(rec['cash_delta'], farm['money'] - 3000)

    def test_land_fill_and_no_cash_controls(self):
        for seat in (0, 1):
            for cash in (0, 3000):
                state, env = self.new(); farm = state[seat].observation.farms[seat]; farm['money'] = cash
                state[seat].action = {'market': [['BUY_LAND']]}
                rec = self.run_turn(state, env)[seat]['BUY_LAND']
                self.assertEqual(rec['filled'], len(farm['unlocked_quadrants']) - 1)
                self.assertEqual(rec['filled'], int(cash > 0)); self.assertEqual(rec['cash_delta'], farm['money'] - cash)

    def test_raw_empty_slot_counts_toward_cap(self):
        for seat in (0, 1):
            state, env = self.new(); env.configuration.maxMarketOrdersPerTurn = 1
            state[seat].action = {'market': [[], ['HIRE']]}
            rec = self.run_turn(state, env)
            self.assertEqual(rec[seat], {}); self.assertEqual(state[seat].observation.farms[seat]['hands'], [])

    def test_minimum_one_raw_slot_even_zero_cap(self):
        for cap in (0, -2):
            state, env = self.new(); env.configuration.maxMarketOrdersPerTurn = cap
            state[0].action = {'market': [['HIRE'], ['HIRE']]}
            rec = self.run_turn(state, env); self.assertEqual(rec[0]['HIRE']['filled'], 1)

    def test_ghost_plant_row_cannot_be_trimmed(self):
        for seat in (0, 1):
            state, env = self.new(); farm = state[seat].observation.farms[seat]
            farm['farmer'] = [0, 0]; farm['tiles'][0][0] = None
            state[seat].observation.private['seeds'] = {'WHEAT': 1}
            state[seat].action = {'farmer': ['PLANT', 'WHEAT'], 'hands': [['PLANT', 'WHEAT']]}
            trimmed_state, trimmed_env = deepcopy((state, env)); trimmed_state[seat].action['hands'] = []
            self.run_turn(state, env); self.run_turn(trimmed_state, trimmed_env)
            self.assertIsNone(farm['tiles'][0][0])
            self.assertEqual(trimmed_state[seat].observation.farms[seat]['tiles'][0][0]['kind'], 'PLANT')

    def test_floor_sale_fills_without_inventory_growth(self):
        for seat in (0, 1):
            state, env = self.new(); market = state[0].observation.market
            market['inventory']['FERTILIZER'] = 1000000; self.engine._refresh_prices(market)
            self.assertEqual(market['prices']['FERTILIZER'], 1)
            state[seat].observation.private['shed']['FERTILIZER'] = 3
            state[seat].action = {'market': [['SELL', 'FERTILIZER', 3]]}
            rec = self.run_turn(state, env)[seat]['SELL:FERTILIZER']
            self.assertEqual(rec['filled'], 3); self.assertEqual(rec['cash_delta'], 3)
            self.assertLessEqual(market['inventory']['FERTILIZER'], 1000000)

    def test_functions_restored_on_success_and_exception(self):
        state, env = self.new(); names = ('_commit_unit', '_do_hire', '_do_buy_land')
        originals = [getattr(self.engine, n) for n in names]
        self.run_turn(state, env)
        self.assertEqual([getattr(self.engine, n) for n in names], originals)
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            with MarketRecorder(self.engine, state): raise RuntimeError('injected')
        self.assertEqual([getattr(self.engine, n) for n in names], originals)

    def test_reentry_and_unbound_farm_rejected(self):
        state, env = self.new(); rec = MarketRecorder(self.engine, state)
        with rec:
            with self.assertRaises(ReplayError): rec.__enter__()
            with self.assertRaises(ReplayError): rec._row(deepcopy(state[0].observation.farms[0]), 'X')

    def test_explicit_hire_multiplier_preserved(self):
        state, env = self.new(); farm = state[0].observation.farms[0]
        with MarketRecorder(self.engine, state) as rec:
            self.engine._do_hire(farm, state[0].observation.private, env.configuration.boardSize, 3)
        self.assertEqual(rec.receipts[0]['HIRE']['cash_delta'], -3)
        self.assertEqual(rec.receipts[0]['HIRE']['filled'], 1)

    def test_randomized_full_interpreter_transparency(self):
        rng = random.Random(1300921)
        markets = ([], [[]], [['HIRE']], [['BUY_LAND']], [['SELL', 'WHEAT', 1000]],
                   [['SELL', 'FERTILIZER', 17]], [['BUY_PRODUCT', 'WHEAT', 1000]],
                   [['BUY_PRODUCT', 'FERTILIZER', 3]], [['BUY_SEED', 'WHEAT', 7]],
                   [['BUY_ANIMAL', 'COW', 3]], [['BUY_PRODUCT', 'MILK', 999]],
                   [[], ['HIRE'], ['SELL', 'WHEAT', 0]], [['PASS']])
        for index in range(240):
            state, env = self.new(9922023 + index)
            env.configuration.maxMarketOrdersPerTurn = rng.choice([-1, 1, 2, 10])
            step = rng.choice([0, 22, 23, 143, 671, 718])
            for seat in (0, 1):
                state[seat].observation.step = step
                farm = state[seat].observation.farms[seat]; farm['money'] = rng.choice([0, 1, 40, 1000, 3000])
                state[seat].observation.private['shed'] = {'WHEAT': rng.randrange(60), 'FERTILIZER': rng.randrange(41)}
                state[seat].action = {'farmer': ['PASS'], 'hands': [['PASS'], ['PASS']],
                                      'market': deepcopy(rng.choice(markets))}
            plain, plain_env = deepcopy((state, env)); before_actions = encoded([s.action for s in state])
            with self.subTest(index=index):
                self.run_turn(plain, plain_env, False); self.run_turn(state, env, True)
                self.assertEqual(encoded((state, env)), encoded((plain, plain_env)))
                self.assertEqual(encoded([s.action for s in state]), before_actions)
            COUNTS['randomized_full_transition_pairs'] += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(); os.environ['TITAN_NATIVE_ROOT'] = str(args.native.resolve())
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'tests_run': result.testsRun, 'failures': [{'test': str(t), 'traceback': v} for t,v in result.failures],
              'errors': [{'test': str(t), 'traceback': v} for t,v in result.errors],
              'skips': len(result.skipped), 'parent_optimized': bool(sys.flags.optimize),
              'counts': COUNTS, 'success': result.wasSuccessful()}
    if args.report: probe.write_json(args.report, report)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__': raise SystemExit(main())
