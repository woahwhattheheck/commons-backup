# SPDX-License-Identifier: MIT
"""Finite-load ingestion through the real benchmark CLI and controlled processes.

Reuses the landed output fixture setup, but runs none of its original test bank.
No official solver, official checker or algorithm comparison is invoked.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import unittest

import test_benchmark_outputs as fixtures

BENCHMARK = Path(__file__).with_name('benchmark.py')
EVIDENCE = None
DETAILS = []


def values(items):
    return [{'t': 0, 'from': i, 'to': i + 1, 'sat': v} for i, v in enumerate(items)]


def checker(items):
    return json.dumps({'valid': True, 'saturations': values(items), 'total_cost': 0}) + '\n'


def stats(items):
    return json.dumps({'loads': values(items), 'budget_used': [0], 'accepted': 1, 'attempted': 2}) + '\n'


@unittest.skipUnless(os.name == 'posix', 'Controlled executable fixtures require POSIX')
class FiniteLoadTests(unittest.TestCase):
    def run_case(self, label, *, predicted=(.75, .5), actual=(.75, .5), score=None,
                 raw_stats=None, raw_6=None, raw_12=None, fail=False):
        instance = fixtures.BenchmarkOutputTests()
        instance.setUp()
        self.addCleanup(instance.doCleanups)
        fixtures.BENCHMARK = BENCHMARK
        payload = {'stats': stats(predicted) if raw_stats is None else raw_stats,
                   'checker-6': checker(actual if score is None else score) if raw_6 is None else raw_6,
                   'checker-12': checker(actual) if raw_12 is None else raw_12}
        protocol = instance.root / 'protocol.json'
        protocol.write_text(json.dumps(payload), encoding='utf-8')
        fixtures.executable(instance.writer, '''from pathlib import Path
import json, os, sys
wire = json.loads(Path(%r).read_text())
Path(sys.argv[-1]).write_text('{"fixture": "finite-load-ingestion"}\\n')
Path(os.environ['SEDGE_STATS']).write_text(wire['stats'])
print('controlled solver completed')
''' % str(protocol))
        fixtures.executable(instance.checker, '''from pathlib import Path
import json, sys
wire = json.loads(Path(%r).read_text())
key = 'checker-' + sys.argv[sys.argv.index('--max-decimal-places') + 1]
assert json.loads(Path(sys.argv[sys.argv.index('--srpaths') + 1]).read_text())['fixture'] == 'finite-load-ingestion'
sys.stdout.write(wire[key])
''' % str(protocol))
        result = instance.run_cli()
        folder = instance.out / 'setB-01/candidate'
        evidence = {str(p.relative_to(instance.out)): p.read_bytes()
                    for p in instance.out.rglob('*') if p.is_file()}
        record = {'case': label, 'expect_failure': fail, 'exit_code': result.returncode,
                  'summary_written': (instance.out/'summary.json').exists(),
                  'result_written': (folder/'result.json').exists(),
                  'stderr': result.stderr,
                  'payload_sha256': hashlib.sha256(protocol.read_bytes()).hexdigest(),
                  'files': {n: {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
                            for n, b in evidence.items()}}
        DETAILS.append(record)
        if EVIDENCE is not None:
            dest = EVIDENCE / label
            dest.mkdir(parents=True, exist_ok=False)
            (dest/'protocol.json').write_bytes(protocol.read_bytes())
            (dest/'cli.stdout').write_text(result.stdout)
            (dest/'cli.stderr').write_text(result.stderr)
            for name, data in evidence.items():
                target = dest/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        # Raw subprocess output and completed-process sidecars survive rejection.
        self.assertEqual((folder/'stats.json').read_text(), payload['stats'])
        for suffix in ('6', '12'):
            path = folder / ('checker-' + suffix + '.stdout')
            if path.exists():
                self.assertEqual(path.read_text(), payload['checker-' + suffix])
                sidecar = json.loads(path.with_suffix('.process.json').read_text())
                self.assertEqual(sidecar['status'], 'completed')
                self.assertTrue(sidecar['capture_complete'])
                self.assertEqual(sidecar['stdout_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        if fail:
            self.assertNotEqual(result.returncode, 0, 'invalid loads acquired a successful result')
            self.assertFalse(record['summary_written'])
            self.assertFalse(record['result_written'])
            self.assertTrue((folder/'solver.stdout').exists())
            self.assertTrue((instance.out/'experiment.json').exists())
            return None
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((instance.out/'summary.json').read_text())
        row = report['results'][0][0]
        self.assertTrue(row['valid'])
        self.assertTrue(math.isfinite(row['mlu_6']))
        self.assertTrue(math.isfinite(row['max_load_error']))
        self.assertEqual(row['input_sha256'].keys(), {'setB-01-net.json','setB-01-tm.json','setB-01-scenario.json'})
        return row

    def test_predicted_nan_first_is_rejected(self):
        self.run_case('predicted-nan-first', predicted=(float('nan'), .5), fail=True)

    def test_predicted_nan_last_cannot_hide_behind_finite_maximum(self):
        self.run_case('predicted-nan-last', predicted=(.75, float('nan')), fail=True)

    def test_checker_twelve_nan_at_either_position_is_rejected(self):
        for index in (0, 1):
            with self.subTest(index=index):
                actual = [.75, .5]; actual[index] = float('nan')
                self.run_case('checker12-nan-' + str(index), actual=actual, score=(.75,.5), fail=True)

    def test_checker_six_nan_is_rejected_even_with_finite_reconciliation(self):
        for index in (0, 1):
            with self.subTest(index=index):
                score = [.75,.5]; score[index] = float('nan')
                self.run_case('checker6-nan-' + str(index), score=score, fail=True)

    def infinity_case(self, source):
        for sign in (1, -1):
            with self.subTest(source=source, sign=sign):
                args = {source: (.75, sign * float('inf')), 'fail': True}
                if source == 'actual': args['score'] = (.75,.5)
                self.run_case(source + '-infinity-' + str(sign), **args)

    def test_predicted_infinities_are_rejected(self):
        self.infinity_case('predicted')

    def test_checker_twelve_infinities_are_rejected(self):
        self.infinity_case('actual')

    def test_checker_six_infinities_are_rejected(self):
        self.infinity_case('score')

    def test_matching_infinities_do_not_make_a_valid_difference(self):
        self.run_case('matching-infinities', actual=(float('inf'),.5),
                      predicted=(float('inf'),.5), score=(.75,.5), fail=True)

    def test_exponent_overflow_tokens_are_rejected(self):
        for source in ('stats', '6', '12'):
            with self.subTest(source=source):
                raw = (stats if source=='stats' else checker)((float('inf'), .5)).replace('Infinity','1e999')
                key = 'raw_stats' if source == 'stats' else 'raw_' + source
                self.run_case('exponent-overflow-' + source, **{key: raw, 'fail': True})

    def test_finite_native_scientific_and_zero_values_are_preserved(self):
        vector = (9.933579335793359e-7, 1e-12, 0.0)
        row = self.run_case('finite-scientific', predicted=vector, actual=vector)
        self.assertEqual(row['mlu_6'], vector[0])
        self.assertEqual(row['max_load_error'], 0)
        self.assertEqual(row['load_count'], 3)

    def test_finite_integer_values_remain_supported(self):
        row = self.run_case('finite-integers', predicted=(2,1,0), actual=(2,1,0))
        self.assertEqual(row['mlu_6'], 2)
        self.assertEqual(row['max_load_error'], 0)

    def test_sub_tolerance_differences_remain_accepted(self):
        row = self.run_case('below-tolerance', predicted=(1e-9, .5), actual=(0., .5))
        self.assertEqual(row['max_load_error'], 1e-9)

    def test_original_tolerance_is_not_weakened(self):
        for delta in (2e-9, 3e-9):
            with self.subTest(delta=delta):
                self.run_case('tolerance-' + str(delta), predicted=(delta,.5), actual=(0.,.5), fail=True)

    def test_finite_subtraction_overflow_remains_a_failure(self):
        self.run_case('finite-difference-overflow', actual=(1e308,.5),
                      predicted=(-1e308,.5), score=(.75,.5), fail=True)


def main():
    global BENCHMARK, EVIDENCE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--benchmark', type=Path, default=BENCHMARK)
    ap.add_argument('--report', type=Path, required=True)
    ap.add_argument('--evidence', type=Path)
    ap.add_argument('--method', action='append', help='Run a named test method; repeat to form a bounded shard')
    args = ap.parse_args()
    BENCHMARK = args.benchmark.resolve()
    if args.evidence:
        EVIDENCE = args.evidence.resolve()
        EVIDENCE.mkdir(parents=True, exist_ok=False)
    methods = args.method or unittest.defaultTestLoader.getTestCaseNames(FiniteLoadTests)
    suite = unittest.TestSuite(FiniteLoadTests(name) for name in methods)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'schema':'roadef-benchmark-finite-loads-v1',
              'benchmark_sha256':fixtures.digest(BENCHMARK), 'test_sha256':fixtures.digest(__file__),
              'fixture_sha256':fixtures.digest(fixtures.__file__), 'python':sys.version,
              'methods':methods, 'tests_run':result.testsRun, 'failures':[[str(t),e] for t,e in result.failures],
              'errors':[[str(t),e] for t,e in result.errors], 'skipped':[[str(t),e] for t,e in result.skipped],
              'cases':DETAILS, 'official_solver_runs':0, 'official_checker_runs':0,
              'algorithm_comparisons':0, 'scope':'actual benchmark CLI; controlled executable protocols'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
