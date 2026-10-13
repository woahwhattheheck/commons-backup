"""Real selected-seed producer -> preservation gate compatibility, offline."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest

import test_guard as support

HERE = Path(__file__).resolve().parent
PRODUCER_BLOB = '78bd08b00a8b7fcf934dcf25c54ece51746a5f5e'
PRODUCER = GATE = None


def proposal(obs, cfg, selected, post, *, complete=True, rows=()):
    contract = PRODUCER.compile_demand(
        obs, cfg, selected, post_unit_seeds=post['private']['seeds'],
        continuations={'selected': list(rows)}, complete=complete)
    packet = PRODUCER.transform(
        obs, cfg, selected, post_unit_seeds=post['private']['seeds'], contract=contract)
    return packet


class ProducerCompatibilityTests(unittest.TestCase):
    def test_real_empty_replacement_accepts_funded_twin(self):
        for seat in (0, 1):
            obs, cfg, post = support.fixture(seat, cash=1000, hires=12)
            obs['step'] = 718
            selected, _ = support.actions([['HIRE']])
            packet = proposal(obs, cfg, selected, post)
            self.assertEqual(packet['action']['market'][0], [])
            gate = GATE(support.MECHANICS)
            out = gate.transform(obs, cfg, selected, packet['action'], post_units=post,
                                 scenarios=[support.scenario()])
            self.assertEqual(out, packet['action'])
            self.assertEqual(gate.last_report['status'], 'preserved_on_supplied_scenarios')
            self.assertEqual(gate.last_report['scenarios'][0]['cash_delta'], 90)

    def test_real_empty_replacement_hits_cash_negative_not_shape_rejection(self):
        for seat in (0, 1):
            obs, cfg, post = support.fixture(seat, cash=233, hires=12)
            obs['step'] = 718
            selected, _ = support.actions([['HIRE']])
            packet = proposal(obs, cfg, selected, post)
            gate = GATE(support.MECHANICS)
            out = gate.transform(obs, cfg, selected, packet['action'], post_units=post,
                                 scenarios=[support.scenario()])
            self.assertEqual(out, selected)
            self.assertEqual(gate.last_report['status'], 'fallback_changed_execution')
            row = gate.last_report['scenarios'][0]
            self.assertEqual((row['baseline_cash'], row['proposal_cash']), (143, 0))

    def test_real_partial_reduction_preserves_trailing_fields(self):
        for seat in (0, 1):
            obs, cfg, post = support.fixture(seat, cash=1000, hires=1)
            obs['step'] = 717
            selected, _ = support.actions([['HIRE']])
            selected['hands'] = [['PASS']]
            selected['market'][0].append({'caller_note': 'keep-exact'})
            rows = [{'step': 718, 'action': {'farmer': ['PLANT', 'WHEAT'],
                     'hands': [['PLANT', 'WHEAT']], 'market': []}}]
            packet = proposal(obs, cfg, selected, post, rows=rows)
            self.assertEqual(packet['action']['market'][0],
                             ['BUY_SEED', 'WHEAT', 2, {'caller_note': 'keep-exact'}])
            gate = GATE(support.MECHANICS)
            out = gate.transform(obs, cfg, selected, packet['action'], post_units=post,
                                 scenarios=[support.scenario()])
            self.assertEqual(out, packet['action'])
            self.assertEqual(gate.last_report['scenarios'][0]['cash_delta'], 70)

    def test_trailing_fields_cannot_be_changed(self):
        obs, cfg, post = support.fixture(cash=1000, hires=0)
        obs['step'] = 717
        selected, _ = support.actions([])
        selected['market'][0].append('unchanged-metadata')
        rows = [{'step': 718, 'action': {'farmer': ['PLANT', 'WHEAT'], 'market': []}}]
        packet = proposal(obs, cfg, selected, post, rows=rows)
        packet['action']['market'][0][3] = 'tampered'
        gate = GATE(support.MECHANICS)
        self.assertEqual(gate.transform(obs, cfg, selected, packet['action'],
                         post_units=post, scenarios=[support.scenario()]), selected)
        self.assertEqual(gate.last_report['status'], 'fallback_unknown')

    def test_incomplete_future_does_not_become_complete_by_composition(self):
        obs, cfg, post = support.fixture(cash=1000)
        selected, _ = support.actions([['HIRE']])
        packet = proposal(obs, cfg, selected, post, complete=False)
        self.assertEqual(packet['status'], 'UNCHANGED')
        self.assertEqual(packet['action'], selected)
        gate = GATE(support.MECHANICS)
        self.assertEqual(gate.transform(obs, cfg, selected, packet['action'],
                         post_units=post, scenarios=None), selected)
        self.assertEqual(gate.last_report['status'], 'unchanged')

    def test_removed_slot_stays_in_place(self):
        obs, cfg, post = support.fixture(cash=1000)
        obs['step'] = 718
        selected, _ = support.actions([['HIRE']])
        packet = proposal(obs, cfg, selected, post)
        self.assertEqual(len(packet['action']['market']), 2)
        packet['action']['market'].pop(0)
        gate = GATE(support.MECHANICS)
        self.assertEqual(gate.transform(obs, cfg, selected, packet['action'],
                         post_units=post, scenarios=[support.scenario()]), selected)
        self.assertEqual(gate.last_report['status'], 'fallback_unknown')

    def test_real_chain_does_not_mutate_caller_or_producer_packet(self):
        obs, cfg, post = support.fixture(cash=1000)
        obs['step'] = 718
        selected, _ = support.actions([['HIRE']])
        before = deepcopy((obs, cfg, post, selected))
        packet = proposal(obs, cfg, selected, post)
        packet_before = deepcopy(packet)
        gate = GATE(support.MECHANICS)
        out = gate.transform(obs, cfg, selected, packet['action'], post_units=post,
                             scenarios=[support.scenario()])
        self.assertEqual(out, packet['action'])
        out['market'][0].append('separate-copy')
        self.assertEqual((obs, cfg, post, selected), before)
        self.assertEqual(packet, packet_before)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-cache', type=Path, required=True)
    parser.add_argument('--evaluator', type=Path, default=HERE.parent/'cloud-eval/evaluate.py')
    parser.add_argument('--engine-loader', type=Path)
    parser.add_argument('--mechanics', type=Path, default=HERE.parent/'cloud-execution-lab/mechanics.py')
    parser.add_argument('--producer', type=Path,
                        default=HERE.parent/'cloud-selected-seed-budget/selected_seed_budget.py')
    parser.add_argument('--producer-blob', default=PRODUCER_BLOB,
                        help='Expected complete producer Git blob; defaults to the original compatibility source')
    parser.add_argument('--guard-file', type=Path, default=HERE/'guard.py')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    raw = args.producer.read_bytes()
    actual_blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if actual_blob != args.producer_blob:
        parser.error('producer bytes do not match the published compatibility pin')
    PRODUCER = support.load(args.producer, 'seed_guard_published_producer')
    GATE = support.load(args.guard_file, 'seed_guard_compatibility_gate').SeedExecutionGuard
    evaluator = support.load(args.evaluator, 'seed_guard_compatibility_evaluator')
    options = {'prepare': False}
    if args.engine_loader: options['loader'] = args.engine_loader
    support.ENGINE, engine_hashes = evaluator.get_engine(args.engine_cache, **options)
    support.MECHANICS = support.load(args.mechanics, 'seed_guard_compatibility_mechanics')
    start = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ProducerCompatibilityTests))
    report = {'tests_run': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped),
              'seconds': time.perf_counter()-start, 'producer_git_blob': actual_blob,
              'producer_commit': ('36ec529659f038725ce325a19c2079a2a5b898b7'
                                  if actual_blob == PRODUCER_BLOB else None),
              'engine_ref': evaluator.ENGINE_REF, 'engine_hashes': engine_hashes,
              'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [args.guard_file, HERE/'test_seed_adapter.py',
                                          HERE/'market_kernel.py', args.mechanics]},
              'full_games': 0, 'scored_seeds': [], 'fixture_type': 'synthetic-consumer'}
    if args.report: args.report.write_text(json.dumps(report, indent=2)+'\n')
    sys.exit(not result.wasSuccessful())
