# SPDX-License-Identifier: Apache-2.0
"""Test receipt-byte binding against retained ZIPs and local file-lifecycle events.

Only the selected reader is imported. No archived code or test suites execute.
"""
from __future__ import annotations
import argparse
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
import zipfile

OPTIONS = None
CASES = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rewrite_log(data, name, body):
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item,body if item.filename==name else src.read(item))
    return out.getvalue()


class InputBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if OPTIONS is None:
            raise unittest.SkipTest('Run with --reader, --archive-a and --archive-b.')
        cls.reader_path=OPTIONS.reader.resolve()
        sys.path.insert(0,str(cls.reader_path.parent))
        sys.modules.pop('supplemental_receipt',None)
        spec=importlib.util.spec_from_file_location('input_binding_reader',cls.reader_path)
        cls.reader=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=cls.reader
        spec.loader.exec_module(cls.reader)
        cls.a=OPTIONS.archive_a.read_bytes();cls.b=OPTIONS.archive_b.read_bytes()
        expected={10036877991:'af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29',
                  10037093197:'ff4fd2542982ba5cf04e081bf3cc74a9206d5c3ec2e430118d76b109de6111b6'}
        if sha(cls.a)!=expected[10036877991] or sha(cls.b)!=expected[10037093197]:
            raise ValueError('The two retained ZIPs must match their original provider digests.')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'control.zip';p.write_bytes(cls.a)
            cls.expected_a=cls.reader.inspect_archive(p,expected_sha256=sha(cls.a))
            p.write_bytes(cls.b)
            cls.expected_b=cls.reader.inspect_archive(p,expected_sha256=sha(cls.b))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'receipt.zip'

    def inspect_event(self, captured, event, **kwargs):
        self.path.write_bytes(captured)
        real_read=Path.read_bytes
        events=[]
        def read_then_event(path):
            data=real_read(path)
            if path==self.path and not events:
                events.append('captured')
                event(path)
            return data
        kwargs.setdefault('expected_sha256',sha(captured))
        with patch.object(Path,'read_bytes',read_then_event):
            result=self.reader.inspect_archive(self.path,**kwargs)
        self.assertEqual(events,['captured'])
        CASES.append({'case':self.id().split('.')[-1], 'snapshot_sha256':sha(captured),
                      'result':result})
        return result

    def replace_with(self, data):
        def event(path):
            other=path.with_suffix('.next');other.write_bytes(data);other.replace(path)
        return event

    def test_replacement_after_capture_keeps_original_methods_and_identity(self):
        out=self.inspect_event(self.a,self.replace_with(self.b))
        self.assertEqual(out,self.expected_a)
        self.assertEqual(out['reported_test_methods'],95)
        self.assertTrue(out['provider_digest_matched'])

    def test_reverse_replacement_keeps_v2_original(self):
        out=self.inspect_event(self.b,self.replace_with(self.a))
        self.assertEqual(out,self.expected_b)
        self.assertEqual(out['reported_test_methods'],117)

    def test_in_place_truncation_after_capture_does_not_destroy_receipt(self):
        out=self.inspect_event(self.a,lambda p:p.write_bytes(b''))
        self.assertEqual(out,self.expected_a)

    def test_removal_after_capture_does_not_destroy_receipt(self):
        out=self.inspect_event(self.a,lambda p:p.unlink())
        self.assertEqual(out,self.expected_a)

    def test_replacement_with_nonzip_cannot_replace_captured_evidence(self):
        out=self.inspect_event(self.a,self.replace_with(b'not a ZIP\n'))
        self.assertEqual(out,self.expected_a)

    def test_original_nonzip_stays_failure_after_valid_replacement(self):
        captured=b'incomplete download\n'
        out=self.inspect_event(captured,self.replace_with(self.a))
        self.assertEqual(out['status'],'FAIL')
        self.assertEqual(out['reported_test_methods'],0)
        self.assertTrue(any('cannot read evidence ZIP' in p['detail'] for p in out['problems']))

    def test_failed_original_test_cannot_be_erased_by_replacement(self):
        with zipfile.ZipFile(io.BytesIO(self.a)) as z:
            log=z.read('funded-join-tests.log')
        failed=rewrite_log(self.a,'funded-join-tests.log',log.replace(b'\nOK\n',b'\nFAILED (failures=1)\n'))
        out=self.inspect_event(failed,self.replace_with(self.a))
        self.assertEqual(out['status'],'FAIL')
        self.assertTrue(any('funded_join' in p['detail'] and 'failure' in p['detail'] for p in out['problems']))

    def test_valid_original_does_not_inherit_later_failed_log(self):
        with zipfile.ZipFile(io.BytesIO(self.a)) as z:
            log=z.read('funded-join-tests.log')
        failed=rewrite_log(self.a,'funded-join-tests.log',log.replace(b'\nOK\n',b'\nFAILED (failures=1)\n'))
        out=self.inspect_event(self.a,self.replace_with(failed))
        self.assertEqual(out,self.expected_a)

    def test_expected_source_fields_apply_to_captured_snapshot(self):
        keys={'expected_checkout':self.expected_a['checkout'],'expected_run_id':self.expected_a['run_id'],
              'expected_attempt':self.expected_a['attempt']}
        out=self.inspect_event(self.a,self.replace_with(self.b),**keys)
        self.assertEqual(out,self.expected_a)

    def test_mismatched_provider_digest_still_fails(self):
        out=self.inspect_event(self.a,self.replace_with(self.b),expected_sha256='0'*64)
        self.assertEqual(out['status'],'FAIL')
        self.assertFalse(out['provider_digest_matched'])
        self.assertEqual(out['reported_test_methods'],95)
        self.assertTrue(any('artifact SHA-256 differs' in p['detail'] for p in out['problems']))

    def test_no_digest_remains_incomplete_with_original_contents(self):
        out=self.inspect_event(self.a,self.replace_with(self.b),expected_sha256=None)
        self.assertEqual(out['status'],'INCOMPLETE')
        self.assertIsNone(out['provider_digest_matched'])
        self.assertEqual(out['reported_test_methods'],95)

    def test_required_suite_still_checks_captured_members(self):
        out=self.inspect_event(self.a,self.replace_with(self.b),required_suites=('reporter',))
        self.assertEqual(out['status'],'INCOMPLETE')
        self.assertTrue(any('reporter' in p['detail'] for p in out['problems']))

    def test_legacy_read_members_path_api_unchanged(self):
        self.path.write_bytes(self.a)
        got=self.reader.read_members(self.path)
        with zipfile.ZipFile(io.BytesIO(self.a)) as z:
            expected={Path(i.filename).name:z.read(i) for i in z.infolist() if not i.is_dir()}
        self.assertEqual(got,expected)

    def test_no_path_reopen_after_snapshot(self):
        self.path.write_bytes(self.a)
        real_read=Path.read_bytes
        read_count=[]
        real_open=io.open
        reopens=[]
        def read(path):
            data=real_read(path)
            if path==self.path:read_count.append('snapshot')
            return data
        def open_once(file,*args,**kwargs):
            if isinstance(file,(str,bytes,os.PathLike)) and os.fsdecode(file)==str(self.path) and read_count:
                reopens.append(str(file))
            return real_open(file,*args,**kwargs)
        with patch.object(Path,'read_bytes',read),patch('io.open',open_once):
            out=self.reader.inspect_archive(self.path,expected_sha256=sha(self.a))
        self.assertEqual(out,self.expected_a)
        self.assertEqual(read_count,['snapshot'])
        self.assertEqual(reopens,[], 'archive pathname reopened after snapshot')

    def test_current_cli_still_emits_identical_stdout_and_report(self):
        self.path.write_bytes(self.a);target=Path(self.tmp.name)/'out/result.json'
        result=subprocess.run([sys.executable,'-B',str(self.reader_path),str(self.path),
            '--expected-sha256',sha(self.a),'--require-suite','funded_join','--json-output',str(target)],
            capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,target.read_bytes())
        self.assertEqual(json.loads(result.stdout)['reported_test_methods'],95)

    def test_no_archived_suites_or_games_are_executed(self):
        out=self.inspect_event(self.a,self.replace_with(self.b))
        self.assertEqual((out['tests_rerun'],out['game_panels'],out['seeds_consumed']),(0,0,[]))


def main():
    global OPTIONS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader',type=Path,required=True)
    parser.add_argument('--archive-a',type=Path,required=True)
    parser.add_argument('--archive-b',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    OPTIONS=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InputBindingTests))
    if OPTIONS.report:
        doc={'schema':'titan.receipt.input-byte-binding-tests.v1','test_methods':result.testsRun,
             'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
             'successful':result.wasSuccessful(),'reader_sha256':sha(OPTIONS.reader.read_bytes()),
             'cases':CASES,'failure_details':[{'case':str(t),'traceback':s} for t,s in result.failures+result.errors],
             'archived_test_methods_rerun':0,'game_panels':0,'seeds_consumed':[]}
        OPTIONS.report.parent.mkdir(parents=True,exist_ok=True)
        OPTIONS.report.write_text(json.dumps(doc,indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
