"""Regression tests for final diagnostic retention in the existing evaluator.

Run: python -m unittest discover -s . -p test_final_diagnostics.py -v
EVALUATOR_UNDER_TEST selects another source file. The real-engine tests use
only the three pinned local engine files and the retained original loader.
Fault injections are not evidence of an observed production game failure.
"""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
TARGET = Path(os.environ.get('EVALUATOR_UNDER_TEST', HERE/'evaluate.py')).resolve()
ORIGINAL = Path(os.environ.get('EVALUATOR_ORIGINAL', HERE/'evaluate.original.py')).resolve()
CACHE = Path(os.environ.get('EVALUATOR_ENGINE_CACHE', HERE/'engine')).resolve()
LOADER = Path(os.environ.get('EVALUATOR_ENGINE_LOADER', CACHE/'original_loader.py')).resolve()

def load(path):
    spec = importlib.util.spec_from_file_location('eval_diagnostics_'+hashlib.sha256(str(path).encode()).hexdigest()[:12],path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def config():
    return {'configuration': {'episodeSteps': 2, 'turnsPerDay': 1}}


def outcome_without_metrics(value):
    return {key: val for key,val in value.items() if key not in {'actors','wall_seconds','driver_cpu_seconds'}}


class FinalDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load(TARGET)

    def initial_failure(self, farms=Ellipsis, extra=None, exception=None):
        original = exception or RuntimeError('primary-interpreter-failure')
        def interpreter(state, env):
            env.configuration.seed = None
            if farms is not Ellipsis:
                state[0].observation.farms = farms
            if extra is not None:
                state[0].observation.extra = extra
            raise original
        engine = SimpleNamespace(specification=config(),interpreter=interpreter)
        return self.mod.play(engine, [], HERE, LOADER, 0, 0)

    def assertPrimary(self, result):
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['failure'],{'kind':'engine_error','seat':None,'step':0,
                                         'error':'RuntimeError: primary-interpreter-failure'})
        self.assertIsNone(result['scores'])
        json.dumps(result,allow_nan=False)

    def test_missing_money_does_not_replace_primary_error(self):
        result = self.initial_failure([{}, {'money': 12}])
        self.assertPrimary(result)
        self.assertEqual(result['bank_snapshot'],[None,12.0])
        self.assertEqual(result['finalization_errors'][0]['seat'],0)

    def test_null_farms_does_not_replace_primary_error(self):
        result=self.initial_failure(None)
        self.assertPrimary(result)
        self.assertEqual(result['bank_snapshot'],[None,None])

    def test_absent_farms_is_unknown_not_zero(self):
        result=self.initial_failure()
        self.assertPrimary(result)
        self.assertEqual(result['bank_snapshot'],[None,None])

    def test_short_farm_list_preserves_known_balance(self):
        result=self.initial_failure([{'money':17}])
        self.assertPrimary(result)
        self.assertEqual(result['bank_snapshot'],[17.0,None])

    def test_nonfinite_balances_remain_json_safe(self):
        for balance in (float('nan'),float('inf'),-float('inf')):
            with self.subTest(balance=balance):
                result=self.initial_failure([{'money':balance},{'money':8}])
                self.assertPrimary(result)
                self.assertEqual(result['bank_snapshot'],[None,8.0])
                self.assertIsNone(result['trace_sha256'])
                self.assertEqual(result['trace_prefix_sha256'],hashlib.sha256().hexdigest())

    def test_conversion_overflow_does_not_replace_primary_error(self):
        result=self.initial_failure([{'money':10**400},{'money':4}])
        self.assertPrimary(result)
        self.assertEqual(result['bank_snapshot'],[None,4.0])
        self.assertIn('OverflowError',result['finalization_errors'][0]['error'])

    def test_unencodable_metadata_preserves_real_balances(self):
        result=self.initial_failure([{'money':-3.5},{'money':'4.25'}],object())
        self.assertPrimary(result)
        self.assertEqual(result['bank_snapshot'],[-3.5,4.25])
        self.assertIsNone(result['trace_sha256'])
        self.assertEqual([r['stage'] for r in result['finalization_errors']],['final_observation_trace'])

    def test_circular_metadata_is_a_named_diagnostic_failure(self):
        cycle=[];cycle.append(cycle)
        result=self.initial_failure([{'money':3},{'money':4}],cycle)
        self.assertPrimary(result)
        self.assertIsNone(result['trace_sha256'])
        self.assertIn('Circular reference',result['finalization_errors'][0]['error'])

    def test_healthy_primary_failure_has_no_new_fields(self):
        result=self.initial_failure([{'money':3},{'money':4}])
        self.assertPrimary(result)
        self.assertNotIn('finalization_errors',result)
        self.assertNotIn('trace_prefix_sha256',result)
        expected=[{'farms':[{'money':3},{'money':4}]},{}]
        self.assertEqual(result['trace_sha256'],hashlib.sha256(self.mod.encoded(expected)).hexdigest())

    def test_primary_keyboard_interrupt_identity_survives(self):
        original=KeyboardInterrupt('stop-witness')
        with self.assertRaises(KeyboardInterrupt) as raised:
            self.initial_failure(None,object(),original)
        self.assertIs(raised.exception,original)

    def test_primary_system_exit_identity_survives(self):
        original=SystemExit(47)
        with self.assertRaises(SystemExit) as raised:
            self.initial_failure(None,object(),original)
        self.assertIs(raised.exception,original)

    def test_diagnostic_messages_remain_bounded(self):
        result=self.initial_failure([{'money':'x'*5000},{'money':3}])
        self.assertPrimary(result)
        self.assertTrue(all(len(row['error'])<=1000 for row in result['finalization_errors']))

    def test_failed_report_is_writable_and_summarizable(self):
        result=self.initial_failure([{'money':float('nan')},{'money':8}])
        result['opponent']='boundary-fixture'
        summary=self.mod.summarize([result])
        self.assertEqual(summary['boundary-fixture']['failed'],1)
        self.assertEqual(summary['boundary-fixture']['completed'],0)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json'
            self.mod.write_report(path,{'games':[result],'summary':summary})
            saved=json.loads(path.read_text())
        self.assertEqual(saved['games'][0]['failure'],result['failure'])
        self.assertIsNone(saved['games'][0]['trace_sha256'])

    def test_unrelated_functions_and_play_body_are_unchanged(self):
        if not ORIGINAL.is_file(): self.skipTest('exact original source not supplied')
        def normalize(path):
            tree=ast.parse(path.read_text())
            for node in tree.body:
                if isinstance(node,ast.FunctionDef) and node.name=='play':
                    node.body[-2].finalbody=node.body[-2].finalbody[:4]
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(normalize(TARGET),normalize(ORIGINAL))


@unittest.skipUnless(all((CACHE/name).is_file() for name in ('kaggriculture.py','kaggriculture.json','utils.py')) and LOADER.is_file(),
                     'retained pinned engine/loader not materialized')
class RealEngineDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod=load(TARGET)
        cls.engine, cls.hashes=cls.mod.get_engine(CACHE,LOADER)
        cls.original_interpreter=cls.engine.interpreter

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='titan-diagnostics-tests-')
        self.root=Path(self.directory.name)
        self.agent=self.root/'pass_agent.py'
        self.agent.write_text('def agent(obs, cfg):\n    return {"farmer": ["PASS"], "hands": [], "market": []}\n')

    def tearDown(self):
        self.directory.cleanup()

    def run_engine(self,module=None,seat=0,mutate=None,exception=None,timeout=1.0):
        mod=module or self.mod
        count=0
        def wrapped(state,env):
            nonlocal count
            type(self).original_interpreter(state,env)
            count+=1
            if mutate is not None: mutate(state,env,count)
            if exception is not None and count==2: raise exception
        engine=SimpleNamespace(specification=self.engine.specification,interpreter=wrapped)
        result=mod.play(engine,[str(self.agent)]*2,CACHE,LOADER,0,seat,action_timeout=timeout,
                        startup_timeout=5.0,game_timeout=10.0,episode_steps=2)
        return result,count

    def test_pinned_official_sources_are_unchanged(self):
        self.assertEqual(set(self.mod.verify_sources(CACHE)),{'kaggriculture.py','kaggriculture.json','utils.py'})

    def test_healthy_official_transition_matches_original_both_seats(self):
        if not ORIGINAL.is_file():self.skipTest('exact original source not supplied')
        for seat in (0,1):
            with self.subTest(seat=seat):
                result,count=self.run_engine(seat=seat)
                baseline,_=self.run_engine(module=load(ORIGINAL),seat=seat)
                self.assertEqual(count,2)  # initialization + one shortened terminal transition
                self.assertEqual(result['status'],'complete')
                self.assertEqual(outcome_without_metrics(result),outcome_without_metrics(baseline))
                self.assertNotIn('finalization_errors',result)
                # Existing close() may SIGKILL after its 100 ms graceful window.
                self.assertTrue(all(actor['exit_code'] in (0,-self.mod.signal.SIGKILL)
                                    and actor['final_resource_sample']=='wait4' for actor in result['actors']))
                self.assertTrue(all(actor['calls']==1 for actor in result['actors']))

    def test_error_after_real_transition_keeps_primary_and_known_balance(self):
        def corrupt(state,env,count):
            if count==2: del state[0].observation.farms[0]['money']
        result,count=self.run_engine(mutate=corrupt,exception=RuntimeError('after-real-transition'))
        self.assertEqual(count,2)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['failure']['error'],'RuntimeError: after-real-transition')
        self.assertIsNone(result['bank_snapshot'][0])
        self.assertTrue(math.isfinite(result['bank_snapshot'][1]))
        # Existing close() may SIGKILL after its 100 ms graceful window.
        self.assertTrue(all(actor['exit_code'] in (0,-self.mod.signal.SIGKILL)
                            and actor['final_resource_sample']=='wait4' for actor in result['actors']))
        json.dumps(result,allow_nan=False)

    def test_trace_only_failure_keeps_terminal_scores_but_not_complete_label(self):
        def corrupt(state,env,count):
            if count==2: state[0].observation.extra=object()
        result,count=self.run_engine(mutate=corrupt)
        self.assertEqual(result['status'],'failed')
        self.assertTrue(all(math.isfinite(value) for value in result['scores']))
        self.assertEqual(result['failure']['kind'],'finalization_error')
        self.assertIsNone(result['trace_sha256'])
        self.assertEqual(len(result['trace_prefix_sha256']),64)
        result['opponent']='fixture'
        self.assertEqual(self.mod.summarize([result])['fixture']['completed'],0)
        json.dumps(result,allow_nan=False)

    def test_completed_transition_prefix_hash_is_retained_exactly(self):
        captured=[]
        def corrupt(state,env,count):
            if count==2:
                captured.append({'step':0,'actions':[s.action for s in state],
                                 'bank':[float(f['money']) for f in state[0].observation.farms]})
                state[0].observation.extra=object()
        result,_=self.run_engine(mutate=corrupt)
        expected=hashlib.sha256(self.mod.encoded(captured[0])).hexdigest()
        self.assertEqual(result['trace_prefix_sha256'],expected)
        self.assertIsNone(result['trace_sha256'])

    def test_real_worker_request_serialization_failure_keeps_transport_record(self):
        def corrupt(state,env,count):
            if count==1: state[0].observation.extra=float('nan')
        result,count=self.run_engine(mutate=corrupt)
        self.assertEqual(count,1)
        self.assertEqual(result['failure']['kind'],'protocol_error')
        rpc=result['failure']['rpc_failure']
        self.assertEqual(rpc['request']['disposition'],'serialization_failed')
        self.assertEqual(rpc['transport']['request_bytes_written'],0)
        self.assertIsNone(rpc['worker_call_seconds'])
        self.assertIsNone(result['trace_sha256'])
        self.assertEqual(len(result['actors']),2)
        # Existing close() may SIGKILL after its 100 ms graceful window.
        self.assertTrue(all(actor['exit_code'] in (0,-self.mod.signal.SIGKILL)
                            and actor['final_resource_sample']=='wait4' for actor in result['actors']))
        json.dumps(result,allow_nan=False)

    def test_real_timeout_failure_and_failed_request_are_unchanged(self):
        self.agent.write_text('import time\ndef agent(obs, cfg):\n    time.sleep(10)\n    return {}\n')
        result,count=self.run_engine(timeout=0.03)
        self.assertEqual(count,1)
        self.assertEqual(result['failure']['kind'],'timeout')
        self.assertEqual(result['failure']['rpc_failure']['request']['disposition'],'complete')
        self.assertEqual(len(result['trace_sha256']),64)
        self.assertNotIn('finalization_errors',result)
        self.assertTrue(all(actor['exit_code'] is not None for actor in result['actors']))

    def test_current_cli_saves_failed_games_and_original_error(self):
        wrapper=self.root/'run_fault_cli.py'
        wrapper.write_text('''import importlib.util,sys
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location("eval_cli_under_test",sys.argv.pop(1))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
get=m.get_engine
def source_engine(*args,**kwargs):
    engine,hashes=get(*args,**kwargs)
    original=engine.interpreter
    def interpret(state,env):
        original(state,env)
        state[0].observation.farms=None
        raise RuntimeError("cli-original-error")
    return SimpleNamespace(specification=engine.specification,interpreter=interpret),hashes
m.get_engine=source_engine
raise SystemExit(m.main())
''')
        output=self.root/'report.json'
        command=[sys.executable,str(wrapper),str(TARGET),'--engine-dir',str(CACHE),'--loader',str(LOADER),
                 '--candidate',str(self.agent),'--opponent','fixture='+str(self.agent),
                 '--seeds','0','--episode-steps','2','--output',str(output)]
        process=subprocess.run(command,capture_output=True,text=True,timeout=15)
        self.assertEqual(process.returncode,1,process.stderr)
        self.assertNotIn('Traceback',process.stderr)
        saved=json.loads(output.read_text())
        progress=json.loads(output.with_name('report.json.progress.json').read_text())
        self.assertEqual(saved['games'],progress['games'])
        self.assertEqual(saved['summary']['fixture']['failed'],2)
        self.assertEqual(saved['progress']['recorded_games'],2)
        self.assertEqual(saved['progress']['state'],'complete')  # invocation completed, both games failed
        self.assertEqual(saved['invocation_id'],progress['invocation_id'])
        for game in saved['games']:
            self.assertEqual(game['status'],'failed')
            self.assertEqual(game['failure']['error'],'RuntimeError: cli-original-error')
            self.assertEqual(game['bank_snapshot'],[None,None])
        self.assertIn('SUMMARY',process.stdout)

if __name__=='__main__':
    unittest.main(verbosity=2)
