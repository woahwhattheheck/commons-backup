import copy, importlib.util, os, unittest
from pathlib import Path
import s03_uct as u
ROOT=Path(os.environ.get('S03_RUNTIME_ROOT','/mnt/data/s02_candidate'))
spec=importlib.util.spec_from_file_location('routes',ROOT/'reference/next-panel/vendor/arlene.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r);R=r.routes()
spec2=importlib.util.spec_from_file_location('mech',ROOT/'mechanics.py');m=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(m)

def obs(step=360,money=100000,shed=None):
 tiles=[[None for _ in range(10)] for _ in range(10)]
 return {'step':step,'player':0,'farms':[{'money':money,'farmer':[4,4],'hands':[[4,4] for _ in range(9)],'hires_today':9,'unlocked_quadrants':['NW'],'tiles':tiles},{'money':1000,'farmer':[5,5],'hands':[],'tiles':tiles}], 'private':{'shed':dict({'WHEAT':20,'MILK':20,'WOOL':20,'EGG':20,'FERTILIZER':20} if shed is None else shed),'seeds':{'WHEAT':20,'CARROT':20},'inventories':[{} for _ in range(10)]}, 'market':{'inventory':{k:5000 for k in u.PRODUCTS},'params':None,'prices':{k:100 for k in u.PRODUCTS}},'town':{'unlocked_shops':['YARN_STORE']}}

class Contracts(unittest.TestCase):
 def test_real_branch_candidates(self):
  self.assertEqual(set(u.prefix_compatible_routes(R,r.MAIN,226)),{r.YARN,r.YARN_CARROT,r.MILK_GLUT})
  self.assertIn(r.MILK_GLUT,u.prefix_compatible_routes(R,r.MAIN,360))
 def test_single_candidate_fails_closed(self):
  routes={'a':[{'farmer':['PASS'],'hands':[],'market':[]}]};x=u.run_uct(routes,'a',0,obs(0),{},m,64);self.assertFalse(x['triggered']);self.assertEqual(x['winner'],'a')
 def test_deterministic_rng_and_result(self):
  o=obs(360);a=u.run_uct(R,r.MAIN,360,o,{},m,64,40);b=u.run_uct(R,r.MAIN,360,o,{},m,64,40);self.assertEqual(a['seed'],b['seed']);self.assertEqual(a['winner'],b['winner']);self.assertEqual(a['scenario_counts'],b['scenario_counts'])
 def test_no_global_random_mutation(self):
  import random
  random.seed(123);before=random.getstate();u.run_uct(R,r.MAIN,360,obs(360),{},m,64,40);self.assertEqual(before,random.getstate())
 def test_public_rival_supply_ignores_private(self):
  o=obs(360);o['farms'][1]['tiles'][0][0]={'kind':'PLANT','crop':'CARROT','yield_units':7};self.assertEqual(u._visible_rival_supply(o,'CARROT'),7);o['rival_private']={'shed':{'CARROT':100}};self.assertEqual(u._visible_rival_supply(o,'CARROT'),7)
 def test_unfunded_hire_rejected(self):
  v,rep=u.leaf_value(r.MAIN,R,360,obs(360,money=0),{},m,'incumbent');self.assertLess(v,-1e14);self.assertFalse(rep['feasible'])
 def test_pickup_requires_actual_stock(self):
  o=obs(360,shed={'WHEAT':0});v,rep=u.leaf_value(r.YARN,R,360,o,{},m,'incumbent');self.assertLess(v,-1e14);self.assertEqual(rep['reason'],'pickup_unavailable')
 def test_progressive_widening_stays_bounded(self):
  x=u.run_uct(R,r.MAIN,226,obs(226),{},m,64,40);self.assertLessEqual(x['simulations_completed'],64);self.assertLess(x['elapsed_ms'],100);self.assertEqual(set(x['scenario_counts']),set(u.SCENARIOS))
 def test_tie_retains_canonical(self):
  row={'farmer':['PASS'],'hands':[],'market':[]};routes={'a':[row],'b':[copy.deepcopy(row)]};x=u.run_uct(routes,'a',0,obs(0),{},m,64,40);self.assertEqual(x['winner'],'a')
 def test_future_obligation_shortfall_fails_closed(self):
  route=[{'farmer':['PASS'],'hands':[],'market':[]} for _ in range(5)];route[1]={'farmer':['FEED'],'hands':[],'market':[]};routes={'a':route,'b':copy.deepcopy(route)};o=obs(0,shed={});o['private']['inventories']=[{} for _ in range(10)];v,rep=u.leaf_value('a',routes,0,o,{},m,'incumbent');self.assertLess(v,-1e14);self.assertEqual(rep['reason'],'future_owned_obligation_shortfall')
if __name__=='__main__':unittest.main()
