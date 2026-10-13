# SPDX-License-Identifier: Apache-2.0
"""Real Linux signal and archived-agent deadline boundary checks; no game panels.

Run as a standalone process because SIGALRM is process-global. The optional
runtime/engine paths reuse an existing checkout or the frozen PR9997 archive.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import types
import unittest

HERE = Path(__file__).resolve().parent
OPTIONS = None
D = None
REAL_RECEIPTS = []


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fixture(step=100):
    return {'step': step, 'day': step // 24, 'hour': step % 24, 'player': 0,
            'farms': [{'hands': [[1, 1]]}]}


class BoundaryActor:
    """Small synchronous boundary fixture, not a replacement policy."""
    def __init__(self, production_delay=0, transform_delay=0, failure=None):
        self.production_delay = production_delay
        self.transform_delay = transform_delay
        self.failure = failure
        self.calls = 0
        self.transform_calls = 0
        self.diagnostics = {}
        self.seen = []
        self.production = types.SimpleNamespace(act=self.select)
        self.action = {'farmer': ['WEST'], 'hands': [['CARE']],
                       'market': [['SELL', 'MILK', 12]]}

    def select(self, obs):
        self.calls += 1
        self.seen.append(copy.deepcopy(obs))
        time.sleep(self.production_delay)
        if self.failure is not None:
            raise self.failure
        return copy.deepcopy(self.action)

    def transform(self, obs, cfg, selected, **kwargs):
        self.transform_calls += 1
        self.seen.append(copy.deepcopy(obs))
        time.sleep(self.transform_delay)
        return copy.deepcopy(selected)


class TimerContractTests(unittest.TestCase):
    def setUp(self):
        self.previous = signal.getsignal(signal.SIGALRM)
        self.previous_timer = signal.getitimer(signal.ITIMER_REAL)
        if self.previous_timer[0]:
            self.fail('Run these SIGALRM tests in a fresh standalone process')
        self.addCleanup(self.restore)

    def restore(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous)

    def arm(self, seconds, interval=0, handler=None):
        handler = handler or (lambda _signal, _frame: None)
        signal.signal(signal.SIGALRM, handler)
        signal.setitimer(signal.ITIMER_REAL, seconds, interval)
        return handler

    def test_success_preserves_remaining_outer_timer_and_handler(self):
        handler = self.arm(.8, .7)
        actor = BoundaryActor(production_delay=.04)
        D.DeadlineFallbackAgent(actor)(fixture())
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        self.assertGreater(remaining, .4)
        self.assertLess(remaining, .78)
        self.assertAlmostEqual(interval, .7, places=5)
        self.assertIs(signal.getsignal(signal.SIGALRM), handler)
        self.assertEqual((actor.calls, actor.transform_calls), (1, 1))

    def test_body_failure_does_not_cancel_outer_timer(self):
        error = ValueError('original producer failure')
        handler = self.arm(.8)
        with self.assertRaises(ValueError) as caught:
            D.DeadlineFallbackAgent(BoundaryActor(failure=error))(fixture())
        self.assertIs(caught.exception, error)
        self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0], .4)
        self.assertIs(signal.getsignal(signal.SIGALRM), handler)

    def test_earlier_caller_alarm_propagates_original_exception(self):
        class OuterExpired(Exception):
            pass
        error = OuterExpired('caller owns this deadline')
        def outer(_signal, _frame):
            raise error
        handler = self.arm(.025, handler=outer)
        actor = BoundaryActor(production_delay=.10)
        with self.assertRaises(OuterExpired) as caught:
            D.DeadlineFallbackAgent(actor, budget_seconds=.3)(fixture())
        self.assertIs(caught.exception, error)
        self.assertEqual((actor.calls, actor.transform_calls), (1, 0))
        self.assertIs(signal.getsignal(signal.SIGALRM), handler)

    def test_same_exception_class_from_caller_is_not_our_fallback(self):
        error = D.DeadlineExceeded('outer deadline identity')
        def outer(_signal, _frame):
            raise error
        self.arm(.025, handler=outer)
        with self.assertRaises(D.DeadlineExceeded) as caught:
            D.DeadlineFallbackAgent(BoundaryActor(production_delay=.10),
                                    budget_seconds=.3)(fixture())
        self.assertIs(caught.exception, error)

    def test_same_exception_class_from_policy_is_not_swallowed(self):
        error = D.DeadlineExceeded('policy body exception')
        with self.assertRaises(D.DeadlineExceeded) as caught:
            D.DeadlineFallbackAgent(BoundaryActor(failure=error))(fixture())
        self.assertIs(caught.exception, error)

    def test_periodic_caller_ticks_and_own_timeout_both_run(self):
        ticks = []
        handler = self.arm(.01, .015, lambda s, f: ticks.append(time.monotonic()))
        actor = BoundaryActor(production_delay=.25)
        guard = D.DeadlineFallbackAgent(actor, budget_seconds=.085, reserve_seconds=.005)
        result = guard(fixture())
        self.assertGreaterEqual(len(ticks), 2)
        self.assertEqual(result, D.legal_pass(fixture()))
        self.assertEqual(guard.diagnostics['fallback_stage'], 'production')
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, .02)
        self.assertAlmostEqual(interval, .015, places=5)
        self.assertIs(signal.getsignal(signal.SIGALRM), handler)

    def test_returning_one_shot_does_not_remove_own_deadline(self):
        ticks = []
        self.arm(.01, handler=lambda s, f: ticks.append(s))
        guard = D.DeadlineFallbackAgent(BoundaryActor(production_delay=.2),
                                        budget_seconds=.055, reserve_seconds=.005)
        self.assertEqual(guard(fixture()), D.legal_pass(fixture()))
        self.assertEqual(ticks, [signal.SIGALRM])
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_handler_rearm_and_disarm_are_preserved(self):
        for rearm in (False, True):
            with self.subTest(rearm=rearm):
                ticks = []
                def handler(s, f):
                    ticks.append(s)
                    signal.setitimer(signal.ITIMER_REAL, .6 if rearm else 0)
                self.arm(.01, .01, handler)
                actor = BoundaryActor(production_delay=.055)
                D.DeadlineFallbackAgent(actor, budget_seconds=.4)(fixture())
                self.assertEqual(ticks, [signal.SIGALRM])
                remaining, interval = signal.getitimer(signal.ITIMER_REAL)
                self.assertEqual(interval, 0)
                if rearm:
                    self.assertGreater(remaining, .3)
                    self.assertLess(remaining, .59)
                else:
                    self.assertEqual(remaining, 0)
                signal.setitimer(signal.ITIMER_REAL, 0)

    def test_ignore_handler_does_not_mask_own_deadline(self):
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        signal.setitimer(signal.ITIMER_REAL, .015)
        guard = D.DeadlineFallbackAgent(BoundaryActor(production_delay=.15),
                                        budget_seconds=.055, reserve_seconds=.005)
        self.assertEqual(guard(fixture()), D.legal_pass(fixture()))
        self.assertEqual(signal.getsignal(signal.SIGALRM), signal.SIG_IGN)

    def test_default_handler_terminates_only_the_test_subprocess(self):
        code = '''import importlib.util, signal, sys, time, types
s=importlib.util.spec_from_file_location('child_adapter',sys.argv[1])
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
p=types.SimpleNamespace(act=lambda obs: (time.sleep(.15) or {'farmer':['PASS'],'hands':[],'market':[]}))
a=types.SimpleNamespace(production=p,diagnostics={},transform=lambda o,c,s,**kw:s)
signal.signal(signal.SIGALRM,signal.SIG_DFL)
signal.setitimer(signal.ITIMER_REAL,.02)
d.DeadlineFallbackAgent(a,budget_seconds=.3)({'step':1,'player':0,'farms':[{'hands':[]}]})
'''
        child = subprocess.run([sys.executable, '-c', code, str(OPTIONS.adapter)],
                               capture_output=True, timeout=3)
        self.assertEqual(child.returncode, -signal.SIGALRM, child.stderr.decode())

    def test_own_transform_timeout_preserves_selected_and_later_caller_timer(self):
        handler = self.arm(.8)
        actor = BoundaryActor(transform_delay=.15)
        guard = D.DeadlineFallbackAgent(actor, budget_seconds=.055, reserve_seconds=.005)
        self.assertEqual(guard(fixture()), actor.action)
        self.assertEqual(guard.diagnostics['fallback_stage'], 'transform')
        self.assertEqual((actor.calls, actor.transform_calls), (1, 1))
        self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0], .4)
        self.assertIs(signal.getsignal(signal.SIGALRM), handler)

    def test_no_external_timer_leaves_no_alarm(self):
        D.DeadlineFallbackAgent(BoundaryActor())(fixture())
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertIs(signal.getsignal(signal.SIGALRM), self.previous)

    def test_nested_outer_deadline_is_not_inner_fallback(self):
        inner_actor = BoundaryActor(production_delay=.2)
        inner_guard = D.DeadlineFallbackAgent(inner_actor, budget_seconds=.3)
        outer_actor = BoundaryActor()
        outer_actor.production = types.SimpleNamespace(act=lambda obs: inner_guard(obs))
        outer_guard = D.DeadlineFallbackAgent(outer_actor, budget_seconds=.055,
                                              reserve_seconds=.005)
        self.assertEqual(outer_guard(fixture()), D.legal_pass(fixture()))
        self.assertEqual(outer_guard.diagnostics['fallback_stage'], 'production')
        self.assertEqual(inner_guard.diagnostics, {})
        self.assertEqual(outer_actor.transform_calls, 0)
        self.assertEqual(inner_actor.calls, 1)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_nonmain_thread_rejected_without_disarming_caller(self):
        handler = self.arm(.8)
        failures = []
        def worker():
            try:
                D.DeadlineFallbackAgent(BoundaryActor())(fixture())
            except Exception as error:
                failures.append(error)
        thread = threading.Thread(target=worker)
        thread.start(); thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], ValueError)
        self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0], .4)
        self.assertIs(signal.getsignal(signal.SIGALRM), handler)

    def test_clock_normalized_on_copy_for_all_stages(self):
        for supplied in (None, '41'):
            with self.subTest(supplied=supplied):
                obs = fixture(); obs.update(day=2, hour=5)
                if supplied is None:
                    obs.pop('step')
                else:
                    obs['step'] = supplied
                cfg = {'turnsPerDay': 12}
                before = copy.deepcopy((obs, cfg))
                actor = BoundaryActor(); seen = []
                guard = D.DeadlineFallbackAgent(actor, before_transform=lambda o,c,s: seen.append(o['step']))
                guard(obs, cfg)
                expected = 29 if supplied is None else 41
                self.assertEqual(seen, [expected])
                self.assertEqual([o['step'] for o in actor.seen], [expected, expected])
                self.assertEqual((obs, cfg), before)

    def test_cancellation_crosses_broad_exception_handler(self):
        actor = BoundaryActor()
        swallowed = []
        def production(obs):
            actor.calls += 1
            try:
                time.sleep(.15)
            except Exception as error:
                swallowed.append(error)
            return copy.deepcopy(actor.action)
        actor.production = types.SimpleNamespace(act=production)
        guard = D.DeadlineFallbackAgent(actor, budget_seconds=.055, reserve_seconds=.005)
        self.assertEqual(guard(fixture()), D.legal_pass(fixture()))
        self.assertEqual(swallowed, [])
        self.assertEqual((actor.calls, actor.transform_calls), (1, 0))
        self.assertEqual(guard.diagnostics['fallback_stage'], 'production')

    def test_terminal_timeout_keeps_existing_liquidation(self):
        obs = {'day': 29, 'hour': 22, 'player': 0,
               'farms': [{'tiles': [[None]*10 for _ in range(10)],
                          'farmer': [4,4], 'hands': [[0,0]]}],
               'private': {'shed': {'MILK':90, 'WOOL':5},
                           'inventories': [{'MILK':10}, {'WOOL':9}]}}
        before = copy.deepcopy(obs)
        actor = BoundaryActor(production_delay=.15)
        guard = D.DeadlineFallbackAgent(actor, budget_seconds=.055, reserve_seconds=.005)
        out = guard(obs)
        self.assertEqual(out, {'farmer':['DROP'],'hands':[['PASS']],
                              'market':[['SELL','MILK',95],['SELL','WOOL',5]]})
        self.assertEqual(guard.diagnostics['fallback_stage'], 'production')
        self.assertEqual(obs, before)


class ActualAgentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = load('deadline_existing_engine_loader', OPTIONS.engine_loader)
        # Source verification before the existing cache-only path: no downloads.
        pins = {'kaggriculture.py':'3c202c7ee921da239356789e266b694635103fc4',
                'kaggriculture.json':'b354d06b742fe48402513792253f1a5c29366b20',
                'utils.py':'91c8822ee6201ba4a5a8416c7dbe34f95dd61c87'}
        for name, expected in pins.items():
            body = (OPTIONS.engine_cache/name).read_bytes()
            blob = hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
            if blob != expected:
                raise ValueError(f'Pinned engine mismatch: {name}')
        cls.engine, _ = cls.loader.get_engine(OPTIONS.engine_cache)
        cfg = {k:v.get('default') if isinstance(v,dict) else v
               for k,v in cls.engine.specification['configuration'].items()}
        cfg['seed'] = 0  # Initialization fixture only, never a scored game.
        cls.cfg = cls.loader.Struct(cfg)
        cls.state = [cls.loader.Struct(observation=cls.loader.Struct(),action={},
                                      status='ACTIVE',reward=0) for _ in range(2)]
        cls.env = cls.loader.Struct(configuration=cls.cfg,done=False,info={})
        cls.engine.interpreter(cls.state,cls.env)
        sys.path.insert(0,str(OPTIONS.runtime.resolve()))
        cls.integrated = load('deadline_real_integrated',OPTIONS.runtime/'integrated_selected.py')

    def compare(self, seat, clock_mode, *, timed=False):
        obs = copy.deepcopy(self.state[seat].observation)
        if clock_mode=='missing':
            obs.pop('step',None)
        elif clock_mode=='null':
            obs['step']=None
        else:
            obs['step']=0
        before=copy.deepcopy(obs)
        direct=self.integrated.make_agent()
        expected=direct.act(copy.deepcopy(obs),self.cfg)
        actor=self.integrated.make_agent()
        calls=[];original=actor.production.agent.act
        def counted(o):
            calls.append(o.get('step'))
            return original(o)
        actor.production.agent.act=counted
        seen=[]
        guard=D.DeadlineFallbackAgent(actor,before_transform=lambda o,c,s:seen.append(o['step']))
        previous=signal.getsignal(signal.SIGALRM)
        try:
            if timed:
                signal.signal(signal.SIGALRM,lambda s,f:None)
                signal.setitimer(signal.ITIMER_REAL,2)
            actual=guard(obs,self.cfg)
            remaining=signal.getitimer(signal.ITIMER_REAL)[0]
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,previous)
        self.assertEqual(actual,expected)
        self.assertEqual(calls,[0])
        self.assertEqual(seen,[0])
        self.assertEqual(obs,before)
        self.assertEqual(guard.diagnostics['status'],'completed')
        if timed:
            self.assertGreater(remaining,1)
        # Exercise one actual interpreter transition, not a match or win label.
        state=copy.deepcopy(self.state);env=copy.deepcopy(self.env)
        for player in (0,1):
            state[player].observation.step=0
            state[player].action=(copy.deepcopy(actual) if player==seat else
                                 {'farmer':['PASS'],'hands':[],'market':[]})
        self.engine.interpreter(state,env)
        self.assertNotIn('INVALID',[s.status for s in state])
        REAL_RECEIPTS.append({'seat':seat,'clock':clock_mode,'parent_calls':len(calls),
                             'action_equal':True,'status':[s.status for s in state],
                             'cash':[s.observation.farms[i]['money'] for i,s in enumerate(state)],
                             'action':actual,'external_timer_preserved':bool(remaining) if timed else None})

    def test_real_parent_sparse_clock_both_seats(self):
        for seat in (0,1):
            with self.subTest(seat=seat): self.compare(seat,'missing')

    def test_real_parent_null_clock_both_seats(self):
        for seat in (0,1):
            with self.subTest(seat=seat): self.compare(seat,'null')

    def test_real_parent_explicit_clock_and_caller_timer_both_seats(self):
        for seat in (0,1):
            with self.subTest(seat=seat): self.compare(seat,'explicit',timed=True)


def main():
    global OPTIONS,D
    parser=argparse.ArgumentParser(description=__doc__)
    lab=HERE.parent/'cloud-execution-lab'
    parser.add_argument('--adapter',type=Path,default=HERE/'deadline_adapter.py')
    parser.add_argument('--runtime',type=Path,default=lab)
    parser.add_argument('--engine-loader',type=Path,default=lab/'reference/evaluator/loader.py')
    parser.add_argument('--engine-cache',type=Path,default=lab/'reference/engine')
    parser.add_argument('--report',type=Path)
    OPTIONS=parser.parse_args()
    D=load('deadline_subject',OPTIONS.adapter)
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c)
                             for c in (TimerContractTests,ActualAgentContractTests)])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    paths={'adapter':OPTIONS.adapter,'tests':Path(__file__),'integrated_selected':OPTIONS.runtime/'integrated_selected.py'}
    report={'schema':'titan.deadline-caller-contract.v1','test_methods':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful(),
            'official_transitions':len(REAL_RECEIPTS),'full_games':0,
            'source_sha256':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()},
            'real_actor_receipts':REAL_RECEIPTS}
    if OPTIONS.report:
        OPTIONS.report.parent.mkdir(parents=True,exist_ok=True)
        OPTIONS.report.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='real_actor_receipts'},sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
