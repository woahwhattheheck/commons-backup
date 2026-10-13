# SPDX-License-Identifier: Apache-2.0
"""CLI source binding and sparse-clock joins, using existing offline inputs only.

Ordinary discovery runs parser/source checks. Native methods require the six
TITAN_PIN_* / KAG_ENGINE_DIR paths documented in PRODUCER-PIN.md; partial
configuration is an error. No provider call or full game is run.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CONSUMER = Path(os.environ.get('TITAN_PIN_CONSUMER', HERE / 'test_seed_adapter.py')).resolve()
OLD_BLOB = '78bd08b00a8b7fcf934dcf25c54ece51746a5f5e'
NEW_BLOB = '595c1c1692cb9dd63999b866bd9de3119fad41d0'
OLD_COMMIT = '36ec529659f038725ce325a19c2079a2a5b898b7'
NATIVE_ENV = ('KAG_ENGINE_DIR', 'TITAN_PIN_EVALUATOR', 'TITAN_PIN_LOADER',
              'TITAN_PIN_MECHANICS', 'TITAN_PIN_ORIGINAL', 'TITAN_PIN_CURRENT')
RECORDS = []


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def invoke(extra):
    return subprocess.run([sys.executable, '-B', str(CONSUMER), *map(str, extra)],
                          capture_output=True, text=True, timeout=30)


def retain(name, completed, report=None):
    row = {'name': name, 'returncode': completed.returncode,
           'stdout': completed.stdout, 'stderr': completed.stderr, 'report': report}
    RECORDS.append(row)


class PinBoundaryTests(unittest.TestCase):
    def probe(self, expected=None):
        # Only the producer is a synthetic import witness. All CLI and support
        # modules are the real consumer files. Rejected bytes must not execute.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); producer = root / 'producer.py'; marker = root / 'loaded'
            raw = (f'from pathlib import Path\nPath({str(marker)!r}).write_text("loaded")\n'
                   'raise RuntimeError("EXPLICIT_PRODUCER_IMPORT_WITNESS")\n').encode()
            producer.write_bytes(raw)
            args = ['--engine-cache', root / 'unused-engine', '--producer', producer,
                    '--report', root / 'result.json']
            if expected is not None:
                args += ['--producer-blob', blob(raw) if expected == 'actual' else expected]
            p = invoke(args)
            return p, marker.exists(), (root / 'result.json').exists()

    def test_help_exposes_explicit_expected_blob(self):
        p = invoke(['--help'])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('--producer-blob', p.stdout)
        self.assertIn('original compatibility source', p.stdout)

    def test_default_rejects_other_source_before_import(self):
        p, imported, report = self.probe()
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn('producer bytes do not match', p.stderr)
        self.assertFalse(imported)
        self.assertFalse(report)

    def test_explicit_pin_is_checked_not_merely_present(self):
        p, imported, report = self.probe(NEW_BLOB)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn('producer bytes do not match', p.stderr)
        self.assertFalse(imported)
        self.assertFalse(report)

    def test_partial_empty_or_malformed_pin_cannot_match(self):
        for expected in ('', '595c1c16', '0' * 40, 'not-a-blob'):
            with self.subTest(expected=expected):
                p, imported, report = self.probe(expected)
                self.assertEqual(p.returncode, 2)
                self.assertIn('producer bytes do not match', p.stderr)
                self.assertFalse(imported)
                self.assertFalse(report)

    def test_matching_explicit_bytes_reach_actual_import(self):
        p, imported, report = self.probe('actual')
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn('EXPLICIT_PRODUCER_IMPORT_WITNESS', p.stderr)
        self.assertTrue(imported)
        self.assertFalse(report)


class NativePinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        values = [os.environ.get(k) for k in NATIVE_ENV]
        if not any(values):
            raise unittest.SkipTest('Native source/engine paths not configured')
        if not all(values):
            raise ValueError('All six native paths in PRODUCER-PIN.md are required')
        cls.cache, cls.evaluator, cls.loader, cls.mechanics, cls.original, cls.current = map(Path, values)
        for path, expected in ((cls.original, OLD_BLOB), (cls.current, NEW_BLOB)):
            if blob(path.read_bytes()) != expected:
                raise ValueError(f'Wrong requested producer snapshot: {path.name}')
        cls.common = ['--engine-cache', cls.cache, '--evaluator', cls.evaluator,
                      '--engine-loader', cls.loader, '--mechanics', cls.mechanics]

    def check_native(self, name, producer, expected, use_option):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'result.json'
            args = [*self.common, '--producer', producer, '--report', output]
            if use_option:
                args += ['--producer-blob', expected]
            p = invoke(args)
            report = json.loads(output.read_text()) if output.exists() else None
            retain(name, p, report)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(report['tests_run'], 7)
            self.assertEqual((report['failures'], report['errors'], report['skipped']), (0, 0, 0))
            self.assertEqual(report['producer_git_blob'], expected)
            return report

    def test_original_default_remains_usable_and_source_labeled(self):
        result = self.check_native('original-default', self.original, OLD_BLOB, False)
        self.assertEqual(result['producer_commit'], OLD_COMMIT)

    def test_explicit_new_source_is_not_labeled_original_commit(self):
        result = self.check_native('current-explicit', self.current, NEW_BLOB, True)
        self.assertIsNone(result['producer_commit'])

    def test_new_source_without_option_does_not_relabel_old_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'result.json'
            p = invoke([*self.common, '--producer', self.current, '--report', output])
            retain('current-default-negative', p)
            self.assertEqual(p.returncode, 2)
            self.assertIn('producer bytes do not match', p.stderr)
            self.assertFalse(output.exists())

    def test_sparse_clock_joins_preserve_both_cash_cases(self):
        # This is a producer->guard integration on new input forms, not another
        # execution of the original 22-method independent guard suite.
        old_path = sys.path[:]
        before = dict(sys.modules)
        try:
            sys.path.insert(0, str(HERE))
            spec = importlib.util.spec_from_file_location('pin_join_support', HERE / 'test_guard.py')
            support = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = support
            spec.loader.exec_module(support)
            ev = support.load(self.evaluator, 'pin_join_evaluator')
            support.ENGINE, hashes = ev.get_engine(self.cache, prepare=False, loader=self.loader)
            support.MECHANICS = support.load(self.mechanics, 'pin_join_mechanics')
            producer = support.load(self.current, 'pin_join_current_producer')
            rows = []
            for position in (0, 1):
                for form in ('missing', 'null'):
                    for cash in (233, 1000):
                        with self.subTest(position=position, form=form, cash=cash):
                            obs, cfg, post = support.fixture(position, cash=cash, hires=12)
                            obs.update(day=29, hour=22)
                            if form == 'missing':
                                obs.pop('step')
                            else:
                                obs['step'] = None
                            selected, _ = support.actions([['HIRE']])
                            before_case = deepcopy((obs, cfg, post, selected))
                            contract = producer.compile_demand(
                                obs, cfg, selected, post_unit_seeds=post['private']['seeds'],
                                continuations={'selected': []}, complete=True)
                            packet = producer.transform(obs, cfg, selected,
                                post_unit_seeds=post['private']['seeds'], contract=contract)
                            self.assertEqual(packet['action']['market'][0], [])
                            guard = support.SeedExecutionGuard(support.MECHANICS)
                            action = guard.transform(obs, cfg, selected, packet['action'],
                                post_units=post, scenarios=[support.scenario()])
                            outcome = guard.last_report
                            if cash == 233:
                                self.assertEqual(action, selected)
                                self.assertEqual(outcome['status'], 'fallback_changed_execution')
                                self.assertEqual(outcome['scenarios'][0]['cash_delta'], -143)
                            else:
                                self.assertEqual(action, packet['action'])
                                self.assertEqual(outcome['status'], 'preserved_on_supplied_scenarios')
                                self.assertEqual(outcome['scenarios'][0]['cash_delta'], 90)
                            self.assertEqual((obs, cfg, post, selected), before_case)
                            rows.append({'position': position, 'clock': form, 'cash': cash,
                                         'report': outcome})
            RECORDS.append({'name': 'sparse-clock-joins', 'cases': rows, 'engine_hashes': hashes})
        finally:
            sys.path[:] = old_path
            # Restore only module names involved in this isolated native import.
            names = ['pin_join_support', 'pin_join_evaluator', 'pin_join_mechanics',
                     'pin_join_current_producer', 'guard', 'market_kernel',
                     'kaggle_environments', 'kaggle_environments.utils', 'official_kaggriculture']
            for name in names:
                if name in before:
                    sys.modules[name] = before[name]
                else:
                    sys.modules.pop(name, None)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    output = os.environ.get('TITAN_PIN_REPORT')
    if output:
        body = {'methods': result.testsRun, 'failures': len(result.failures),
                'errors': len(result.errors), 'skips': len(result.skipped),
                'consumer_git_blob': blob(CONSUMER.read_bytes()), 'records': RECORDS,
                'full_games': 0, 'scope': 'CLI pin handling and new-source consumer joins'}
        Path(output).write_text(json.dumps(body, sort_keys=True, indent=2) + '\n')
    raise SystemExit(not result.wasSuccessful())
