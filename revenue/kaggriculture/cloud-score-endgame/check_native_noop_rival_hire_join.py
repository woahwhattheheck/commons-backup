# SPDX-License-Identifier: Apache-2.0
"""Joined validation for native own-order no-ops and explicit rival HIRE.

This executes the existing terminal-input producer and current score selector.
It introduces no runtime implementation, scenario generator, actor, or game.
All rival queues are explicit constructed hypotheses; no hidden action is read.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import time
import unittest
from unittest.mock import patch

DEPS = PRODUCER = CASES = RIVAL = None
COUNTS = {
    'producer_market_cells': 0,
    'full_terminal_interpreter_comparisons': 0,
    'selector_transforms': 0,
    'unit_snapshots': 0,
}
WITNESSES = []


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load supplied source: ' + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity(path):
    body = Path(path).read_bytes()
    return {
        'bytes': len(body),
        'sha256': hashlib.sha256(body).hexdigest(),
        'git_blob': hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest(),
    }


def fixture(player=0, *, quantity='native-noop'):
    obs, cfg, action, scenarios = RIVAL.fixture(player)
    # Active slot 9 is retained as an inherited non-sale position. Native
    # _parse_order returns None for this quantity, so the order changes no state.
    action['market'] += [[] for _ in range(7)]
    action['market'].append(['BUY_SEED', 'CARROT', deepcopy(quantity)])
    assert len(action['market']) == 10
    return obs, cfg, action, scenarios


def build(obs, cfg, action, scenarios, **kwargs):
    result = PRODUCER.build_terminal_inputs(
        DEPS.engine, obs, cfg, action,
        post_unit_observation=deepcopy(obs),
        scenarios=deepcopy(scenarios),
        allow_rival_hire=True,
        **kwargs,
    )
    COUNTS['producer_market_cells'] += result['native_market_calls']
    return result


def native_check(test, obs, cfg, packet):
    by_id = {row['id']: row for row in packet['scenarios']}
    for receipt in packet['document']['receipts']:
        if not receipt['done']:
            continue
        state, env = CASES.make_state(obs, cfg, receipt['own_action'], by_id[receipt['scenario']])
        DEPS.engine.interpreter(state, env)
        COUNTS['full_terminal_interpreter_comparisons'] += 1
        test.assertEqual([step.status for step in state], ['DONE', 'DONE'])
        p = obs['player']
        test.assertEqual(
            [receipt['own_cash'], receipt['rival_cash']],
            [state[p].reward, state[1-p].reward],
        )
        test.assertEqual(receipt['own_shed_after'], state[p].observation.private['shed'])
        test.assertEqual(receipt['own_seeds_after'], state[p].observation.private['seeds'])
        test.assertEqual(receipt['own_hands_after'], len(state[p].observation.farms[p]['hands']))
        test.assertEqual(receipt['rival_hands_after'], len(state[p].observation.farms[1-p]['hands']))
        test.assertEqual(receipt['rival_hires_today_after'],
                         state[p].observation.farms[1-p]['hires_today'])


def actor(*, tie_break='cash_pareto'):
    return DEPS.score.make_score_selector(
        DEPS.selector.WholePlanSelector,
        DEPS.weighted.make_selector,
        DEPS.terminal.build_table,
        DEPS.core.solve_full_table,
        DEPS.core.verify_certificate,
        rng=random.Random(10282),
        tie_break=tie_break,
    )


def consume(current, obs, cfg, action, packet):
    COUNTS['selector_transforms'] += 1
    valid = [plan['action'] for plan in packet['plans']] if packet['complete'] else []
    return current.transform_terminal(
        obs, cfg, action,
        document=packet['document'],
        feasible=lambda candidate: any(candidate == value for value in valid),
    )


class JoinedNoopHireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if any(value is None for value in (DEPS, PRODUCER, CASES, RIVAL)):
            raise unittest.SkipTest('Use the explicit CLI with pinned native dependencies')

    def test_malformed_quantity_preserves_slot_and_native_hire_matrix(self):
        for player in (0, 1):
            for quantity in (None, 'native-noop', '', [], {}):
                with self.subTest(player=player, quantity=quantity):
                    obs, cfg, action, scenarios = fixture(player, quantity=quantity)
                    before = deepcopy((obs, cfg, action, scenarios))
                    self.assertIsNone(DEPS.engine._parse_order(action['market'][9]))
                    packet = build(obs, cfg, action, scenarios)
                    self.assertTrue(packet['complete'])
                    self.assertEqual(len(packet['plans']), 2)
                    self.assertTrue(all(plan['action']['market'][9] == action['market'][9]
                                        for plan in packet['plans']))
                    rows = packet['document']['receipts']
                    self.assertEqual([[r['own_cash'], r['rival_cash']] for r in rows],
                                     [[156, 377], [156, 0], [160, 375], [160, 375]])
                    self.assertEqual([r['rival_hands_after'] for r in rows], [13, 14, 13, 13])
                    native_check(self, obs, cfg, packet)
                    self.assertEqual((obs, cfg, action, scenarios), before)

    def test_unhashable_unknown_opcode_preserves_slot_with_hire(self):
        for player in (0, 1):
            for opcode in ([], {}):
                with self.subTest(player=player, opcode=opcode):
                    obs, cfg, action, scenarios = fixture(player)
                    action['market'][9] = [deepcopy(opcode), 'WHEAT', 2]
                    self.assertIsNone(DEPS.engine._parse_order(action['market'][9]))
                    packet = build(obs, cfg, action, scenarios)
                    self.assertTrue(packet['complete'])
                    self.assertTrue(all(plan['action']['market'][9] == action['market'][9]
                                        for plan in packet['plans']))
                    self.assertEqual([[r['own_cash'], r['rival_cash']]
                                      for r in packet['document']['receipts']],
                                     [[156, 377], [156, 0], [160, 375], [160, 375]])
                    native_check(self, obs, cfg, packet)

    def test_hire_column_reverses_cash_tie_selection_even_with_noop(self):
        for player in (0, 1):
            obs, cfg, action, scenarios = fixture(player)
            sale_only = build(obs, cfg, action, scenarios[:1])
            complete = build(obs, cfg, action, scenarios)
            sale_actor, complete_actor = actor(), actor()
            sale_action = consume(sale_actor, obs, cfg, action, sale_only)
            complete_action = consume(complete_actor, obs, cfg, action, complete)
            self.assertNotEqual(sale_action, action)
            self.assertEqual(sale_action['market'][9], action['market'][9])
            self.assertEqual((sale_actor.draws, sale_actor.provider_calls), (1, 1))
            self.assertEqual(complete_action, action)
            self.assertEqual((complete_actor.draws, complete_actor.provider_calls), (0, 1))
            self.assertEqual(complete_actor.last_objective['status'], 'baseline_optimal')
            self.assertEqual(DEPS.terminal.build_table(complete['document'])['win_points'],
                             [['0', '1'], ['0', '0']])
            WITNESSES.append({
                'player': player,
                'inherited_noop': action['market'][9],
                'sale_only_action': sale_action,
                'with_hire_action': complete_action,
                'sale_only_status': sale_actor.last_objective['status'],
                'with_hire_status': complete_actor.last_objective['status'],
                'scope': 'Constructed terminal hypotheses; not a game result',
            })

    def test_identical_retry_keeps_one_draw_and_parent_binding(self):
        for player in (0, 1):
            obs, cfg, action, scenarios = fixture(player)
            packet = build(obs, cfg, action, scenarios[:1])
            current = actor()
            first = consume(current, obs, cfg, action, packet)
            committed = deepcopy(current.active)
            second = consume(current, deepcopy(obs), deepcopy(cfg), deepcopy(action),
                             deepcopy(packet))
            self.assertEqual(first, second)
            self.assertEqual(current.active, committed)
            self.assertEqual(current.active['terminal_parent_action'], action)
            self.assertEqual((current.draws, current.provider_calls), (1, 1))

    def test_changed_parent_retires_before_reusing_old_noop_draw(self):
        for player in (0, 1):
            obs, cfg, action, scenarios = fixture(player)
            packet = build(obs, cfg, action, scenarios[:1])
            current = actor()
            self.assertNotEqual(consume(current, obs, cfg, action, packet), action)
            changed = deepcopy(action)
            changed['caller_metadata'] = {'new': True}
            self.assertEqual(consume(current, obs, cfg, changed, packet), changed)
            self.assertIsNone(current.active)
            self.assertEqual(current.last_decision['reason'], 'terminal_parent_changed')
            self.assertEqual((current.draws, current.provider_calls), (1, 1))

    def test_changed_visible_cash_retires_context_without_redraw(self):
        for player in (0, 1):
            obs, cfg, action, scenarios = fixture(player)
            packet = build(obs, cfg, action, scenarios[:1])
            current = actor()
            self.assertNotEqual(consume(current, obs, cfg, action, packet), action)
            changed = deepcopy(obs)
            changed['farms'][player]['money'] += 1
            self.assertEqual(consume(current, changed, cfg, action, packet), action)
            self.assertIsNone(current.active)
            self.assertEqual(current.last_decision['reason'], 'terminal_context_changed')
            self.assertEqual((current.draws, current.provider_calls), (1, 1))

    def test_incomplete_or_expired_hire_table_never_draws(self):
        for player in (0, 1):
            obs, cfg, action, scenarios = fixture(player)
            for kwargs, expected_calls in (({'max_cells': 1}, 1),
                                           ({'deadline': time.perf_counter() - 1}, 0)):
                with self.subTest(player=player, kwargs=kwargs):
                    packet = build(obs, cfg, action, scenarios, **kwargs)
                    self.assertFalse(packet['complete'])
                    self.assertEqual(packet['native_market_calls'], expected_calls)
                    current = actor()
                    self.assertEqual(consume(current, obs, cfg, action, packet), action)
                    self.assertEqual((current.draws, current.provider_calls), (0, 0))

    def test_overflow_still_stops_before_hire_native_call(self):
        for player in (0, 1):
            obs, cfg, action, scenarios = fixture(player, quantity=float('inf'))
            with patch.object(DEPS.engine, '_process_market',
                              side_effect=AssertionError('native market entered')):
                with self.assertRaisesRegex(ValueError, 'Unsupported noninteger'):
                    build(obs, cfg, action, scenarios)

    def test_post_unit_snapshot_is_consumed_once_with_noop_and_hire(self):
        for player in (0, 1):
            obs, cfg, action, scenarios = fixture(player)
            obs['private']['shed'] = {}
            obs['private']['inventories'] = [{'MILK': 1}]
            action['farmer'] = ['DROP']
            post = CASES.own_unit_snapshot(DEPS.engine, obs, cfg, action)
            COUNTS['unit_snapshots'] += 1
            with patch.object(DEPS.engine, '_apply_unit_action',
                              side_effect=AssertionError('duplicate unit stage')):
                packet = PRODUCER.build_terminal_inputs(
                    DEPS.engine, obs, cfg, action,
                    post_unit_observation=post,
                    scenarios=deepcopy(scenarios),
                    allow_rival_hire=True,
                )
            COUNTS['producer_market_cells'] += packet['native_market_calls']
            self.assertTrue(packet['complete'])
            self.assertEqual(packet['fallback_action'], action)
            self.assertEqual(packet['plans'][0]['action']['farmer'], ['DROP'])
            native_check(self, obs, cfg, packet)


def main(argv=None):
    global DEPS, PRODUCER, CASES, RIVAL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer-file', type=Path, required=True)
    parser.add_argument('--score-file', type=Path, required=True)
    parser.add_argument('--rival-test-file', type=Path, required=True)
    parser.add_argument('--cases-file', type=Path, required=True)
    parser.add_argument('--loader', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--core-file', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.report.exists():
        parser.error('use a new report path')
    PRODUCER = load(args.producer_file.resolve(), '_joined_terminal_inputs')
    sys.modules['terminal_inputs'] = PRODUCER
    CASES = load(args.cases_file.resolve(), '_joined_terminal_cases')
    DEPS = CASES.dependencies(args.loader.resolve(), args.engine_dir.resolve(),
                              args.dependencies.resolve(), args.core_file.resolve())
    DEPS.score = load(args.score_file.resolve(), '_joined_current_score')
    RIVAL = load(args.rival_test_file.resolve(), '_joined_rival_fixture')
    RIVAL.DEPS, RIVAL.TI, RIVAL.CASES = DEPS, PRODUCER, CASES

    paths = [args.producer_file, args.score_file, args.rival_test_file,
             args.cases_file, args.loader, args.core_file, Path(__file__),
             *[args.dependencies / name for name in
               ('terminal_utility.py', 'selector.py', 'solver.py', 'weighted_selector.py')],
             *[args.engine_dir / name for name in
               ('kaggriculture.py', 'kaggriculture.json', 'utils.py')]]
    before = {str(path.resolve()): identity(path) for path in paths}
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(JoinedNoopHireTests))
    after = {str(path.resolve()): identity(path) for path in paths}
    if before != after:
        raise AssertionError('source changed during execution')
    report = {
        'schema': 'titan.native-noop-rival-hire-joined.v1',
        'tests': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'skipped': len(result.skipped),
        'success': result.wasSuccessful(),
        'counts': COUNTS,
        'witnesses': WITNESSES,
        'sources': before,
        'full_games': 0,
        'game_seed_uses': 0,
        'runtime_changes': 0,
        'scope': ('Current native-noop terminal producer + explicit rival-HIRE + '
                  'current context/parent-bound score selector; constructed terminal cases only.'),
        'log': log.getvalue(),
    }
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(log.getvalue(), end='')
    print(json.dumps({key: report[key] for key in
          ('success', 'tests', 'failures', 'errors', 'skipped', 'counts')}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
