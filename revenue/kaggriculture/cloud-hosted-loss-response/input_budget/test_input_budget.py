# SPDX-License-Identifier: Apache-2.0
"""Regression cases plus observed-state tests; fixtures are development only."""
import base64, copy, gzip, importlib, json, os
from pathlib import Path
import sys, unittest
HERE=Path(__file__).resolve().parent
RUNTIME=HERE/'runtime'
if not (RUNTIME/'scheduler.py').is_file():RUNTIME=HERE.parents[1]/'cloud-execution-lab'
sys.path.insert(0,str(RUNTIME))
import scheduler as s
mod=importlib.import_module(os.environ.get('INPUT_BUDGET_MODULE','input_budget'))
B=HERE.parent

class InputBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=HERE/'fixture.json.gz.b64'
        cls.frame=json.loads(gzip.decompress(base64.b64decode(p.read_text())))
        cls.route=s.parent.routes()['a84d06f1d12add7c']
    def setUp(self):
        self.obs=copy.deepcopy(self.frame['observations'][0]);self.action=copy.deepcopy(self.frame['actions'][0])
        self.policy=mod.FinalInputBudget(s.m,s.parent._noop,s.post_units)
    def apply(self,**kw):return self.policy.transform(kw.get('obs',self.obs),kw.get('cfg',{}),kw.get('action',self.action),kw.get('route',self.route))
    def test_actual_observation_one_unit_reduction(self):
        self.assertEqual(self.apply()['market'][9],['BUY_PRODUCT','FERTILIZER',21])
        self.assertEqual(self.policy.last.reason,'trimmed')
    def test_no_input_mutation(self):
        old=copy.deepcopy((self.obs,self.action,self.route));self.apply();self.assertEqual(old,(self.obs,self.action,self.route))
    def test_slot_and_workers_preserved(self):
        result=self.apply();self.assertEqual(result['market'][:9],self.action['market'][:9]);self.assertEqual(result['farmer'],self.action['farmer']);self.assertEqual(result['hands'],self.action['hands'])
    def test_no_rival_read(self):
        class Farms(list):
            def __getitem__(self,index):
                if index!=0:raise AssertionError('rival accessed')
                return super().__getitem__(index)
        self.obs['farms']=Farms(self.obs['farms']);self.apply()
    def test_missing_future_collection_preserves_purchase(self):
        for row in self.obs['farms'][0]['tiles']:
            for tile in row:
                if isinstance(tile,dict) and 'fertilizer_available' in tile:tile['fertilizer_available']=False
        self.assertIs(self.apply(),self.action)
    def test_low_cash_uncertain_hires(self):
        self.obs['farms'][0]['money']=0;self.assertIs(self.apply(),self.action);self.assertEqual(self.policy.last.reason,'uncertain_hires')
    def test_nonfinal_day(self):
        self.obs['step']=672;self.assertIs(self.apply(),self.action)
    def test_not_day_open(self):
        self.obs['step']=697;self.assertIs(self.apply(),self.action)
    def test_later_pickup_rejected(self):
        route=copy.deepcopy(self.route);route[698]['farmer']=['PICKUP','FERTILIZER',1];self.assertIs(self.apply(route=route),self.action)
    def test_later_buy_rejected(self):
        route=copy.deepcopy(self.route);route[698]['market']=[['BUY_PRODUCT','FERTILIZER',1]];self.assertIs(self.apply(route=route),self.action)
    def test_other_product_pickup_rejected(self):
        route=copy.deepcopy(self.route);route[697]['farmer']=['PICKUP','WHEAT',1];self.assertIs(self.apply(route=route),self.action)
    def test_postpurchase_dependency_rejected(self):
        self.action['market'].append(['HIRE']);self.assertIs(self.apply(cfg={'maxMarketOrdersPerTurn':11}),self.action)
    def test_prior_fertilizer_sale_rejected(self):
        self.action['market'][0]=['SELL','FERTILIZER',1];self.assertIs(self.apply(),self.action)
    def test_prior_animal_buy_rejected(self):
        self.action['market'][0]=['BUY_ANIMAL','SHEEP',1];self.assertIs(self.apply(),self.action)
    def test_short_route_rejected(self):self.assertIs(self.apply(route=self.route[:700]),self.action)
    def test_unexecuted_order_limit(self):self.assertIs(self.apply(cfg={'maxMarketOrdersPerTurn':9}),self.action)
    def test_duplicate_buy_rejected(self):
        self.action['market'][0]=['BUY_PRODUCT','FERTILIZER',1];self.assertIs(self.apply(),self.action)
    def test_quantity_types_rejected(self):
        for q in (True,2.5,-1,0,101):
            self.action['market'][9][2]=q
            with self.subTest(q=q):self.assertIs(self.apply(),self.action)
    def test_same_turn_fertilize_water_harvest_not_aliased(self):
        farm=copy.deepcopy(self.obs['farms'][0]);private=copy.deepcopy(self.obs['private'])
        farm['farmer']=[4,4];farm['hands']=[[4,4],[4,4]]
        farm['tiles'][4][4]=s.m._new_plant('CARROT',26,24);farm['tiles'][4][4]['yield_units']=2
        private['inventories']=[{},{},{}];private['shed']['FERTILIZER']=0
        route=[{'farmer':['PASS'],'hands':[],'market':[]} for _ in range(699)]
        route[697]={'farmer':['PICKUP','FERTILIZER',1],'hands':[['PASS'],['PASS']],'market':[]}
        route[698]={'farmer':['FERTILIZE'],'hands':[['WATER'],['HARVEST']],'market':[]}
        # Both end with an empty crop tile, but the harvests differ 4 versus3.
        self.assertNotEqual(self.policy._project(farm,private,route,696,698,{},1),self.policy._project(farm,private,route,696,698,{},0))
    def test_atomic_plant_stock_is_bound_before_unit_execution(self):
        from types import SimpleNamespace
        farm=copy.deepcopy(self.obs['farms'][0]);private=copy.deepcopy(self.obs['private'])
        farm['farmer']=[0,0];farm['hands']=[[1,0]];farm['tiles'][0][0]=farm['tiles'][0][1]=None
        private['inventories']=[{},{}];private['seeds']['CARROT']=2
        route=[{'farmer':['PASS'],'hands':[],'market':[]} for _ in range(698)]
        route[697]={'farmer':['PLANT','CARROT'],'hands':[['PLANT','CARROT']],'market':[]}
        recorded=[]
        def apply(f,p,i,a,*args):recorded.append(list(a));return s.m._apply_unit_action(f,p,i,a,*args)
        self.policy.m=SimpleNamespace(_apply_unit_action=apply,_decay_plants=s.m._decay_plants)
        self.policy._project(farm,private,route,696,697,{},0)
        self.assertEqual(recorded,[['PLANT','CARROT'],['PLANT','CARROT']])
    def test_below_selected_quantity_changes_physics(self):
        farm,private=s.post_units(self.obs,self.action,{})
        for _ in range(9):s.m._do_hire(farm,private,10,1)
        self.assertNotEqual(self.policy._project(farm,private,self.route,696,718,{},22),self.policy._project(farm,private,self.route,696,718,{},20))

class AdapterTests(InputBudgetTests):
    # Only adapter-specific methods; inherited fixture helpers are reused below.
    def parent_fixture(self,**feature_kw):
        import candidate
        from types import SimpleNamespace
        from titan_runtime import Features
        p=SimpleNamespace(ready=True,diagnostics={'status':'completed'},features=Features(**feature_kw),controller=SimpleNamespace(R={'route':self.route},cur='route'),calls=0)
        def act(obs,cfg):p.calls+=1;return self.action
        p.act=act
        return candidate.InputBudgetAgent(p),p
    def test_adapter_single_parent_and_actual_trim(self):
        a,p=self.parent_fixture();out=a.act(self.obs,{});self.assertEqual(p.calls,1);self.assertEqual(out['market'][9][2],21)
    def test_adapter_disabled_single_parent(self):
        a,p=self.parent_fixture();a.enabled=False;self.assertIs(a.act(self.obs,{}),self.action);self.assertEqual(p.calls,1)
    def test_adapter_missing_step_public_clock(self):
        a,p=self.parent_fixture();self.obs.pop('step');self.obs['day']=29;self.obs['hour']=0;self.assertEqual(a.act(self.obs,{})['market'][9][2],21)
    def test_adapter_actual_own_deadline_fallback(self):
        import time
        a,p=self.parent_fixture(budget_seconds=.03,reserve_seconds=.01)
        def slow(*args):time.sleep(.2);raise AssertionError('deadline did not fire')
        a.budget.transform=slow
        self.assertIs(a.act(self.obs,{}),self.action);self.assertEqual(p.calls,1);self.assertTrue(a.diagnostics['budget_expired'])
    def test_adapter_unrelated_error_not_suppressed(self):
        a,p=self.parent_fixture()
        def fail(*args):raise ValueError('fixture')
        a.budget.transform=fail
        with self.assertRaisesRegex(ValueError,'fixture'):a.act(self.obs,{})
    def test_adapter_foreign_deadline_not_suppressed(self):
        import candidate
        a,p=self.parent_fixture();exc=candidate.deadline.DeadlineExceeded('foreign')
        def fail(*args):raise exc
        a.budget.transform=fail
        with self.assertRaises(candidate.deadline.DeadlineExceeded) as caught:a.act(self.obs,{})
        self.assertIs(caught.exception,exc)
    def test_adapter_other_producer_not_used(self):
        a,p=self.parent_fixture(consumer='ordered');self.assertIs(a.act(self.obs,{}),self.action)

# Reuse setUp/fixture methods, not the twenty inherited test methods.
for name in list(InputBudgetTests.__dict__):
    if name.startswith('test_'):setattr(AdapterTests,name,None)

if __name__=='__main__':unittest.main(verbosity=2)
