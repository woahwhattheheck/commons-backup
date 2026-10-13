"""Public-clock/configuration checks for the existing lonespear consumer.

Uses retained development cases and the original market mechanics. No full game,
controller, new scenario model, or hidden evaluation is run by these checks.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import time
import unittest

import behavior
import engine_cases
import queue_response

HERE = Path(__file__).resolve().parent
KAG = HERE.parents[1]
QUEUE = Path(os.environ.get('TITAN_QUEUE_SOURCE', KAG / 'cloud-market-queue-delta/queue_delta.py'))
ENGINE = Path(os.environ.get('TITAN_ENGINE', KAG / 'cloud-policy-portfolio/vendor/engine'))
SOURCE = Path(os.environ.get('TITAN_LONESPEAR_SOURCE', KAG / 'cloud-policy-portfolio/revision2/vendor/opponents/sources/lonespear-v18/main_v18.py'))
CASES = Path(os.environ.get('TITAN_LONESPEAR_CASES', HERE / 'cases.json.gz'))
CASE_SHA256 = '3850381a54e1fcaf0c83a7073fce53787cae03b6f246fc1027c4f6724d200077'


def sparse(observation, form):
    result = copy.deepcopy(observation)
    if form == 'missing':
        result.pop('step', None)
    elif form == 'null':
        result['step'] = None
    return result


def untimed(value):
    value = copy.deepcopy(value)
    if value.get('comparison'):
        value['comparison'].pop('elapsed_seconds', None)
    return value


class PublicClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue = engine_cases.load(QUEUE, 'iris_clock_queue')
        cls.mechanics = cls.queue.load_market_engine(ENGINE / 'kaggriculture.py')
        cls.source = engine_cases.source(SOURCE)
        data = CASES.read_bytes()
        if hashlib.sha256(data).hexdigest() != CASE_SHA256:
            raise ValueError('Use the original six IRIS development cases')
        cls.cases = json.loads(gzip.decompress(data))
        cls.cfg = json.loads((HERE / 'base-frame.json').read_text())['configuration']

    def inputs(self, case, form='explicit', cfg=None):
        own = case['own']; rival = 1-own
        post = case['post_unit_observation']
        originals = case['original_actions']
        privates = case['offline_post_unit_privates']
        no_feed = copy.deepcopy(originals[rival])
        no_feed['market'] = [['PASS'] if isinstance(o, list) and len(o) == 3
                            and o[:2] == ['BUY_PRODUCT', 'WHEAT'] else o
                            for o in no_feed['market']]
        scenarios = [dict(id='recorded-rival', provenance='Retained offline label; not a runtime inference',
                          farm=post['farms'][rival], private=privates[rival], action=originals[rival]),
                     dict(id='no-feed', provenance='Existing named no-feed intervention',
                          farm=post['farms'][rival], private=privates[rival], action=no_feed)]
        return copy.deepcopy(dict(observation=sparse(case['observation'], form),
            configuration=self.cfg if cfg is None else cfg, selected_action=originals[own],
            own_farm=post['farms'][own], own_private=privates[own], market=post['market'],
            scenarios=scenarios, retained_wheat=0))

    def compare(self, args):
        return queue_response.evaluate_wheat_response(self.queue.compare_queues, self.mechanics, **args)

    def test_missing_step_predictions_equal_original_explicit(self):
        for case in self.cases:
            with self.subTest(trace=case['trace']):
                explicit = behavior.predict(case['observation'], self.cfg)
                self.assertEqual(explicit, behavior.predict(sparse(case['observation'], 'missing'), self.cfg))
                self.assertEqual(explicit['step'], 697)

    def test_null_step_predictions_equal_original_explicit(self):
        for case in self.cases:
            with self.subTest(trace=case['trace']):
                self.assertEqual(behavior.predict(case['observation'], self.cfg),
                    behavior.predict(sparse(case['observation'], 'null'), self.cfg))

    def test_sparse_period_comes_from_configuration(self):
        for period in (3, 12, 31):
            obs = sparse(self.cases[0]['observation'], 'missing')
            cfg = dict(self.cfg, turnsPerDay=period)
            self.assertEqual(behavior.predict(obs, cfg)['step'], 29*period+1)
            obs['step'] = 29*period+1
            self.assertEqual(behavior.predict(obs, cfg),
                             behavior.predict(sparse(obs, 'null'), cfg))

    def test_explicit_clock_remains_authoritative(self):
        obs = copy.deepcopy(self.cases[0]['observation'])
        # Existing explicit-step behavior does not reinterpret a supplied step.
        obs['step'] = 11
        self.assertEqual(behavior.predict(obs, {'turnsPerDay': 12})['step'], 11)
        self.assertEqual(behavior.predict(obs, {'turnsPerDay': 0})['step'], 11)

    def test_invalid_sparse_clock_is_unknown_not_zero(self):
        for period in (0, -1, True, None, 2.5, '24'):
            obs = sparse(self.cases[0]['observation'], 'missing')
            self.assertEqual(behavior.predict(obs, {'turnsPerDay': period})['status'], 'unknown')
        for field, value in (('day', None), ('day', -1), ('hour', 24), ('hour', True)):
            obs = sparse(self.cases[0]['observation'], 'null'); obs[field] = value
            self.assertEqual(behavior.predict(obs)['status'], 'unknown')

    def test_configuration_none_retains_default_clock(self):
        obs = sparse(self.cases[0]['observation'], 'missing')
        self.assertEqual(behavior.predict(obs, None), behavior.predict(obs, {}))
        self.assertEqual(behavior.predict(obs, None)['step'], 697)

    def fill_frames(self, actor):
        before = copy.deepcopy(self.cases[0]['observation'])
        before.update(day=5, hour=1, step=121)
        after = copy.deepcopy(before); after.update(hour=2, step=122)
        after['farms'][actor]['hires_today'] += 2
        after['farms'][actor]['hands'] += [[4, 4], [4, 4]]
        after['farms'][actor]['money'] += 7
        return before, after

    def test_fill_delta_supports_all_mixed_clock_forms(self):
        for actor in (0, 1):
            before, after = self.fill_frames(actor)
            expected = behavior.observed_fill(before, after, actor=actor)
            self.assertEqual(expected['fills'], 2)
            for left, right in itertools.product(('explicit', 'missing', 'null'), repeat=2):
                with self.subTest(actor=actor, before=left, after=right):
                    actual = behavior.observed_fill(sparse(before, left), sparse(after, right), actor=actor)
                    self.assertEqual(actual, expected)

    def test_custom_period_public_fill_delta(self):
        before, after = self.fill_frames(1)
        before['step'], after['step'] = 61, 62
        expected = behavior.observed_fill(before, after, actor=1)
        self.assertEqual(behavior.observed_fill(sparse(before, 'missing'), sparse(after, 'null'),
            actor=1, configuration={'turnsPerDay': 12}), expected)

    def test_sparse_fill_never_crosses_resets_or_missing_transitions(self):
        before, after = self.fill_frames(1)
        for day, hour in ((5, 1), (5, 3), (6, 0)):
            changed = sparse(after, 'missing'); changed.update(day=day, hour=hour)
            self.assertEqual(behavior.observed_fill(sparse(before, 'missing'), changed,
                             actor=1)['status'], 'unknown')
        self.assertEqual(behavior.observed_fill(sparse(before, 'missing'), sparse(after, 'null'),
            actor=1, configuration={'turnsPerDay': 0})['status'], 'unknown')

    def test_zero_cost_hire_prefix_matches_original_market(self):
        # New configuration boundary, not a repeat of the original multiplier1/3 grid.
        for case in self.cases:
            own = case['own']; actor = 1-own
            obs = case['observation']; post = case['post_unit_observation']
            cfg = dict(self.cfg, farmHandCostMult=0)
            private = case['offline_post_unit_privates'][actor]
            actual_orders = engine_cases.source_orders(self.source, obs, actor, private)
            request_count = next((i for i, order in enumerate(actual_orders) if order != ['HIRE']), len(actual_orders))
            prediction = behavior.predict(sparse(obs, 'missing'), cfg)
            self.assertEqual(prediction['status'], 'known')
            self.assertEqual(prediction['hire_requests'], request_count)
            scenario = dict(id='zero-cost-prefix', provenance='Configured source-bound prefix case',
                farm=post['farms'][actor], private=private,
                action={'market': actual_orders[:request_count]})
            no_orders = {'market': []}
            report = self.queue.compare_queues(self.mechanics, step=697, seat=own,
                own_farm=post['farms'][own], own_private=case['offline_post_unit_privates'][own],
                market=post['market'], baseline_action=no_orders, proposed_action=no_orders,
                scenarios=[scenario], configuration=cfg)
            self.assertEqual(report['status'], 'complete_conditional')
            filled = report['scenario_results'][0]['baseline']['rival']
            self.assertEqual(filled['hires_today']-post['farms'][actor]['hires_today'], prediction['hire_prefix_fills'])
            self.assertEqual(filled['cash'], prediction['cash_after_hire_prefix'])
            self.assertEqual(prediction['hire_costs'], [0]*request_count)

    def test_sparse_consumer_preserves_all_retained_complete_states(self):
        matches = 0
        for case, form in itertools.product(self.cases, ('missing', 'null')):
            args = self.inputs(case, form); before = copy.deepcopy(args)
            result = self.compare(args)
            with self.subTest(trace=case['trace'], form=form):
                self.assertEqual(result['status'], 'complete_conditional')
                self.assertEqual(result['fallback_action'], case['original_actions'][case['own']])
                self.assertEqual(result['proposal_action'], case['proposed_actions'][case['own']])
                self.assertFalse(result['action_selected'])
                self.assertEqual(args, before)
                for row in result['comparison']['scenario_results']:
                    expected = case if row['id'] == 'recorded-rival' else case['no_feed_control']
                    for a, b in (('baseline', 'baseline'), ('proposed', 'candidate')):
                        got, want = row[a], expected[b]
                        for actual, original, position in (('own_farm', 'farms', case['own']),
                                ('rival_farm', 'farms', 1-case['own']),
                                ('own_private', 'privates', case['own']),
                                ('rival_private', 'privates', 1-case['own'])):
                            self.assertEqual(got[actual], want[original][position]); matches += 1
                        self.assertEqual(got['market'], want['market']); matches += 1
                    own, rival = case['own'], 1-case['own']
                    dc = [expected['candidate']['after_cash'][i] - expected['baseline']['after_cash'][i]
                          for i in (0, 1)]
                    self.assertEqual(row['delta']['own_cash'], dc[own])
                    self.assertEqual(row['delta']['rival_cash'], dc[rival])
                    self.assertEqual(row['delta']['relative_cash'], dc[own]-dc[rival])
        self.assertEqual(matches, 240)

    def test_custom_clock_and_zero_cost_complete_consumer(self):
        for case in self.cases[:2]:
            cfg = dict(self.cfg, turnsPerDay=12, farmHandCostMult=0)
            missing = self.inputs(case, 'missing', cfg)
            explicit = copy.deepcopy(missing); explicit['observation']['step'] = 349
            got = self.compare(missing); direct = self.compare(explicit)
            self.assertEqual(got['status'], 'complete_conditional')
            self.assertEqual(got['prediction']['step'], 349)
            self.assertEqual(untimed(got), untimed(direct))

    def test_sparse_deadline_still_preserves_fallback(self):
        args = self.inputs(self.cases[2], 'null'); args['deadline'] = time.monotonic()-1
        result = self.compare(args)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['comparison']['reason'], 'deadline')
        self.assertIsNone(result['proposal_action'])
        self.assertIsNone(result['comparison']['bounds'])
        self.assertEqual(result['fallback_action'], args['selected_action'])

    def test_public_clock_does_not_read_private_or_labels(self):
        obs = sparse(self.cases[0]['observation'], 'missing')
        expected = behavior.predict(obs)
        obs.update(private={'shed': {'WHEAT': 999}}, action={'market': [['HIRE']]}, seed=9, outcome='WIN')
        self.assertEqual(expected, behavior.predict(obs))


if __name__ == '__main__':
    unittest.main(verbosity=2)
