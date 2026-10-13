#!/usr/bin/env python3
"""Synthetic UIOWA-064 report-publication tests; no provider or customer I/O.

UIOWA_METRICS_CALCULATOR optionally selects another exact source revision.
Every destructive counterexample uses a disposable temporary source copy.
"""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('UIOWA_METRICS_CALCULATOR', str(HERE/'calculator.py'))).resolve()
spec = importlib.util.spec_from_file_location('uiowa64_output_integrity', SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f'cannot import calculator: {SOURCE}')
calc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = calc
spec.loader.exec_module(calc)

CSV = (
    'deployment_id,service,commit_at,deployed_at,intervention_required,recovered_at,unplanned_rework,notes\n'
    'SYNTH-01,synthetic-service,2026-09-01T09:00:00Z,2026-09-01T12:00:00Z,false,,false,"SYNTHETIC café 東京"\n'
)
START = '2026-09-01T00:00:00Z'
END = '2026-09-15T00:00:00Z'


class OutputIntegrityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='uiowa64-output-test-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = self.root/'source.csv'
        self.source.write_text(CSV, encoding='utf-8', newline='\n')
        self.original = self.source.read_bytes()
        self.output = self.root/'report.json'

    def args(self, output=None):
        values = [str(self.source), '--window-start', START, '--window-end', END]
        if output is not None:
            values.extend(['--output', str(output)])
        return values

    def invoke(self, output=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = calc.main(self.args(output))
        return code, stdout.getvalue(), stderr.getvalue()

    def require_refusal(self, result):
        code, out, err = result
        self.assertEqual(code, 2, result)
        self.assertEqual(out, '')
        self.assertTrue(err.startswith('ERROR:'), err)
        self.assertNotIn('Traceback', err)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob('.uiowa64-report-*.tmp')), [])

    def test_input_path_is_refused_and_source_bytes_survive(self):
        self.require_refusal(self.invoke(self.source))

    def test_hardlink_to_input_is_refused_and_both_names_survive(self):
        alias = self.root/'input-hardlink.csv'
        os.link(self.source, alias)
        self.require_refusal(self.invoke(alias))
        self.assertTrue(os.path.samefile(alias, self.source))
        self.assertEqual(alias.read_bytes(), self.original)

    def test_symlink_to_input_is_refused_and_target_survives(self):
        alias = self.root/'input-symlink.csv'
        alias.symlink_to(self.source)
        self.require_refusal(self.invoke(alias))
        self.assertTrue(alias.is_symlink())
        self.assertEqual(alias.read_bytes(), self.original)

    def test_parent_symlink_alias_to_input_is_refused(self):
        parent = self.root/'directory-alias'
        parent.symlink_to(self.root, target_is_directory=True)
        self.require_refusal(self.invoke(parent/'source.csv'))

    def test_lexically_different_input_alias_is_refused(self):
        child = self.root/'child'
        child.mkdir()
        self.require_refusal(self.invoke(child/'..'/'source.csv'))

    def test_existing_unrelated_report_is_replaced_only_with_complete_json(self):
        self.output.write_bytes(b'previous complete report\n')
        result = self.invoke(self.output)
        self.assertEqual(result, (0, '', ''))
        self.assertEqual(json.loads(self.output.read_text()), json.loads(self.invoke()[1]))
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob('.uiowa64-report-*.tmp')), [])

    def test_new_output_exactly_matches_stdout(self):
        expected = self.invoke()
        self.assertEqual(expected[0], 0)
        self.assertEqual(self.invoke(self.output), (0, '', ''))
        self.assertEqual(self.output.read_bytes(), expected[1].encode('utf-8'))
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_unicode_output_path_is_supported(self):
        path = self.root/'résumé-東京.json'
        self.assertEqual(self.invoke(path), (0, '', ''))
        self.assertEqual(json.loads(path.read_text()), json.loads(self.invoke()[1]))

    def test_unrelated_symlink_output_is_refused_without_touching_target(self):
        target = self.root/'old-report.json'
        target.write_bytes(b'previous complete report\n')
        self.output.symlink_to(target)
        self.require_refusal(self.invoke(self.output))
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(target.read_bytes(), b'previous complete report\n')

    def test_dangling_symlink_output_is_refused(self):
        target = self.root/'not-created.json'
        self.output.symlink_to(target)
        self.require_refusal(self.invoke(self.output))
        self.assertTrue(self.output.is_symlink())
        self.assertFalse(target.exists())

    def test_directory_output_is_refused(self):
        self.output.mkdir()
        self.require_refusal(self.invoke(self.output))
        self.assertTrue(self.output.is_dir())

    def test_missing_parent_is_controlled_and_creates_nothing(self):
        self.require_refusal(self.invoke(self.root/'missing'/'report.json'))
        self.assertFalse((self.root/'missing').exists())

    def test_invalid_csv_leaves_existing_report_intact(self):
        self.source.write_bytes(b'invalid columns\n')
        self.original = self.source.read_bytes()
        self.output.write_bytes(b'previous complete report\n')
        self.require_refusal(self.invoke(self.output))
        self.assertEqual(self.output.read_bytes(), b'previous complete report\n')

    def test_flush_failure_preserves_existing_report_and_cleans_temporary(self):
        self.output.write_bytes(b'previous complete report\n')
        with mock.patch.object(calc.os, 'fsync', side_effect=OSError('synthetic flush failure')):
            self.require_refusal(self.invoke(self.output))
        self.assertEqual(self.output.read_bytes(), b'previous complete report\n')

    def test_flush_failure_does_not_publish_a_new_report(self):
        with mock.patch.object(calc.os, 'fsync', side_effect=OSError('synthetic flush failure')):
            self.require_refusal(self.invoke(self.output))
        self.assertFalse(self.output.exists())

    def test_replace_failure_preserves_existing_report_and_cleans_temporary(self):
        self.output.write_bytes(b'previous complete report\n')
        with mock.patch.object(calc.os, 'replace', side_effect=OSError('synthetic replace failure')):
            self.require_refusal(self.invoke(self.output))
        self.assertEqual(self.output.read_bytes(), b'previous complete report\n')

    def test_replace_failure_does_not_publish_a_new_report(self):
        with mock.patch.object(calc.os, 'replace', side_effect=OSError('synthetic replace failure')):
            self.require_refusal(self.invoke(self.output))
        self.assertFalse(self.output.exists())

    def test_encoding_failure_cannot_truncate_existing_report(self):
        self.output.write_bytes(b'previous complete report\n')
        with self.assertRaises(UnicodeError):
            calc._write_report('bad surrogate: \ud800', self.output, self.source)
        self.assertEqual(self.output.read_bytes(), b'previous complete report\n')
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob('.uiowa64-report-*.tmp')), [])

    def test_identity_recheck_refuses_new_source_hardlink_at_destination(self):
        real_fsync = os.fsync
        def bind_alias(fd):
            real_fsync(fd)
            os.link(self.source, self.output)
        with mock.patch.object(calc.os, 'fsync', side_effect=bind_alias):
            self.require_refusal(self.invoke(self.output))
        self.assertTrue(os.path.samefile(self.source, self.output))

    def test_replacing_an_unrelated_hardlink_does_not_mutate_its_other_name(self):
        old = self.root/'archived-report.json'
        old.write_bytes(b'previous complete report\n')
        os.link(old, self.output)
        self.assertEqual(self.invoke(self.output), (0, '', ''))
        self.assertFalse(os.path.samefile(old, self.output))
        self.assertEqual(old.read_bytes(), b'previous complete report\n')
        self.assertEqual(json.loads(self.output.read_text()), json.loads(self.invoke()[1]))

    def test_cli_subprocess_input_alias_refusal_is_controlled(self):
        result = subprocess.run(
            [sys.executable, *(['-O'] if not __debug__ else []), str(SOURCE), *self.args(self.source)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.require_refusal((result.returncode, result.stdout, result.stderr))

    def test_cli_subprocess_success_is_byte_identical_to_library_entrypoint(self):
        result = subprocess.run(
            [sys.executable, *(['-O'] if not __debug__ else []), str(SOURCE), *self.args(self.output)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertEqual(self.output.read_bytes(), self.invoke()[1].encode('utf-8'))


if __name__ == '__main__':
    unittest.main()
