# SPDX-License-Identifier: Apache-2.0
"""Exercise the existing receipt CLI on detached evidence and real local files.

No code or tests from the validation ZIP are executed. Supply an already saved
95-method artifact; copies made in TemporaryDirectory are disposable witnesses.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--reader', type=Path, default=Path(__file__).with_name('check_joint_receipt.py'))
PARSER.add_argument('--archive', type=Path, required=True)
PARSER.add_argument('--report', type=Path)
ARGS = PARSER.parse_args()
READER = ARGS.reader.resolve()
ARCHIVE = ARGS.archive.resolve()
RAW = ARCHIVE.read_bytes()
DIGEST = hashlib.sha256(RAW).hexdigest()
sys.path.insert(0, str(READER.parent))
SPEC = importlib.util.spec_from_file_location('_receipt_output_subject', READER)
SUBJECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUBJECT)
RECORDS = []


class PartialWrite:
    """Write a real prefix, then inject an ordinary failure at the file boundary."""
    def __init__(self, stream, error):
        self.stream, self.error = stream, error

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def write(self, value):
        self.stream.write(value[:17])
        self.stream.flush()
        raise self.error


class ReceiptOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'evidence.zip'
        self.archive.write_bytes(RAW)
        self.output = self.root / 'receipt.json'
        self.old = b'{"prior":"complete receipt"}\n'

    def invoke(self, output=None, *, archive=None, expected=DIGEST, required=None):
        arguments = [str(READER), str(archive or self.archive)]
        if expected is not None:
            arguments += ['--expected-sha256', expected]
        if output is not None:
            arguments += ['--json-output', str(output)]
        if required is not None:
            arguments += ['--require-suite', required]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', arguments), redirect_stdout(stdout), redirect_stderr(stderr):
            code = SUBJECT.main()
        result = (code, stdout.getvalue(), stderr.getvalue())
        RECORDS.append({'case': self.id().split('.')[-1], 'exit': code,
                        'stdout_sha256': hashlib.sha256(result[1].encode()).hexdigest(),
                        'stderr': result[2],
                        'archive_preserved': self.archive.read_bytes() == RAW})
        return result

    def assert_untouched(self):
        self.assertEqual(self.archive.read_bytes(), RAW)
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(list(self.root.glob('.receipt.json.*.tmp')), [])

    def assert_alias_rejected(self, target, *, archive=None):
        code, out, err = self.invoke(target, archive=archive)
        self.assertEqual(code, 3)
        self.assertEqual(out, '')
        self.assertEqual(json.loads(err)['status'], 'ERROR')
        self.assertIn('evidence archive', json.loads(err)['detail'])
        self.assertEqual(self.archive.read_bytes(), RAW)

    def test_stdout_only_retains_existing_cli(self):
        code, out, err = self.invoke()
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out)['reported_test_methods'], 95)
        self.assertEqual(self.archive.read_bytes(), RAW)
        self.assertFalse(self.output.exists())

    def test_new_nested_report_matches_stdout(self):
        target = self.root / 'new' / 'nested' / 'receipt.json'
        code, out, err = self.invoke(target)
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(target.read_bytes(), out.encode('utf-8'))
        self.assertEqual(self.archive.read_bytes(), RAW)
        self.assertEqual(list(target.parent.glob('.*.tmp')), [])

    def test_existing_report_replaced_completely(self):
        self.output.write_bytes(self.old)
        code, out, err = self.invoke(self.output)
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(self.output.read_bytes(), out.encode('utf-8'))
        self.assertEqual(json.loads(out)['status'], 'COMPLETE_PASS')
        self.assertEqual(self.archive.read_bytes(), RAW)

    def test_direct_archive_alias_rejected(self):
        self.assert_alias_rejected(self.archive)

    def test_normalized_relative_archive_alias_rejected(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            self.assert_alias_rejected(Path('.') / 'evidence.zip')
        finally:
            os.chdir(previous)

    def test_output_symlink_to_archive_rejected(self):
        self.output.symlink_to(self.archive)
        self.assert_alias_rejected(self.output)
        self.assertTrue(self.output.is_symlink())

    def test_output_hardlink_to_archive_rejected(self):
        os.link(self.archive, self.output)
        self.assert_alias_rejected(self.output)
        self.assertTrue(self.output.samefile(self.archive))

    def test_parent_directory_alias_rejected(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.assert_alias_rejected(alias / 'evidence.zip')

    def test_input_symlink_real_destination_rejected(self):
        alias = self.root / 'input-link.zip'
        alias.symlink_to(self.archive)
        self.assert_alias_rejected(self.archive, archive=alias)
        self.assertTrue(alias.is_symlink())

    def test_distinct_report_symlink_preserved(self):
        actual = self.root / 'actual.json'
        actual.write_bytes(self.old)
        self.output.symlink_to(actual)
        code, out, err = self.invoke(self.output)
        self.assertEqual((code, err), (0, ''))
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(actual.read_bytes(), out.encode())
        self.assertEqual(self.archive.read_bytes(), RAW)

    def test_failure_verdict_and_exit_one_preserved(self):
        code, out, err = self.invoke(self.output, expected='0' * 64)
        self.assertEqual((code, err), (1, ''))
        self.assertEqual(json.loads(out)['status'], 'FAIL')
        self.assertEqual(self.output.read_bytes(), out.encode())
        self.assertEqual(self.archive.read_bytes(), RAW)

    def test_incomplete_verdict_and_exit_two_preserved(self):
        code, out, err = self.invoke(self.output, expected=None)
        self.assertEqual((code, err), (2, ''))
        self.assertEqual(json.loads(out)['status'], 'INCOMPLETE')
        self.assertEqual(self.output.read_bytes(), out.encode())
        self.assertEqual(self.archive.read_bytes(), RAW)

    def test_inspection_error_keeps_prior_report(self):
        self.output.write_bytes(self.old)
        code, out, err = self.invoke(self.output, required='not_a_suite')
        self.assertEqual((code, out), (3, ''))
        self.assertEqual(json.loads(err)['status'], 'ERROR')
        self.assert_untouched()

    def test_partial_write_keeps_prior_report(self):
        self.output.write_bytes(self.old)
        error = OSError('injected partial receipt write')
        original_temp = tempfile.NamedTemporaryFile
        original_open = Path.open

        def temporary(*args, **kwargs):
            return PartialWrite(original_temp(*args, **kwargs), error)

        def path_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            mode = args[0] if args else kwargs.get('mode', 'r')
            return PartialWrite(stream, error) if path == self.output and 'w' in mode else stream

        # Exercise both the previous direct writer and the staged writer at
        # their real file boundary, without replacing inspect_archive or main.
        with patch('tempfile.NamedTemporaryFile', side_effect=temporary), patch.object(Path, 'open', path_open):
            code, out, err = self.invoke(self.output)
        self.assertEqual((code, out), (3, ''))
        self.assertIn(str(error), err)
        self.assert_untouched()

    def test_fsync_failure_keeps_prior_report(self):
        self.output.write_bytes(self.old)
        with patch('os.fsync', side_effect=OSError('injected fsync failure')):
            code, out, err = self.invoke(self.output)
        self.assertEqual((code, out), (3, ''))
        self.assertIn('injected fsync failure', err)
        self.assert_untouched()

    def test_replace_failure_keeps_prior_report(self):
        self.output.write_bytes(self.old)
        with patch('os.replace', side_effect=OSError('injected replacement failure')):
            code, out, err = self.invoke(self.output)
        self.assertEqual((code, out), (3, ''))
        self.assertIn('injected replacement failure', err)
        self.assert_untouched()

    def test_cancelled_replace_keeps_prior_report_and_exception(self):
        self.output.write_bytes(self.old)
        marker = KeyboardInterrupt('cancel publication')
        with patch('os.replace', side_effect=marker):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.invoke(self.output)
        self.assertIs(caught.exception, marker)
        self.assert_untouched()

    def test_stage_creation_failure_keeps_prior_report(self):
        self.output.write_bytes(self.old)
        with patch('tempfile.NamedTemporaryFile', side_effect=OSError('injected stage creation failure')):
            code, out, err = self.invoke(self.output)
        self.assertEqual((code, out), (3, ''))
        self.assertIn('injected stage creation failure', err)
        self.assert_untouched()

    def test_cleanup_error_does_not_hide_replace_error(self):
        self.output.write_bytes(self.old)
        original_unlink = Path.unlink

        def unlink(path, *args, **kwargs):
            if path.name.startswith('.receipt.json.'):
                raise OSError('injected cleanup failure')
            return original_unlink(path, *args, **kwargs)

        with patch('os.replace', side_effect=OSError('original replacement failure')), patch.object(Path, 'unlink', unlink):
            code, out, err = self.invoke(self.output)
        self.assertEqual((code, out), (3, ''))
        self.assertIn('original replacement failure', err)
        self.assertNotIn('injected cleanup failure', err)
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(self.archive.read_bytes(), RAW)

    def test_hard_exit_before_publication_retains_old_report(self):
        self.output.write_bytes(self.old)
        child = '''import importlib.util, os, sys
from pathlib import Path
reader, archive, output, digest = sys.argv[1:]
sys.path.insert(0, str(Path(reader).parent))
spec = importlib.util.spec_from_file_location("subject", reader)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
def stop_before_publish(*args, **kwargs): os._exit(97)
os.replace = stop_before_publish
sys.argv = [reader, archive, "--json-output", output, "--expected-sha256", digest]
raise SystemExit(module.main())
'''
        result = subprocess.run([sys.executable, '-B', '-c', child, str(READER), str(self.archive),
                                 str(self.output), DIGEST], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 97)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(self.archive.read_bytes(), RAW)
        stages = list(self.root.glob('.receipt.json.*.tmp'))
        self.assertEqual(len(stages), 1)
        self.assertEqual(json.loads(stages[0].read_text())['status'], 'COMPLETE_PASS')
        RECORDS.append({'case': self.id().split('.')[-1], 'child_exit': 97,
                        'prior_report_preserved': True, 'unpublished_stage_count': 1})

    def test_real_cli_success_and_alias_rejection(self):
        result = subprocess.run([sys.executable, '-B', str(READER), str(self.archive),
                                  '--expected-sha256', DIGEST, '--json-output', str(self.output)],
                                 capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, self.output.read_bytes())
        bad = subprocess.run([sys.executable, '-B', str(READER), str(self.archive),
                               '--expected-sha256', DIGEST, '--json-output', str(self.archive)],
                              capture_output=True, timeout=15)
        self.assertEqual((bad.returncode, bad.stdout), (3, b''))
        self.assertEqual(json.loads(bad.stderr)['status'], 'ERROR')
        self.assertEqual(self.archive.read_bytes(), RAW)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReceiptOutputTests))
    assert ARCHIVE.read_bytes() == RAW, 'original supplied artifact must remain untouched'
    if ARGS.report:
        report = {'schema': 1, 'reader_sha256': hashlib.sha256(READER.read_bytes()).hexdigest(),
                  'helper_sha256': hashlib.sha256(READER.with_name('supplemental_receipt.py').read_bytes()).hexdigest(),
                  'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'artifact_sha256': DIGEST, 'tests': result.testsRun, 'successful': result.wasSuccessful(),
                  'failures': [{'test': str(t), 'traceback': text} for t, text in result.failures],
                  'errors': [{'test': str(t), 'traceback': text} for t, text in result.errors],
                  'skipped': list(result.skipped), 'records': RECORDS,
                  'archived_tests_executed': 0, 'official_transitions': 0, 'games': 0}
        ARGS.report.parent.mkdir(parents=True, exist_ok=True)
        ARGS.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
