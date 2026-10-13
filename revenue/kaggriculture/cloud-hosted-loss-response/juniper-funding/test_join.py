# SPDX-License-Identifier: Apache-2.0
"""New optional T13 funding join; existing peer suites are not collected.

Constructed selected actions exercise the actual budget, post-unit mechanics and
certificate. Separate unmodified-parent calls exercise construction/forwarding.
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
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
P = argparse.ArgumentParser(description=__doc__)
P.add_argument('--engine-dir', type=Path, required=True)
P.add_argument('--funding-source', type=Path, default=ROOT/'cloud-integration-differentials/seed_funding.py')
P.add_argument('--report', type=Path, required=True)
ARGS = P.parse_args()

def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod
    spec.loader.exec_module(mod);return mod

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

S=load(HERE.parent/'seed_main.py','juniper_seed_subject')
F=load(ARGS.funding_source,'juniper_funding_input')
E=load(ROOT/'cloud-eval/evaluate.py','juniper_existing_evaluator')
K,HASHES=E.get_engine(ARGS.engine_dir, ROOT/'20260907-offline-agent/evaluate.py')
TRANSITIONS=0
RECEIPTS=[]


def action(orders=(), farmer=None):
    return {'farmer':farmer or ['PASS'],'hands':[], 'market':deepcopy(list(orders))}


def fixture(cash=1000, seat=0, step=100, seeds=0, stock=None, carried=None):
    farms=[K._new_farm(10,5000),K._new_farm(10,5000)]
    privates=[K._new_private(),K._new_private()]
    farms[seat]['money']=float(cash);farms[seat]['hires_today']=12
    privates[seat]['seeds']['WHEAT']=seeds
    privates[seat]['shed'].update(stock or {})
    privates[seat]['inventories'][0].update(carried or {})
    cfg={key:value.get('default') if isinstance(value,dict) else value
         for key,value in K.specification['configuration'].items()}
    obs={'player':seat,'step':step,'day':step//24,'hour':step%24,
         'farms':farms,'private':privates[seat],'market':K._new_market(),'town':K._new_town()}
    return obs,cfg,privates


def execute(obs,cfg,privates,chosen,rival=None):
    global TRANSITIONS
    obs,cfg,privates=deepcopy((obs,cfg,privates))
    states=[];seat=obs['player']
    # The current unit sequence precedes the complete shared market phase.
    for i in (0,1):
        decision=chosen if i==seat else (rival or action())
        units=[decision.get('farmer',['PASS']),*decision.get('hands',[])]
        for worker,op in enumerate(units):
            K._apply_unit_action(obs['farms'][i],privates[i],worker,op,10,
                                 obs['step']//24,24,cfg['shedCapacity'])
        states.append(E.Struct(observation=E.Struct(farms=obs['farms'],private=privates[i],
                      market=obs['market']),action=deepcopy(decision)))
    K._process_market(states,E.Struct(configuration=cfg));TRANSITIONS+=1
    return {'farms':obs['farms'],'privates':privates,'market':obs['market']}


def no_cash_seeds(value,seat):
    value=deepcopy(value);value['farms'][seat].pop('money');value['privates'][seat].pop('seeds')
    return value


class JoinTests(unittest.TestCase):
    def case(self, selected, future=(), callback=F.select_seed_queue, enabled=True, sell=True):
        run=S.make_agent(HERE.parent,sell=sell,enabled=enabled,seed_queue_selector=callback)
        route=[action() for _ in range(720)];route[100]=deepcopy(selected)
        for step in future:route[step]=action(farmer=['PLANT','WHEAT'])
        run.controller.R={'case':route};run.controller.cur='case'
        # The actual SeedBudget must use the selected route, not fixed constants.
        run.budget.__init__(run.controller.R)
        return run

    def test_funded_hire_both_seats_preserves_nonseed_state(self):
        base=action([['BUY_SEED','WHEAT',17],['HIRE']])
        for seat in (0,1):
            run=self.case(base,future=(101,102,103));obs,cfg,private=fixture(seat=seat)
            saved=deepcopy((obs,cfg,base))
            with patch.object(run.policy,'act',return_value=deepcopy(base)) as called:
                out=run(obs,cfg)
            self.assertEqual(called.call_count,1)
            self.assertEqual(out,action([['BUY_SEED','WHEAT',3],['HIRE']]))
            self.assertEqual(run.seed_funding['status'],'certified')
            before=execute(obs,cfg,private,base);after=execute(obs,cfg,private,out)
            self.assertEqual(after['farms'][seat]['money']-before['farms'][seat]['money'],140)
            self.assertEqual(no_cash_seeds(before,seat),no_cash_seeds(after,seat))
            self.assertEqual((obs,cfg,base),saved)
            RECEIPTS.append({'case':'funded_hire','seat':seat,'cash_before':before['farms'][seat]['money'],
                             'cash_after':after['farms'][seat]['money'],'nonseed_equal':True})

    def test_underfunded_keeps_frozen_queue_not_legacy_seed_action(self):
        base=action([['BUY_SEED','WHEAT',17],['HIRE']]);obs,cfg,private=fixture(cash=300)
        run=self.case(base)
        with patch.object(run.policy,'act',return_value=deepcopy(base)):safe=run(obs,cfg)
        self.assertEqual(safe,base);self.assertEqual(run.seed_funding['status'],'not_certified')
        legacy=self.case(base,callback=None)
        with patch.object(legacy.policy,'act',return_value=deepcopy(base)):old=legacy(obs,cfg)
        self.assertEqual(old,action([[],['HIRE']]))
        before=execute(obs,cfg,private,safe);after=execute(obs,cfg,private,old)
        self.assertEqual(before['farms'][0]['money'],130)
        self.assertEqual(after['farms'][0]['money'],67)
        self.assertEqual(len(after['farms'][0]['hands']),len(before['farms'][0]['hands'])+1)
        RECEIPTS.append({'case':'underfunded_hire','safe_cash':130,'legacy_cash':67,'safe_queue_preserved':True})

    def test_callback_sees_post_current_plant_seeds(self):
        base=action([['BUY_SEED','WHEAT',17],['HIRE']],farmer=['PLANT','WHEAT'])
        cb=Mock(wraps=F.select_seed_queue);run=self.case(base,future=(101,),callback=cb)
        obs,cfg,private=fixture(seeds=1)
        with patch.object(run.policy,'act',return_value=deepcopy(base)):out=run(obs,cfg)
        self.assertEqual(cb.call_count,1);self.assertEqual(cb.call_args.args[1]['private']['seeds']['WHEAT'],0)
        self.assertEqual(out['market'][0],['BUY_SEED','WHEAT',1])
        before=execute(obs,cfg,private,base);after=execute(obs,cfg,private,out)
        self.assertEqual(no_cash_seeds(before,0),no_cash_seeds(after,0))
        self.assertEqual(after['farms'][0]['money']-before['farms'][0]['money'],160)

    def test_callback_preserves_deposit_sale_queue(self):
        base=action([['BUY_SEED','WHEAT',17],['HIRE'],['SELL','EGG',3]],farmer=['DROP'])
        run=self.case(base);obs,cfg,private=fixture(carried={'EGG':3})
        with patch.object(run.policy,'act',return_value=deepcopy(base)):out=run(obs,cfg)
        self.assertEqual(out['farmer'],['DROP']);self.assertEqual(out['market'][1:],base['market'][1:])
        before=execute(obs,cfg,private,base,action([['SELL','EGG',1]]))
        after=execute(obs,cfg,private,out,action([['SELL','EGG',1]]))
        self.assertEqual(no_cash_seeds(before,0),no_cash_seeds(after,0))
        self.assertEqual(after['farms'][0]['money']-before['farms'][0]['money'],170)

    def test_disabled_and_no_seed_clear_report_without_callback(self):
        base=action([['BUY_SEED','WHEAT',17],['HIRE']]);cb=Mock(side_effect=AssertionError('callback'))
        obs,cfg,_=fixture();run=self.case(base,callback=cb,enabled=False)
        with patch.object(run.policy,'act',return_value=base):self.assertEqual(run(obs,cfg),base)
        cb.assert_not_called()
        run=self.case(base,callback=cb);run.seed_funding={'status':'old'}
        with patch.object(run.policy,'act',return_value=action()):self.assertEqual(run(obs,cfg),action())
        self.assertIsNone(run.seed_funding);cb.assert_not_called()

    def test_no_edit_and_no_dependent_order_bypass_callback(self):
        cb=Mock(side_effect=AssertionError('callback'));obs,cfg,_=fixture()
        for base,future,expected in [(action([['BUY_SEED','WHEAT',1],['HIRE']]),(101,),action([['BUY_SEED','WHEAT',1],['HIRE']])),
                                     (action([['BUY_SEED','WHEAT',17]]),(),action([[]]))]:
            run=self.case(base,future=future,callback=cb)
            with patch.object(run.policy,'act',return_value=base):self.assertEqual(run(obs,cfg),expected)
        cb.assert_not_called()

    def test_product_purchase_keeps_existing_fixed_only_fallback(self):
        base=action([['BUY_SEED','WHEAT',17],['BUY_PRODUCT','WHEAT',1]])
        run=self.case(base);obs,cfg,_=fixture()
        with patch.object(run.policy,'act',return_value=base):self.assertEqual(run(obs,cfg),base)
        self.assertIn('paired-flow',run.seed_funding['reason'])

    def test_configuration_and_truncated_order_positions(self):
        base=action([['BUY_SEED','WHEAT',17],['HIRE']]);run=self.case(base)
        obs,cfg,private=fixture(cash=170);cfg['maxMarketOrdersPerTurn']=1
        with patch.object(run.policy,'act',return_value=base):out=run(obs,cfg)
        self.assertEqual(out,action([[],['HIRE']]))
        self.assertEqual(run.seed_funding['original_fixed_cost_upper_bound'],170)
        before=execute(obs,cfg,private,base);after=execute(obs,cfg,private,out)
        self.assertEqual(no_cash_seeds(before,0),no_cash_seeds(after,0))

    def test_detached_callback_inputs_and_output(self):
        base=action([['BUY_SEED','WHEAT',17],['HIRE']]);obs,cfg,_=fixture()
        saved=deepcopy((obs,cfg,base));held=[]
        def cb(m,post,selected,proposal,config):
            held.extend([proposal,{'status':'certified'}]);post['farms'][0]['money']=0
            selected['market'].clear();config['nested']['x']=7
            return held
        cfg['nested']={'x':1};saved=deepcopy((obs,cfg,base));run=self.case(base,callback=cb)
        with patch.object(run.policy,'act',return_value=base):out=run(obs,cfg)
        self.assertEqual((obs,cfg,base),saved)
        held[0]['market'].clear();held[1]['status']='mutated'
        self.assertTrue(out['market']);self.assertEqual(run.seed_funding['status'],'certified')

    def test_callback_failure_is_not_retried(self):
        marker=TypeError('body-marker');cb=Mock(side_effect=marker)
        base=action([['BUY_SEED','WHEAT',17],['HIRE']]);run=self.case(base,callback=cb);obs,cfg,_=fixture()
        with patch.object(run.policy,'act',return_value=base) as parent:
            with self.assertRaises(TypeError) as raised:run(obs,cfg)
        self.assertIs(raised.exception,marker);self.assertEqual(parent.call_count,1);self.assertEqual(cb.call_count,1)

    def test_non_dict_callback_result_is_reported(self):
        base=action([['BUY_SEED','WHEAT',17],['HIRE']]);obs,cfg,_=fixture()
        for result in ((None,{}),({},None)):
            run=self.case(base,callback=Mock(return_value=result))
            with patch.object(run.policy,'act',return_value=base),self.assertRaises(TypeError):run(obs,cfg)

    def test_intact_parent_called_once_both_seats_and_no_selector_parity(self):
        for seat in (0,1):
            obs,cfg,_=fixture(step=0,seat=seat)
            on=S.make_agent(HERE.parent,seed_queue_selector=F.select_seed_queue)
            off=S.make_agent(HERE.parent)
            saved=deepcopy((obs,cfg))
            with patch.object(on.controller,'act',wraps=on.controller.act) as called:
                a=on(obs,cfg)
            b=off(obs,cfg)
            self.assertEqual(called.call_count,1);self.assertEqual(a,b)
            self.assertEqual(on.policy.planned,off.policy.planned)
            self.assertEqual((obs,cfg),saved)
            RECEIPTS.append({'case':'actual_parent_once','seat':seat,'calls':1,'action_equal':True,'planned_equal':True})

    def test_arlene_without_sell_uses_same_callback(self):
        base=action([['BUY_SEED','WHEAT',17],['HIRE']]);run=self.case(base,sell=False);obs,cfg,_=fixture()
        with patch.object(run.policy,'act',return_value=base) as called:out=run(obs,cfg)
        self.assertEqual(called.call_count,1);self.assertEqual(out,action([[],['HIRE']]))
        self.assertEqual(run.seed_funding['status'],'certified')


if __name__=='__main__':
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(JoinTests))
    report={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'successful':result.wasSuccessful(),'official_market_transitions':TRANSITIONS,'full_games':0,
            'wall_seconds':time.perf_counter()-start,'cases':RECEIPTS,'engine':HASHES,
            'sources':{str(p):digest(p) for p in (Path(__file__),HERE.parent/'seed_main.py',HERE.parent/'seed_budget.py',
                        ARGS.funding_source,ROOT/'cloud-titan-composition/vendor/sell/scheduler.py')}}
    ARGS.report.parent.mkdir(parents=True,exist_ok=True);ARGS.report.write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
