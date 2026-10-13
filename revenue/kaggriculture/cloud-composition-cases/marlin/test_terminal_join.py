# SPDX-License-Identifier: Apache-2.0
"""New terminal/ordered-SELL composition cases; not an old suite rerun.

Requires existing pinned source paths, not a network fetch or environment install.
Official interpreter frames are synthetic and seed-free. No full game is played.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from terminal_join import TerminalActionJoin, IntegratedTerminalAgent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class Struct(dict):
    def __getattr__(self, key):
        try: return self[key]
        except KeyError: raise AttributeError(key) from None
    def __setattr__(self, key, value): self[key] = value


PASS = {'farmer': ['PASS'], 'hands': [], 'market': []}
RECEIPTS = []
TRANSITIONS = 0


def frame(step, seat=0, *, at=(3, 4), carry=4, shed=0, capacity=100, hand=False):
    cfg = Struct({k: v.get('default') if isinstance(v, dict) else v
                  for k, v in K.specification['configuration'].items()})
    cfg.update(shedCapacity=capacity)
    farms = [K._new_farm(10, 1000) for _ in range(2)]
    private = [K._new_private() for _ in range(2)]
    farms[seat]['farmer'] = list(at)
    private[seat]['inventories'][0] = {'EGG': carry} if carry else {}
    private[seat]['shed']['EGG'] = shed
    if hand:
        farms[seat]['hands'] = [[4, 4]]
        private[seat]['inventories'].append({'MILK': 2})
    private[1-seat]['shed']['EGG'] = 2
    market, town = K._new_market(), K._new_town()
    state = [Struct(observation=Struct(farms=farms, private=private[i],
                                      market=market, town=town, player=i,
                                      day=step//24, hour=step%24, step=step),
                    action=deepcopy(PASS), status='ACTIVE', reward=0.0) for i in range(2)]
    return state, Struct(configuration=cfg, done=False, info={}), cfg


def advance(state, env, own, seat, step, rival=None):
    global TRANSITIONS
    for s in state: s.observation.step = step
    state[seat].action = deepcopy(own)
    state[1-seat].action = deepcopy(rival or PASS)
    K.interpreter(state, env)
    TRANSITIONS += 1
    for s in state: s.observation.step = step + 1
    return deepcopy(state[seat].observation)


class TerminalJoinTests(unittest.TestCase):
    def make_join(self):
        return TerminalActionJoin(OSPREY, ORDERED.OrderedSelectedSell())

    def test_matching_route_deposits_718_wrong_tape_does_not(self):
        for seat in (0, 1):
            state, env, cfg = frame(717, seat)
            obs = deepcopy(state[seat].observation)
            before = deepcopy(obs)
            join = self.make_join()
            selected = join.transform(obs, cfg, PASS, own_future_actions=[PASS, PASS])
            self.assertEqual(selected['farmer'], ['EAST'])
            self.assertEqual(obs, before)
            packet = join.last_packet
            actual = [e for e in packet['projection']['stock_events'] if e['product'] == 'EGG']
            self.assertEqual([(e['step'], e['quantity_delta']) for e in actual], [(718, 4)])
            wrong = ORDERED.OrderedSelectedSell().prepare(obs, cfg, join.last_selected,
                        future_actions={718: deepcopy(PASS)}, end_step=718)
            self.assertEqual(wrong['projection']['stock_events'], [])
            # Execute each complete continuation in the official interpreter.
            negative, nenv = deepcopy(state), deepcopy(env)
            advance(state, env, selected, seat, 717, {'farmer':['PASS'],'hands':[], 'market':[['SELL','EGG',2]]})
            advance(negative, nenv, selected, seat, 717, {'farmer':['PASS'],'hands':[], 'market':[['SELL','EGG',2]]})
            action = join.transform(deepcopy(state[seat].observation), cfg, PASS)
            advance(state, env, action, seat, 718)
            advance(negative, nenv, PASS, seat, 718)
            self.assertTrue(all(s.status == 'DONE' for s in state))
            own, rival = state[0].observation.farms[seat]['money'], state[0].observation.farms[1-seat]['money']
            nown, nrival = negative[0].observation.farms[seat]['money'], negative[0].observation.farms[1-seat]['money']
            self.assertGreater(own, nown)
            self.assertEqual(rival, nrival)
            self.assertEqual(sum(state[seat].observation.private['inventories'][0].values()), 0)
            RECEIPTS.append({'case':'matching-route-vs-wrong-tape','seat':seat,
                             'own':own,'rival':rival,'wrong_tape_own':nown,
                             'wrong_tape_rival':nrival,'cash_delta':own-nown,
                             'projection_events':actual,'decisions':2})

    def test_wrong_tape_withholding_fails_true_deposit_capacity(self):
        state, env, cfg = frame(716, at=(3, 4), carry=4, shed=4, capacity=5)
        state[0].observation.town['unlocked_shops'] = ['BAKERY']
        obs = deepcopy(state[0].observation); join = self.make_join()
        correct = join.transform(obs, cfg, PASS)
        wrong_execution = ORDERED.OrderedSelectedSell()
        wrong = wrong_execution.transform(obs, cfg, join.last_selected,
                    future_actions={717: deepcopy(PASS), 718: deepcopy(PASS)}, end_step=718)
        self.assertEqual(correct['market'], [['SELL', 'EGG', 4]])
        self.assertEqual(wrong['market'], [['SELL', 'EGG', 1]])
        from selected_action_sell import ProjectionLedger
        packet = join.last_packet
        ledger = ProjectionLedger(obs, cfg, join.last_selected, packet['post_unit_shed'],
                                  packet['projection'], None, None, 8)
        bad_plan = wrong_execution.diagnostics['chosen']['plan']
        self.assertFalse(ledger.feasible('EGG', bad_plan))
        # A fixed continuation, NOT receding-horizon T05 gameplay: replay the
        # promised DROP after the wrong-tape withholding. It loses two eggs.
        advance(state, env, wrong, 0, 716)
        advance(state, env, {'farmer':['DROP'], 'hands':[], 'market':[]}, 0, 717)
        remaining = (sum(state[0].observation.private['shed'].values()) +
                     sum(sum(i.values()) for i in state[0].observation.private['inventories']))
        self.assertEqual(8 - 1 - remaining, 2)
        RECEIPTS.append({'case':'wrong-tape-withholding-capacity', 'seat':0,
                         'step':716, 'correct_sell_now':4, 'wrong_sell_now':1,
                         'wrong_plan':bad_plan, 'true_ledger_accepts_wrong_plan':False,
                         'fixed_drop_lost_eggs':2,
                         'interpretation':'fixed-continuation mechanical probe, not replan/game performance'})

    def test_failed_prepare_does_not_consume_planner_queue(self):
        state, env, cfg = frame(716, at=(2, 4)); join = self.make_join()
        original = join.execution.prepare
        def fail(*args, **kwargs): raise ValueError('injected packet failure')
        join.execution.prepare = fail
        with self.assertRaisesRegex(ValueError, 'injected packet failure'):
            join.transform(deepcopy(state[0].observation), cfg, PASS)
        self.assertIsNone(join.planner.last_step)
        self.assertIsNone(join.planner.queues)
        join.execution.prepare = original

    def test_drop_on_last_action_sells_current_not_future_stock(self):
        state, env, cfg = frame(718, at=(4, 4), carry=4)
        obs = deepcopy(state[0].observation); join = self.make_join()
        action = join.transform(obs, cfg, PASS)
        self.assertEqual(join.last_packet['post_unit_shed']['EGG'], 4)
        self.assertEqual(join.last_packet['projection']['stock_events'], [])
        advance(state, env, action, 0, 718)
        self.assertEqual(state[0].observation.private['shed']['EGG'], 0)
        self.assertGreater(state[0].reward, 1000)

    def test_one_step_too_late_keeps_cargo_unsold(self):
        state, env, cfg = frame(718, at=(3, 4), carry=4)
        join = self.make_join(); action = join.transform(deepcopy(state[0].observation), cfg, PASS)
        self.assertEqual(join.last_packet['projection']['stock_events'], [])
        advance(state, env, action, 0, 718)
        self.assertEqual(state[0].reward, 1000)
        self.assertEqual(state[0].observation.private['inventories'][0]['EGG'], 4)

    def test_ordered_workers_shared_small_capacity(self):
        state, env, cfg = frame(717, at=(4, 4), carry=3, shed=3, capacity=5, hand=True)
        join = self.make_join()
        for step in (717, 718):
            for s in state: s.observation.step = step
            action = join.transform(deepcopy(state[0].observation), cfg, PASS)
            advance(state, env, action, 0, step)
            self.assertLessEqual(sum(state[0].observation.private['shed'].values()), 5)
        self.assertEqual(sum(sum(i.values()) for i in state[0].observation.private['inventories']), 0)
        self.assertGreater(state[0].reward, 1000)

    def test_packet_binding_and_planner_fork_are_not_mutated(self):
        state, env, cfg = frame(716, at=(2, 4))
        join = self.make_join(); obs=deepcopy(state[0].observation)
        join.transform(obs, cfg, PASS)
        self.assertEqual(join.planner.last_step, 716)
        self.assertEqual(join.last_future[717]['farmer'], ['EAST'])
        self.assertIn(join.last_future[718]['farmer'][0], ('DROP','PLACE'))
        self.assertEqual(join.execution.diagnostics['unit_projection_calls'], 0)
        self.assertEqual(obs['farms'][0]['farmer'], [2, 4])

    def test_source_real_arlene_supplied_action_parent_called_once(self):
        state, env, cfg = frame(717)
        parent = OSPREY.seller.parent.Agent()
        calls=[]; original = parent.act
        class Producer:
            one_way=True; last_day=29; plans={}
            def __init__(self): self.agent=parent
            def act(self, obs):
                calls.append(obs['step']); return original(obs)
        # The dispatch harness supplies the actual frozen Arlene and actual
        # ordered seller. It is not a claim to execute cap production here.
        integrated = SimpleNamespace(production=Producer(), controller=parent,
                                     execution=ORDERED.OrderedSelectedSell(), sell=True)
        integrated.transform = lambda obs,cfg,action,**kw: deepcopy(action)
        agent = IntegratedTerminalAgent(integrated, OSPREY)
        action=agent.act(deepcopy(state[0].observation), cfg)
        self.assertEqual(calls,[717]); self.assertEqual(action['farmer'],['EAST'])
        self.assertEqual(agent.diagnostics['parent_calls'],0)

    def test_prefix_disabled_and_active_errand_delegate_exact_action(self):
        state, env, cfg=frame(697); calls=[]
        selected={'farmer':['PASS'],'hands':[],'market':[['HIRE']]}
        class Producer:
            one_way=True; last_day=29; plans={}
            def act(self, obs): calls.append('parent'); return deepcopy(selected)
        integrated=SimpleNamespace(production=Producer(), controller=None,
                                   execution=ORDERED.OrderedSelectedSell(),sell=True)
        def unchanged(obs,cfg,action,**kw):
            calls.append('transform'); return deepcopy(action)
        integrated.transform=unchanged
        agent=IntegratedTerminalAgent(integrated, OSPREY)
        self.assertEqual(agent.act(state[0].observation,cfg),selected)
        self.assertEqual(calls,['parent','transform'])
        for s in state: s.observation.update(step=717,day=29,hour=21)
        agent.terminal_enabled=False
        self.assertEqual(agent.act(state[0].observation,cfg),selected)
        agent.terminal_enabled=True; integrated.production.plans={0:{'phase':'go'}}
        self.assertEqual(agent.act(state[0].observation,cfg),selected)
        self.assertEqual(calls,['parent','transform']*3)

    def test_omitted_step_and_sell_disabled(self):
        state,env,cfg=frame(718,seat=1,at=(4,4));obs=deepcopy(state[1].observation)
        obs.pop('step');join=self.make_join()
        action=join.transform(obs,cfg,PASS,sell=False)
        self.assertEqual(join.planner.last_step,718)
        self.assertEqual(join.diagnostics['status'],'terminal_without_sell')
        self.assertIsNone(join.last_packet)
        advance(state,env,action,1,718)
        self.assertGreater(state[1].reward,1000)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lab',type=Path,required=True)
    parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--engine-cache',type=Path,required=True)
    parser.add_argument('--loader',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    global K, OSPREY, ORDERED
    # Existing loader reads only these already-present, pinned source files.
    for name in ('kaggriculture.py','kaggriculture.json','utils.py'):
        if not (args.engine_cache/name).is_file(): raise FileNotFoundError(name)
    expected_engine = {
        'kaggriculture.py':'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
        'kaggriculture.json':'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
        'utils.py':'537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b'}
    for name, expected in expected_engine.items():
        if hashlib.sha256((args.engine_cache/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Unpinned engine source: '+name)
    loader=load(args.loader,'marlin_existing_loader')
    K, hashes=loader.get_engine(args.engine_cache)
    sys.path.insert(0,str(args.lab)); ORDERED=load(args.lab/'ordered_selected_sell.py','marlin_ordered')
    OSPREY=load(args.composition,'marlin_osprey')
    before=time.perf_counter()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TerminalJoinTests))
    sources={'terminal_join.py':HERE/'terminal_join.py','test_terminal_join.py':Path(__file__),
             'composition.py':args.composition,'terminal.py':OSPREY.TERMINAL_FILE,
             'ordered_selected_sell.py':args.lab/'ordered_selected_sell.py',
             'selected_action_sell.py':args.lab/'selected_action_sell.py',
             'selected_sell_core.py':args.lab/'selected_sell_core.py',
             'projection.py':args.lab/'reference/ordered-feasibility/atlas/projection.py',
             'mechanics.py':args.lab/'mechanics.py',
             'decision.py':args.lab/'reference/decision/decision.py',
             'arlene.py':args.lab/'reference/next-panel/vendor/arlene.py',
             'scheduler.py':OSPREY.SELL_DIR/'scheduler.py', 'loader.py':args.loader}
    report={'successful':result.wasSuccessful(),'test_methods':result.testsRun,
            'errors':len(result.errors),'failures':len(result.failures),
            'test_seconds':time.perf_counter()-before,'official_transitions':TRANSITIONS,
            'full_games':0,'game_seeds_used':[], 'fixture_kind':'explicit seed-free synthetic terminal frames',
            'sources':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sources.items()},
            'engine':hashes,'receipts':RECEIPTS,
            'scope':'Actual T05 planner + ordered SELL + official interpreter; dispatch contracts separate. Not full integrated cap-agent gameplay.'}
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__': raise SystemExit(main())
