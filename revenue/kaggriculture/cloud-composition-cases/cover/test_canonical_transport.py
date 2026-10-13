# SPDX-License-Identifier: Apache-2.0
"""Run the exact workflow copy block on explicit filesystem fixtures; no games."""
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

WORKFLOW = (Path(__file__).resolve().parent /
            '../../../../.github/workflows/titan-selected-projection.yml').resolve()
LAB = 'revenue/kaggriculture/cloud-execution-lab/'
NAMES = ('exports/titan-current.tar.gz',
         'runtime/integrated-selected/CURRENT-ARCHIVE.json',
         'runtime/integrated-selected/CURRENT-SOURCE.json')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def copy_code(text):
    marker = '      - name: Retain checked canonical bytes for existing consumers\n'
    if text.count(marker) != 1:
        raise ValueError('Expected one canonical copy step')
    body = text.split(marker, 1)[1].split('      - uses: actions/upload-artifact@v4', 1)[0]
    return textwrap.dedent(body.split('        run: |\n', 1)[1])


class CanonicalTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text()
        cls.code = copy_code(cls.workflow)
        compile(cls.code, 'canonical-copy', 'exec')

    def exercise(self, *, mutate=None, prefix=''):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkout, temp = base/'checkout', base/'runner'
            checkout.mkdir(); temp.mkdir()
            out = temp/'canonical-validation'; out.mkdir()
            payload = {NAMES[0]: b'\x1f\x8b\x00\xffbinary archive fixture\x00',
                       NAMES[2]: b'{"files": {"main.py": "fixture"}}\n'}
            pointer = {'path': NAMES[0], 'sha256': digest(payload[NAMES[0]]),
                       'bytes': len(payload[NAMES[0]]), 'source_manifest': NAMES[2],
                       'source_manifest_sha256': digest(payload[NAMES[2]])}
            payload[NAMES[1]] = (json.dumps(pointer, indent=2)+'\n').encode()
            for name, data in payload.items():
                path = checkout/(LAB+name)
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            identity = {'checkout': 'a'*40, 'event_sha': 'a'*40, 'pull_request_head': 'b'*40}
            checked = dict(identity, successful=True, changed_paths=[], release=pointer)
            snapshot = dict(identity, files={LAB+name: {'bytes': len(data), 'sha256': digest(data)}
                                            for name,data in payload.items()})
            (out/'CANONICAL-RESULTS.json').write_text(json.dumps(checked))
            (out/'SOURCE-SNAPSHOT.json').write_text(json.dumps(snapshot))
            if mutate:
                mutate(checkout, out, checked, snapshot, payload)
            # Capture AFTER the deliberate fault, so the actual step must not
            # alter any checked source even when reporting that fault.
            before = {str(p.relative_to(checkout)): p.read_bytes()
                      for p in checkout.rglob('*') if p.is_file()}
            env = dict(os.environ, RUNNER_TEMP=str(temp), PYTHONDONTWRITEBYTECODE='1')
            process = subprocess.run([sys.executable, '-B', '-c', prefix+self.code],
                                     cwd=checkout, env=env, capture_output=True, text=True)
            after = {str(p.relative_to(checkout)): p.read_bytes()
                     for p in checkout.rglob('*') if p.is_file()}
            self.assertEqual(before, after, 'Copy step changed checked source')
            result_path = out/'PACKAGE-TRANSFER.json'
            self.assertTrue(result_path.is_file(), process.stderr)
            result = json.loads(result_path.read_text())
            copied = {str(p.relative_to(out/'checked-package')): p.read_bytes()
                      for p in (out/'checked-package').rglob('*') if p.is_file()}
            self.assertFalse(list(temp.glob('canonical-copy-*')), 'Staged files were not cleaned')
            return process, result, copied, payload

    def test_exact_binary_and_both_manifests_are_retained(self):
        process, result, copied, payload = self.exercise()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(result['successful'])
        self.assertEqual(copied, payload)
        self.assertEqual(set(result['files']), set(NAMES))
        self.assertEqual(result['checkout'], 'a'*40)
        self.assertEqual(result['pull_request_head'], 'b'*40)
        for name,data in copied.items():
            self.assertEqual(result['files'][name], {'bytes': len(data), 'sha256': digest(data)})

    def test_failed_or_changed_canonical_result_does_not_copy(self):
        for patch in ({'successful': False}, {'changed_paths': ['changed.py']}):
            with self.subTest(patch=patch):
                def mutate(root, out, checked, snapshot, payload):
                    checked.update(patch)
                    (out/'CANONICAL-RESULTS.json').write_text(json.dumps(checked))
                process,result,copied,_ = self.exercise(mutate=mutate)
                self.assertEqual(process.returncode, 1)
                self.assertFalse(result['successful']); self.assertEqual(copied,{})

    def test_snapshot_identity_must_match_actual_checked_result(self):
        for key in ('checkout', 'event_sha', 'pull_request_head'):
            with self.subTest(key=key):
                def mutate(root, out, checked, snapshot, payload):
                    snapshot[key] = 'c'*40
                    (out/'SOURCE-SNAPSHOT.json').write_text(json.dumps(snapshot))
                process,result,copied,_ = self.exercise(mutate=mutate)
                self.assertEqual(process.returncode, 1)
                self.assertIn('identity differ', result['problems'][0]); self.assertEqual(copied,{})

    def test_each_payload_changed_after_check_is_rejected(self):
        for name in NAMES:
            with self.subTest(name=name):
                def mutate(root, out, checked, snapshot, payload):
                    (root/(LAB+name)).write_bytes(payload[name]+b'changed')
                process,result,copied,_ = self.exercise(mutate=mutate)
                self.assertEqual(process.returncode, 1)
                self.assertIn('source changed', result['problems'][0]); self.assertEqual(copied,{})

    def test_missing_payload_retains_an_explicit_failure(self):
        for name in NAMES:
            with self.subTest(name=name):
                process,result,copied,_ = self.exercise(
                    mutate=lambda root,out,c,s,p: (root/(LAB+name)).unlink())
                self.assertEqual(process.returncode,1)
                self.assertFalse(result['successful']);self.assertEqual(copied,{})

    def test_pointer_must_equal_successfully_checked_receipt(self):
        def mutate(root,out,checked,snapshot,payload):
            checked['release'] = dict(checked['release'], bytes=0)
            (out/'CANONICAL-RESULTS.json').write_text(json.dumps(checked))
        process,result,copied,_ = self.exercise(mutate=mutate)
        self.assertEqual(process.returncode,1)
        self.assertIn('pointer differs',result['problems'][0]);self.assertEqual(copied,{})

    def test_pointer_binds_exact_paths_archive_size_hash_and_manifest(self):
        for key in ('path','source_manifest','bytes','sha256','source_manifest_sha256'):
            with self.subTest(key=key):
                def mutate(root,out,checked,snapshot,payload):
                    checked['release'][key] = 0 if key=='bytes' else 'wrong'
                    data=(json.dumps(checked['release'])+'\n').encode()
                    (root/(LAB+NAMES[1])).write_bytes(data)
                    snapshot['files'][LAB+NAMES[1]]={'bytes':len(data),'sha256':digest(data)}
                    (out/'SOURCE-SNAPSHOT.json').write_text(json.dumps(snapshot))
                    (out/'CANONICAL-RESULTS.json').write_text(json.dumps(checked))
                process,result,copied,_ = self.exercise(mutate=mutate)
                self.assertEqual(process.returncode,1)
                self.assertIn('does not bind',result['problems'][0]);self.assertEqual(copied,{})

    def test_write_failure_publishes_no_partial_package(self):
        prefix = '''from pathlib import Path
_original_write=Path.write_bytes
def fail_write(self,data):
    if 'canonical-copy-' in str(self) and self.name=='CURRENT-ARCHIVE.json':
        raise OSError('injected full disk')
    return _original_write(self,data)
Path.write_bytes=fail_write
'''
        process,result,copied,_=self.exercise(prefix=prefix)
        self.assertEqual(process.returncode,1)
        self.assertIn('injected full disk',result['problems'][0]);self.assertEqual(copied,{})

    def test_short_copy_is_detected_before_publishing_directory(self):
        prefix = '''from pathlib import Path
_original_write=Path.write_bytes
def short_write(self,data):
    if 'canonical-copy-' in str(self) and self.name=='titan-current.tar.gz':
        return _original_write(self,data[:-1])
    return _original_write(self,data)
Path.write_bytes=short_write
'''
        process,result,copied,_=self.exercise(prefix=prefix)
        self.assertEqual(process.returncode,1)
        self.assertIn('Copied bytes differ',result['problems'][0]);self.assertEqual(copied,{})

    def test_existing_destination_is_not_overwritten(self):
        def mutate(root,out,checked,snapshot,payload):
            dest=out/'checked-package';dest.mkdir();(dest/'existing.txt').write_bytes(b'preserve')
        process,result,copied,_=self.exercise(mutate=mutate)
        self.assertEqual(process.returncode,1)
        self.assertIn('already present',result['problems'][0])
        self.assertEqual(copied,{'existing.txt':b'preserve'})

    def test_same_job_runs_copy_after_final_check_and_retains_tests(self):
        text=self.workflow
        copy_at=text.index('      - name: Retain checked canonical bytes for existing consumers')
        final_at=text.index('      - name: Record canonical result and source preservation')
        upload_at=text.index('          name: titan-canonical-check-')
        self.assertLess(final_at,copy_at);self.assertLess(copy_at,upload_at)
        step=text[copy_at:upload_at]
        self.assertNotIn('continue-on-error',step)
        self.assertNotIn('build_integrated.py',step)
        self.assertNotIn('tarfile',step)
        self.assertIn('canonical-transport-tests.log',text)
        self.assertIn('python3 -B '+LAB+'build_integrated.py --check',text)
        self.assertEqual(text.count('name: titan-selected-projection\n'),1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--workflow',type=Path,default=WORKFLOW)
    args,remaining=parser.parse_known_args()
    WORKFLOW=args.workflow
    unittest.main(argv=[sys.argv[0]]+remaining)
