# SPDX-License-Identifier: Apache-2.0
"""Contract tests for diagnostic orchestration, not game strength claims."""
import ast
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_native_ablation as a


class Tests(unittest.TestCase):
    def test_plan_is_complete_and_ordered(self):
        p = a.make_plan([9923101, 9923102], ['seed', 'funding'])
        self.assertEqual(16, len(p))
        self.assertEqual(16, len({r['id'] for r in p}))
        self.assertEqual(['base'] * 4 + ['sham'] * 4 + ['seed'] * 4 + ['funding'] * 4,
                         [r['variant'] for r in p])
        for name in ('base', 'sham', 'seed', 'funding'):
            self.assertEqual({(seed, seat) for seed in (9923101, 9923102) for seat in (0, 1)},
                             {(r['seed'], r['candidate_seat']) for r in p if r['variant'] == name})

    def test_rejects_bad_plans(self):
        for seeds, features in [([], ['seed']), ([True], ['seed']), ([1,1], ['seed']),
                                ([1], []), ([1], ['seed','seed']), ([1], ['unknown'])]:
            with self.subTest(seeds=seeds, features=features), self.assertRaises(ValueError):
                a.make_plan(seeds, features)

    def test_wrapper_changes_exactly_one_flag(self):
        for feature in (*a.FEATURES, None):
            tree = ast.parse(a.wrapper_text(Path('/tmp/path with spaces'), feature))
            assigns = [n for n in tree.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'OVERRIDES' for t in n.targets)]
            self.assertEqual(1, len(assigns))
            self.assertEqual({} if feature is None else {feature: False}, ast.literal_eval(assigns[0].value))
        with self.assertRaises(ValueError):
            a.wrapper_text(Path('/tmp'), 'budget_seconds')

    def test_trace_proxy_retains_raw_phantom_commands_and_identity(self):
        class S(dict):
            __getattr__ = dict.__getitem__
        class E:
            specification = {'x': 1}
            def interpreter(self, state, env):
                self.observed = (state, env)
                state[0].action['market'].append(['SELL', 'MILK', 1])
                return self
        engine = E(); proxy = a.TraceEngine(engine)
        raw = {'farmer': ['PLANT', 'WHEAT'], 'hands': [['PLANT', 'WHEAT']]*5,
               'market': [[]]*10 + [['HIRE']]}
        state = [S(observation={'farms': [{},{}]}, action=copy.deepcopy(raw)),
                 S(observation={'farms': [{},{}]}, action={'farmer':['PASS']})]
        env = object()
        self.assertIs(engine, proxy.interpreter(state, env))
        self.assertIs(state, engine.observed[0]); self.assertIs(env, engine.observed[1])
        self.assertEqual(raw, proxy.actions[0][0])
        self.assertEqual(11, len(proxy.actions[0][0]['market']))
        self.assertEqual(5, len(proxy.actions[0][0]['hands']))
        self.assertEqual(engine.specification, proxy.specification)

    def test_initialization_is_not_an_action(self):
        class S(dict):
            __getattr__ = dict.__getitem__
        class E:
            def interpreter(self, state, env):
                return state
        p = a.TraceEngine(E()); s=[S(observation={}, action={})]
        self.assertIs(s, p.interpreter(s, None)); self.assertEqual([], p.actions)

    def fixture(self, directory):
        plan = a.make_plan([1], ['seed'])
        tape = [[{'farmer':['PASS'], 'hands':[], 'market':[]}] * 2 for _ in range(719)]
        results = []
        for row in plan:
            name = row['id'] + '.actions.json.gz'
            (directory/name).write_bytes(gzip.compress(a.encoded(tape), mtime=0))
            results.append(dict(row, status='complete', scores=[100,100], trace_sha256='same',
                           action_sha256='same', recorded_action_callbacks=719, tape_file=name))
        return plan, results

    def test_paired_delta_sign_and_seat_orientation(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d); plan, results = self.fixture(directory)
            for row in results:
                if row['variant'] == 'seed':
                    row['scores'] = [112,103] if row['candidate_seat']==0 else [103,112]
                    row['trace_sha256']='changed'
            report = a.paired_report(plan, results, directory)
            self.assertTrue(report['sham_control_gate'])
            self.assertEqual(9, report['summary']['seed']['mean_delta_margin'])
            self.assertEqual(12, report['summary']['seed']['mean_delta_own'])
            self.assertEqual(3, report['summary']['seed']['mean_delta_rival'])

    def test_first_divergence_and_callback_count(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d); plan, results = self.fixture(directory)
            row = next(r for r in results if r['variant']=='seed' and r['candidate_seat']==0)
            path=directory/row['tape_file']; tape=json.loads(gzip.decompress(path.read_bytes()))
            tape[7][0]['farmer']=['HARVEST']; tape[8][0]['market']=[['HIRE']]
            path.write_bytes(gzip.compress(a.encoded(tape), mtime=0))
            report=a.paired_report(plan, results, directory)
            pair=next(r for r in report['pairs'] if r['seat']==0)
            self.assertEqual(7,pair['first_changed_callback'])
            self.assertEqual(2,pair['changed_candidate_callbacks'])
            self.assertEqual(['HARVEST'],pair['first_off_action']['farmer'])

    def test_failed_sham_does_not_pass_partial_control(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d); plan, results = self.fixture(directory)
            row=next(r for r in results if r['variant']=='sham')
            row['status']='failed'
            report=a.paired_report(plan,results,directory)
            self.assertFalse(report['sham_control_gate'])
            self.assertIn(row['id'],report['failed_or_unpaired_ids'])

    def test_changed_sham_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);plan,results=self.fixture(directory)
            next(r for r in results if r['variant']=='sham')['trace_sha256']='different'
            self.assertFalse(a.paired_report(plan,results,directory)['sham_control_gate'])

    def test_missing_duplicate_unplanned_rows_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);plan,results=self.fixture(directory)
            for rows in (results[:-1], results+[results[0]], results+[dict(results[0],id='unknown')]):
                with self.assertRaises(ValueError):a.paired_report(plan,rows,directory)

    def test_result_coordinates_must_match_plan_before_pair_math(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d); plan, results=self.fixture(directory)
            target=next(r for r in results if r['variant']=='seed' and r['candidate_seat']==0)
            poisons=(('variant','sham'),('seed',2),('candidate_seat',1),('candidate_seat',True))
            for field, value in poisons:
                poisoned=copy.deepcopy(results)
                row=next(r for r in poisoned if r['id']==target['id'])
                row[field]=value
                with self.subTest(field=field,value=value), self.assertRaisesRegex(
                        ValueError, 'Result coordinates disagree with PLAN'):
                    a.paired_report(plan,poisoned,directory)

    def test_failure_and_negative_delta_are_retained(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);plan,results=self.fixture(directory)
            rows=[r for r in results if r['variant']=='seed']
            rows[0]['scores']=[80,100];rows[1]['status']='failed'
            report=a.paired_report(plan,results,directory)
            self.assertEqual(-20,report['summary']['seed']['mean_delta_margin'])
            self.assertEqual(1,report['summary']['seed']['complete_pairs'])
            self.assertEqual(2,report['summary']['seed']['scheduled_pairs'])
            self.assertIn(rows[1]['id'],report['failed_or_unpaired_ids'])

    def test_incomplete_action_tape_cannot_be_a_full_game(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);plan,results=self.fixture(directory)
            results[-1]['recorded_action_callbacks']=718
            with self.assertRaises(ValueError):a.paired_report(plan,results,directory)

    def test_unknown_source_manifest_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'SOURCE.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'source manifest'):a.verify_package(root)

    def _minimal_authenticated_package(self, root: Path) -> bytes:
        config = {feature: True for feature in a.FEATURES}
        files = {
            'main.py': b'ORIGINAL_MAIN = True\n',
            'TITAN-CONFIG.json': json.dumps(config, sort_keys=True).encode(),
            'checks/reference/evaluator/evaluate.py': (
                b"class Engine:\n    pass\n"
                b"def get_engine(cache, loader):\n    return Engine(), {'engine':'captured'}\n"
                b"def play(proxy, specs, cache, loader, seed, seat, **kwargs):\n"
                b"    return {'status':'complete','scores':[1,1],'trace_sha256':'captured'}\n"
            ),
            'checks/reference/evaluator/loader.py': b'# captured loader\n',
        }
        for index in range(105):
            files[f'dummy/{index:03d}.txt'] = f'captured-{index}\n'.encode()
        self.assertEqual(109, len(files))
        runtime = {}
        for relative, data in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            runtime[relative] = {'bytes': len(data), 'sha256': a.digest(data)}
        source = a.encoded({'runtime': runtime})
        (root/'SOURCE.json').write_bytes(source)
        return source

    def test_run_job_uses_captured_bytes_after_whole_package_path_swap(self):
        with tempfile.TemporaryDirectory() as d:
            parent=Path(d); root=parent/'package'; root.mkdir()
            source=self._minimal_authenticated_package(root)
            tape=parent/'actions.json.gz'
            job={'id':'base-7-0','variant':'base','seed':7,'candidate_seat':0,
                 'root':str(root),'tape':str(tape)}
            original_capture=a.capture_package
            moved=parent/'captured-original'

            def capture_then_replace(path):
                pins, captured=original_capture(path)
                Path(path).rename(moved)
                root.mkdir()
                (root/'checks/reference/evaluator').mkdir(parents=True)
                (root/'main.py').write_text('EVIL_MAIN = True\n')
                (root/'checks/reference/evaluator/evaluate.py').write_text(
                    "raise RuntimeError('reopened attacker evaluator')\n")
                return pins, captured

            with patch.object(a,'SOURCE_SHA256',a.digest(source)), \
                 patch.object(a,'capture_package',side_effect=capture_then_replace):
                result=a.run_job(job)
            self.assertEqual('complete',result['status'])
            self.assertEqual('captured',result['trace_sha256'])
            self.assertEqual(a.digest(b'ORIGINAL_MAIN = True\n'),result['candidate_entry_sha256'])
            self.assertTrue(tape.is_file())

    def test_numeric_json_rejects_nonfinite(self):
        for x in (float('nan'),float('inf'),-float('inf')):
            with self.assertRaises(ValueError):a.encoded({'score':x})


if __name__ == '__main__':
    unittest.main()
