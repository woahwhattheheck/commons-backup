"""Run the actual public parent compiler, then the actual workbench exporter.

No fake parent module is substituted. Missing checkout/runtime dependencies are
reported as skips, never as successful parent compilation.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from contract import audit_pair, compare_json, loads_exact


def _run_python(*arguments: str) -> subprocess.CompletedProcess:
    """Execute the real child at this suite's optimization level, not default 0."""
    command = [sys.executable, *(['-O'] * sys.flags.optimize), *arguments]
    return subprocess.run(command, check=True, text=True, capture_output=True, timeout=30)


class ParentCompilerWorkbenchTests(unittest.TestCase):
    def test_public_compiler_to_actual_workbench_keeps_report_and_draft_consistent(self):
        revenue = HERE.parents[1]
        parent = Path(os.environ.get('WORKSHARE_DIR', str(revenue / 'uiowa_rfq_18649_workshare')))
        app = Path(os.environ.get('WORKBENCH_APP_JS', str(revenue / 'uiowa_rfq_18649_workbench/app.js')))
        if not (parent / 'compiler.py').exists() or not app.exists() or not shutil.which('node'):
            self.skipTest('Requires actual parent workshare checkout, actual app.js and Node')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'parent-report.json'
            compile_run = _run_python(
                str(parent / 'compiler.py'), 'compile',
                str(parent / 'fixtures/synthetic_packet.json'),
                str(parent / 'fixtures/synthetic_authority.json'), str(report)
            )
            self.assertIn('HOLD_TRUSTED_AUTHORITY_REQUIRED', compile_run.stdout)
            verify = _run_python(str(parent / 'compiler.py'), 'verify', str(report))
            self.assertIn('UNTRUSTED_INTEGRITY_ONLY', verify.stdout)
            capture = root / 'capture'
            subprocess.run(['node', str(HERE / 'capture_workbench.cjs'), str(app), str(capture), str(report)],
                           check=True, text=True, capture_output=True, timeout=30)
            self.assertEqual(compare_json(report.read_bytes(), (capture / 'report.json').read_bytes())['result'], 'PASS')
            original = loads_exact(report.read_bytes())
            draft = loads_exact((capture / 'handoff.json').read_bytes())
            self.assertEqual(audit_pair(original, draft), [])
            self.assertEqual(draft['report_receipt_sha256'], original['receipt_sha256'])
            self.assertEqual(len(original['assessment_matrix']), 12)
            self.assertTrue(all(row['maturity'] is None and row['confidence_bp'] is None
                                for row in original['assessment_matrix']))
            self.assertFalse(draft['synthetic_demo'], 'actual compiler does not set the UI-only demo marker')


if __name__ == '__main__':
    unittest.main()
