# SPDX-License-Identifier: Apache-2.0
"""Exercise the existing receipt reader with a retained artifact and detached faults.

The archive is evidence only: no archived Python, tests, or games are executed.
Run explicitly with --archive; --reader selects the actual implementation to test.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ARTIFACT_SHA256 = 'af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29'
ARTIFACT_ID = 10036877991
CHECKOUT = '0144d5c6e2d71ac80cb62abd8d7ca0223bb75f27'
RUN_ID = '34174806533'
FUNDED_REPORT = 'funded-join-results.json'
INTEGRATION_PATH = 'cloud-execution-lab/integrated_selected.py'
TEST_PATH = 'cloud-composition-cases/cypress/test_funded_join.py'
ROOT = 'revenue/kaggriculture/'
EXTRA_LOGS = ('loader-tests.log', 'empty-lot-tests.log',
              'joined-wrapper-tests.log', 'funded-join-tests.log')
ARCHIVE: Path | None = None
READER_PATH: Path | None = None
CASES: list[dict] = []


def load_reader(path: Path):
    """Import a caller-selected local source file, never an archive member."""
    sys.path.insert(0, str(path.resolve().parent))
    spec = importlib.util.spec_from_file_location('receipt_under_test', path)
    if spec is None or spec.loader is None:
        raise ValueError(f'cannot load reader: {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, 'inspect_archive', None)):
        raise ValueError('selected reader does not expose inspect_archive')
    return module


def revise_json(members: dict[str, bytes], name: str, change) -> None:
    value = json.loads(members[name])
    change(value)
    members[name] = json.dumps(value, sort_keys=True).encode('utf-8')


class ArchiveFaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ARCHIVE is None or READER_PATH is None:
            raise unittest.SkipTest('Run this evidence consumer with --archive and --reader.')
        if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != ARTIFACT_SHA256:
            raise ValueError('expected the unchanged artifact10036877991, not a replacement ZIP')
        with zipfile.ZipFile(ARCHIVE) as archive:
            cls.original_members = {item.filename: archive.read(item)
                                    for item in archive.infolist() if not item.is_dir()}
        cls.reader = load_reader(READER_PATH)
        cls.control_receipt = cls.reader.inspect_archive(
            ARCHIVE, expected_sha256=ARTIFACT_SHA256, expected_checkout=CHECKOUT,
            expected_run_id=RUN_ID, expected_attempt='1')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def inspect(self, suffix: str = '', change=None):
        if change is None:
            path = ARCHIVE
            digest = ARTIFACT_SHA256
        else:
            members = copy.deepcopy(self.original_members)
            change(members)
            path = Path(self.tmp.name) / 'detached-evidence.zip'
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, body in members.items():
                    archive.writestr(name, body)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out = self.reader.inspect_archive(path, expected_sha256=digest,
                                         expected_checkout=CHECKOUT,
                                         expected_run_id=RUN_ID, expected_attempt='1')
        CASES.append({'case': self.id().split('.')[-1] + suffix,
                      'detached_mutation': change is not None,
                      'input_sha256': digest, 'output': out})
        return out

    def assert_not_complete(self, out):
        self.assertIn(out['status'], ('FAIL', 'INCOMPLETE'), out)
        self.assertTrue(out.get('problems'), out)
        original = {json.dumps(p, sort_keys=True) for p in self.control_receipt.get('problems', [])}
        changed = {json.dumps(p, sort_keys=True) for p in out.get('problems', [])}
        self.assertTrue(changed - original, 'An unrelated baseline issue cannot satisfy a fault case.')
        # A newly calculated digest is supplied for detached fixtures, so a
        # structural failure cannot be explained by the original provider hash.
        self.assertTrue(out['provider_digest_matched'])
        self.assertFalse(any('artifact SHA-256 differs' in str(p)
                             for p in out.get('problems', [])))

    def test_real_seven_suite_artifact_counts_95(self):
        out = self.inspect()
        self.assertEqual(out['reported_test_methods'], 95, out)
        self.assertEqual(sum(row.get('test_methods') or 0
                             for row in out['suites'].values()), 95)

    def test_reading_evidence_does_not_execute_tests_or_games(self):
        out = self.inspect()
        self.assertEqual(out['tests_rerun'], 0)
        self.assertEqual(out['game_panels'], 0)
        self.assertEqual(out['seeds_consumed'], [])

    def test_failed_additional_logs_cannot_be_ignored(self):
        for log in EXTRA_LOGS:
            with self.subTest(log=log):
                def change(m, log=log):
                    m[log] = m[log].replace(b'\nOK\n', b'\nFAILED (failures=1)\n')
                    self.assertIn(b'FAILED', m[log])
                self.assert_not_complete(self.inspect(':' + log, change))

    def test_truncated_additional_logs_remain_incomplete(self):
        for log in EXTRA_LOGS:
            with self.subTest(log=log):
                self.assert_not_complete(self.inspect(':' + log,
                    lambda m, log=log: m.__setitem__(log, b'test_started ... ')))

    def test_present_log_with_missing_loader_report_is_incomplete(self):
        self.assert_not_complete(self.inspect(change=lambda m: m.pop('loader-results.json')))

    def test_present_log_with_missing_funded_report_is_incomplete(self):
        self.assert_not_complete(self.inspect(change=lambda m: m.pop(FUNDED_REPORT)))

    def test_present_loader_report_with_missing_log_is_incomplete(self):
        self.assert_not_complete(self.inspect(change=lambda m: m.pop('loader-tests.log')))

    def test_present_funded_report_with_missing_log_is_incomplete(self):
        self.assert_not_complete(self.inspect(change=lambda m: m.pop('funded-join-tests.log')))

    def funded(self, change):
        return self.inspect(change=lambda m: revise_json(m, FUNDED_REPORT, change))

    def test_funded_report_failure_is_not_pass(self):
        self.assert_not_complete(self.funded(lambda d: d.update(failures=1)))

    def test_funded_report_error_is_not_pass(self):
        self.assert_not_complete(self.funded(lambda d: d.update(errors=1)))

    def test_funded_false_success_is_not_pass(self):
        self.assert_not_complete(self.funded(lambda d: d.update(successful=False)))

    def test_funded_count_disagreement_is_not_pass(self):
        self.assert_not_complete(self.funded(lambda d: d.update(test_methods=15)))

    def test_funded_boolean_count_is_not_integer_coverage(self):
        self.assert_not_complete(self.funded(lambda d: d.update(test_methods=True)))

    def test_funded_runtime_hash_must_match_snapshot(self):
        def change(d):
            d['sources'][INTEGRATION_PATH]['sha256'] = '0' * 64
        self.assert_not_complete(self.funded(change))

    def test_funded_test_hash_must_match_snapshot(self):
        def change(d):
            d['sources'][TEST_PATH]['sha256'] = '0' * 64
        self.assert_not_complete(self.funded(change))

    def test_funded_missing_runtime_identity_is_incomplete(self):
        def change(d):
            del d['sources'][INTEGRATION_PATH]
        self.assert_not_complete(self.funded(change))

    def test_funded_snapshot_must_contain_reported_source(self):
        def change(m):
            revise_json(m, 'SOURCE-SNAPSHOT.json',
                        lambda d: d['files'].pop(ROOT + INTEGRATION_PATH))
        self.assert_not_complete(self.inspect(change=change))

    def test_funded_wrong_workflow_run_is_not_pass(self):
        self.assert_not_complete(self.funded(lambda d: d.update(workflow_run='34174806534')))

    def test_funded_wrong_workflow_attempt_is_not_pass(self):
        self.assert_not_complete(self.funded(lambda d: d.update(workflow_attempt='2')))

    def test_funded_nonzero_full_games_is_not_component_scope(self):
        self.assert_not_complete(self.funded(lambda d: d.update(full_games=1)))

    def test_funded_nonzero_new_seeds_is_not_component_scope(self):
        self.assert_not_complete(self.funded(lambda d: d.update(new_game_seeds=1)))

    def test_missing_funded_engine_source_is_incomplete(self):
        def change(d):
            del d['sources']['cloud-execution-lab/reference/engine/kaggriculture.py']
        self.assert_not_complete(self.funded(change))

    def test_unrecognized_test_log_is_explicitly_unexamined(self):
        def change(m):
            m['not-yet-integrated-tests.log'] = b'Ran 3 tests in 0.1s\n\nFAILED (errors=1)\n'
        out = self.inspect(change=change)
        self.assert_not_complete(out)
        self.assertIn('not-yet-integrated-tests.log', json.dumps(out))

    def test_unexecuted_source_file_does_not_add_test_count(self):
        def change(m):
            revise_json(m, 'SOURCE-SNAPSHOT.json', lambda d: d['files'].update({
                ROOT + 'unused-research/test_not_executed.py': {
                    'size': 7, 'sha256': hashlib.sha256(b'unused\n').hexdigest()}}))
        out = self.inspect(change=change)
        self.assertEqual(out['reported_test_methods'], 95)
        self.assertEqual(out['reported_test_methods'], self.inspect(':control')['reported_test_methods'])

    def test_funded_qualified_completion_is_not_full_coverage(self):
        def change(m):
            m['funded-join-tests.log'] = m['funded-join-tests.log'].replace(
                b'\nOK\n', b'\nOK (skipped=1)\n')
        self.assert_not_complete(self.inspect(change=change))

    def test_funded_duplicate_completion_is_ambiguous(self):
        def change(m):
            m['funded-join-tests.log'] += b'Ran 16 tests in 0.1s\n\nOK\n'
        self.assert_not_complete(self.inspect(change=change))


def main() -> int:
    global ARCHIVE, READER_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--reader', type=Path,
                        default=Path(__file__).with_name('check_joint_receipt.py'))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    ARCHIVE = args.archive.resolve()
    READER_PATH = args.reader.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ArchiveFaultTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.report:
        source = READER_PATH.read_bytes()
        report = {
            'schema': 'titan.selected-joint-receipt.archive-fault-tests.v1',
            'reader_path': READER_PATH.name,
            'reader_sha256': hashlib.sha256(source).hexdigest(),
            'reader_git_blob': hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest(),
            'artifact_id': ARTIFACT_ID, 'artifact_sha256': ARTIFACT_SHA256,
            'checkout': CHECKOUT, 'run_id': RUN_ID,
            'tests_run': result.testsRun, 'failures': len(result.failures),
            'errors': len(result.errors), 'skipped': len(result.skipped),
            'successful': result.wasSuccessful(), 'cases': CASES,
            'failure_details': [{'test': str(test), 'traceback': text}
                                for test, text in result.failures + result.errors],
            'archived_test_methods_rerun': 0, 'game_panels': 0, 'seeds_consumed': [],
            'scope': 'Original hosted ZIP consumption and detached-evidence fault detection. '
                     'Only these reader regression methods execute, never archived code or games. '
                     'Mutated archive digests are locally calculated fixture identities, not provider receipts.'}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
