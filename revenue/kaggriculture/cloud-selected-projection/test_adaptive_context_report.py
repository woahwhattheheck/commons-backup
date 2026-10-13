#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic report/CI wiring fixtures, not additional policy executions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import build_combined_report as subject
import test_combined_report as retained


class AdaptiveContextReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        retained.fixture(self.path)
        snapshot = json.loads((self.path/'SOURCE-SNAPSHOT.json').read_text())
        sources = set(subject.ADAPTIVE_SOURCES.values())
        sources.update(row[2] for row in subject.ADAPTIVE_CONTEXT)
        sources.add(subject.ROOT+'cloud-observed-fills/observed_fills.py')
        snapshot['files'].update({p: {'sha256': retained.sha(p)} for p in sources})
        retained.save(self.path/'SOURCE-SNAPSHOT.json', snapshot)
        for row, count in zip(subject.ADAPTIVE_CONTEXT, (28, 29, 1)):
            (self.path/row[1]).write_text(retained.log(count))
        self.packet = {'schema': 1, 'tests': 28, 'failures': [], 'errors': [], 'skipped': [],
            'sources': {name: {'sha256': retained.sha(path)}
                        for name, path in subject.ADAPTIVE_SOURCES.items()},
            'evidence': [{'kind': 'official_interpreter',
                          'transitions': [{'step': 72}, {'step': 73}]}]}
        self.save()

    def save(self):
        retained.save(self.path/'adaptive-context-results.json', self.packet)

    def build(self):
        return subject.build_report(self.path, include_adaptive_context=True)

    def test_counts_and_transition_units_are_separate(self):
        result = self.build()
        self.assertTrue(result['successful'], result['problems'])
        self.assertEqual(result['total_tests'], 79+28+29+1)
        self.assertEqual(result['suite_count'], 9)
        self.assertEqual(result['adaptive_context_interpreter_transitions'], 2)
        self.assertEqual(result['full_games'], 0)
        self.assertEqual(result['lazy_offers_tests'], 29)
        self.assertEqual(result['adaptive_context_binding']['runtime'],
                         self.packet['sources']['runtime']['sha256'])

    def test_disabled_option_preserves_whole_legacy_result(self):
        before = subject.build_report(self.path)
        self.packet['errors'] = ['invalid']; self.save()
        (self.path/'lazy-offers-tests.log').unlink()
        self.assertEqual(subject.build_report(self.path), before)
        self.assertNotIn('adaptive_context_binding', before)

    def test_missing_each_log_is_not_a_pass(self):
        for row in subject.ADAPTIVE_CONTEXT:
            with self.subTest(suite=row[0]):
                path=self.path/row[1]; text=path.read_text(); path.unlink()
                result=self.build()
                self.assertFalse(result['successful'])
                self.assertFalse(result['complete'])
                self.assertIsNone(result['total_tests'])
                path.write_text(text)

    def test_each_source_binding_mismatch_is_detected(self):
        for name in subject.ADAPTIVE_SOURCES:
            with self.subTest(source=name):
                value=self.packet['sources'][name]['sha256']
                self.packet['sources'][name]['sha256']='0'*64; self.save()
                result=self.build()
                self.assertTrue(any('adaptive context '+name in p for p in result['problems']))
                self.packet['sources'][name]['sha256']=value
        self.save()

    def test_missing_dependency_snapshot_is_detected(self):
        path=self.path/'SOURCE-SNAPSHOT.json'; baseline=json.loads(path.read_text())
        for source in (subject.ROOT+'cloud-observed-fills/observed_fills.py',
                       subject.ROOT+'cloud-plan-continuation/continuation.py',
                       subject.ADAPTIVE+'test_lazy_offers.py'):
            with self.subTest(source=source):
                changed=copy.deepcopy(baseline); del changed['files'][source]
                retained.save(path,changed)
                self.assertFalse(self.build()['successful'])
        retained.save(path,baseline)

    def test_json_failure_error_skip_arrays_are_required_empty(self):
        original=copy.deepcopy(self.packet)
        for key in ('failures','errors','skipped'):
            for value in (None,0,['record']):
                with self.subTest(field=key,value=value):
                    self.packet=copy.deepcopy(original); self.packet[key]=value; self.save()
                    self.assertFalse(self.build()['successful'])
        self.packet=original; self.save()

    def test_count_and_schema_types_are_exact(self):
        original=copy.deepcopy(self.packet)
        for field,value in (('tests',27),('tests',True),('schema',True),('schema',2)):
            with self.subTest(field=field,value=value):
                self.packet=copy.deepcopy(original);self.packet[field]=value;self.save()
                self.assertFalse(self.build()['successful'])
        self.packet=original;self.save()

    def test_missing_or_invalid_official_transitions_are_rejected(self):
        for evidence in (None,[],[{'kind':'model'}],
                         [{'kind':'official_interpreter','transitions':[]}],
                         [{'kind':'official_interpreter','transitions':['bad']} ]):
            with self.subTest(evidence=evidence):
                self.packet['evidence']=evidence;self.save()
                self.assertFalse(self.build()['successful'])

    def test_missing_and_duplicate_json_keys_are_rejected(self):
        path=self.path/'adaptive-context-results.json';path.unlink()
        self.assertFalse(self.build()['successful'])
        path.write_text('{"schema":1,"schema":1}')
        self.assertTrue(any('duplicate JSON key' in p for p in self.build()['problems']))

    def test_skipped_failed_or_multiple_logs_are_not_passes(self):
        path=self.path/'lazy-offers-tests.log'
        for text in (retained.log(29).replace('OK','OK (skipped=1)'),
                     retained.log(29).replace('OK','FAILED (errors=1)'),
                     retained.log(29)+retained.log(29)):
            with self.subTest(text=text):
                path.write_text(text);self.assertFalse(self.build()['successful'])

    def test_cli_propagates_success_and_failure(self):
        output=self.path/'COMBINED.json'
        command=[sys.executable,subject.__file__,'--directory',str(self.path),
                 '--include-adaptive-context','--output',str(output)]
        done=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertTrue(json.loads(output.read_text())['successful'])
        self.packet['sources']['runtime']['sha256']='0'*64;self.save()
        done=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(done.returncode,1,done.stderr)
        self.assertFalse(json.loads(output.read_text())['successful'])

    def test_existing_queue_option_composes_without_counting_it_twice(self):
        # No queue evidence was supplied: requesting it must fail independently.
        result=subject.build_report(self.path,include_adaptive_context=True,include_queue_copy=True)
        self.assertFalse(result['successful'])
        self.assertTrue(result['suites']['adaptive_context']['successful'])
        self.assertTrue(result['suites']['lazy_offers']['successful'])
        self.assertEqual(result['observed_tests'],79+28+29+1)


class AdaptiveContextWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[3]
        cls.workflow=(root/'.github/workflows/titan-selected-projection.yml').read_text()

    def test_all_dependencies_trigger_and_are_checked_out(self):
        for path in (*subject.ADAPTIVE_SOURCES.values(),
                     subject.ADAPTIVE+'context_cases/test_market_context.py',
                     subject.ADAPTIVE+'test_lazy_offers.py',
                     subject.ROOT+'cloud-observed-fills/observed_fills.py'):
            with self.subTest(path=path):
                checked = str(Path(path).parent)+'/' if '/reference/engine/' in path else path
                self.assertIn('/'+checked,self.workflow)
                # Engine and core already have existing umbrella/path triggers.
                if '/reference/engine/' not in path:
                    self.assertIn("'"+path+"'",self.workflow)

    def test_each_suite_has_one_command_and_retained_log(self):
        for text in ('python3 -B '+subject.ADAPTIVE+'context_cases/test_market_context.py',
                     'python3 -B '+subject.ADAPTIVE+'test_lazy_offers.py -v',
                     'python3 -B -m unittest -v test_adaptive_context_report'):
            self.assertEqual(self.workflow.count(text),1)
        for row in subject.ADAPTIVE_CONTEXT:
            self.assertIn('tee "$RUNNER_TEMP/projection-validation/'+row[1]+'"',self.workflow)
        self.assertIn('--engine "$LAB/reference/engine/kaggriculture.py"',self.workflow)
        self.assertEqual(self.workflow.count('--include-adaptive-context'),1)

    def test_new_support_files_are_snapshotted(self):
        self.assertIn("paths.append(root/'cloud-market-game-theory/selector.py')",self.workflow)
        self.assertIn("'cloud-plan-continuation', 'cloud-observed-fills'",self.workflow)
        self.assertIn("'cloud-market-game-theory/adaptive'",self.workflow)

    def test_existing_queue_and_stress_commands_remain(self):
        for text in ('test_queue_copy.py','test_runner_guard_join.py',
                     '--include-queue-copy','--include-stress-runner'):
            self.assertIn(text,self.workflow)
        focused = re.search(r'^  focused:\n(.*?)(?=^  [A-Za-z_][\w-]*:|\Z)', self.workflow, re.M | re.S)
        self.assertIsNotNone(focused)
        self.assertEqual(focused.group(1).count('actions/upload-artifact@v4'),1)


if __name__=='__main__':
    unittest.main(verbosity=2)
