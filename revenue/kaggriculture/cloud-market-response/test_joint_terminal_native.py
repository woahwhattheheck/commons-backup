# SPDX-License-Identifier: MIT
"""New history -> POLY -> native interpreter composition, no full games/seeds.

Set TITAN_ENGINE_DIR to the existing engine artifact's engine/ directory and
TITAN_TERMINAL_INPUTS_PATH to POLY's unchanged terminal_inputs.py.
"""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
import importlib.util
import ast
import random
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace as NS
from typing import Any, Callable
import unittest
from unittest.mock import patch

from joint_terminal_history import build_joint_terminal_scenarios as build


def register_module(stack, name, module):
    """Restore only our temporary registration, not unrelated imported modules."""
    missing = object()
    original = sys.modules.get(name, missing)
    sys.modules[name] = module
    def restore():
        if original is missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original
    stack.callback(restore)


def load(stack, name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    register_module(stack, name, module)
    spec.loader.exec_module(module)
    return module


def configure(stack):
    """Optional native resources are required only while this class executes.

    Missing configuration is a named skip during ordinary test discovery.
    Explicitly configured missing or invalid files remain failures. Cleanup is
    registered before any engine import, including partially failed setup.
    """
    global flow, m, terminal, TERMINAL_PATH
    required = ('TITAN_ENGINE_DIR', 'TITAN_TERMINAL_INPUTS_PATH')
    absent = [name for name in required if not os.environ.get(name)]
    if absent:
        raise unittest.SkipTest('native inputs not configured: ' + ', '.join(absent))
    engine_dir = Path(os.environ['TITAN_ENGINE_DIR'])
    TERMINAL_PATH = Path(os.environ['TITAN_TERMINAL_INPUTS_PATH'])
    flow_path = Path(os.environ.get('TITAN_FLOW_PATH', Path(__file__).with_name('flow.py')))
    flow = load(stack, 'joint_native_flow', flow_path)
    # Extract the exact official seed utility, avoiding unrelated package
    # imports. Post-initialization fixtures do not invoke it or draw a seed.
    pkg = ModuleType('kaggle_environments')
    pkg.__path__ = [str(engine_dir)]
    register_module(stack, 'kaggle_environments', pkg)
    utils_tree = ast.parse((engine_dir/'utils.py').read_text())
    seed_fn = next(n for n in utils_tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == 'resolve_episode_seed')
    utils_module = ModuleType('kaggle_environments.utils')
    utils_module.__dict__.update(Any=Any, Callable=Callable, random=random)
    exec(compile(ast.Module(body=[seed_fn], type_ignores=[]),
                 str(engine_dir/'utils.py'), 'exec'), utils_module.__dict__)
    register_module(stack, 'kaggle_environments.utils', utils_module)
    m = load(stack, 'joint_native_mechanics', engine_dir/'kaggriculture.py')
    terminal = load(stack, 'joint_poly_terminal_inputs', TERMINAL_PATH)


CFG = dict(episodeSteps=720, boardSize=10, turnsPerDay=24, shedCapacity=100,
           maxMarketOrdersPerTurn=10, farmHandCostMult=1)
NOW = 718
COUNTS = dict(training_transitions=0, inferred_exact_intervals=0,
              terminal_reference_transitions=0, terminal_table_cells=0,
              fixed_slot_controls=0)
DETAILS = []


def private(shed):
    return dict(shed=deepcopy(shed), seeds={}, inventories=[{}],
                farmerPos=[0, 0], handPositions=[])


def fixture(player=0, step=NOW, own_stock=None, inventory=10000, money=1000.0):
    farms = [m._new_farm(10, money) for _ in range(2)]
    market = m._new_market()
    market['inventory'] = {p: inventory for p in m.PRODUCTS}
    m._refresh_prices(market)
    return dict(player=player, step=step, farms=farms,
                market=market,
                town=dict(unlocked_shops=[]), private=private(own_stock or {}))


def transition(obs, own_action, rival):
    """Independent full interpreter entry, including workers/market/terminal status."""
    me = obs['player']
    shared = {k: deepcopy(obs[k]) for k in ('farms', 'market', 'town')}
    states = []
    for player in range(2):
        priv = deepcopy(obs['private']) if player == me else private(rival['shed'])
        action = deepcopy(own_action) if player == me else dict(farmer=['PASS'], hands=[], market=deepcopy(rival['market']))
        states.append(NS(observation=NS(**shared, private=priv, player=player, step=obs['step']),
                         action=action, status='ACTIVE', reward=0))
    env = NS(configuration=NS(**CFG), done=False, steps=[None]*(obs['step']+1))
    m.interpreter(states, env)
    next_obs = deepcopy(obs)
    next_obs.update(step=obs['step']+1, **shared)
    next_obs['private'] = deepcopy(states[me].observation.private)
    return states, next_obs


def trained(player=0, repeated=None):
    """Infer history from prior native public inventory transitions only."""
    h = flow.FlowHistory(period=24, window=5, minimum=3)
    lots = [dict(CARROT=12, WOOL=7), dict(EGG=20, WOOL=3), dict(CARROT=8, EGG=10, WOOL=4)]
    if repeated is not None:
        lots = [deepcopy(repeated) for _ in range(3)]
    for lag, lot in zip((3, 2, 1), lots):
        obs = fixture(player, NOW-24*lag, {'CARROT': 2, 'EGG': 1})
        own = dict(farmer=['PASS'], hands=[], market=[['SELL','CARROT',2],['SELL','EGG',1]])
        rival = dict(shed=lot, market=[['SELL',p,q] for p,q in lot.items()])
        _, current = transition(obs, own, rival)
        COUNTS['training_transitions'] += 1
        for product in m.PRODUCTS:
            interval = flow.infer_flow(obs, current, {'CARROT':2,'EGG':1}, product, CFG, m,
                                      lambda *args: 0)
            # These constructed same-hour transitions have no town/EOD stage.
            if product in flow.OPERATING:
                assert interval is None
            else:
                assert interval.exact and interval.lower == lot.get(product, 0)
                COUNTS['inferred_exact_intervals'] += 1
            h.add(interval)
    return h


def family(h):
    return build(h, m.PRODUCTS, NOW,
        slot_templates=[dict(id='interior', origin='constructed ordered hypothesis, not inferred',
                             slots=['WOOL', None, 'CARROT', 'EGG','WHEAT','FERTILIZER']),
                        dict(id='reverse', origin='second explicit slot hypothesis',
                             slots=['CARROT','EGG', None,'WOOL','FERTILIZER','WHEAT'])],
        unobserved_lots=[dict(id='quiet-operating', origin='explicit zero-stock hypothesis',
                             stock={'WHEAT':0,'FERTILIZER':0}),
                        dict(id='operating-lot', origin='explicit operating-stock alternative',
                             stock={'WHEAT':3,'FERTILIZER':2})])


class NativeJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        resources = ExitStack()
        cls.addClassCleanup(resources.close)
        configure(resources)
        cls.histories = {seat: trained(seat) for seat in (0,1)}

    def test_actual_source_identities(self):
        b = TERMINAL_PATH.read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),
                         '2eae54ea4c62a83048ba8c5d69b9bbd48af2caa7')
        self.assertEqual(m.PRODUCTS, ['WHEAT','CARROT','TOMATO','STRAWBERRY','MELON','EGG','MILK','WOOL','FERTILIZER'])

    def test_inferred_prior_joint_vectors_are_preserved(self):
        f = family(self.histories[0])
        self.assertTrue(f['ready'])
        self.assertEqual(f['joint_support'], 3)
        self.assertEqual(len(f['scenarios']), 12)
        self.assertEqual({(s['shed'].get('CARROT',0),s['shed'].get('EGG',0),s['shed'].get('WOOL',0))
                          for s in f['scenarios']}, {(12,0,7),(0,20,3),(8,10,4)})

    def test_all_generated_cells_match_full_interpreter_both_seats(self):
        for seat in (0,1):
            for inventory in (0, 95, 500):
                obs = fixture(seat, own_stock={'CARROT':7,'EGG':11,'WOOL':5}, inventory=inventory, money=80.5)
                action = dict(farmer=['PASS'], hands=[], market=[['SELL','EGG',11],
                              ['BUY_SEED','CARROT',1],['SELL','WOOL',5],['SELL','CARROT',7]])
                original = deepcopy((obs,action))
                f = family(self.histories[seat])
                packet = terminal.build_terminal_inputs(m,obs,CFG,action,post_unit_observation=obs,
                                                        scenarios=f['scenarios'],max_plans=4)
                self.assertTrue(packet['complete'])
                self.assertEqual(packet['source']['hypothesis_family'], 'caller-supplied-sale-hypotheses')
                self.assertEqual(packet['fallback_action'], action)
                rivals = {s['id']:s for s in packet['scenarios']}
                COUNTS['terminal_table_cells'] += packet['native_market_calls']
                for receipt in packet['document']['receipts']:
                    self.assertTrue(receipt['done'])
                    states,_ = transition(obs,receipt['own_action'],rivals[receipt['scenario']])
                    COUNTS['terminal_reference_transitions'] += 1
                    self.assertEqual((receipt['own_cash'],receipt['rival_cash']),
                                     (states[seat].reward,states[1-seat].reward))
                    self.assertEqual(receipt['own_shed_after'], states[seat].observation.private['shed'])
                    self.assertEqual(receipt['own_seeds_after'], states[seat].observation.private['seeds'])
                    self.assertEqual(receipt['own_action']['market'][1], action['market'][1])
                    self.assertTrue(all(s.status=='DONE' for s in states))
                self.assertEqual((obs,action),original)
                DETAILS.append(dict(kind='table',seat=seat,inventory=inventory,
                                    cells=packet['native_market_calls'],complete=True))

    def test_zero_slots_have_an_actual_cash_consequence(self):
        for seat in (0,1):
            h = trained(seat, {'EGG':20})
            f = build(h,m.PRODUCTS,NOW,
                      slot_templates=[dict(id='egg-at-two',origin='explicit gap discriminator',slots=[None,None,'EGG'])],
                      unobserved_lots=[dict(id='quiet',origin='explicit hypothesis',stock={'WHEAT':0,'FERTILIZER':0})])
            self.assertTrue(f['ready'])
            scenario=f['scenarios'][0]
            self.assertEqual(scenario['market'],[[],[],['SELL','EGG',20]])
            obs=fixture(seat,own_stock={'EGG':10})
            action=dict(farmer=['PASS'],hands=[],market=[['SELL','EGG',5],['SELL','EGG',5]])
            packet=terminal.build_terminal_inputs(m,obs,CFG,action,post_unit_observation=obs,
                                                  scenarios=f['scenarios'],max_plans=1)
            COUNTS['terminal_table_cells'] += packet['native_market_calls']
            correct,_=transition(obs,action,scenario)
            compacted=deepcopy(scenario);compacted['market']=[o for o in scenario['market'] if o]
            wrong,_=transition(obs,action,compacted)
            COUNTS['fixed_slot_controls'] += 2
            pair=(correct[seat].reward,correct[1-seat].reward)
            bad=(wrong[seat].reward,wrong[1-seat].reward)
            self.assertEqual(pair,(1474.0,1897.0))
            self.assertEqual(bad,(1458.0,1915.0))
            self.assertEqual((packet['document']['receipts'][0]['own_cash'],
                              packet['document']['receipts'][0]['rival_cash']),pair)
            DETAILS.append(dict(kind='fixed-slot-negative',seat=seat,preserved=pair,compacted=bad,
                                margin_difference=(pair[0]-pair[1])-(bad[0]-bad[1])))

    def test_cell_exhaustion_preserves_incomplete_family_and_fallback(self):
        f=family(self.histories[0]);obs=fixture(own_stock={'EGG':3})
        action=dict(farmer=['PASS'],hands=[],market=[['SELL','EGG',3]])
        p=terminal.build_terminal_inputs(m,obs,CFG,action,post_unit_observation=obs,
                                        scenarios=f['scenarios'],max_cells=1)
        COUNTS['terminal_table_cells'] += p['native_market_calls']
        self.assertFalse(p['complete'])
        self.assertEqual(p['status'],'cell_limit')
        self.assertEqual(p['fallback_action'],action)
        self.assertEqual(len(p['document']['receipts']),p['required_cells'])
        self.assertEqual(sum(r['done'] for r in p['document']['receipts']),1)
        self.assertTrue(all(r['own_cash'] is None for r in p['document']['receipts'] if not r['done']))

    def test_deadline_does_not_publish_a_completed_subset(self):
        obs=fixture(own_stock={'EGG':3});action=dict(farmer=['PASS'],hands=[],market=[])
        p=terminal.build_terminal_inputs(m,obs,CFG,action,post_unit_observation=obs,
                  scenarios=family(self.histories[0])['scenarios'],deadline=time.perf_counter()-1)
        self.assertEqual(p['status'],'deadline')
        self.assertEqual(p['native_market_calls'],0)
        self.assertEqual(p['fallback_action'],action)
        self.assertFalse(any(r['done'] for r in p['document']['receipts']))

    def test_composed_path_does_not_call_units_twice(self):
        obs=fixture(own_stock={'EGG':3});action=dict(farmer=['PASS'],hands=[],market=[])
        with patch.object(m,'_apply_unit_action',side_effect=AssertionError('duplicate unit call')):
            p=terminal.build_terminal_inputs(m,obs,CFG,action,post_unit_observation=obs,
                          scenarios=family(self.histories[0])['scenarios'],max_plans=1)
        COUNTS['terminal_table_cells'] += p['native_market_calls']
        self.assertTrue(p['complete'])


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(NativeJoinTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                skipped=len(result.skipped),skip_reasons=[reason for _, reason in result.skipped],
                counts=COUNTS,details=DETAILS,full_games=0,new_game_seeds=0,
                limits='Constructed state integration, not reached-state accuracy, calibrated probability, or gameplay strength.')
    if os.environ.get('TITAN_JOINT_REPORT'):
        Path(os.environ['TITAN_JOINT_REPORT']).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))
    sys.exit(not result.wasSuccessful())
