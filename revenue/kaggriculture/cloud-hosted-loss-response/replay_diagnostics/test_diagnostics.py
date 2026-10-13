"""Real pinned-interpreter cases, not public episodes or full-game panels."""
from __future__ import annotations
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import diagnostics as d

ENGINE_DIR = Path(os.environ.get('KAG_ENGINE_DIR', d.ROOT / 'cloud-eval/engine'))


class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tm = d.load_trace_module()
        cls.ev = cls.tm.evaluator()
        cls.engine, cls.engine_hashes = cls.ev.get_engine(ENGINE_DIR)
        cls.cfg = {k: v.get('default') if isinstance(v, dict) else v
                   for k, v in cls.engine.specification['configuration'].items()}

    def observation(self, step=240, own=0):
        e = self.engine
        return {'step': step, 'player': own, 'day': step // 24, 'hour': step % 24,
                'farms': [e._new_farm(10, 3000), e._new_farm(10, 3000)],
                'market': e._new_market(), 'town': e._new_town(), 'private': e._new_private()}

    def animal(self, obs, *, units=3, cared=True):
        tile = self.engine._new_animal('COW', 0)
        tile.update(yield_units=units, cared_today=cared, fed_today=True)
        farm = obs['farms'][obs['player']]
        x, y = farm['farmer']
        farm['tiles'][y][x] = tile
        return tile

    def replay(self, obs, actions, *, episode=90000):
        shared = self.ev.structify(copy.deepcopy(obs))
        state = []
        for s in (0, 1):
            visible = self.ev.structify(copy.deepcopy(obs))
            visible.player = s
            visible.farms, visible.market, visible.town = shared.farms, shared.market, shared.town
            if s != obs['player']:
                visible.private = self.ev.structify(self.engine._new_private())
            state.append(self.ev.Struct(observation=visible, action=None, status='ACTIVE', reward=0))
        before = copy.deepcopy(state)
        for s in (0, 1):
            state[s].action = copy.deepcopy(actions[s])
        env = self.ev.Struct(configuration=self.ev.structify(copy.deepcopy(self.cfg)), done=False, info={})
        self.engine.interpreter(state, env)
        for row in state:
            row.observation.step = obs['step'] + 1
        return {'configuration': copy.deepcopy(self.cfg),
                'info': {'EpisodeId': episode, 'evidence_kind': 'manufactured_official_engine_fixture'},
                'steps': [before, copy.deepcopy(state)]}

    def trace(self, replay):
        return self.tm.analyze(replay, self.engine, self.ev)

    def test_joint_noop_candidate_preserves_input_and_market(self):
        obs = self.observation()
        self.animal(obs)
        action = {'farmer': ['CARE'], 'hands': [], 'market': [['HIRE'], ['SELL', 'MILK', 3]]}
        original = copy.deepcopy((obs, action))
        alternatives = d.scan_noop_harvests(obs, action, self.engine, self.cfg)
        self.assertEqual(len(alternatives), 1)
        self.assertEqual(alternatives[0]['additional_inventory_after_all_units'], {'MILK': 3})
        self.assertEqual(alternatives[0]['action']['market'], action['market'])
        self.assertEqual((obs, action), original)

    def test_following_worker_harvest_is_not_double_counted(self):
        obs = self.observation()
        self.animal(obs)
        obs['farms'][0]['hands'] = [[4, 4]]
        obs['private']['inventories'].append({})
        action = {'farmer': ['CARE'], 'hands': [['HARVEST']], 'market': []}
        self.assertEqual(d.scan_noop_harvests(obs, action, self.engine, self.cfg), [])

    def test_effective_care_is_not_replaced(self):
        obs = self.observation()
        self.animal(obs, cared=False)
        self.assertEqual(d.scan_noop_harvests(obs, {'farmer': ['CARE']}, self.engine, self.cfg), [])

    def test_empty_or_immature_tile_has_no_harvest_gain(self):
        obs = self.observation(step=24)
        for tile in (None, self.engine._new_plant('CARROT', 0, 24)):
            with self.subTest(tile=tile):
                obs['farms'][0]['tiles'][4][4] = tile
                self.assertEqual(d.scan_noop_harvests(obs, {'farmer': ['PASS']}, self.engine, self.cfg), [])

    def test_atomic_seed_cancellation_is_preserved(self):
        obs = self.observation()
        self.animal(obs)
        obs['farms'][0]['hands'] = [[3, 4]]
        obs['private']['inventories'].append({})
        obs['private']['seeds']['CARROT'] = 1
        action = {'farmer': ['PLANT', 'CARROT'], 'hands': [['PLANT', 'CARROT']]}
        farm, private, records = d._owned_phase(obs, action, self.engine, self.cfg)
        self.assertEqual(private['seeds']['CARROT'], 1)
        self.assertEqual([r['effective'] for r in records], [['PASS'], ['PASS']])
        self.assertEqual(d.scan_noop_harvests(obs, action, self.engine, self.cfg), [])

    def test_scanner_does_not_read_rival_state(self):
        obs = self.observation(own=1)
        self.animal(obs)
        obs['farms'][0] = None  # Own-phase primitive requires no rival farm at all.
        obs.pop('market')
        obs.pop('town')
        cases = d.scan_noop_harvests(obs, {'farmer': ['CARE']}, self.engine, self.cfg)
        self.assertEqual(cases[0]['additional_inventory_after_all_units'], {'MILK': 3})

    def test_full_transition_needs_deposit_before_sale(self):
        obs = self.observation()
        self.animal(obs)
        action = {'farmer': ['CARE'], 'market': [['SELL', 'MILK', 3]]}
        replay = self.replay(obs, [action, {}])
        alternative = d.scan_noop_harvests(obs, action, self.engine, self.cfg)[0]['action']
        cf = d.counterfactual_transition(replay, 1, 0, alternative, self.engine, self.ev, self.tm)
        self.assertEqual(cf['status'], 'RECORDED_COACTION_COUNTERFACTUAL')
        self.assertEqual(cf['cash_delta_vs_observed_by_seat'], [0, 0])
        self.assertEqual(cf['own_inventory_delta'], {'MILK': 3})
        self.assertEqual(cf['own_held_yield_delta'], {'MILK': -3})

    def test_drop_then_sell_counterfactual_is_real_cash(self):
        obs = self.observation()
        obs['private']['inventories'][0] = {'MILK': 3}
        action = {'farmer': ['PASS'], 'market': [['SELL', 'MILK', 3]]}
        replay = self.replay(obs, [action, {}])
        original = copy.deepcopy(replay)
        alt = copy.deepcopy(action)
        alt['farmer'] = ['DROP']
        cf = d.counterfactual_transition(replay, 1, 0, alt, self.engine, self.ev, self.tm)
        e = self.engine
        inv = obs['market']['inventory']['MILK']
        expected = sum(e.market_price('MILK', inv + i) for i in range(3))
        self.assertEqual(cf['cash_delta_vs_observed_by_seat'], [expected, 0])
        self.assertEqual(cf['relative_cash_delta'], expected)
        self.assertEqual(cf['alternative_actions'][1], {})
        self.assertEqual(replay, original)

    def test_corrupted_transition_has_no_inferred_effect(self):
        obs = self.observation()
        replay = self.replay(obs, [{}, {}])
        replay['steps'][1][0]['observation']['farms'][0]['money'] += 1
        trace = self.trace(replay)
        report = d.summarize_trace(trace, 0)
        self.assertEqual(report['transition_statuses'], {'MISMATCH': 1})
        self.assertIsNone(report['first_observed_differences']['cash_gap']['effects']['cash_by_cause'])
        cf = d.counterfactual_transition(replay, 1, 0, {}, self.engine, self.ev, self.tm)
        self.assertEqual(cf['status'], 'BASELINE_MISMATCH')
        self.assertNotIn('relative_cash_delta', cf)

    def test_missing_private_is_not_copied_between_players(self):
        replay = self.replay(self.observation(), [{}, {}])
        del replay['steps'][0][1]['observation']['private']
        self.assertNotIn('private', self.tm.observations(replay['steps'][0])[1])
        cf = d.counterfactual_transition(replay, 1, 0, {}, self.engine, self.ev, self.tm)
        self.assertEqual(cf['status'], 'BASELINE_UNAVAILABLE')

    def test_cash_binding_seat_direction_and_exact_event_causes(self):
        obs = self.observation(own=1)
        obs['private']['shed']['MILK'] = 4
        replay = self.replay(obs, [{}, {'market': [['SELL', 'MILK', 4]]}])
        report = d.summarize_trace(self.trace(replay), 0, material_cash=1)
        self.assertEqual(report['transition_statuses'], {'RECONCILED': 1})
        self.assertLess(report['terminal_margin'], 0)
        first = report['first_observed_differences']['material_deficit']
        self.assertEqual(first['action_step'], obs['step'])
        self.assertEqual(first['effects']['own_minus_rival_by_cause']['trade:SELL:MILK'], report['terminal_margin'])
        self.assertEqual(report['observed_cash_telescope_residual'], [0, 0])
        self.assertEqual(report['largest_adverse_cash_transitions'][0]['frame'], 1)

    def test_day_boundary_real_production_and_exclusions(self):
        obs = self.observation(step=239)
        animal = self.animal(obs, units=0)
        animal['placed_day'] = 0
        replay = self.replay(obs, [{}, {}])
        trace = self.trace(replay)
        report = d.summarize_trace(trace, 0)
        self.assertEqual(report['transition_statuses'], {'RECONCILED': 1})
        self.assertIsNotNone(report['first_observed_differences']['production_event'])
        cf = d.counterfactual_transition(replay, 1, 0, {}, self.engine, self.ev, self.tm)
        self.assertEqual(cf['excluded_random_boundary_fields'], ['weed locations', 'new shop draw'])
        self.assertEqual(cf['relative_cash_delta'], 0)

    def test_file_api_hash_binding_gzip_and_witnesses(self):
        obs = self.observation()
        self.animal(obs)
        replay = self.replay(obs, [{'farmer': ['CARE']}, {}])
        data = gzip.compress(json.dumps(replay).encode(), mtime=0)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'fixture.gz'
            path.write_bytes(data)
            report, witnesses = d.analyze_file(path, ENGINE_DIR, own_seat=0, episode_id=90000,
                expected_cash=(3000, 3000), max_witnesses=1)
            self.assertEqual(report['source']['transport_sha256'], hashlib.sha256(data).hexdigest())
            self.assertTrue(report['binding']['terminal_cash_checked'])
            self.assertEqual(len(witnesses), 1)
            self.assertEqual(report['noop_harvest_scan']['alternatives_found'], 1)
            for kwargs in ({'episode_id': 90001}, {'expected_cash': (1, 2)}):
                arguments = {'own_seat': 0, 'episode_id': 90000, 'expected_cash': (3000, 3000), **kwargs}
                with self.assertRaises(ValueError):
                    d.analyze_file(path, ENGINE_DIR, **arguments)

    def test_cli_success_writes_parseable_outputs(self):
        replay = self.replay(self.observation(), [{}, {}])
        with tempfile.TemporaryDirectory() as temp:
            path, output = Path(temp) / 'fixture.json', Path(temp) / 'out'
            path.write_text(json.dumps(replay))
            run = subprocess.run([sys.executable, str(d.HERE/'diagnostics.py'), str(path), '--engine-dir', str(ENGINE_DIR),
                '--own-seat', '0', '--episode-id', '90000', '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads((output/'diagnostics.json').read_text())['terminal_margin'], 0)
            self.assertEqual(json.loads(gzip.decompress((output/'witnesses.json.gz').read_bytes())), [])

    def test_opening_portfolio_difference_is_not_misattributed_to_first_action(self):
        obs = self.observation()
        self.animal(obs)
        trace = self.trace(self.replay(obs, [{}, {}]))
        report = d.summarize_trace(trace, 0)
        for kind in ('portfolio', 'held_yield'):
            first = report['first_observed_differences'][kind]
            self.assertEqual(first['frame'], 0)
            self.assertEqual(first['phase'], 'opening')
            self.assertIsNone(first['action_step'])

    def test_nonlist_hands_matches_interpreter(self):
        obs = self.observation()
        self.animal(obs)
        action = {'farmer': ['CARE'], 'hands': None}
        cases = d.scan_noop_harvests(obs, action, self.engine, self.cfg)
        self.assertEqual(len(cases), 1)
        self.assertIsNone(cases[0]['action']['hands'])
        replay = self.replay(obs, [action, {}])
        cf = d.counterfactual_transition(replay, 1, 0, cases[0]['action'], self.engine, self.ev, self.tm)
        self.assertEqual(cf['own_inventory_delta'], {'MILK': 3})

    def test_bad_expected_cash_cli_is_clean_error(self):
        with tempfile.TemporaryDirectory() as temp:
            run = subprocess.run([sys.executable, str(d.HERE/'diagnostics.py'), '/unused',
                '--engine-dir', str(ENGINE_DIR), '--own-seat', '0', '--episode-id', '90000',
                '--expected-cash', 'garbled', '--output', temp], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertNotIn('Traceback', run.stderr)

    def test_invalid_thresholds_seats_and_frames(self):
        replay = self.replay(self.observation(), [{}, {}])
        trace = self.trace(replay)
        for seat in (True, -1, 2):
            with self.assertRaises(ValueError):
                d.summarize_trace(trace, seat)
        for threshold in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                d.summarize_trace(trace, 0, material_cash=threshold)
        for frame in (0, 2):
            with self.assertRaises(ValueError):
                d.counterfactual_transition(replay, frame, 0, {}, self.engine, self.ev, self.tm)


if __name__ == '__main__':
    unittest.main()
