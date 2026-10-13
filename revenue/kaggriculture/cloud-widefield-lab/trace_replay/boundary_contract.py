# SPDX-License-Identifier: Apache-2.0
"""Independent contract cases for the ONE observation-reconstruction consumer.

This module is test-only: it never reconstructs a recorded observation stream.
Call run_contract(recover, evaluator, engine, hashes), where recover(report,
seat=...) returns normalized {configuration, frame_count, frames} as documented.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import unittest

TRACE_SCHEMA = "titan.widefield.loss-trace.v1"
EVALUATOR = ENGINE = HASHES = RECOVER = None


def fixture():
    """Construct a complete static-action trace independently of reconstruct()."""
    e, engine = EVALUATOR, ENGINE
    cfg = e.Struct({k: copy.deepcopy(v.get('default') if isinstance(v, dict) else v)
                    for k, v in engine.specification['configuration'].items()})
    cfg.seed = 0  # Explicit test fixture, not a claimed development/held sample.
    env = e.Struct(configuration=cfg, done=False, info={})
    state = [e.Struct(observation=e.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    rows, observations = [], [[], []]
    digest = hashlib.sha256()
    for step in range(cfg.episodeSteps):
        actions = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(2)]
        if step == 0:
            actions[0]['market'] = [['BUY_PRODUCT', 'WHEAT', 3], ['BUY_SEED', 'CARROT', 2], ['HIRE']]
            actions[1]['market'] = [['BUY_PRODUCT', 'FERTILIZER', 1], ['BUY_SEED', 'TOMATO', 1]]
        if step in (25, 49, 97):
            actions[0]['market'] = [['SELL', 'WHEAT', 1]]
        for seat, s in enumerate(state):
            s.observation.step = step
            s.observation.remainingOverageTime = 0
            observations[seat].append(copy.deepcopy(dict(s.observation)))
            s.action = actions[seat]
        engine.interpreter(state, env)
        bank = [float(state[0].observation.farms[i]['money']) for i in range(2)]
        digest.update(e.encoded({'step': step, 'actions': actions, 'bank': bank}))
        rows.append({'step': step, 'actions': actions, 'bank': bank})
        if all(s.status == 'DONE' for s in state):
            env.done = True
            break
    digest.update(e.encoded([s.observation for s in state]))
    report = {'schema': TRACE_SCHEMA, 'engine_ref': e.ENGINE_REF, 'engine_sha256': HASHES,
              'games': [{'seed': 0, 'candidate_seat': 0, 'status': 'complete', 'failure': None,
                         'scores': [s.reward for s in state], 'steps_completed': len(rows),
                         'trace_sha256': digest.hexdigest(), 'actions_and_timing': rows,
                         'candidate': {'fixture': 'static actions, no policy'},
                         'opponent': {'fixture': 'static actions, no policy'}}]}
    return report, observations


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.observations = fixture()

    def convert(self, report=None, **kwargs):
        payload = copy.deepcopy(self.report if report is None else report)
        before = copy.deepcopy(payload)
        try:
            return RECOVER(payload, **kwargs)
        finally:
            self.assertEqual(payload, before, "Recovery must preserve its source trace")

    def changed(self):
        return copy.deepcopy(self.report)

    def test_every_observation_and_action_matches_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                got = self.convert(seat=seat)
                self.assertEqual(got['frame_count'], 719)
                self.assertEqual([f['observation'] for f in got['frames']], self.observations[seat])
                self.assertEqual([f['expected_action'] for f in got['frames']],
                                 [r['actions'][seat] for r in self.report['games'][0]['actions_and_timing']])
                self.assertIsNone(got['configuration']['seed'])
                self.assertEqual(got['frames'][1]['observation']['player'], seat)
        self.assertNotEqual(self.observations[0][1]['private'], self.observations[1][1]['private'])

    def test_output_detached_from_source_and_adjacent_frames(self):
        got = self.convert()
        got['frames'][0]['expected_action']['market'].clear()
        got['frames'][0]['observation']['private']['seeds']['CARROT'] = 999
        self.assertTrue(self.report['games'][0]['actions_and_timing'][0]['actions'][0]['market'])
        self.assertNotEqual(got['frames'][1]['observation']['private']['seeds'].get('CARROT'), 999)

    def test_wrong_engine_revision_or_hash(self):
        for field in ('engine_ref', 'engine_sha256'):
            p = self.changed(); p[field] = 'wrong' if field == 'engine_ref' else {}
            with self.assertRaises(ValueError):
                self.convert(p)

    def test_compact_summary_and_custom_configuration_rejected(self):
        p = self.changed(); p.pop('schema')
        with self.assertRaises(ValueError): self.convert(p)
        p = self.changed(); p['configuration_overrides'] = {'startingMoney': 1}
        with self.assertRaises(ValueError): self.convert(p)

    def test_failed_or_missing_full_stream(self):
        for field, value in [('status', 'failed'), ('failure', {'step': 4}), ('actions_and_timing', [])]:
            p = self.changed(); p['games'][0][field] = value
            with self.assertRaises(ValueError): self.convert(p)

    def test_missing_duplicate_out_of_order_or_extra_rows(self):
        for change in ('missing', 'duplicate', 'out_of_order', 'extra'):
            p = self.changed(); g = p['games'][0]; r = g['actions_and_timing']
            if change == 'missing': del r[25]
            elif change == 'duplicate': r.insert(25, copy.deepcopy(r[25]))
            elif change == 'out_of_order': r[25], r[26] = r[26], r[25]
            else:
                r.append(copy.deepcopy(r[-1])); r[-1]['step'] += 1
            g['steps_completed'] = len(r)
            with self.subTest(change=change), self.assertRaises(ValueError): self.convert(p)

    def test_missing_rival_action(self):
        p = self.changed(); p['games'][0]['actions_and_timing'][0]['actions'].pop()
        with self.assertRaises(ValueError): self.convert(p)

    def test_changed_bank_and_invalid_cash(self):
        for value in ([1, 2], [float('nan'), 2], [True, 2]):
            p = self.changed(); p['games'][0]['actions_and_timing'][0]['bank'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): self.convert(p)

    def test_wrong_seed_rejected_by_cash_or_full_state_digest(self):
        p = self.changed(); p['games'][0]['seed'] = 1
        with self.assertRaises(ValueError): self.convert(p)

    def test_cash_neutral_action_tamper_rejected(self):
        p = self.changed(); p['games'][0]['actions_and_timing'][-1]['actions'][0]['farmer'] = ['EAST']
        with self.assertRaises(ValueError): self.convert(p)

    def test_truncated_stream_count_rewards_digest_and_seat(self):
        edits = [('steps_completed', 718), ('scores', [1, 2]), ('trace_sha256', '0' * 64),
                 ('candidate_seat', True), ('seed', 0.0)]
        for field, value in edits:
            p = self.changed(); p['games'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.convert(p)
        p = self.changed(); p['games'][0]['actions_and_timing'].pop(); p['games'][0]['steps_completed'] -= 1
        with self.assertRaises(ValueError): self.convert(p)


def run_contract(recover, evaluator, engine, hashes):
    """Exercise an injected consumer; return counts without claiming an unrun pass.

    recover receives a detached source trace and optional seat (default candidate).
    It must return configuration, frame_count and frames, each with observation
    and expected_action. Invalid complete-trace inputs must raise ValueError.
    An adapter may normalize field names; it must not regenerate observations or
    replace the implementation being checked.
    """
    global EVALUATOR, ENGINE, HASHES, RECOVER
    EVALUATOR, ENGINE, HASHES, RECOVER = evaluator, engine, hashes, recover
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReplayTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return {"kind": "constructed official-engine replay contract; no policy panel",
            "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
            "successful": result.wasSuccessful(), "fixture_seed": 0,
            "observation_comparisons_expected": 1438,
            "scored_games": 0, "policy_calls": 0,
            "engine_ref": evaluator.ENGINE_REF, "engine_sha256": hashes,
            "contract_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "failure_details": [{"case": str(t), "detail": detail} for t, detail in result.failures],
            "error_details": [{"case": str(t), "detail": detail} for t, detail in result.errors]}
