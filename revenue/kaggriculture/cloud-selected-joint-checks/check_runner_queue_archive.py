# SPDX-License-Identifier: Apache-2.0
"""Consume the existing 282-method ZIP and detached faults; run no archived code."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from check_joint_receipt import inspect_archive

ARTIFACT_SHA256 = 'fe33a36cebf521ee4188609fc68a1739c68bbbb26e99f9ef87e3b7abbe91000b'
CHECKOUT = 'fc2c8a3b515d771c5b918ad3476d916d2ca801e9'
RUN_ID = '34182300969'
ROOT = 'revenue/kaggriculture/'
SPECS = {
 'stress_runner_boundary': ('stress-runner-boundary-tests.log', 'stress-runner-boundary.json', 20,
                           ROOT+'cloud-economic-stress/test_runner_guard_join.py'),
 'stress_runner_existing': ('stress-runner-existing-tests.log', None, 2,
                           ROOT+'cloud-economic-stress/test_runner.py'),
 'stress_runner_reporter': ('stress-runner-reporter-tests.log', None, 13,
                           ROOT+'cloud-selected-projection/test_stress_runner_report.py'),
 'queue_copy': ('queue-copy-tests.log', 'queue-copy-results.json', 23,
                ROOT+'cloud-selected-market-checks/test_queue_copy.py'),
 'queue_copy_reporter': ('queue-copy-reporter-tests.log', None, 14,
                        ROOT+'cloud-selected-projection/test_queue_copy_report.py'),
}
ARCHIVE = None
READS = []


def change_json(members, name, change):
    data=json.loads(members[name]);change(data)
    members[name]=json.dumps(data, sort_keys=True).encode()


class ArchiveContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ARCHIVE is None:
            raise unittest.SkipTest('Run explicitly with --archive.')
        if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()!=ARTIFACT_SHA256:
            raise ValueError('expected unchanged artifact10039313918')
        with zipfile.ZipFile(ARCHIVE) as z:
            cls.original={i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}

    def read(self, mutate=None, required=()):
        if mutate is None:
            out=inspect_archive(ARCHIVE, expected_sha256=ARTIFACT_SHA256,
                expected_checkout=CHECKOUT, expected_run_id=RUN_ID, expected_attempt='1',
                required_suites=required)
        else:
            members=dict(self.original)
            # Detached fixtures drop the aggregate so its stale input digests
            # cannot mask missing semantic checks in the supplemental reader.
            members.pop('COMBINED-RESULTS.json')
            mutate(members)
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'fault.zip'
                with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
                    for name,body in members.items(): z.writestr(name,body)
                out=inspect_archive(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected_checkout=CHECKOUT,expected_run_id=RUN_ID,expected_attempt='1',
                    required_suites=required)
        READS.append({'case':self.id().split('.')[-1], 'detached':mutate is not None, 'receipt':out})
        self.assertTrue(out['provider_digest_matched'])
        self.assertFalse(any('input digest differs' in p['detail'] for p in out['problems']))
        return out

    def assert_bad(self, out, label):
        self.assertIn(out['status'], ('FAIL','INCOMPLETE'), out)
        self.assertIn(label,str(out['problems']),out)

    def test_full_282_declarations_and_source_bindings(self):
        out=self.read(required=tuple(SPECS))
        self.assertEqual(out['status'],'COMPLETE_PASS',out)
        self.assertEqual(out['reported_test_methods'],282)
        self.assertEqual(out['aggregate_summary']['declared_suite_count'],18)
        self.assertEqual(out['supplemental_receipt']['reported_test_methods'],181)
        self.assertEqual((out['tests_rerun'],out['game_panels'],out['seeds_consumed']),(0,0,[]))

    def test_failed_new_logs_independently_reject(self):
        for label,spec in SPECS.items():
            with self.subTest(label=label):
                def change(m):
                    m[spec[0]]=f'Ran {spec[2]} tests in 0.1s\n\nFAILED (errors=1)\n'.encode()
                self.assert_bad(self.read(change),label)

    def test_missing_required_new_logs_is_not_silent_subset(self):
        for label,spec in SPECS.items():
            with self.subTest(label=label):
                self.assert_bad(self.read(lambda m:m.pop(spec[0]),required=(label,)),label if label=='stress_runner_existing' else spec[0])

    def test_actual_runner_source_and_scope_faults(self):
        for changes in ({'runner_sha256':'0'*64}, {'adapter_sha256':'0'*64},
                        {'test_sha256':'0'*64}, {'actual_source':True}, {'full_games':1},
                        {'failures':0}, {'tests_run':True}):
            with self.subTest(changes=changes):
                def change(m):change_json(m,'stress-runner-boundary.json',lambda d:d.update(changes))
                self.assert_bad(self.read(change),'stress_runner_boundary')

    def test_actual_queue_embedded_log_and_source_faults(self):
        for changes in ({'source_sha256':'0'*64},{'passed':False}, {'methods':True},
                        {'log':'OK\nRan 23 tests in 0.1s\n'},
                        {'log':'Ran 23 tests in 0.1s\n\nFAILED (errors=1)\n'}):
            with self.subTest(changes=changes):
                def change(m):change_json(m,'queue-copy-results.json',lambda d:d.update(changes))
                self.assert_bad(self.read(change),'queue_copy')

    def test_shared_runner_file_without_new_execution_stays_210(self):
        def change(m):
            for label,spec in SPECS.items():
                m.pop(spec[0],None)
                if spec[1]:m.pop(spec[1],None)
            def sources(d):
                for label,spec in SPECS.items():
                    if label!='stress_runner_existing':d['files'].pop(spec[3])
            change_json(m,'SOURCE-SNAPSHOT.json',sources)
        out=self.read(change)
        self.assertEqual(out['status'],'COMPLETE_PASS',out)
        self.assertEqual(out['reported_test_methods'],210)
        self.assertNotIn('stress_runner_existing',out['suites'])

    def test_three_guard_methods_are_not_recounted_in_runner_subset(self):
        def change(m):m['stress-runner-existing-tests.log']=b'Ran 5 tests in 0.1s\n\nOK\n'
        self.assert_bad(self.read(change),'stress_runner_existing')

    def test_missing_new_report_is_incomplete(self):
        for label in ('stress_runner_boundary','queue_copy'):
            with self.subTest(label=label):
                name=SPECS[label][1]
                self.assert_bad(self.read(lambda m:m.pop(name)),name)

    def test_unknown_future_log_is_still_unexamined(self):
        def change(m):m['future-suite-tests.log']=b'Ran 7 tests in 0.1s\n\nOK\n'
        out=self.read(change)
        self.assertEqual(out['status'],'INCOMPLETE',out)
        self.assertEqual(out['reported_test_methods'],282)
        self.assertIn('future-suite-tests.log',str(out['problems']))


def main():
    global ARCHIVE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();ARCHIVE=args.archive.resolve()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ArchiveContracts))
    if args.report:
        paths=[Path(__file__),Path(__file__).with_name('check_joint_receipt.py'),Path(__file__).with_name('supplemental_receipt.py')]
        source={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'git_blob':hashlib.sha1(b'blob '+str(p.stat().st_size).encode()+b'\0'+p.read_bytes()).hexdigest()} for p in paths}
        payload={'schema':'titan.runner-queue-archive-consumption.v1','artifact_id':10039313918,
            'artifact_sha256':ARTIFACT_SHA256,'sources':source,'tests_run':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'successful':result.wasSuccessful(),'reads':READS,
            'failure_details':[{'case':str(case),'text':text} for case,text in result.failures+result.errors],
            'archived_test_methods_rerun':0,'engine_transitions':0,'games':0,
            'scope':'Reader tests and detached evidence faults. No archived code executed; detached hashes are local fixture identities.'}
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':
    raise SystemExit(main())
