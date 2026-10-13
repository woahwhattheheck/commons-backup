# SPDX-License-Identifier: Apache-2.0
"""Offline complete-interpreter acceptance for the new B5 companion, not donor EV."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('TITAN_NATIVE_ROOT', '/mnt/data/native-artifact/final-pressure-runtime'))
ENGINE_BLOBS = {'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
                'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
                'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87'}
LOADER_SHA = 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e'
RECEIPT = {'scope': 'constructed full official-interpreter transitions and terminal suffixes',
           'engine_calls': 0, 'physical_pairs': 0, 'positive_pairs': 0,
           'terminal_suffixes': [], 'field_games': 0}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def authenticated_engine(root=ROOT):
    engine_dir = root / 'checks/reference/engine'
    hashes = {}
    for filename, expected in ENGINE_BLOBS.items():
        raw = (engine_dir / filename).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != expected:
            raise ValueError('official engine mismatch: ' + filename)
        hashes[filename] = hashlib.sha256(raw).hexdigest()
    loader_path = root / 'checks/reference/evaluator/loader.py'
    if hashlib.sha256(loader_path.read_bytes()).hexdigest() != LOADER_SHA:
        raise ValueError('loader mismatch')
    loader = load(loader_path, 'tomato_official_loader')
    engine, _ = loader.get_engine(engine_dir)
    return engine, loader.Struct, hashes


H = load(Path(os.environ.get('TOMATO_HELPER', HERE / 'discarded_fertilizer_tomato.py')), 'tomato_candidate')


def action(farmer=None, hands=(), market=()):
    return {'farmer': ['PASS'] if farmer is None else farmer,
            'hands': deepcopy(list(hands)), 'market': deepcopy(list(market))}


def fixture(engine, S, seat=0, *, day=17, age=8, held=0, fertilizer=1,
            water=True, full=100, actor=0, market_level=10000):
    cfg = S({k: v.get('default') if isinstance(v, dict) else v
             for k, v in engine.specification['configuration'].items()})
    cfg.weedSpawnChance = 0
    farms = [engine._new_farm(10, 3000), engine._new_farm(10, 3000)]
    market = engine._new_market()
    market['inventory']['TOMATO'] = market_level
    engine._refresh_prices(market)
    town = engine._new_town()
    state = []
    for i in range(2):
        priv = engine._new_private()
        state.append(S(observation=S(player=i, step=day*24+23, day=day, hour=23,
                                     farms=farms, private=priv, market=market, town=town),
                       action=action(), status='ACTIVE', reward=0))
    own = state[seat].observation
    own.private['shed'] = {'WHEAT': full}
    own.private['inventories'] = [{} for _ in range(actor+1)]
    own.private['inventories'][actor] = {'FERTILIZER': fertilizer} if fertilizer else {}
    farm = farms[seat]
    farm['farmer'] = [0, 0] if actor == 0 else [4, 4]
    farm['hands'] = [[0, 0] for _ in range(actor)]
    farm['hires_today'] = actor
    plant = engine._new_plant('TOMATO', day+1-age, 24)
    plant.update(watered_today=water, consecutive_unwatered=0, yield_units=held)
    farm['tiles'][0][0] = plant
    state[seat].action = action(hands=[['PASS'] for _ in range(actor)])
    return state, S(configuration=cfg, done=False, info={'seed': 2611151001})


def transition(engine, state, env, step=None):
    if step is not None:
        for s in state:
            s.observation.step = step
    RECEIPT['engine_calls'] += 1
    engine.interpreter(state, env)
    if any(s.status == 'DONE' for s in state):
        env.done = True
    return state


class TomatoAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e, cls.S, hashes = authenticated_engine()
        RECEIPT['engine_sha256'] = hashes
        RECEIPT['loader_sha256'] = LOADER_SHA

    def check_pair(self, state, env, seat, *, expect=True):
        before = deepcopy((state, env))
        selected = state[seat].action
        output, report = H.apply_discarded_fertilizer(state[seat].observation, selected,
                                                       env.configuration, enabled=True)
        self.assertEqual((state, env), before, 'helper changed its input')
        self.assertEqual(report['changed'], expect, report)
        if not expect:
            self.assertIs(output, selected)
        else:
            self.assertIsNot(output, selected)
            self.assertEqual(output['market'], selected['market'])
        base, be = deepcopy((state, env))
        cand, ce = deepcopy((state, env))
        cand[seat].action = output
        transition(self.e, base, be)
        transition(self.e, cand, ce)
        # Compare COMPLETE world + environment after neutralizing exactly the
        # advertised plant fields and returned action; no reward-only shortcut.
        normalized = deepcopy(cand)
        normalized[seat].action = deepcopy(base[seat].action)
        for x, y in report.get('sites', []):
            a = base[seat].observation.farms[seat]['tiles'][y][x]
            b = cand[seat].observation.farms[seat]['tiles'][y][x]
            self.assertEqual(b['yield_units'] - a['yield_units'], 1)
            self.assertEqual(b['fertilized_until_day'], state[seat].observation.step//24+2)
            n = normalized[seat].observation.farms[seat]['tiles'][y][x]
            n['yield_units'] = a['yield_units']
            n['fertilized_until_day'] = a['fertilized_until_day']
        self.assertEqual(normalized, base)
        self.assertEqual(ce, be)
        RECEIPT['physical_pairs'] += 1
        RECEIPT['positive_pairs'] += expect
        return base, be, cand, ce, report

    def test_disabled_strict_boolean_and_identity(self):
        s, e = fixture(self.e, self.S)
        for enabled in (False, None, 0, 1, 'true', [], {}):
            out, rep = H.apply_discarded_fertilizer(s[0].observation, s[0].action,
                                                   e.configuration, enabled=enabled)
            self.assertIs(out, s[0].action)
            self.assertFalse(rep['changed'])

    def test_complete_world_productive_matrix_both_seats(self):
        for seat, age, held, actor, stock in itertools.product((0,1), range(8,12), range(3), (0,1), (100,113)):
            with self.subTest(seat=seat, age=age, held=held, actor=actor, stock=stock):
                s, e = fixture(self.e, self.S, seat, age=age, held=held, actor=actor, full=stock)
                self.check_pair(s, e, seat)

    def test_no_bonus_conditions_against_complete_engine(self):
        cases = [('watered_today', False), ('yield_units',3), ('yield_units',4),
                 ('fertilized_until_day',17), ('fertilized_until_day',19),
                 ('planted_day',11), ('planted_day',6)]
        for seat, (key, value) in itertools.product((0,1), cases):
            with self.subTest(seat=seat, key=key, value=value):
                s, e = fixture(self.e, self.S, seat)
                s[seat].observation.farms[seat]['tiles'][0][0][key] = value
                self.check_pair(s,e,seat,expect=False)

    def test_carrot_and_strawberry_are_not_tomato(self):
        for crop in ('CARROT','STRAWBERRY','WHEAT','MELON'):
            s,e = fixture(self.e,self.S)
            s[0].observation.farms[0]['tiles'][0][0] = self.e._new_plant(crop,10,24)
            self.check_pair(s,e,0,expect=False)

    def test_shed_room_and_carried_input_are_binding(self):
        for full, fert in ((99,1),(0,1),(100,0)):
            s,e=fixture(self.e,self.S,full=full,fertilizer=fert)
            self.check_pair(s,e,0,expect=False)

    def test_effective_raw_market_prefix_and_minimum_one(self):
        for cap in (-5,0,1,2,10):
            s,e=fixture(self.e,self.S)
            e.configuration.maxMarketOrdersPerTurn=cap
            s[0].action['market']=[[]]*max(1,cap)+[['SELL','WHEAT',1]]
            self.check_pair(s,e,0)
            s[0].action['market'][max(1,cap)-1]=['SELL','WHEAT',1]
            self.check_pair(s,e,0,expect=False)

    def test_market_and_opponent_effects_do_not_fake_free_input(self):
        ours=[[],[['HIRE']],[['BUY_LAND']],[['BUY_SEED','TOMATO',2]],
              [['BUY_PRODUCT','FERTILIZER',3]],[['BUY_ANIMAL','GOOSE',1]]]
        theirs=[[],[['BUY_PRODUCT','WHEAT',1]],[['HIRE']], [['BUY_SEED','TOMATO',1]]]
        for seat, market, rival in itertools.product((0,1),ours,theirs):
            s,e=fixture(self.e,self.S,seat)
            s[seat].action['market']=deepcopy(market)
            s[1-seat].action['market']=deepcopy(rival)
            self.check_pair(s,e,seat)

    def test_ghost_actor_suffix_preserved_without_false_room_or_service(self):
        for ghost in (['PASS'], ['PICKUP','WHEAT',100], ['FERTILIZE'], ['PLANT','WHEAT']):
            s,e=fixture(self.e,self.S)
            s[0].action['hands']=[ghost]
            self.check_pair(s,e,0)
        # Ghost PLANT contributes to the atomic crop demand, even though its
        # actor never executes. Preserve the blockage of the real farmer's PLANT.
        s,e=fixture(self.e,self.S,actor=1)
        s[0].observation.private['seeds']['WHEAT']=1
        s[0].action=action(['PLANT','WHEAT'],hands=[['PASS'],['PLANT','WHEAT']])
        self.check_pair(s,e,0)

    def test_other_actor_pickup_veto_even_when_not_on_target(self):
        s,e=fixture(self.e,self.S,actor=1)
        s[0].action['farmer']=['PICKUP','WHEAT',1]
        self.check_pair(s,e,0,expect=False)

    def test_collocated_service_and_dig_veto(self):
        for command in (['DIG'],['HARVEST'],['WATER'],['FERTILIZE'],['PLANT','TOMATO']):
            s,e=fixture(self.e,self.S,actor=1)
            s[0].observation.farms[0]['farmer']=[0,0]
            s[0].action['farmer']=command
            s[0].observation.private['inventories'][0]={'FERTILIZER':1}
            self.check_pair(s,e,0,expect=False)

    def test_distinct_sites_and_collocated_pass_are_deduplicated(self):
        for same in (False,True):
            s,e=fixture(self.e,self.S,actor=1)
            farm=s[0].observation.farms[0]
            farm['farmer']=[0,0]
            farm['hands']=[[0,0] if same else [1,0]]
            farm['tiles'][0][1]=deepcopy(farm['tiles'][0][0])
            s[0].observation.private['inventories'][0]={'FERTILIZER':2}
            *_, report=self.check_pair(s,e,0)
            self.assertEqual(len(report['proposed_actors']),1 if same else 2)

    def test_other_actor_noninterfering_work(self):
        for cmd in (['NORTH'],['SOUTH'],['EAST'],['WEST'],['PASS'],['WATER'],['CARE'],
                    ['FEED'],['HARVEST'],['FERTILIZE'],['COLLECT_FERTILIZER'],
                    ['DIG'],['BUILD_COOP'],['BUILD_PASTURE'],['DROP'],['PLANT','WHEAT']):
            s,e=fixture(self.e,self.S,actor=1)
            s[0].action['farmer']=cmd
            s[0].observation.private['inventories'][0]={'MILK':4,'FERTILIZER':2,'WHEAT':1}
            s[0].observation.private['seeds']['WHEAT']=1
            self.check_pair(s,e,0)

    def test_schema_poison_is_identity_not_opportunity(self):
        def failures():
            for field in ('step','player'):
                for value in (True,1.0,'1',None):
                    yield lambda s,e,f=field,v=value:s[0].observation.__setitem__(f,v)
            for field in ('planted_day','yield_units','fertilized_until_day','consecutive_unwatered','max_lifespan_step'):
                for value in (True,1.0,'1',None):
                    yield lambda s,e,f=field,v=value:s[0].observation.farms[0]['tiles'][0][0].__setitem__(f,v)
            for field in ('shed','inventories'):
                yield lambda s,e,f=field:s[0].observation.private.__setitem__(f,None)
            for field in ('boardSize','turnsPerDay','shedCapacity','episodeSteps','maxMarketOrdersPerTurn'):
                yield lambda s,e,f=field:e.configuration.__setitem__(f,True)
                yield lambda s,e,f=field:e.configuration.__setitem__(f,1.0)
            yield lambda s,e:s[0].action.__setitem__('hands','bad')
            yield lambda s,e:s[0].action.__setitem__('farmer',['PASS',0])
            yield lambda s,e:s[0].action.__setitem__('market',[['BUY_PRODUCT','FERTILIZER',float('inf')]])
            yield lambda s,e:s[0].observation.private['shed'].__setitem__('WHEAT',True)
            yield lambda s,e:s[0].observation.private['inventories'][0].__setitem__('FERTILIZER',True)
        for poison in failures():
            s,e=fixture(self.e,self.S);poison(s,e)
            out,report=H.apply_discarded_fertilizer(s[0].observation,s[0].action,e.configuration,enabled=True)
            self.assertIs(out,s[0].action,report)
            self.assertFalse(report['changed'],report)

    def test_cross_site_cross_farm_and_inventory_aliases_fail_closed(self):
        for kind in ('tile','rival_tile','inventory'):
            s,e=fixture(self.e,self.S,actor=1)
            farm=s[0].observation.farms[0]
            if kind=='tile':farm['tiles'][0][1]=farm['tiles'][0][0]
            elif kind=='rival_tile':s[0].observation.farms[1]['tiles'][0][0]=farm['tiles'][0][0]
            else:s[0].observation.private['inventories'][0]=s[0].observation.private['inventories'][1]
            out,report=H.apply_discarded_fertilizer(s[0].observation,s[0].action,e.configuration,enabled=True)
            self.assertIs(out,s[0].action,report)
            self.assertFalse(report['changed'])

    def test_expiry_sentinel_and_episode_boundary(self):
        s,e=fixture(self.e,self.S,day=28)
        self.check_pair(s,e,0)
        for step in (0,22,24,696,718,719,743):
            s,e=fixture(self.e,self.S,day=28)
            s[0].observation.step=step
            out,r=H.apply_discarded_fertilizer(s[0].observation,s[0].action,e.configuration,enabled=True)
            self.assertIs(out,s[0].action,r)
        s,e=fixture(self.e,self.S)
        s[0].observation.farms[0]['tiles'][0][0]['max_lifespan_step']=500
        out,r=H.apply_discarded_fertilizer(s[0].observation,s[0].action,e.configuration,enabled=True)
        self.assertIs(out,s[0].action,r)

    def test_repeat_application_and_mutation_isolation(self):
        s,e=fixture(self.e,self.S)
        first,r=H.apply_discarded_fertilizer(s[0].observation,s[0].action,e.configuration,enabled=True)
        again,r2=H.apply_discarded_fertilizer(s[0].observation,first,e.configuration,enabled=True)
        self.assertIs(first,again)
        self.assertFalse(r2['changed'])
        first['farmer'].append('mutated')
        first['market'].append(['SELL','WHEAT',1])
        self.assertEqual(s[0].action,action())

    def test_constructed_final_day_harvest_and_sale_cash(self):
        for seat, inventory in itertools.product((0,1),(9800,10000,10600)):
            s,e=fixture(self.e,self.S,seat,day=28,market_level=inventory)
            b,be,c,ce,r=self.check_pair(s,e,seat)
            path=[['WEST']]*4+[['NORTH']]*4+[['HARVEST']]+[['SOUTH']]*4+[['EAST']]*4+[['DROP']]
            for step in range(696,719):
                cmd=path[step-696] if step-696<len(path) else ['PASS']
                for state,env in ((b,be),(c,ce)):
                    market=[]
                    if step==696:market=[['SELL','WHEAT',100]]
                    if step==714:market=[['SELL','TOMATO',100]]
                    state[seat].action=action(deepcopy(cmd),market=market)
                    state[1-seat].action=action()
                    transition(self.e,state,env,step)
            self.assertEqual([x.status for x in b],['DONE','DONE'])
            self.assertEqual([x.status for x in c],['DONE','DONE'])
            delta=c[seat].reward-b[seat].reward
            self.assertGreater(delta,0)
            self.assertEqual(c[1-seat].reward,b[1-seat].reward)
            RECEIPT['terminal_suffixes'].append({'seat':seat,'tomato_inventory_at_695':inventory,
                'baseline_score':b[seat].reward,'candidate_score':c[seat].reward,
                'delta_cash':delta,'scope':'constructed 24-transition suffix, not native field game'})

    def test_no_harvest_continuation_does_not_establish_cash_gain(self):
        s,e=fixture(self.e,self.S,day=28)
        b,be,c,ce,r=self.check_pair(s,e,0)
        for step in range(696,719):
            for state,env in ((b,be),(c,ce)):
                for player in state:player.action=action()
                transition(self.e,state,env,step)
        self.assertEqual(c[0].reward,b[0].reward)
        self.assertEqual(c[1].reward,b[1].reward)
        self.assertFalse(r['observed_fill'])
        self.assertEqual(r['economic_disposition'],'UNMEASURED_CONTINUATION_NOT_PROMOTION')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TomatoAcceptance))
    RECEIPT.update(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                   skips=len(result.skipped),optimized=not __debug__)
    if args.report:args.report.write_text(json.dumps(RECEIPT,indent=2,sort_keys=True)+'\n')
    print(json.dumps(RECEIPT,sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
