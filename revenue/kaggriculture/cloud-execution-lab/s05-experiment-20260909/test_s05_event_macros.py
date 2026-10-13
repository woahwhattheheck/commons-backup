import copy, importlib.util, os, unittest
from pathlib import Path
from s05_event_macros import *
ROOT=Path(os.environ.get('S05_RUNTIME_ROOT','/mnt/data/s02_f8'))
ROUTE=ROOT/'reference/next-panel/vendor/arlene.py'
LIB=build_library(ROUTE); IDX=index_library(LIB)
spec=importlib.util.spec_from_file_location('routes',ROUTE); routes=importlib.util.module_from_spec(spec);spec.loader.exec_module(routes); R=routes.routes()

def farm(money=1000,pos=(4,4)):
    tiles=[[None for _ in range(10)] for _ in range(10)]
    return {'money':money,'farmer':list(pos),'hands':[],'hires_today':0,'unlocked_quadrants':['NW'],'tiles':tiles}
def obs(step=23,money=1000,pos=(4,4),shed=None,inv=None):
    return {'step':step,'player':0,'farms':[farm(money,pos),{}],'private':{'shed':dict(shed or {}),'seeds':{},'inventories':[dict(inv or {})]},'town':{'unlocked_shops':[]}}
def macro(fam,step,action): return {'id':'x','family':fam,'step':step,'action':action,'routes':['r'],'layer':'canonical_route_action_before_runtime_transforms'}

class Contracts(unittest.TestCase):
 def test_library_is_deterministic_bounded_and_family_complete(self):
  other=build_library(ROUTE); self.assertEqual(LIB,other); self.assertLessEqual(len(LIB),2000)
  self.assertEqual(set(m['family'] for m in LIB),set(FAMILIES)); self.assertEqual(library_sha256(LIB),library_sha256(other))
 def test_nearest_fragment_wrong_step_rejected(self):
  m=next(m for m in LIB if m['family']=='hire')
  o=obs(m['step']+1,money=10**9); ok,info=precondition(m,o,{})
  self.assertFalse(ok); self.assertEqual(info['reason'],'wrong_step')
 def test_hire_cash_is_exact_and_stale_cash_rejected(self):
  a={'farmer':['PASS'],'hands':[],'market':[['HIRE'],['HIRE'],['HIRE']]}; m=macro('hire',24,a)
  self.assertTrue(precondition(m,obs(24,money=4),{})[0]); self.assertFalse(precondition(m,obs(24,money=3),{})[0])
 def test_pickup_exact_quantity_and_stale_quantity_rejected(self):
  a={'farmer':['PICKUP','WHEAT',2],'hands':[],'market':[]}; m=macro('pickup_drop',24,a)
  self.assertTrue(precondition(m,obs(24,shed={'WHEAT':2}),{})[0]); self.assertFalse(precondition(m,obs(24,shed={'WHEAT':1}),{})[0])
 def test_drop_requires_access_and_nonempty_inventory(self):
  a={'farmer':['DROP'],'hands':[],'market':[]};m=macro('pickup_drop',24,a)
  self.assertFalse(precondition(m,obs(24,pos=(0,0),inv={'MILK':1}),{})[0]); self.assertFalse(precondition(m,obs(24,pos=(4,4),inv={}),{})[0]); self.assertTrue(precondition(m,obs(24,pos=(4,4),inv={'MILK':1}),{})[0])
 def test_immature_harvest_rejected(self):
  a={'farmer':['HARVEST'],'hands':[],'market':[]};m=macro('maturity',24,a);o=obs(24,pos=(1,1));o['farms'][0]['tiles'][1][1]={'kind':'PLANT','crop':'WHEAT','planted_day':1,'yield_units':2}
  self.assertFalse(precondition(m,o,{})[0]);o['farms'][0]['tiles'][1][1]['planted_day']=-2;self.assertTrue(precondition(m,o,{})[0])
 def test_escape_requires_exact_legal_feed(self):
  a={'farmer':['FEED'],'hands':[],'market':[]};m=macro('escape',23,a);o=obs(23,pos=(1,1),inv={'WHEAT':1});o['farms'][0]['tiles'][1][1]={'kind':'PASTURE','animal':'COW','fed_today':False,'consecutive_unfed':1}
  self.assertTrue(precondition(m,o,{})[0]);o['private']['inventories'][0]={};self.assertFalse(precondition(m,o,{})[0])
 def test_unlock_identity_is_not_predicted_but_count_is_exact(self):
  a={'farmer':['PASS'],'hands':[],'market':[]};m=macro('unlock',71,a);o=obs(71);ok,info=precondition(m,o,{'townShopUnlockInterval':3});self.assertTrue(ok);self.assertEqual(info['shops_before'],0)
  nxt=copy.deepcopy(o);nxt['step']=72;nxt['town']['unlocked_shops']=['YARN_STORE'];self.assertTrue(revalidate(m,info,o,nxt,{'townShopUnlockInterval':3})[0])
 def test_reset_postcondition_discards_stale_commitment(self):
  a={'farmer':['PASS'],'hands':[],'market':[]};m=macro('reset',23,a);o=obs(23);ok,info=precondition(m,o,{});self.assertTrue(ok)
  nxt=obs(24);nxt['farms'][0]['hands']=[[4,4]];self.assertFalse(revalidate(m,info,o,nxt,{})[0])
 def test_beam_only_recommends_strict_exact_prior_improvement(self):
  # Synthetic two-route branch with identical prefix. Only alternative has exact pickup.
  base=[{'farmer':['PASS'],'hands':[],'market':[]} for _ in range(3)];alt=copy.deepcopy(base);alt[2]={'farmer':['PICKUP','WHEAT',1],'hands':[],'market':[]}; routes0={'a':base,'b':alt}
  l=[macro('pickup_drop',2,alt[2])];l[0]['routes']=['b'];l[0]['id']='m';i=index_library(l);o=obs(2,shed={'WHEAT':1})
  r=rank_prefix_beam(routes0,'a',2,o,{},i);self.assertTrue(r['changed_recommendation']);self.assertEqual(r['winner'],'b')
 def test_settlement_off_by_one_rejected(self):
  a={'farmer':['DROP'],'hands':[],'market':[]};m=macro('settlement',718,a);self.assertFalse(precondition(m,obs(717),{})[0]);self.assertTrue(precondition(m,obs(718),{})[0])

if __name__=='__main__':unittest.main()
