"""Cross-check S05 strict predicates against the pinned official unit engine."""
import copy, importlib.util, json, os, random, sys, types, unittest
from pathlib import Path
try:
 import kaggle_environments.utils  # type: ignore
except ModuleNotFoundError:
 pkg=types.ModuleType('kaggle_environments'); util=types.ModuleType('kaggle_environments.utils'); util.resolve_episode_seed=lambda cfg: int(getattr(cfg,'seed',0) if not isinstance(cfg,dict) else cfg.get('seed',0) or 0); pkg.utils=util; sys.modules['kaggle_environments']=pkg; sys.modules['kaggle_environments.utils']=util
from s05_event_macros import precondition
ROOT=Path(os.environ.get('S05_RUNTIME_ROOT','/mnt/data/s02_f8'))
ENG=ROOT/'checks/reference/engine/kaggriculture.py'
spec=importlib.util.spec_from_file_location('s05_engine',ENG);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)

def base_obs(step=24,pos=(4,4),money=1000):
 tiles=[[None for _ in range(10)] for _ in range(10)]
 return {'step':step,'player':0,'farms':[{'money':money,'farmer':list(pos),'hands':[],'hires_today':0,'unlocked_quadrants':['NW'],'tiles':tiles},{}], 'private':{'shed':{},'seeds':{},'inventories':[{}]},'town':{'unlocked_shops':[]}}
def macro(fam,step,action):return {'id':'x','family':fam,'step':step,'action':action,'routes':['r'],'layer':'canonical_route_action_before_runtime_transforms'}

class Precision(unittest.TestCase):
 def test_pickup_predicate_matches_official_non_noop(self):
  rng=random.Random(20260909);cases=0
  for _ in range(200):
   step=24;adj=rng.choice([True,False]);pos=(4,4) if adj else (0,0);avail=rng.randrange(0,5);req=rng.randrange(1,5)
   o=base_obs(step,pos);o['private']['shed']['WHEAT']=avail;a=['PICKUP','WHEAT',req];m=macro('pickup_drop',step,{'farmer':a,'hands':[],'market':[]})
   predicted=precondition(m,o,{})[0];f=copy.deepcopy(o['farms'][0]);p=copy.deepcopy(o['private']);before=copy.deepcopy(p)
   e._apply_unit_action(f,p,0,a,10,1,24,100);exact=(adj and avail>=req and req>0 and int(before['shed'].get('WHEAT',0))-int(p['shed'].get('WHEAT',0))==req)
   self.assertEqual(predicted,exact,(adj,avail,req));cases+=1
  self.assertEqual(cases,200)
 def test_drop_predicate_matches_official_non_noop(self):
  rng=random.Random(20260910)
  for _ in range(160):
   adj=rng.choice([True,False]);pos=(4,4) if adj else (0,0);qty=rng.randrange(0,4);o=base_obs(24,pos);o['private']['inventories'][0]={'MILK':qty} if qty else {};a=['DROP'];m=macro('pickup_drop',24,{'farmer':a,'hands':[],'market':[]})
   predicted=precondition(m,o,{})[0];f=copy.deepcopy(o['farms'][0]);p=copy.deepcopy(o['private']);before=copy.deepcopy(p);e._apply_unit_action(f,p,0,a,10,1,24,100);changed=p!=before
   self.assertEqual(predicted,changed,(adj,qty))
 def test_harvest_predicate_matches_official_non_noop(self):
  rng=random.Random(20260911)
  for _ in range(180):
   step=rng.choice([24,48,72,96]);day=step//24;age=rng.randrange(0,5);yield_units=rng.randrange(0,4);o=base_obs(step,(1,1));o['farms'][0]['tiles'][1][1]={'kind':'PLANT','crop':'WHEAT','planted_day':day-age,'yield_units':yield_units,'watered_today':False,'consecutive_unwatered':0,'max_lifespan_step':999,'fertilized_until_day':-1};a=['HARVEST'];m=macro('maturity',step,{'farmer':a,'hands':[],'market':[]})
   predicted=precondition(m,o,{})[0];f=copy.deepcopy(o['farms'][0]);p=copy.deepcopy(o['private']);before=(copy.deepcopy(f),copy.deepcopy(p));e._apply_unit_action(f,p,0,a,10,day,24,100);changed=(f,p)!=before
   self.assertEqual(predicted,changed,(step,age,yield_units))
 def test_hire_cash_predicate_matches_official_all_hires_complete(self):
  for count in range(1,8):
   for money in range(0,40):
    action={'farmer':['PASS'],'hands':[],'market':[['HIRE'] for _ in range(count)]};m=macro('hire',24,action);o=base_obs(24,money=money);pred=precondition(m,o,{})[0];f=copy.deepcopy(o['farms'][0]);p=copy.deepcopy(o['private'])
    for _ in range(count): e._do_hire(f,p,10,1)
    self.assertEqual(pred,int(f['hires_today'])==count,(count,money,f['hires_today']))

if __name__=='__main__':unittest.main()
