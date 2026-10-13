# SPDX-License-Identifier: Apache-2.0
"""Existing canonical CI binding and its actual finalization code; no games.

Filesystem records below are explicit synthetic CI receipts. The real builder
and its existing corruption cases execute separately in the canonical job.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

WORKFLOW = (Path(__file__).resolve().parent / '../../../../.github/workflows/titan-selected-projection.yml').resolve()
LAB = 'revenue/kaggriculture/cloud-execution-lab/'
SIBLING_SOURCE_ROOTS = (
    'revenue/kaggriculture/cloud-economic-stress/funded_payback',
    'revenue/kaggriculture/cloud-quickstep',
    'revenue/kaggriculture/cloud-runtime-pulse',
    'revenue/kaggriculture/cloud-opponent-league/lark-responsive',
)


def focused(text):
    match = re.search(r'^  focused:\n(.*?)(?=^  [A-Za-z_][\w-]*:|\Z)', text, re.M | re.S)
    if not match:
        raise ValueError('Focused job is absent')
    return match.group(1)


def canonical(text):
    match = re.search(r'^  canonical:\n(.*?)(?=^  [A-Za-z_][\w-]*:|\Z)', text, re.M | re.S)
    if not match:
        raise ValueError('Canonical job is absent')
    return match.group(1)


def step(job, name):
    marker = '      - name: ' + name + '\n'
    if job.count(marker) != 1:
        raise ValueError('Expected one step: ' + name)
    return re.split(r'^      - (?:name|uses):', job.split(marker, 1)[1], maxsplit=1, flags=re.M)[0]


def finalizer(job):
    return textwrap.dedent(step(job, 'Record canonical result and source preservation').split('        run: |\n', 1)[1])


class CanonicalBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()
        cls.job = canonical(cls.text)
        cls.focused = focused(cls.text)

    def test_canonical_sources_trigger_the_existing_workflow(self):
        triggers = self.text.split('  workflow_dispatch:', 1)[0]
        self.assertIn("- '" + LAB + "**'", triggers)
        self.assertIn("- 'revenue/kaggriculture/cloud-composition-cases/cover/**'", triggers)
        self.assertIn('name: titan-selected-projection\n', self.text)

    def test_independent_exact_event_checkout_with_complete_lab(self):
        self.assertIn('          ref: ${{ github.sha }}\n', self.job)
        self.assertIn('          persist-credentials: false\n', self.job)
        self.assertIn('            /' + LAB + '\n', self.job)
        self.assertIn('            /.github/workflows/titan-selected-projection.yml\n', self.job)
        self.assertNotIn('    needs:', self.job)
        self.assertIn("      PYTHONDONTWRITEBYTECODE: '1'", self.job)

    def test_external_canonical_sources_are_triggered_checked_out_and_snapshotted(self):
        triggers = self.text.split('  workflow_dispatch:', 1)[0]
        snapshot = step(self.job, 'Record canonical source before checking')
        for root in SIBLING_SOURCE_ROOTS:
            with self.subTest(root=root):
                self.assertIn("- '" + root + "/**'", triggers)
                self.assertIn('            /' + root + '/\n', self.job)
                self.assertIn("'" + root + "'", snapshot)

    def test_focused_runtime_pulse_is_checked_out_and_snapshotted(self):
        snapshot = step(self.focused, 'Record committed test and runtime inputs')
        root = 'revenue/kaggriculture/cloud-runtime-pulse'
        self.assertIn('            /' + root + '/\n', self.focused)
        self.assertIn("'cloud-runtime-pulse'", snapshot)

    def test_actual_builder_check_never_rebuilds_the_checkout(self):
        body = step(self.job, 'Check the committed canonical package without rebuilding')
        calls = [line.strip() for line in body.splitlines() if 'build_integrated.py' in line]
        self.assertEqual(calls, ['python3 -B ' + LAB + 'build_integrated.py --check \\'])
        self.assertIn('current-check.json', body)
        self.assertIn('current-check.stderr', body)
        self.assertIn('set -euo pipefail', body)
        self.assertNotIn('continue-on-error', body)

    def test_existing_discriminators_are_reused_in_separate_temporary_copies(self):
        body = step(self.job, 'Existing release consistency cases in temporary copies')
        self.assertIn('python3 -B -m unittest -v test_release_consistency', body)
        self.assertIn('set -euo pipefail', body)
        self.assertIn('if: ${{ !cancelled() }}', body)

    def test_event_and_head_are_recorded_separately(self):
        body = step(self.job, 'Record canonical source before checking')
        for text in ("checkout != os.environ['GITHUB_SHA']", "'pull_request_head'",
                     "'pull_request_base'", "'zlib'", "'git_blob'", "'sha256'"):
            self.assertIn(text, body)
        compile(textwrap.dedent(body.split('        run: |\n', 1)[1]), 'snapshot', 'exec')

    def test_outcomes_and_failure_artifacts_are_retained(self):
        body = step(self.job, 'Record canonical result and source preservation')
        self.assertIn('if: ${{ always() }}', body)
        for name in ('snapshot', 'check', 'consistency', 'bindings'):
            self.assertIn('${{ steps.canonical_' + name + '.outcome }}', body)
        self.assertIn('name: titan-canonical-check-', self.job)
        self.assertIn('path: ${{ runner.temp }}/canonical-validation/', self.job)
        self.assertNotIn('upload-release', self.job)
        self.assertNotIn('cp ', self.job)


class FinalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = finalizer(canonical(WORKFLOW.read_text()))
        compile(cls.code, 'canonical-finalizer', 'exec')

    def exercise(self, change=None, outcomes=None, receipt_change=None, snapshot_change=None):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root, out = base/'checkout', base/'results'
            root.mkdir(); out.mkdir()
            original = {LAB+'main.py': b'original code\n',
                        LAB+'exports/titan-current.tar.gz': b'archive fixture',
                        LAB+'record/CURRENT-SOURCE.json': b'manifest fixture',
                        '.github/workflows/titan-selected-projection.yml': b'workflow fixture'}
            for name, data in original.items():
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            records = {name: {'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
                       for name,data in original.items()}
            snapshot = {'checkout':'a'*40, 'event_sha':'a'*40, 'pull_request_head':'b'*40,
                        'roots':[LAB.rstrip('/')], 'files':records}
            receipt = {'path':'exports/titan-current.tar.gz', 'bytes':len(b'archive fixture'),
                       'sha256':hashlib.sha256(b'archive fixture').hexdigest(),
                       'source_manifest':'record/CURRENT-SOURCE.json',
                       'source_manifest_sha256':hashlib.sha256(b'manifest fixture').hexdigest()}
            if receipt_change: receipt_change(receipt)
            actual_out = out/'canonical-validation';actual_out.mkdir()
            (actual_out/'SOURCE-SNAPSHOT.json').write_text(json.dumps(snapshot))
            (actual_out/'current-check.json').write_text(json.dumps(receipt))
            if snapshot_change: snapshot_change(actual_out)
            if change: change(root)
            env = dict(os.environ, RUNNER_TEMP=str(out), PYTHONDONTWRITEBYTECODE='1')
            env.update({key:'success' for key in
                        ('SNAPSHOT_OUTCOME','CHECK_OUTCOME','CONSISTENCY_OUTCOME','BINDINGS_OUTCOME')})
            env.update(outcomes or {})
            before = {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result = subprocess.run([sys.executable,'-B','-c',self.code],cwd=root,env=env,capture_output=True,text=True)
            after = {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before,after,'Finalizer modified checked source')
            self.assertTrue((actual_out/'CANONICAL-RESULTS.json').is_file(),result.stderr)
            report = json.loads((actual_out/'CANONICAL-RESULTS.json').read_text())
            return result,report

    def test_success_keeps_merge_and_head_distinct_without_source_writes(self):
        call,report = self.exercise()
        self.assertEqual(call.returncode,0,call.stderr)
        self.assertTrue(report['successful'])
        self.assertEqual(report['checkout'],'a'*40)
        self.assertEqual(report['pull_request_head'],'b'*40)
        self.assertEqual(report['changed_paths'],[])

    def test_every_failed_or_skipped_step_prevents_a_successful_report(self):
        for name in ('SNAPSHOT_OUTCOME','CHECK_OUTCOME','CONSISTENCY_OUTCOME','BINDINGS_OUTCOME'):
            for value in ('failure','skipped','cancelled'):
                with self.subTest(name=name,value=value):
                    call,report=self.exercise(outcomes={name:value})
                    self.assertEqual(call.returncode,1)
                    self.assertFalse(report['successful'])
                    self.assertIn(name+': '+value,report['problems'])

    def test_changed_added_or_deleted_source_is_reported(self):
        changes = [lambda root:(root/(LAB+'main.py')).write_bytes(b'changed'),
                   lambda root:(root/(LAB+'added.py')).write_bytes(b'new'),
                   lambda root:(root/(LAB+'main.py')).unlink()]
        for change in changes:
            with self.subTest(change=change):
                call,report=self.exercise(change=change)
                self.assertEqual(call.returncode,1)
                self.assertTrue(report['changed_paths'])

    def test_receipt_archive_size_hash_and_manifest_are_bound(self):
        for key in ('bytes','sha256','source_manifest_sha256'):
            with self.subTest(key=key):
                call,report=self.exercise(receipt_change=lambda row:row.update({key:0 if key=='bytes' else '0'*64}))
                self.assertEqual(call.returncode,1)
                self.assertIn('Builder result differs from pre-check source snapshot',report['problems'])

    def test_missing_snapshot_still_produces_a_failure_receipt(self):
        call,report=self.exercise(snapshot_change=lambda out:(out/'SOURCE-SNAPSHOT.json').unlink())
        self.assertEqual(call.returncode,1)
        self.assertFalse(report['successful'])

    def test_malformed_check_output_is_not_success(self):
        call,report=self.exercise(snapshot_change=lambda out:(out/'current-check.json').write_text('truncated{'))
        self.assertEqual(call.returncode,1)
        self.assertFalse(report['successful'])

    def test_failed_check_cannot_be_rescued_by_a_stale_valid_receipt(self):
        call,report=self.exercise(outcomes={'CHECK_OUTCOME':'failure'})
        self.assertEqual(call.returncode,1)
        self.assertNotIn('release',report)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--workflow',type=Path,default=WORKFLOW)
    args,remaining=parser.parse_known_args()
    WORKFLOW=args.workflow
    unittest.main(argv=[sys.argv[0]]+remaining)
