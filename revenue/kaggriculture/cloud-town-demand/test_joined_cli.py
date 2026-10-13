"""Source-bound AMBER CLI checks; reuse the retained input and joined report.

No controller, engine transition or new game is executed. Complete pricing is
run once through the changed reader; other integration calls stop on budgets.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import joined_case as target

SETTINGS = None
EVIDENCE = {}


def load_pristine(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


class JoinedCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = SETTINGS.source_root / 'cloud-capital-bundles/reached_quote_case.py'
        cls.reader_module = load_pristine(cls.reader, '_amber_cli_reference_reader')
        cls.deps = cls.reader_module.load_dependencies(SETTINGS.source_root)
        cls.row = json.loads(SETTINGS.input.read_text())
        cls.paths = json.loads(SETTINGS.paths.read_text())
        m = cls.deps.mechanics
        cls.mechanics = SimpleNamespace(SHOPS=m.SHOPS, PRODUCTS=m.PRODUCTS,
                                       TOWN_CENTER_PRODUCTS=m.TOWN_CENTER_PRODUCTS,
                                       MAX_SHOP_INSTANCES=8)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='town-cli-')
        self.addCleanup(self.directory.cleanup)
        self.out = Path(self.directory.name) / 'result.json'
        prior = sys.modules.get('_amber_reached')
        def restore():
            if prior is None:
                sys.modules.pop('_amber_reached', None)
            else:
                sys.modules['_amber_reached'] = prior
        self.addCleanup(restore)

    def cli(self, *extra, source_root=None):
        args = [sys.executable, '-B', str(SETTINGS.runtime), '--input', str(SETTINGS.input),
                '--paths', str(SETTINGS.paths), '--source-root', str(source_root or SETTINGS.source_root),
                '--engine', str(SETTINGS.engine), '--output', str(self.out), *extra]
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        return result

    def test_current_reader_adopted_and_metadata_retained(self):
        module, blob = target.load_consumer(self.reader)
        self.assertEqual(blob, 'f5f64be61dd6277e8436d930286498486ff4f2de')
        self.assertEqual(module.__file__, str(self.reader))
        self.assertIsNotNone(module.__spec__)
        self.assertEqual(module.DEPENDENCIES, self.reader_module.DEPENDENCIES)

    def test_historical_reader_still_accepted(self):
        for root, expected in [(SETTINGS.prior_root, '794b56813daf89e06b76aaa8cbb291498e15c73c')]:
            module, blob = target.load_consumer(root / 'cloud-capital-bundles/reached_quote_case.py')
            self.assertEqual(blob, expected)
            self.assertTrue(callable(module.compare_saved_input))

    def test_captured_reader_body_does_not_ask_bytecode_loader(self):
        with patch.object(importlib.machinery.SourceFileLoader, 'exec_module',
                          side_effect=AssertionError('Unexpected cached body route')):
            module, _ = target.load_consumer(self.reader)
        self.assertTrue(callable(module.load_dependencies))

    def test_unknown_source_preserves_existing_alias(self):
        modified = Path(self.directory.name) / 'reader.py'
        modified.write_bytes(self.reader.read_bytes() + b'\n')
        sentinel = object()
        sys.modules['_amber_reached'] = sentinel
        with self.assertRaises(ValueError):
            target.load_consumer(modified)
        self.assertIs(sys.modules['_amber_reached'], sentinel)

    def test_failed_body_restores_existing_alias(self):
        sentinel = object()
        sys.modules['_amber_reached'] = sentinel
        with patch.object(target, 'exec', create=True, side_effect=RuntimeError('body')):
            with self.assertRaisesRegex(RuntimeError, 'body'):
                target.load_consumer(self.reader)
        self.assertIs(sys.modules['_amber_reached'], sentinel)

    def test_cancelled_body_removes_new_alias(self):
        sys.modules.pop('_amber_reached', None)
        with patch.object(target, 'exec', create=True, side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                target.load_consumer(self.reader)
        self.assertNotIn('_amber_reached', sys.modules)

    def test_actual_fresh_cli_equals_retained_complete_report(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertTrue(status['complete'])
        self.assertEqual(status['reason'], 'complete_conditional_flow')
        actual = json.loads(self.out.read_text())
        previous = json.loads(SETTINGS.reference.read_text())
        blob = actual.pop('joined_consumer_git_blob')
        previous.pop('joined_consumer_git_blob')
        actual.pop('elapsed_quote_flow_rank_seconds')
        previous.pop('elapsed_quote_flow_rank_seconds')
        self.assertEqual(actual, previous)
        EVIDENCE['complete'] = {
            'reader_git_blob': blob, 'entire_result_equal_except_reader_and_time': True,
            'scenario_records': actual['result']['reconciled_route_scenarios'],
            'cash_rows': sum(len(r['cash_flow_rows']) for world in actual['result']['flow']['rows'] for r in world),
            'conditional_choice': status['conditional_choice'],
            'canonical_unchanged_report_sha256': hashlib.sha256(json.dumps(actual, sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode()).hexdigest()}

    def incomplete(self, *flags):
        result = self.cli(*flags)
        self.assertEqual(result.returncode, 3, (result.stdout, result.stderr))
        status = json.loads(result.stdout)
        report = json.loads(self.out.read_text())
        self.assertFalse(status['complete'])
        self.assertIsNone(status['conditional_choice'])
        self.assertEqual(status['reason'], 'incomplete_budget')
        self.assertIsNone(report['result']['ranking'])
        self.assertEqual(report['result']['flow']['rows'], [])
        self.assertEqual(report['result']['individual_rankings'], [])
        self.assertNotIn('Traceback', result.stderr)
        return status

    def test_zero_clock_returns_preserved_incomplete_report(self):
        EVIDENCE['zero_clock'] = self.incomplete('--seconds', '0')

    def test_unit_exhaustion_returns_preserved_incomplete_report(self):
        EVIDENCE['unit_limit'] = self.incomplete('--max-units', '1')

    def test_existing_output_is_not_overwritten(self):
        self.out.write_bytes(b'original receipt\n')
        result = self.cli('--seconds', '0')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.out.read_bytes(), b'original receipt\n')
        self.assertNotIn('Traceback', result.stderr)

    def test_output_parent_is_created(self):
        self.out = self.out.parent / 'new' / 'nested' / 'result.json'
        self.incomplete('--seconds', '0')

    def test_invalid_scenario_remains_input_error_not_partial_ranking(self):
        bad = Path(self.directory.name) / 'bad.json'
        bad.write_text('[{"name":"bad", "future_shops": []}]')
        result = self.cli('--paths', str(bad))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.out.exists())
        self.assertNotIn('Traceback', result.stderr)

    def test_invalid_flow_keeps_reason_without_missing_ranking_error(self):
        repeated = Path(self.directory.name) / 'repeated.json'
        repeated.write_text(json.dumps([self.paths[0], self.paths[0]]))
        result = self.cli('--paths', str(repeated), source_root=SETTINGS.prior_root)
        self.assertEqual(result.returncode, 3, result.stderr)
        status = json.loads(result.stdout)
        report = json.loads(self.out.read_text())
        self.assertEqual(status['reason'], 'invalid_flow')
        self.assertIsNone(status['conditional_choice'])
        self.assertEqual(report['result']['flow']['rows'], [])
        self.assertNotIn('Traceback', result.stderr)
        EVIDENCE['invalid_flow'] = status

    def test_budget_options_forward_once_without_prices_or_input_edits(self):
        calls = []
        def consumer(row, specifications, dependencies, **kwargs):
            calls.append(kwargs)
            return {'complete': False, 'ranking': None, 'flow': {'reason': 'incomplete_budget'}}
        before = copy.deepcopy((self.row, self.paths))
        report = target.run(self.row, self.paths, self.deps, self.mechanics, consumer,
                            max_units=7, seconds=.1)
        self.assertEqual(calls, [{'max_units': 7, 'seconds': .1, 'retain_trace': True}])
        self.assertEqual((self.row, self.paths), before)
        self.assertFalse(report['result']['complete'])

    def test_original_run_defaults_are_preserved(self):
        calls = []
        def consumer(*args, **kwargs):
            calls.append(kwargs)
            return {'complete': False}
        target.run(self.row, self.paths, self.deps, self.mechanics, consumer)
        self.assertEqual(calls, [{'max_units': 200_000, 'seconds': None, 'retain_trace': True}])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('source-root', 'prior-root', 'input', 'paths', 'reference', 'engine', 'report'):
        parser.add_argument('--' + arg, type=Path, required=True)
    parser.add_argument('--runtime', type=Path, default=Path(__file__).with_name('joined_case.py'))
    global SETTINGS, target
    SETTINGS = parser.parse_args()
    if SETTINGS.runtime.resolve() != Path(target.__file__).resolve():
        target = load_pristine(SETTINGS.runtime, '_amber_cli_subject')
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(JoinedCliTests))
    report = {'methods': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'passed': result.wasSuccessful(),
        'runtime_sha256': hashlib.sha256(SETTINGS.runtime.read_bytes()).hexdigest(),
        'input_sha256': hashlib.sha256(SETTINGS.input.read_bytes()).hexdigest(),
        'reference_sha256': hashlib.sha256(SETTINGS.reference.read_bytes()).hexdigest(),
        'evidence': EVIDENCE, 'new_engine_transitions': 0, 'actor_calls': 0, 'new_games': 0}
    SETTINGS.report.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__ == '__main__':
    main()
