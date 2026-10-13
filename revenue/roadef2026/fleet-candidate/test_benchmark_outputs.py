# SPDX-License-Identifier: MIT
"""Actual benchmark CLI output ownership; controlled solver/checker executables.

No contest solver, official checker, network request, or algorithm panel runs.
The fixtures write/read real solutions and stats in isolated temporary folders.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BENCHMARK = Path(__file__).with_name('benchmark.py')
DETAILS = []


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(path):
    return {str(p.relative_to(path)): p.read_bytes()
            for p in path.rglob('*') if p.is_file() and not p.is_symlink()}


def executable(path, body):
    path.write_text('#!' + sys.executable + '\n' + body, encoding='utf-8')
    path.chmod(0o755)
    return path


@unittest.skipUnless(os.name == 'posix', 'CLI fixtures use POSIX executable script files')
class BenchmarkOutputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='roadef-benchmark-output-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root/'data'
        self.out = self.root/'output'
        self.log = self.root/'child-calls.jsonl'
        for name in ('setB-01', 'setB-02'):
            for suffix in ('net', 'tm', 'scenario'):
                p = self.data/'setB'/f'{name}-{suffix}.json'
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('{}\n')
        self.writer = self.solver('writer', .75)
        self.better = self.solver('better', .65)
        self.noop = self.solver('noop', .1, mode='noop')
        self.failed = self.solver('failed', .1, mode='fail')
        self.checker = executable(self.root/'checker', '''from pathlib import Path
import json, os, sys
p=Path(sys.argv[sys.argv.index('--srpaths')+1])
s=json.loads(p.read_text())
assert s['writer'] in ('writer','better','slow'), 'unknown fixture producer'
with open(os.environ['ROADEF_FIXTURE_LOG'],'a') as f:
    f.write(json.dumps({'checker':sys.argv[sys.argv.index('--max-decimal-places')+1],'path':str(p)})+'\\n')
print(json.dumps({'valid':True,'saturations':[{'t':0,'from':0,'to':1,'sat':s['sat']}],'total_cost':0}))
''')

    def solver(self, label, saturation, mode='write'):
        return executable(self.root/label, '''from pathlib import Path
import json, os, sys, time
label=%r; value=%r; mode=%r
with open(os.environ['ROADEF_FIXTURE_LOG'],'a') as f:
    f.write(json.dumps({'solver':label,'argv':sys.argv[1:]})+'\\n')
if mode=='noop':
    print('new solver wrote no output'); raise SystemExit(0)
if mode=='fail':
    print('new solver failed',file=sys.stderr); raise SystemExit(3)
if mode=='slow': time.sleep(.1)
result={'writer':label,'sat':value,'seconds':os.environ.get('SEDGE_SECONDS'),
        'rounds':os.environ.get('SEDGE_MAX_ROUNDS'),'resume':os.environ.get('CLOUD_INITIAL_SOLUTION')}
if result['resume']:
    result['incumbent']=json.loads(Path(result['resume']).read_text())
Path(sys.argv[-1]).write_text(json.dumps(result))
Path(os.environ['SEDGE_STATS']).write_text(json.dumps({'loads':[{'t':0,'from':0,'to':1,'sat':value}],
    'budget_used':[0],'accepted':1,'attempted':2}))
print('fixture current output complete')
''' % (label, saturation, mode))

    def command(self, solvers=None, instances=None, output=None, extra=()):
        cmd = [sys.executable, '-B', str(BENCHMARK), '--data', str(self.data),
               '--checker', str(self.checker), '--instances', *(instances or ['setB-01']),
               '--seconds', '.01', '--workers', '2', '--output', str(output or self.out)]
        for label, path in solvers or [('candidate', self.writer)]:
            cmd += ['--solver', label + '=' + str(path)]
        return cmd + list(extra)

    def environment(self):
        return dict(os.environ, ROADEF_FIXTURE_LOG=str(self.log),
                    SEDGE_MAX_ROUNDS='ambient-rounds', CLOUD_INITIAL_SOLUTION='/ambient/incumbent')

    def run_cli(self, **kwargs):
        return subprocess.run(self.command(**kwargs), capture_output=True, text=True,
                              env=self.environment(), timeout=15)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def assert_conflict(self, result, before, calls_before):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(tree(self.out), before)
        self.assertEqual(self.calls(), calls_before, 'must reject before starting children')

    def test_fresh_current_outputs_and_original_environment_contract(self):
        self.assert_success(self.run_cli())
        solution = json.loads((self.out/'setB-01/candidate/solution.json').read_text())
        self.assertEqual(solution['writer'], 'writer')
        self.assertEqual(solution['seconds'], '0.01')
        self.assertIsNone(solution['rounds'])
        self.assertIsNone(solution['resume'])
        report = json.loads((self.out/'summary.json').read_text())
        self.assertEqual(report['solvers']['candidate']['sha256'], digest(self.writer))
        self.assertEqual(report['results'][0][0]['solution_sha256'], digest(self.out/'setB-01/candidate/solution.json'))
        self.assertEqual([c.get('checker') for c in self.calls() if 'checker' in c], ['6','12'])

    def test_reused_output_cannot_credit_no_output_solver(self):
        self.assert_success(self.run_cli())
        before, calls = tree(self.out), self.calls()
        result = self.run_cli(solvers=[('candidate', self.noop)])
        DETAILS.append({'case':'stale_no_output', 'second_exit':result.returncode,
                        'prior_evidence_unchanged':tree(self.out)==before,
                        'new_children':len(self.calls())-len(calls)})
        self.assert_conflict(result, before, calls)

    def test_reused_output_cannot_leave_old_success_under_new_failed_run(self):
        self.assert_success(self.run_cli())
        before, calls = tree(self.out), self.calls()
        self.assert_conflict(self.run_cli(solvers=[('candidate', self.failed)]), before, calls)

    def test_stale_cell_without_top_level_receipt_is_not_used(self):
        self.assert_success(self.run_cli())
        (self.out/'experiment.json').unlink()
        (self.out/'summary.json').unlink()
        before, calls = tree(self.out), self.calls()
        self.assert_conflict(self.run_cli(solvers=[('candidate', self.noop)]), before, calls)

    def test_either_top_level_receipt_is_preserved_before_child_start(self):
        for name in ('experiment.json', 'summary.json'):
            with self.subTest(name=name):
                out = self.root/name.replace('.json', '')
                out.mkdir(); (out/name).write_bytes(b'old or interrupted evidence\n')
                calls = self.calls(); before = tree(out)
                result = self.run_cli(output=out)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tree(out), before)
                self.assertEqual(self.calls(), calls)

    def test_duplicate_solver_labels_reject_before_writes(self):
        result = self.run_cli(solvers=[('candidate', self.writer), ('candidate', self.noop)])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.out/'experiment.json').exists())

    def test_duplicate_instances_reject_before_parallel_execution(self):
        result = self.run_cli(instances=['setB-01','setB-01'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.out/'experiment.json').exists())

    def test_alias_and_ancestor_cells_do_not_overlap(self):
        for alias in ('nested/../candidate', 'candidate/nested'):
            with self.subTest(alias=alias):
                result = self.run_cli(solvers=[('candidate', self.writer), (alias,self.better)])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(), [])
                self.assertFalse((self.out/'experiment.json').exists())

    def test_output_escape_does_not_write_a_separate_tree(self):
        outside = self.root/'outside'
        result = self.run_cli(solvers=[('../../outside', self.writer)])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertFalse(outside.exists())

    def test_metadata_path_is_not_a_trial_folder(self):
        result = self.run_cli(instances=['.'],solvers=[('experiment.json', self.writer)])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.out/'experiment.json').exists())

    def test_precreated_empty_root_and_unrelated_file_are_supported(self):
        self.out.mkdir(); note=self.out/'operator-note.txt'; note.write_bytes(b'keep me')
        self.assert_success(self.run_cli())
        self.assertEqual(note.read_bytes(), b'keep me')
        self.assertTrue((self.out/'summary.json').is_file())

    def test_explicit_resume_input_and_rounds_preserved(self):
        # The resume file is allowed in the same root, but is not a trial output.
        resume=self.out/'setB-01/solution.json'; resume.parent.mkdir(parents=True)
        resume.write_text('{"retained_incumbent": 17}\n')
        before=resume.read_bytes()
        self.assert_success(self.run_cli(extra=['--resume-dir',str(self.out),'--rounds','7']))
        solution=json.loads((self.out/'setB-01/candidate/solution.json').read_text())
        self.assertEqual(solution['resume'],str(resume.resolve()))
        self.assertEqual(solution['incumbent'],{'retained_incumbent':17})
        self.assertEqual(solution['rounds'],'7')
        self.assertEqual(resume.read_bytes(),before)

    def test_parallel_distinct_instances_keep_ranking_and_input_binding(self):
        self.assert_success(self.run_cli(instances=['setB-01','setB-02'],
                                       solvers=[('first',self.writer),('second',self.better)]))
        report=json.loads((self.out/'summary.json').read_text())
        self.assertEqual(len(report['results']),2)
        for rows in report['results']:
            self.assertEqual([r['solver'] for r in rows],['first','second'])
            self.assertEqual(rows[1]['vs_first'],'win')
            self.assertEqual(rows[1]['first_difference_rank'],1)
            self.assertEqual([r['mlu_6'] for r in rows],[.75,.65])
            for row in rows:
                self.assertEqual(row['max_load_error'],0)
                self.assertEqual(row['total_cost'],0)
                self.assertEqual(row['load_count'],1)
                self.assertEqual(row['accepted_moves'],1)
                self.assertEqual(row['attempted_moves'],2)
                self.assertEqual(len(row['input_sha256']),3)
        self.assertEqual(sum('solver' in c for c in self.calls()),4)
        self.assertEqual(sum('checker' in c for c in self.calls()),8)

    def test_no_output_on_fresh_run_is_failure_not_valid_result(self):
        result=self.run_cli(solvers=[('candidate',self.noop)])
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.out/'summary.json').exists())
        self.assertFalse((self.out/'setB-01/candidate/result.json').exists())
        self.assertTrue((self.out/'setB-01/candidate/solver.stdout').exists())

    def test_symlink_alias_cannot_reuse_same_experiment(self):
        self.assert_success(self.run_cli())
        alias=self.root/'alias'; alias.symlink_to(self.out, target_is_directory=True)
        before,calls=tree(self.out),self.calls()
        self.assert_conflict(self.run_cli(output=alias,solvers=[('candidate',self.noop)]),before,calls)

    def test_competing_cli_runs_publish_exactly_one_experiment(self):
        slow=self.solver('slow',.75,mode='slow')
        commands=[self.command(solvers=[('candidate',slow)]) for _ in range(4)]
        children=[]
        try:
            children=[subprocess.Popen(c,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                       text=True,env=self.environment()) for c in commands]
            results=[(p,*p.communicate(timeout=15)) for p in children]
        finally:
            for p in children:
                if p.poll() is None:
                    p.kill();p.communicate()
        self.assertEqual(sum(p.returncode==0 for p,_,_ in results),1)
        self.assertEqual(sum('solver' in c for c in self.calls()),1)
        self.assertEqual(sum('checker' in c for c in self.calls()),2)
        self.assertTrue((self.out/'summary.json').is_file())
        DETAILS.append({'case':'concurrent_same_output','processes':4,
                        'exit_codes':[p.returncode for p,_,_ in results],
                        'solver_invocations':sum('solver' in c for c in self.calls())})


def main():
    global BENCHMARK
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--benchmark',type=Path,default=BENCHMARK)
    ap.add_argument('--report',type=Path)
    args=ap.parse_args()
    BENCHMARK=args.benchmark.resolve()
    result=unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(BenchmarkOutputTests))
    report={'schema':'roadef-benchmark-output-ownership-v1','benchmark_sha256':digest(BENCHMARK),
            'test_sha256':digest(__file__),'python':sys.version,'tests_run':result.testsRun,
            'failures':[[str(t),e] for t,e in result.failures],
            'errors':[[str(t),e] for t,e in result.errors],
            'skipped':[[str(t),e] for t,e in result.skipped], 'details':DETAILS,
            'scope':'actual benchmark CLI with controlled executable solver/checker fixtures',
            'official_solver_runs':0,'official_checker_runs':0,'algorithm_comparisons':0}
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
