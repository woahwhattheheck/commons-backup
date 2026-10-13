#!/usr/bin/env python3
"""Regression tests for the operator rehearsal, not another metrics engine."""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('uiowa64_operator_rehearsal', HERE/'rehearse_output.py')
if spec is None or spec.loader is None:
    raise RuntimeError('cannot load rehearsal')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
CALC = HERE/'calculator.py'
FIXTURE = HERE/'fixtures/synthetic_deployments.csv'

class RehearsalTests(unittest.TestCase):
    def test_all_seven_cases_have_expected_outcomes(self):
        result = r.rehearse(CALC, FIXTURE)
        self.assertTrue(result['passed'])
        self.assertEqual([x['observed_exit'] for x in result['cases']], [0,2,2,0,2,2,0])
        self.assertTrue(all(x['source_preserved'] and x['temporary_files_cleaned'] for x in result['cases']))
        self.assertTrue(result['cases'][-1]['archive_preserved'])

    def test_deterministic_across_disposable_directories(self):
        self.assertEqual(r.rehearse(CALC, FIXTURE), r.rehearse(CALC, FIXTURE))

    def test_source_and_fixture_not_modified(self):
        before = CALC.read_bytes(), FIXTURE.read_bytes()
        r.rehearse(CALC, FIXTURE)
        self.assertEqual(before, (CALC.read_bytes(), FIXTURE.read_bytes()))

    def test_reference_is_real_original_fixture_result(self):
        report = r.rehearse(CALC, FIXTURE)['reference_report']
        self.assertEqual(report['scope']['deployment_count'], 8)
        m=report['metrics']
        self.assertEqual(m['deployment_frequency']['deployments_per_week'],4.0)
        self.assertEqual(m['change_lead_time']['mean'],14.875)
        self.assertEqual(m['failed_deployment_recovery_time']['median'],3.0)
        self.assertEqual(m['change_fail_rate']['percent'],25.0)

    def test_never_mints_external_authority(self):
        result = r.rehearse(CALC, FIXTURE)
        self.assertTrue(result['synthetic'])
        self.assertTrue(result['boundaries'])
        self.assertTrue(all(value is False for value in result['boundaries'].values()))

    def test_exactly_captured_calculator_is_executed_after_disk_change(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'calc.py'; captured=CALC.read_bytes();p.write_bytes(captured)
            original_loader=r.load_captured
            def change_after_capture(path):
                loaded=original_loader(path)
                path.write_bytes(b'raise RuntimeError("new unexecuted source")\n')
                return loaded
            with mock.patch.object(r,'load_captured',side_effect=change_after_capture):
                result=r.rehearse(p,FIXTURE)
            self.assertTrue(result['passed'])
            self.assertEqual(result['source_binding']['calculator_git_blob'],r.git_blob(captured))
            self.assertNotEqual(r.git_blob(p.read_bytes()),r.git_blob(captured))

    def test_exactly_captured_fixture_is_used_after_disk_change(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'fixture.csv';captured=FIXTURE.read_bytes();p.write_bytes(captured)
            original_loader=r.load_captured
            def change_after_capture(path):
                loaded=original_loader(path)
                p.write_bytes(b'not the captured fixture\n')
                return loaded
            with mock.patch.object(r,'load_captured',side_effect=change_after_capture):
                result=r.rehearse(CALC,p)
            self.assertTrue(result['passed'])
            self.assertEqual(result['source_binding']['fixture_git_blob'],r.git_blob(captured))

    def test_module_is_removed_after_success(self):
        name='_uiowa64_rehearsal_'+r.git_blob(CALC.read_bytes())
        sys.modules.pop(name,None)
        r.rehearse(CALC,FIXTURE)
        self.assertNotIn(name,sys.modules)

    def test_existing_module_is_restored(self):
        name='_uiowa64_rehearsal_'+r.git_blob(CALC.read_bytes())
        old=sys.modules.get(name); sentinel=types.ModuleType(name);sys.modules[name]=sentinel
        try:
            r.rehearse(CALC,FIXTURE)
            self.assertIs(sys.modules[name],sentinel)
        finally:
            if old is None:sys.modules.pop(name,None)
            else:sys.modules[name]=old

    def test_import_failure_cleans_module_registration(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'broken.py';b=b'raise ValueError("broken source")\n';p.write_bytes(b)
            name='_uiowa64_rehearsal_'+r.git_blob(b)
            with self.assertRaisesRegex(ValueError,'broken source'):r.load_captured(p)
            self.assertNotIn(name,sys.modules)

    def test_stdout_json_is_valid_complete_result(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):code=r.main(['--format','json'])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(out.getvalue()),r.rehearse(CALC,FIXTURE))

    def test_markdown_has_case_diagnostics_and_not_just_pass_count(self):
        text=r.render_markdown(r.rehearse(CALC,FIXTURE))
        self.assertIn('synthetic disk flush failure',text)
        self.assertIn('synthetic replace failure',text)
        self.assertIn('last complete report',text)
        self.assertNotIn('/tmp/',text)
        self.assertIn('25.0%',text)

    def test_missing_fixture_is_controlled(self):
        with tempfile.TemporaryDirectory() as td:
            out,err=io.StringIO(),io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                code=r.main(['--fixture',str(Path(td)/'missing.csv')])
            self.assertEqual(code,2);self.assertEqual(out.getvalue(),'')
            self.assertTrue(err.getvalue().startswith('ERROR:'));self.assertNotIn('Traceback',err.getvalue())

    def test_real_cli_same_as_function(self):
        proc=subprocess.run([sys.executable,*(['-O'] if not __debug__ else []),str(HERE/'rehearse_output.py'),'--format','json'],capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout),r.rehearse(CALC,FIXTURE))

    def test_git_blob_uses_object_header(self):
        data=b'abc\n'
        expected=hashlib.sha1(b'blob 4\0abc\n').hexdigest()
        self.assertEqual(r.git_blob(data),expected)

if __name__=='__main__':
    unittest.main()
