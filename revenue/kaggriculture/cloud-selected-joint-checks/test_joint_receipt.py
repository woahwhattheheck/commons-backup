# SPDX-License-Identifier: Apache-2.0
"""Reader regression fixtures are synthetic evidence, not simulated game outcomes."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

from check_joint_receipt import ENGINE_FILES, LAB, MARKET, PROJECTION, RUNTIME_FILES, SUITES, inspect_archive


def synthetic_members():
    files = {}
    paths = [LAB + name for name in RUNTIME_FILES]
    paths += [LAB + 'reference/engine/' + name for name in ENGINE_FILES]
    paths += [PROJECTION + 'projection.py'] + [row[3] for row in SUITES.values()]
    for name in paths:
        files[name] = {'sha256': hashlib.sha256(name.encode()).hexdigest()}
    snapshot = dict(checkout='a'*40, run_id='123', attempt='1', files=files)
    engines = {name: files[LAB+'reference/engine/'+name]['sha256'] for name in ENGINE_FILES}
    projection = dict(tests_run=21, failures=0, errors=0, differential_cases=144,
                      interpreter_transitions=378, engine_sha256=engines,
                      seller_sha256=files[LAB+'selected_action_sell.py']['sha256'],
                      projection_sha256=files[PROJECTION+'projection.py']['sha256'])
    market = dict(schema='titan.selected-market-checks.v1', test_methods=14,
                  failures=0, errors=0, successful=True, official_market_cases=28,
                  engine_sha256=engines, game_panels=0, seeds_consumed=[],
                  sources={name: files[LAB+name]['sha256'] for name in RUNTIME_FILES})
    return {'SOURCE-SNAPSHOT.json': snapshot, 'projection-results.json': projection,
            'market-results.json': market,
            **{row[0]: f'Ran {row[2]} tests in 0.1s\n\nOK\n' for row in SUITES.values()}}


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'evidence.zip'
        self.members = synthetic_members()

    def write(self, members=None):
        with zipfile.ZipFile(self.path, 'w') as archive:
            for name, value in (self.members if members is None else members).items():
                archive.writestr(name, json.dumps(value) if isinstance(value, dict) else value)
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def inspect(self, **kwargs):
        digest = self.write()
        kwargs.setdefault('expected_sha256', digest)
        return inspect_archive(self.path, **kwargs)

    def test_complete_synthetic_schema_is_aligned(self):
        out = self.inspect(expected_checkout='a'*40, expected_run_id='123', expected_attempt='1')
        self.assertEqual(out['status'], 'COMPLETE_PASS')
        self.assertEqual(out['reported_test_methods'], 51)
        self.assertEqual(out['tests_rerun'], 0)
        self.assertEqual(out['problems'], [])

    def test_missing_market_preserves_37_method_partial(self):
        del self.members['market-results.json'], self.members['market-tests.log']
        del self.members['SOURCE-SNAPSHOT.json']['files'][MARKET+'check_market_contracts.py']
        out = self.inspect()
        self.assertEqual(out['status'], 'INCOMPLETE')
        self.assertEqual(out['reported_test_methods'], 37)
        self.assertEqual(len(out['problems']), 3)

    def test_digest_mismatch_is_failure(self):
        self.assertEqual(self.inspect(expected_sha256='0'*64)['status'], 'FAIL')

    def test_no_provider_digest_is_not_complete(self):
        self.assertEqual(self.inspect(expected_sha256=None)['status'], 'INCOMPLETE')

    def test_source_difference_is_failure(self):
        self.members['market-results.json']['sources']['selected_action_sell.py'] = '0'*64
        self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_engine_difference_is_failure(self):
        # Detach shared synthetic map before changing only one report.
        self.members['market-results.json'] = copy.deepcopy(self.members['market-results.json'])
        self.members['market-results.json']['engine_sha256']['utils.py'] = '0'*64
        self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_report_log_count_disagreement_is_failure(self):
        self.members['market-results.json']['test_methods'] = 15
        self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_false_success_cannot_hide_failures(self):
        self.members['market-results.json']['failures'] = 1
        self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_failed_footer_without_count_is_failure(self):
        self.members['market-tests.log'] = 'FAILED (errors=1)\n'
        self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_skipped_completion_is_incomplete(self):
        self.members['market-tests.log'] = 'Ran 14 tests in 0.1s\n\nOK (skipped=1)\n'
        self.assertEqual(self.inspect()['status'], 'INCOMPLETE')

    def test_truncated_log_is_incomplete(self):
        self.members['market-tests.log'] = 'test_something ... '
        self.assertEqual(self.inspect()['status'], 'INCOMPLETE')

    def test_boolean_is_not_method_count(self):
        self.members['projection-results.json']['tests_run'] = True
        self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_wrong_checkout_run_attempt_each_fail(self):
        for kw in ({'expected_checkout':'b'*40}, {'expected_run_id':'124'}, {'expected_attempt':'2'}):
            with self.subTest(**kw):
                self.assertEqual(self.inspect(**kw)['status'], 'FAIL')

    def test_missing_runtime_source_is_incomplete(self):
        del self.members['SOURCE-SNAPSHOT.json']['files'][LAB+'mechanics.py']
        self.assertEqual(self.inspect()['status'], 'INCOMPLETE')

    def test_zero_or_insufficient_methods_fail(self):
        for n in (0, 13):
            with self.subTest(n=n):
                self.members['market-tests.log'] = f'Ran {n} tests in 0.1s\n\nOK\n'
                self.members['market-results.json']['test_methods'] = n
                self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_malformed_and_duplicate_json_keys_fail(self):
        for text in ('{broken', '{"checkout":"a", "checkout":"b"}'):
            with self.subTest(text=text):
                self.members['SOURCE-SNAPSHOT.json'] = text
                self.assertEqual(self.inspect()['status'], 'FAIL')

    def test_duplicate_zip_members_are_rejected(self):
        self.write()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(self.path, 'a') as archive:
                archive.writestr('SOURCE-SNAPSHOT.json', '{}')
        self.assertEqual(inspect_archive(self.path)['status'], 'FAIL')

    def test_prefixed_zip_and_custom_market_names(self):
        renamed = dict(self.members)
        renamed['market-consumer.log'] = renamed.pop('market-tests.log')
        renamed['market-consumer.json'] = renamed.pop('market-results.json')
        digest = self.write({'output/'+k:v for k,v in renamed.items()})
        out = inspect_archive(self.path, expected_sha256=digest, market_log='market-consumer.log',
                              market_report='market-consumer.json')
        self.assertEqual(out['status'], 'COMPLETE_PASS')

    def test_path_traversal_member_is_not_extracted(self):
        self.members['../unexpected.txt'] = 'data'
        self.assertEqual(self.inspect()['status'], 'FAIL')
        self.assertFalse((Path(self.tmp.name).parent/'unexpected.txt').exists())

    def test_cli_exit_and_json_output(self):
        digest = self.write()
        output = Path(self.tmp.name)/'out'/'receipt.json'
        command = [sys.executable, str(Path(__file__).with_name('check_joint_receipt.py')),
                   str(self.path), '--expected-sha256', digest, '--json-output', str(output)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(output.read_text())['status'], 'COMPLETE_PASS')
        self.members.pop('market-results.json')
        digest = self.write()
        command[4] = digest
        run = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 2, run.stderr)


if __name__ == '__main__':
    unittest.main()
