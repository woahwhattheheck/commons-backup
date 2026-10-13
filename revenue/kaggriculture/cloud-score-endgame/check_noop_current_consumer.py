# SPDX-License-Identifier: Apache-2.0
"""Exercise the native no-op repair with the existing context-bound score selector.

No controller, new engine fixture family, or score policy is implemented here.
The adjacent native-noop suite supplies its existing constructed fixtures only;
its test methods are not rerun. Select the consumer source paths explicitly.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import io
import json
from pathlib import Path
import random
import unittest

import test_terminal_order_noops as native

DEPS = None
RECORDS = []
TRANSFORMS = 0


def make_actor(tie_break='baseline'):
    return DEPS.score.make_score_selector(DEPS.selector.WholePlanSelector,
        DEPS.weighted.make_selector, DEPS.terminal.build_table,
        DEPS.core.solve_full_table, DEPS.core.verify_certificate,
        rng=random.Random(5307), tie_break=tie_break)


def consume(actor, obs, cfg, action, packet):
    global TRANSFORMS
    TRANSFORMS += 1
    native.COUNTS["consumer_calls"] += 1
    valid = {native.PRODUCER.fingerprint(p['action']) for p in packet['plans']} if packet['complete'] else set()
    return actor.transform_terminal(obs, cfg, action, document=packet['document'],
        feasible=lambda a: native.PRODUCER.fingerprint(a) in valid)


class CurrentNoopConsumer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if DEPS is None:
            raise unittest.SkipTest('Run with explicit native engine and current score source paths')

    def test_native_noops_still_select_and_execute_with_current_context_binding(self):
        for position in (0, 1):
            for kind in ('quantity', 'opcode'):
                with self.subTest(position=position, kind=kind):
                    obs, cfg, action, scenarios = native.fixture(position)
                    if kind == 'opcode':
                        action['market'][9] = [{}, 'WHEAT', 2]
                    before = deepcopy((obs, cfg, action, scenarios))
                    packet = native.build(obs, cfg, action, scenarios)
                    actor = make_actor()
                    out = consume(actor, obs, cfg, action, packet)
                    self.assertNotEqual(out, action)
                    self.assertEqual(out['market'][9], action['market'][9])
                    self.assertEqual(actor.draws, 1)
                    self.assertEqual(actor.provider_calls, 1)
                    self.assertIn('terminal_context_sha256', actor.active)
                    receipts = [native.native_receipt(obs, cfg, out, s) for s in scenarios]
                    self.assertTrue(all(r['own_cash'] > r['rival_cash'] for r in receipts))
                    self.assertEqual((obs, cfg, action, scenarios), before)
                    RECORDS.append({'position': position, 'case': kind, 'output': out,
                        'context': actor.active['terminal_context_sha256'],
                        'draws': actor.draws, 'provider_calls': actor.provider_calls,
                        'native_cash': [{'own': r['own_cash'], 'rival': r['rival_cash']} for r in receipts]})

    def test_identical_noop_retry_keeps_one_draw_and_solution(self):
        for position in (0, 1):
            obs, cfg, action, scenarios = native.fixture(position)
            packet = native.build(obs, cfg, action, scenarios)
            actor = make_actor()
            out = consume(actor, obs, cfg, action, packet)
            committed = deepcopy(actor.active)
            retry = consume(actor, deepcopy(obs), deepcopy(cfg), deepcopy(action), deepcopy(packet))
            self.assertEqual(out, retry)
            self.assertEqual(actor.active, committed)
            self.assertEqual((actor.draws, actor.provider_calls), (1, 1))

    def test_changed_parent_metadata_retires_old_noop_commitment(self):
        for position in (0, 1):
            obs, cfg, action, scenarios = native.fixture(position)
            packet = native.build(obs, cfg, action, scenarios)
            actor = make_actor()
            out = consume(actor, obs, cfg, action, packet)
            self.assertNotEqual(out, action)
            changed = deepcopy(action)
            changed['caller_metadata']['retained'] = 'new caller action'
            new_packet = native.build(obs, cfg, changed, scenarios)
            self.assertEqual(consume(actor, obs, cfg, changed, new_packet), changed)
            self.assertIsNone(actor.active)
            self.assertEqual((actor.draws, actor.provider_calls), (1, 1))
            self.assertEqual(actor.last_decision['reason'], 'terminal_parent_changed')
            self.assertEqual(consume(actor, obs, cfg, action, packet), action)
            self.assertEqual((actor.draws, actor.provider_calls), (1, 1))

    def test_changed_cash_context_and_incomplete_table_remain_fallbacks(self):
        for position in (0, 1):
            obs, cfg, action, scenarios = native.fixture(position)
            packet = native.build(obs, cfg, action, scenarios)
            actor = make_actor(tie_break='cash_pareto')
            self.assertNotEqual(consume(actor, obs, cfg, action, packet), action)
            changed = deepcopy(obs)
            changed['farms'][position]['money'] += 1
            # Keep the old document deliberately: a retry cannot revive a stale
            # context even when the caller's physical action remains feasible.
            self.assertEqual(consume(actor, changed, cfg, action, packet), action)
            self.assertIsNone(actor.active)
            self.assertEqual((actor.draws, actor.provider_calls), (1, 1))
            incomplete = native.build(obs, cfg, action, scenarios, max_cells=1)
            fresh = make_actor()
            self.assertEqual(consume(fresh, obs, cfg, action, incomplete), action)
            self.assertEqual((fresh.draws, fresh.provider_calls), (0, 0))


def main(argv=None):
    global DEPS
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--producer-file', type=Path, default=Path(__file__).with_name('terminal_inputs.py'))
    p.add_argument('--loader', type=Path, required=True)
    p.add_argument('--engine-dir', type=Path, required=True)
    p.add_argument('--consumers', type=Path, required=True)
    p.add_argument('--core-file', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args(argv)
    DEPS = native.cases.dependencies(a.loader, a.engine_dir, a.consumers, a.core_file)
    native.DEPS = DEPS
    native.PRODUCER = native.load_producer(a.producer_file)
    log = io.StringIO()
    r = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CurrentNoopConsumer))
    report = {'schema': 'titan.native-noop.current-consumer.v1', 'tests': r.testsRun,
        'failures': len(r.failures), 'errors': len(r.errors), 'skipped': len(r.skipped),
        'success': r.wasSuccessful(), 'transforms': TRANSFORMS, 'counts': native.COUNTS,
        'witnesses': RECORDS, 'sources': {name: native.source_identity(path) for name, path in {
            'producer': a.producer_file, 'check': Path(__file__),
            'fixture_source': Path(native.__file__), 'native_cases': Path(native.cases.__file__),
            'score': a.consumers / 'score_endgame.py', 'weighted': a.consumers / 'weighted_selector.py',
            'selector': a.consumers / 'selector.py', 'utility': a.consumers / 'terminal_utility.py',
            'solver': a.core_file, 'engine': a.engine_dir / 'kaggriculture.py'}.items()},
        'scope': 'New native-parser source joined to the context-bound score selector; constructed terminal cases only',
        'full_games': 0, 'new_game_seeds': 0, 'canonical_archive_execution': False,
        'log': log.getvalue()}
    with a.report.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, allow_nan=False); f.write('\n')
    print(log.getvalue(), end='')
    print(json.dumps({k: report[k] for k in ('tests', 'success', 'failures', 'errors', 'skipped', 'transforms', 'counts')}, indent=2))
    return 0 if r.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
