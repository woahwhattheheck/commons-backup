# SPDX-License-Identifier: Apache-2.0
"""Native stock-prefix tests: full helper, exact caller, unmodified full engine.

Synthetic mechanism fixtures are not a whole-agent or competitive economic gate.
The official initialization seed helper is loaded from its original AST, not mocked.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import random
import sys
import tempfile
import types
from typing import Any, Callable
import unittest
from unittest.mock import patch

import port_operating_stock_prefix as port
import test_operating_stock_current_delegate as oracle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ENGINE = ROOT / 'checks/reference/engine/kaggriculture.py'
CALLER = (HERE / 'current_caller.fixture.txt').read_text()


def module_from(source, name):
    module = types.ModuleType(name)
    exec(compile(source, name, 'exec'), module.__dict__)
    return module


ORIGINAL = (ROOT / 'operating_stock.py').read_text()
NATIVE = port.port_helper(ORIGINAL)
OLD = module_from(ORIGINAL, 'old_stock')
NEW = module_from(NATIVE, 'native_stock')
RUNTIME = 'class TitanAgent:\n' + CALLER
NATIVE_RUNTIME = port.port_runtime(RUNTIME)


def propose(module, fixture):
    obs, cfg, selected, farm, private, route = fixture
    return module.protect_operating_stock(oracle.Mechanics(), obs, cfg, selected,
                                          farm, private, route, ())


def fixture(cap=10, tail=(), future=None):
    f = list(oracle.fixture())
    k = max(1, int(cap))
    f[1]['maxMarketOrdersPerTurn'] = cap
    f[2]['market'] = [['SELL', 'FERTILIZER', 2]] + [[] for _ in range(k - 1)] + deepcopy(list(tail))
    if future is not None:
        f[5][future]['market'] = [[] for _ in range(k)] + deepcopy(list(tail))
        f[2]['market'] = f[2]['market'][:k]
    return f


TAILS = (
    [['HIRE']], [['BUY_PRODUCT', 'FERTILIZER', 99]], [['SELL', 'FERTILIZER', 99]],
    [['BUY_ANIMAL', 'COW', 99]], [['BUY_SEED', 'BERRY', 99999]], [['BUY_LAND']],
    [None, [], {'unparsed': ['HIRE']}, 8, ['SELL', 'FERTILIZER', 'invalid']],
)
CAPS = (-2, 0, 1, 2, 3, 10)


class NativeHelperTests(unittest.TestCase):
    def test_authentic_inputs(self):
        self.assertEqual(port.git_blob(ORIGINAL.encode()), port.HELPER_BEFORE)
        self.assertEqual(port.git_blob(CALLER.rstrip('\n').encode()), port.CALLER_BEFORE)
        self.assertEqual(port.git_blob(NATIVE.encode()), '6a511194c53a5a3baab112160d52d97f2e271472')

    def test_only_three_fertilizer_functions_changed(self):
        allowed = {'protect_operating_stock', '_bonus_water_service', '_operating_stock_commitments'}
        for node in ast.parse(ORIGINAL).body:
            if isinstance(node, ast.FunctionDef) and node.name not in allowed:
                self.assertEqual(port._function(ORIGINAL, node.name)[2], port._function(NATIVE, node.name)[2])
        for name in allowed:
            self.assertNotEqual(port._function(ORIGINAL, name)[2], port._function(NATIVE, name)[2])
        # No imports, globals, feature keys or extra controller functions added.
        self.assertEqual([getattr(x, 'name', None) for x in ast.parse(ORIGINAL).body],
                         [getattr(x, 'name', None) for x in ast.parse(NATIVE).body])

    def test_current_and_future_suffix_invariance_and_input_custody(self):
        for cap in CAPS:
            k = max(1, cap)
            control = propose(OLD, fixture(k))
            self.assertTrue(control[1]['changed'])
            for tail in TAILS:
                for future in (None, 25, 30, 48):
                    with self.subTest(cap=cap, tail=tail, future=future):
                        f = fixture(cap, tail, future)
                        before = deepcopy(f)
                        out, report = propose(NEW, f)
                        self.assertTrue(report['changed'], report)
                        self.assertEqual(out['market'][:k], control[0]['market'])
                        self.assertEqual(report, control[1])
                        self.assertEqual(out['market'][k:], f[2]['market'][k:])
                        self.assertEqual(len(out['market']), len(f[2]['market']))
                        self.assertEqual({x:y for x,y in out.items() if x != 'market'},
                                         {x:y for x,y in f[2].items() if x != 'market'})
                        self.assertEqual(f, before)

    def test_noop_returns_original_and_does_not_compact_empty_slots(self):
        for cap in CAPS:
            f = fixture(cap)
            k = max(1, cap)
            f[2]['market'] = [[] for _ in range(k)] + [['SELL', 'FERTILIZER', 2]]
            out, report = propose(NEW, f)
            self.assertIs(out, f[2])
            self.assertEqual(report, {'changed': False, 'reason': 'no_fertilizer_sale'})
        f = fixture(3)
        f[2]['market'] = [[], ['SELL', 'FERTILIZER', 2], []] + [['HIRE']]
        out, report = propose(NEW, f)
        self.assertTrue(report['changed'])
        self.assertEqual(out['market'], [[], ['SELL', 'FERTILIZER', 1], [], ['HIRE']])

    def test_below_cap_exact_parity_for_existing_admissions_and_vetoes(self):
        cases = [[], [['HIRE']], [['BUY_PRODUCT','FERTILIZER',99]], [['BUY_SEED','BERRY',2]]]
        count = 0
        for cap in (4, 10):
            for current in cases:
                for future in cases:
                    f = fixture(cap)
                    f[2]['market'] = [['SELL','FERTILIZER',2]] + deepcopy(current)
                    f[5][25]['market'] = deepcopy(future)
                    self.assertEqual(propose(NEW, f), propose(OLD, f))
                    count += 1
        self.assertEqual(count, 32)

    def test_active_hire_and_replenishment_remain_vetoes(self):
        f = fixture(2)
        f[2]['market'][1] = ['HIRE']
        self.assertEqual(propose(NEW, f)[1]['reason'], 'current_hiring_boundary')
        f = fixture(2)
        f[5][25]['market'] = [['BUY_PRODUCT', 'FERTILIZER', 1]]
        self.assertEqual(propose(NEW, f)[1]['reason'], 'intervening_requested_replenishment')
        f = fixture(2)
        f[5][25]['market'] = [['HIRE']]
        self.assertFalse(propose(NEW, f)[1]['changed'])

    def test_commitment_cap_normalizes_like_engine_with_no_sale_credit(self):
        for cap in CAPS:
            k = max(1, cap)
            row = {'market': [['BUY_SEED','BERRY',2]] + [[] for _ in range(k-1)] + [['HIRE']]}
            report = NEW._operating_stock_commitments(oracle.Mechanics(),
                {'maxMarketOrdersPerTurn':cap}, {'money':5, 'hands':[]}, [(30,row)])
            self.assertEqual(report['required_cash'], 2)
            self.assertEqual(report['cash_after_commitments'], 3)
            self.assertEqual(report['future_sale_cash_credit'], 0)
            self.assertEqual(len(report['commitments']), 1)

    def test_bonus_service_cap_zero_cannot_ignore_active_hire(self):
        f = fixture(0)
        obs, cfg, selected, farm, private, route = f
        farm['money'] = 0
        route[30]['market'] = [['HIRE']]
        obligations = [{'step':26, 'position':(4,4), 'crop':'BERRY', 'bonus_day':2}]
        _, reason = NEW._bonus_water_service(oracle.Mechanics(), obs, cfg, selected,
                                             farm, route, obligations, ())
        self.assertEqual(reason, 'bonus_day_hire_not_funded')
        # Same exact active row is invisible to predecessor's cap-zero slice.
        self.assertIsNone(OLD._bonus_water_service(oracle.Mechanics(), obs, cfg, selected,
                                                  farm, route, obligations, ())[1])

    def test_predecessor_negative_controls(self):
        failures = []
        for tail, future in ((TAILS[0],None),(TAILS[1],None),(TAILS[2],None),
                             (TAILS[0],25),(TAILS[1],25)):
            f = fixture(10, tail, future)
            old, old_report = propose(OLD, f)
            new, new_report = propose(NEW, f)
            self.assertTrue(new_report['changed'])
            failures.append(old != new or old_report != new_report)
        self.assertEqual(failures, [True]*5)

    def test_each_read_or_rewrite_mutant_is_detected(self):
        variants = (
            ("orders = (selected.get('market') or [])[:max_orders]",
             "orders = selected.get('market') or []", fixture(10, TAILS[0])),
            ("for o in route[step].get('market', [])[:max_orders]",
             "for o in route[step].get('market', [])", fixture(10, TAILS[0],25)),
            ("for order in row.get('market', [])[:max_orders]",
             "for order in row.get('market', [])", fixture(10, TAILS[1],25)),
            ("enumerate(out['market'][:max_orders])", "enumerate(out['market'])", fixture(10, TAILS[2])),
            ("reservation_bound = min(len(obligations), max_orders)",
             "reservation_bound = min(len(obligations), max(0, int(cfg.get('maxMarketOrdersPerTurn',10))))", fixture(0)),
        )
        for i, (before, after, f) in enumerate(variants):
            with self.subTest(mutant=i):
                self.assertEqual(NATIVE.count(before), 1)
                mutant = module_from(NATIVE.replace(before, after), 'mutant')
                self.assertNotEqual(propose(mutant,f), propose(NEW,f))


class NativeCallerTests(unittest.TestCase):
    def agent(self, native=True, consumer='frozen', enabled=True, terminal=False, snapshot=True):
        cls = module_from(NATIVE_RUNTIME if native else RUNTIME,'caller').TitanAgent
        agent = cls()
        f = fixture(10)
        agent.features = types.SimpleNamespace(operating_stock=enabled, consumer=consumer, terminal_route=terminal)
        agent.consumer = types.SimpleNamespace(selected_post_units=(f[3],f[4]) if snapshot else None)
        agent.selected = deepcopy(f[2])
        agent.controller = types.SimpleNamespace(R=[f[5]],cur=0)
        agent.diagnostics = {}
        return agent, f

    def test_only_caller_changes_and_other_runtime_repairs_survive(self):
        source = '# peer header\n' + RUNTIME + '\n    def peer_fix(self):\n        return 731\n'
        out = port.port_runtime(source)
        self.assertTrue(out.startswith('# peer header\n'))
        self.assertTrue(out.endswith('    def peer_fix(self):\n        return 731\n'))
        self.assertEqual(source.replace(CALLER.rstrip('\n'), ''),
                         out.replace(port._function(out,'_operating_stock_selected','TitanAgent')[2], ''))

    def test_tail_only_sale_never_reaches_snapshot_or_imports(self):
        for native in (True, False):
            a, f = self.agent(native=native,snapshot=False)
            f[2]['market'] = [[] for _ in range(10)] + [['SELL','FERTILIZER',2]]
            self.assertIs(a._operating_stock_selected(f[0], f[1], f[2]), f[2])
            self.assertEqual(bool(a.diagnostics), not native)

    def test_feature_and_consumer_gates_keep_identity(self):
        for enabled, consumer, terminal in ((False,'frozen',False),(True,'ordered',False),
                                            (True,'parent',False),(True,'frozen',True)):
            a,f = self.agent(enabled=enabled,consumer=consumer,terminal=terminal)
            self.assertIs(a._operating_stock_selected(f[0],f[1],f[2]),f[2])
            self.assertEqual(a.diagnostics,{})

    def test_snapshot_and_unit_binding_still_required(self):
        a,f = self.agent(snapshot=False)
        self.assertIs(a._operating_stock_selected(f[0],f[1],f[2]),f[2])
        a,f = self.agent()
        a.selected['farmer']=['WEST']
        self.assertIs(a._operating_stock_selected(f[0],f[1],f[2]),f[2])
        self.assertEqual(a.diagnostics['operating_stock']['reason'],'no_completed_unit_snapshot')

    def test_actual_caller_to_full_helper_with_tail_and_cap_zero(self):
        for cap in (0,1,10):
            a,f = self.agent()
            f[1]['maxMarketOrdersPerTurn'] = cap
            k = max(1,cap)
            f[2]['market'] = [['SELL','FERTILIZER',2]]+[[] for _ in range(k-1)]+[['HIRE']]
            scheduler = types.SimpleNamespace(m=oracle.Mechanics(),parent=types.SimpleNamespace(DECISIONS=[]))
            with patch.dict(sys.modules, {'operating_stock':NEW,'scheduler':scheduler}):
                out = a._operating_stock_selected(f[0],f[1],f[2])
            self.assertEqual(out['market'][0],['SELL','FERTILIZER',1])
            self.assertEqual(out['market'][k:],[['HIRE']])
            self.assertTrue(a.diagnostics['operating_stock']['changed'])


class SourceCustodyTests(unittest.TestCase):
    def test_wrong_or_already_changed_preimages_rejected(self):
        for bad in (ORIGINAL+'\n',NATIVE,''):
            with self.assertRaises(ValueError):port.port_helper(bad)
        for bad in (RUNTIME.replace('final market','new market'),NATIVE_RUNTIME,
                    'class Other:\n'+CALLER,RUNTIME+'\n'+RUNTIME):
            with self.assertRaises(ValueError):port.port_runtime(bad)

    def test_materializer_preserves_inputs_and_existing_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            src = base/'source';src.mkdir()
            (src/'operating_stock.py').write_text(ORIGINAL)
            (src/'titan_runtime.py').write_text(RUNTIME)
            output = base/'result'
            receipt = port.materialize(src,ENGINE,output)
            self.assertFalse(receipt['production_modified'])
            self.assertEqual((src/'operating_stock.py').read_text(),ORIGINAL)
            self.assertEqual((src/'titan_runtime.py').read_text(),RUNTIME)
            self.assertEqual((output/'operating_stock.py').read_text(),NATIVE)
            self.assertEqual((output/'titan_runtime.py').read_text(),NATIVE_RUNTIME)
            for target in (src,output):
                with self.assertRaises(FileExistsError):port.materialize(src,ENGINE,target)
            alias=base/'alias';alias.symlink_to(src,target_is_directory=True)
            with self.assertRaises(FileExistsError):port.materialize(src,ENGINE,alias)
            bad_engine=base/'bad.py';bad_engine.write_text('wrong engine')
            with self.assertRaises(ValueError):port.materialize(src,bad_engine,base/'must-not-exist')
            self.assertFalse((base/'must-not-exist').exists())


class Struct(dict):
    def __getattr__(self,k):
        try:return self[k]
        except KeyError:raise AttributeError(k) from None
    def __setattr__(self,k,v):self[k]=v


def load_engine():
    if port.git_blob(ENGINE.read_bytes()) != port.ENGINE_BLOB:
        raise ValueError('official engine source mismatch')
    utils = ENGINE.with_name('utils.py')
    if port.git_blob(utils.read_bytes()) != "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87":
        raise ValueError("official seed-helper source mismatch")
    tree = ast.parse(utils.read_text())
    func = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='resolve_episode_seed')
    ns={'Any':Any,'Callable':Callable,'random':random}
    exec(compile(ast.Module(body=[func],type_ignores=[]),'official seed helper','exec'),ns)
    package=types.ModuleType('kaggle_environments')
    utility=types.ModuleType('kaggle_environments.utils')
    utility.resolve_episode_seed=ns['resolve_episode_seed']
    with patch.dict(sys.modules,{'kaggle_environments':package,'kaggle_environments.utils':utility}):
        spec=importlib.util.spec_from_file_location('official_stockport_engine',ENGINE)
        e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
    return e


class OfficialEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.e=load_engine()

    def world(self,seat,cap=10):
        e=self.e
        cfg=Struct(maxMarketOrdersPerTurn=cap,turnsPerDay=24,episodeSteps=720,
                   boardSize=10,shedCapacity=100,farmHandCostMult=1,weedSpawnChance=0)
        farms=[e._new_farm(10,100),e._new_farm(10,100)]
        market=e._new_market();market['inventory']['STRAWBERRY']=9900;e._refresh_prices(market)
        town=e._new_town()
        tile=e._new_plant('STRAWBERRY',2,24)
        tile.update(watered_today=True,consecutive_unwatered=0)
        farms[seat]['tiles'][4][3]=tile
        states=[]
        for p in (0,1):
            private=e._new_private();private['shed']['FERTILIZER']=2
            states.append(Struct(observation=Struct(player=p,step=240,day=10,hour=0,
                farms=farms,private=private,market=market,town=town),
                action=oracle.blank_action(),status='ACTIVE',reward=0))
        route=[oracle.blank_action() for _ in range(720)]
        route[241]['farmer']=['PICKUP','FERTILIZER',1]
        route[242]['farmer']=['WEST'];route[243]['farmer']=['FERTILIZE']
        route[264]['farmer']=['WEST'];route[265]['farmer']=['WATER']
        return states,Struct(configuration=cfg,done=False,info={'seed':9600803}),route

    def action(self,module,states,env,route,seat,tail):
        obs=states[seat].observation;k=max(1,int(env.configuration.maxMarketOrdersPerTurn))
        selected=oracle.blank_action()
        selected['market']=[['SELL','FERTILIZER',2]]+[[] for _ in range(k-1)]+deepcopy(tail)
        return module.protect_operating_stock(self.e,obs,env.configuration,selected,
            obs.farms[seat],obs.private,route,())

    def test_full_interpreter_ignores_raw_tail_in_both_seats(self):
        cells=0
        for seat in (0,1):
            for cap in CAPS:
                for tail in TAILS[:6]:
                    a,env,route=self.world(seat,cap);b=deepcopy(a)
                    selected,report=self.action(NEW,a,env,route,seat,tail)
                    self.assertTrue(report['changed'],report)
                    a[seat].action=selected;b[seat].action=deepcopy(selected)
                    b[seat].action['market']=b[seat].action['market'][:max(1,cap)]
                    self.e.interpreter(a,deepcopy(env));self.e.interpreter(b,deepcopy(env))
                    # Compare public + private poststate, not unequal action metadata.
                    self.assertEqual([s.observation for s in a],[s.observation for s in b])
                    self.assertEqual(a[seat].observation.private['shed']['FERTILIZER'],1)
                    cells+=1
        self.assertEqual(cells,72)

    def test_true_prefix_slot_precedes_parsing(self):
        for cap in CAPS:
            for seat in (0,1):
                a,env,route=self.world(seat,cap)
                k=max(1,cap)
                a[seat].action['market']=[[] for _ in range(k)]+[['SELL','FERTILIZER',2]]
                self.e.interpreter(a,env)
                self.assertEqual(a[seat].observation.private['shed']['FERTILIZER'],2)
                self.assertEqual(a[seat].observation.farms[seat]['money'],100)

    def test_actual_pickup_fertilize_water_refresh_chain(self):
        # Old tail-HIRE veto sells both units; native retains one, delivers it to
        # the same authored pickup/fertilize, and produces +1 unit at day refresh.
        # No extrapolation to final cash or game win rate is made.
        for seat in (0,1):
            worlds=[]
            for module in (OLD,NEW):
                state,env,route=self.world(seat)
                action,report=self.action(module,state,env,route,seat,[['HIRE']])
                initial_report=deepcopy(report)
                for step in range(240,288):
                    for s in state:
                        s.observation.step=step
                        s.action=oracle.blank_action()
                    state[seat].action=action if step==240 else deepcopy(route[step])
                    self.e.interpreter(state,env)
                worlds.append((state,initial_report))
            old,new=worlds
            self.assertFalse(old[1]['changed']);self.assertTrue(new[1]['changed'])
            old_tile=old[0][seat].observation.farms[seat]['tiles'][4][3]
            new_tile=new[0][seat].observation.farms[seat]['tiles'][4][3]
            self.assertEqual(new_tile['yield_units']-old_tile['yield_units'],1)
            self.assertEqual(new[0][seat].observation.farms[seat]['money']-
                             old[0][seat].observation.farms[seat]['money'],-100)


if __name__=='__main__':unittest.main()
