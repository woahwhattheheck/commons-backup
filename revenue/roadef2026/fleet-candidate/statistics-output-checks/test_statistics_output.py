#!/usr/bin/env python3
"""Native solver output-ownership and statistics-publication regressions.

All inputs are copied into per-test temporary directories. No contest panel,
network request, long-running search, or provided input is modified.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

BINARY: Path
REFERENCE: Path
FIXTURES: Path

class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='solver-artifacts-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.net = self.root/'network.json'
        self.tm = self.root/'traffic.json'
        self.scenario = self.root/'scenario.json'
        for dst, name in ((self.net,'joint-net.json'),(self.tm,'joint-tm.json'),
                          (self.scenario,'joint-scenario.json')):
            shutil.copyfile(FIXTURES/name, dst)
        self.out = self.root/'solution.json'
        self.stats = self.root/'stats.json'

    def run_solver(self, *, binary=None, output=None, stats=None, initial=None,
                   file_limit=None, rounds=3, env_extra=None):
        env = {k:v for k,v in os.environ.items()
               if not k.startswith(('SEDGE_', 'FLEET_', 'CLOUD_INITIAL_SOLUTION'))}
        env.update(SEDGE_SECONDS='30', SEDGE_MAX_ROUNDS=str(rounds),
                   FLEET_DIRECTED='1', FLEET_JOINT='1')
        if stats is not None: env['SEDGE_STATS'] = str(stats)
        if initial is not None: env['CLOUD_INITIAL_SOLUTION'] = str(initial)
        if env_extra: env.update(env_extra)
        def limit():
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
        return subprocess.run([str(binary or BINARY), str(self.net), str(self.tm),
                               str(self.scenario), str(output or self.out)],
                              env=env, cwd=self.root, capture_output=True, timeout=10,
                              preexec_fn=limit if file_limit is not None else None)

    def assert_rejected(self, result):
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b'Loaded ', result.stderr, 'alias detected after solver work started')
        self.assertIn(b'aliases', result.stderr)

    def assert_solution(self, path=None):
        data=json.loads((path or self.out).read_bytes())
        self.assertEqual(set(data), {'srpaths'})
        self.assertIsInstance(data['srpaths'], list)
        return data

    def test_stats_disabled_preserves_normal_solution(self):
        result=self.run_solver()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assert_solution()
        self.assertFalse(self.stats.exists())

    def test_separate_stats_preserve_all_fields_and_solution(self):
        result=self.run_solver(stats=self.stats)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assert_solution()
        stats=json.loads(self.stats.read_bytes())
        self.assertGreaterEqual(stats['attempted'],0)
        self.assertIn('loads',stats)
        self.assertFalse(Path(str(self.stats)+'.tmp').exists())

    def test_same_output_existing_is_rejected_before_changes(self):
        saved=b'{"srpaths":[],"saved":true}\n'; self.out.write_bytes(saved)
        self.assert_rejected(self.run_solver(stats=self.out))
        self.assertEqual(self.out.read_bytes(),saved)

    def test_same_output_nonexistent_is_rejected_before_creation(self):
        self.assert_rejected(self.run_solver(stats=self.out))
        self.assertFalse(self.out.exists())

    def test_normalized_relative_alias_is_rejected(self):
        (self.root/'sub').mkdir()
        self.assert_rejected(self.run_solver(stats='sub/../solution.json'))
        self.assertFalse(self.out.exists())

    def test_symlink_stats_to_solution_is_rejected(self):
        saved=b'previous solution'; self.out.write_bytes(saved)
        self.stats.symlink_to(self.out.name)
        self.assert_rejected(self.run_solver(stats=self.stats))
        self.assertTrue(self.stats.is_symlink())
        self.assertEqual(self.out.read_bytes(),saved)

    def test_hardlink_stats_to_solution_is_rejected(self):
        saved=b'previous solution'; self.out.write_bytes(saved)
        os.link(self.out,self.stats)
        self.assert_rejected(self.run_solver(stats=self.stats))
        self.assertEqual(self.out.read_bytes(),saved)
        self.assertEqual(self.stats.read_bytes(),saved)

    def test_stats_cannot_replace_any_problem_input(self):
        for path in (self.net,self.tm,self.scenario):
            with self.subTest(path=path.name):
                saved=path.read_bytes()
                self.assert_rejected(self.run_solver(stats=path))
                self.assertEqual(path.read_bytes(),saved)
                self.assertFalse(self.out.exists())

    def test_stats_input_aliases_are_rejected(self):
        for kind in ('symbolic','hard'):
            with self.subTest(kind=kind):
                alias=self.root/(kind+'.stats'); saved=self.net.read_bytes()
                if kind=='symbolic': alias.symlink_to(self.net.name)
                else: os.link(self.net,alias)
                self.assert_rejected(self.run_solver(stats=alias))
                self.assertEqual(self.net.read_bytes(),saved)
                self.assertFalse(self.out.exists())

    def test_output_cannot_replace_problem_input(self):
        for path in (self.net,self.tm,self.scenario):
            with self.subTest(path=path.name):
                saved=path.read_bytes()
                self.assert_rejected(self.run_solver(output=path))
                self.assertEqual(path.read_bytes(),saved)

    def test_output_input_aliases_are_rejected(self):
        for kind in ('symbolic','hard'):
            with self.subTest(kind=kind):
                alias=self.root/(kind+'.solution'); saved=self.net.read_bytes()
                if kind=='symbolic': alias.symlink_to(self.net.name)
                else: os.link(self.net,alias)
                self.assert_rejected(self.run_solver(output=alias))
                self.assertEqual(self.net.read_bytes(),saved)

    def test_output_staging_cannot_truncate_input(self):
        stage=Path(str(self.out)+'.tmp'); stage.symlink_to(self.net.name)
        saved=self.net.read_bytes()
        self.assert_rejected(self.run_solver())
        self.assertEqual(self.net.read_bytes(),saved)
        self.assertTrue(stage.is_symlink())

    def test_stats_staging_cannot_truncate_input(self):
        stage=Path(str(self.stats)+'.tmp'); stage.symlink_to(self.net.name)
        saved=self.net.read_bytes()
        self.assert_rejected(self.run_solver(stats=self.stats))
        self.assertEqual(self.net.read_bytes(),saved)
        self.assertFalse(self.out.exists())

    def test_crossed_staging_roles_are_rejected(self):
        for output,stats in ((self.out,Path(str(self.out)+'.tmp')),
                             (Path(str(self.stats)+'.tmp'),self.stats)):
            with self.subTest(output=output.name,stats=stats.name):
                self.assert_rejected(self.run_solver(output=output,stats=stats))
                self.assertFalse(output.exists())
                self.assertFalse(stats.exists())

    def test_stats_cannot_replace_resume_input(self):
        initial=self.root/'initial.json'; initial.write_bytes(b'{"srpaths":[]}\n')
        saved=initial.read_bytes()
        self.assert_rejected(self.run_solver(stats=initial,initial=initial))
        self.assertEqual(initial.read_bytes(),saved)
        self.assertFalse(self.out.exists())

    def test_in_place_resume_remains_supported(self):
        self.out.write_bytes(b'{"srpaths":[]}\n')
        result=self.run_solver(stats=self.stats, initial=self.out)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assert_solution()
        self.assertTrue(json.loads(self.stats.read_bytes())['resumed'])

    def test_separate_resume_remains_supported(self):
        initial=self.root/'initial.json'; initial.write_bytes(b'{"srpaths":[]}\n')
        saved=initial.read_bytes()
        result=self.run_solver(stats=self.stats,initial=initial)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(initial.read_bytes(),saved)
        self.assert_solution()

    def test_missing_statistics_parent_is_reported(self):
        stats=self.root/'missing'/'stats.json'
        result=self.run_solver(stats=stats)
        self.assertNotEqual(result.returncode,0,result.stderr)
        self.assertIn(b'Cannot write',result.stderr)
        self.assert_solution()
        self.assertFalse(stats.exists())

    def test_statistics_staging_open_failure_preserves_previous(self):
        saved=b'{"previous":true}\n'; self.stats.write_bytes(saved)
        Path(str(self.stats)+'.tmp').mkdir()
        result=self.run_solver(stats=self.stats)
        self.assertNotEqual(result.returncode,0,result.stderr)
        self.assertIn(b'Cannot write',result.stderr)
        self.assertEqual(self.stats.read_bytes(),saved)
        self.assert_solution()

    def test_statistics_rename_failure_is_reported(self):
        self.stats.mkdir(); (self.stats/'marker').write_text('preserve')
        result=self.run_solver(stats=self.stats)
        self.assertNotEqual(result.returncode,0,result.stderr)
        self.assertTrue(self.stats.is_dir())
        self.assertEqual((self.stats/'marker').read_text(),'preserve')
        self.assert_solution()

    def test_file_limit_preserves_previous_statistics(self):
        saved=b'{"previous":true}\n'; self.stats.write_bytes(saved)
        result=self.run_solver(stats=self.stats,file_limit=256)
        self.assertNotEqual(result.returncode,0,result.stderr)
        self.assertIn(b'Failed writing',result.stderr)
        self.assertEqual(self.stats.read_bytes(),saved)
        self.assert_solution()

    def test_empty_statistics_path_is_reported_before_work(self):
        result=self.run_solver(stats='')
        self.assertNotEqual(result.returncode,0,result.stderr)
        self.assertNotIn(b'Loaded ',result.stderr)
        self.assertFalse(self.out.exists())

    def test_success_replaces_existing_statistics(self):
        self.stats.write_bytes(b'old statistics')
        result=self.run_solver(stats=self.stats)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIsInstance(json.loads(self.stats.read_bytes())['loads'],list)
        self.assertFalse(Path(str(self.stats)+'.tmp').exists())

    def test_fixed_work_matches_original_solver(self):
        for rounds in (0,3,12):
            for joint in ('0','1'):
                with self.subTest(rounds=rounds,joint=joint):
                    refout=self.root/f'original-{rounds}-{joint}.json'
                    refstats=self.root/f'original-{rounds}-{joint}.stats.json'
                    old=self.run_solver(binary=REFERENCE,output=refout,stats=refstats,
                                        rounds=rounds,env_extra={'FLEET_JOINT':joint})
                    new=self.run_solver(stats=self.stats,rounds=rounds,env_extra={'FLEET_JOINT':joint})
                    self.assertEqual(old.returncode,0,old.stderr)
                    self.assertEqual(new.returncode,0,new.stderr)
                    self.assertEqual(refout.read_bytes(),self.out.read_bytes())
                    a=json.loads(refstats.read_bytes()); b=json.loads(self.stats.read_bytes())
                    a.pop('seconds'); b.pop('seconds')
                    self.assertEqual(a,b)


def main():
    global BINARY,REFERENCE,FIXTURES
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--reference-binary',type=Path,required=True)
    parser.add_argument('--fixtures',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if args.report and (args.report.exists() or args.report.is_symlink()):
        parser.error('report already exists; choose a new output path')
    BINARY=args.binary.resolve(strict=True); REFERENCE=args.reference_binary.resolve(strict=True)
    FIXTURES=args.fixtures.resolve(strict=True)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ArtifactTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    record={'scope':'native generated-file regressions; not a public-instance benchmark',
            'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),
            'reference_sha256':hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
            'tests_run':result.testsRun, 'successful':result.wasSuccessful(),
            'failures':[{'test':str(t),'traceback':tb} for t,tb in result.failures],
            'errors':[{'test':str(t),'traceback':tb} for t,tb in result.errors],
            'skipped':[(str(t),why) for t,why in result.skipped]}
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        with args.report.open('x', encoding='utf8') as handle:
            handle.write(json.dumps(record,indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':
    raise SystemExit(main())
