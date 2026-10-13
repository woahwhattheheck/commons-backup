#!/usr/bin/env python3
"""Malformed report recovery in the actual comparator and portfolio supervisor.

The subprocess checkers inject protocol faults; they do not validate routes or
establish benchmark quality. The original supervisor code is executed unchanged.
Set ROADEF_TEST_SOURCE to compare another directory containing both source files.
Set ROADEF_TEST_EVIDENCE to retain each CLI run's logs, bytes and receipt.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal

SOURCE = Path(os.environ.get('ROADEF_TEST_SOURCE', Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location('checked_report_boundary', SOURCE / 'compare_checker.py')
SUBJECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUBJECT)


def report(sat=3, **extra):
    return dict(valid=True, saturations=[dict(t=0, **{'from': 1, 'to': 2}, sat=sat)], **extra)


class ReportParsing(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'checker.json'

    def read(self, doc):
        self.path.write_text(json.dumps(doc), encoding='utf-8')
        return SUBJECT.load_result(self.path)

    def test_non_object_documents_are_report_errors(self):
        for doc in (None, [], [1], True, False, 7, 1.25, 'text'):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                self.read(doc)

    def test_malformed_decimal_strings_are_report_errors(self):
        for sat in ('bad', '', '1.2.3', '++1', 'not available'):
            with self.subTest(sat=sat), self.assertRaises(ValueError):
                self.read(report(sat))

    def test_decimal_overflow_is_a_report_error(self):
        with self.assertRaises(ValueError):
            self.read(report('1e999999999'))

    def test_json_decimal_construction_is_a_report_error(self):
        self.path.write_text('{"valid":true,"saturations":[{"t":0,"from":1,"to":2,'
                             '"sat":1e99999999999999999999}]}', encoding='utf-8')
        with self.assertRaises(ValueError):
            SUBJECT.load_result(self.path)

    def test_nonfinite_and_negative_remain_invalid(self):
        for sat in ('NaN', 'sNaN', 'Infinity', '-Infinity', -1, '-0.000001'):
            with self.subTest(sat=sat), self.assertRaises(ValueError):
                self.read(report(sat))

    def test_seven_decimal_places_not_rounded(self):
        with self.assertRaises(ValueError):
            self.read(report('0.0000011'))
        self.assertEqual(self.read(report('0.000001'))['vector'], [Decimal('0.000001')])

    def test_missing_and_nonboolean_valid_remain_invalid(self):
        for doc in ({}, {'valid': 0}, {'valid': 1}, {'valid': 'true'}):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                self.read(doc)

    def test_valid_false_needs_no_vector(self):
        parsed = self.read({'valid': False, 'total_cost': 8})
        self.assertIs(parsed['valid'], False)
        self.assertNotIn('vector', parsed)

    def test_empty_or_missing_vector_remains_invalid(self):
        for doc in ({'valid': True}, {'valid': True, 'saturations': []}):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                self.read(doc)

    def test_duplicate_coordinates_remain_invalid(self):
        doc = report()
        doc['saturations'] *= 2
        with self.assertRaises(ValueError):
            self.read(doc)

    def test_exact_values_order_and_source_identity(self):
        doc = {'valid': True, 'total_cost': 9, 'saturations': [
            {'t': i, 'from': 1, 'to': 2, 'sat': x}
            for i, x in enumerate(('1.000001', 3, '0.1', '0.000001'))]}
        value = self.read(doc)
        self.assertEqual(value['vector'], list(map(Decimal, ('3', '1.000001', '0.1', '0.000001'))))
        self.assertEqual(value['sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(value['path'], str(self.path.resolve()))
        self.assertEqual(value['keys'], {(i, '1', '2') for i in range(4)})

    def test_generated_rankings_keep_exact_six_decimal_objective(self):
        rng = random.Random(830139)
        for _ in range(250):
            n = rng.randint(1, 16)
            a, b = ([rng.randrange(20_000_001) for _ in range(n)] for j in range(2))
            docs = [{'valid': True, 'total_cost': cost, 'saturations': [
                {'t': i, 'from': 1, 'to': 2, 'sat': f'{v//1000000}.{v%1000000:06d}'}
                for i, v in enumerate(vec)]} for vec, cost in ((a, 1000), (b, 0))]
            left, right = (self.read(doc) for doc in docs)
            aa, bb = sorted(a, reverse=True), sorted(b, reverse=True)
            expected = 'left' if aa < bb else 'right' if bb < aa else 'tie'
            got = SUBJECT.compare(left, right)
            self.assertEqual(got['winner'], expected)
            self.assertFalse(got['cost_used_in_ranking'])
            tied = SUBJECT.compare(left, dict(left, total_cost=-999))
            self.assertEqual(tied['winner'], 'tie')

    def test_different_coordinate_sets_still_cannot_be_ranked(self):
        left = self.read(report(1))
        right = dict(left, keys={(1, '1', '2')})
        with self.assertRaises(ValueError):
            SUBJECT.compare(left, right)


# These are executable protocol fixtures, not a substitute solver/checker.
SOLVER = '''import json,sys
from pathlib import Path
Path(sys.argv[-1]).write_text(json.dumps({"score":3,"srpaths":[]}))
'''
CHECKER = '''import json,os,sys
from pathlib import Path
p=Path(sys.argv[sys.argv.index('--srpaths')+1])
x=json.loads(p.read_text()); marker=p.with_suffix('.attempt-count')
n=int(marker.read_text())+1 if marker.exists() else 1; marker.write_text(str(n))
kind=os.environ['BOUNDARY_FAULT']; mode=os.environ['BOUNDARY_MODE']
lane='score' in x; inject=(mode=='all' or lane) and (mode!='once' or n==1)
if inject:
 if kind=='bad_sat': print(json.dumps({'valid':True,'saturations':[{'t':0,'from':1,'to':2,'sat':'bad'}]}))
 elif kind=='overflow': print(json.dumps({'valid':True,'saturations':[{'t':0,'from':1,'to':2,'sat':'1e999999999'}]}))
 elif kind=='huge_json': print('{"valid":true,"saturations":[{"t":0,"from":1,"to":2,"sat":1e99999999999999999999}]}')
 elif kind=='null': print('null')
 elif kind=='list': print('[]')
 elif kind=='invalid': print('{"valid":false}');sys.exit(2)
 elif kind=='crash': sys.exit(7)
 else: raise AssertionError(kind)
else:
 print(json.dumps({'valid':True,'total_cost':0,'saturations':[{'t':0,'from':1,'to':2,'sat':x.get('score',10)}]}))
'''


@unittest.skipUnless(os.name == 'posix', 'executable protocol fixtures use POSIX shebangs')
class SupervisorRecovery(unittest.TestCase):
    def run_case(self, kind, mode):
        with tempfile.TemporaryDirectory(prefix='roadef-checker-boundary-') as tmp:
            root = Path(tmp)
            for name in ('supervisor.py', 'compare_checker.py'):
                shutil.copy2(SOURCE / name, root / name)
            for name, code in (('solver', SOLVER), ('checker', CHECKER)):
                path = root / name
                path.write_text('#!' + sys.executable + '\n' + code, encoding='utf-8')
                path.chmod(0o755)
            inputs = [root / n for n in ('net.json', 'tm.json', 'scenario.json')]
            for path in inputs:
                path.write_text('{}', encoding='utf-8')
            out = root / 'selected output.json'
            env = dict(os.environ, PORTFOLIO_SECONDS='4', PORTFOLIO_CHECK_INTERVAL='0.05',
                       PORTFOLIO_CHECK_TIMEOUT='1', PORTFOLIO_ARTIFACTS=str(root),
                       PORTFOLIO_RECEIPT=str(root / 'receipt.json'), BOUNDARY_FAULT=kind, BOUNDARY_MODE=mode,
                       PORTFOLIO_CHECKER=str(root / 'checker'))
            for lane in ('SEDGE', 'FLORA', 'CANDIDATE'):
                env['PORTFOLIO_' + lane] = str(root / 'solver')
            result = subprocess.run([sys.executable, '-B', str(root / 'supervisor.py'),
                                     *map(str, inputs), str(out)], env=env, cwd=root,
                                    capture_output=True, text=True, timeout=9)
            receipt = json.loads((root / 'receipt.json').read_text())
            packet = {'kind':kind, 'mode':mode, 'returncode':result.returncode,
                      'stdout':result.stdout, 'stderr':result.stderr,
                      'output':json.loads(out.read_text()), 'receipt':receipt,
                      'source_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest()
                                       for n in ('supervisor.py','compare_checker.py')}}
            evidence = os.environ.get('ROADEF_TEST_EVIDENCE')
            if evidence:
                target = Path(evidence) / (self._testMethodName + '-' + kind)
                shutil.copytree(root, target, ignore=shutil.ignore_patterns('__pycache__'))
                (target/'result.json').write_text(json.dumps(packet, indent=2)+'\n')
            return packet

    def test_transient_malformed_reports_retry_then_select_same_bytes(self):
        for kind in ('bad_sat','null','list','overflow','huge_json'):
            with self.subTest(kind=kind):
                got = self.run_case(kind, 'once')
                self.assertEqual(got['returncode'], 0, got['stderr'])
                self.assertEqual(got['output']['score'], 3)
                events = got['receipt']['events']
                retries = [e for e in events if e['event']=='check_retry_queued']
                self.assertEqual(len(retries), 1)
                completed = [e for e in events if e['event']=='check_completed']
                self.assertIn(retries[0]['solution_sha256'], [e['solution_sha256'] for e in completed])
                self.assertTrue(got['receipt']['validated'])
                self.assertEqual(got['receipt']['status'], 'complete')

    def test_permanent_malformed_reports_preserve_validated_incumbent(self):
        for kind in ('bad_sat','list'):
            with self.subTest(kind=kind):
                got = self.run_case(kind, 'always')
                self.assertEqual(got['returncode'], 0, got['stderr'])
                self.assertEqual(got['output'], {'srpaths': []})
                events = got['receipt']['events']
                self.assertEqual(sum(e['event']=='check_retry_queued' for e in events), 1)
                self.assertEqual(sum(e['event']=='check_retries_exhausted' for e in events), 1)
                self.assertEqual(got['receipt']['selected_lane'], 'zero_change_baseline')
                self.assertEqual(got['receipt']['maximum_load'], '10')

    def test_no_valid_report_remains_explicit_failure(self):
        got = self.run_case('null', 'all')
        self.assertEqual(got['returncode'], 1, got['stderr'])
        self.assertFalse(got['receipt']['validated'])
        self.assertEqual(got['receipt']['status'], 'no_validated_solution')
        self.assertNotIn('Traceback', got['stderr'])
        self.assertEqual(sum(e['event']=='check_retries_exhausted' for e in got['receipt']['events']), 2)

    def test_infeasible_is_conclusive_not_retried(self):
        got = self.run_case('invalid', 'always')
        self.assertEqual(got['returncode'], 0, got['stderr'])
        self.assertEqual(got['output'], {'srpaths': []})
        self.assertEqual(sum(e['event']=='check_retry_queued' for e in got['receipt']['events']), 0)
        self.assertEqual(sum(e['event']=='candidate_invalid' for e in got['receipt']['events']), 1)

    def test_checker_crash_retry_is_unchanged(self):
        got = self.run_case('crash', 'once')
        self.assertEqual(got['returncode'], 0, got['stderr'])
        self.assertEqual(got['output']['score'], 3)
        self.assertEqual(sum(e['event']=='check_retry_queued' for e in got['receipt']['events']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
