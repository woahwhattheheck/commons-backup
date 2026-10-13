#!/usr/bin/env python3
from __future__ import annotations
from copy import deepcopy
import hashlib, importlib.util, os, sys, types, unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))
import native_census as census
from unit_pipeline_admission import reorder_unit_pipeline

DEFAULT_ENGINE = (HERE.parents[3] / 'reference' / 'engine' / 'kaggriculture.py') if len(HERE.parents) > 3 else Path('/nonexistent/kaggriculture.py')
ENGINE = Path(os.environ.get('TILEPIPE_TEST_ENGINE', str(DEFAULT_ENGINE)))

def git_blob(p):
 b=p.read_bytes(); return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()

def load_engine():
 pkg=types.ModuleType('kaggle_environments'); utils=types.ModuleType('kaggle_environments.utils'); utils.resolve_episode_seed=lambda env:0
 oldp=sys.modules.get('kaggle_environments'); oldu=sys.modules.get('kaggle_environments.utils'); sys.modules['kaggle_environments']=pkg;sys.modules['kaggle_environments.utils']=utils
 try:
  spec=importlib.util.spec_from_file_location('_tilepipe_test_engine',ENGINE); mod=importlib.util.module_from_spec(spec);sys.modules['_tilepipe_test_engine']=mod;spec.loader.exec_module(mod);return mod
 finally:
  if oldp is None:sys.modules.pop('kaggle_environments',None)
  else:sys.modules['kaggle_environments']=oldp
  if oldu is None:sys.modules.pop('kaggle_environments.utils',None)
  else:sys.modules['kaggle_environments.utils']=oldu

def world(tile,*,hands=2,seeds=None,inventories=None):
 board=[[None for _ in range(10)] for _ in range(10)];board[4][4]=deepcopy(tile)
 farm={'money':3000.0,'tiles':board,'farmer':[4,4],'hands':[[4,4] for _ in range(hands)],'unlocked_quadrants':['NW'],'hires_today':0}
 private={'shed':{},'seeds':dict(seeds or {}),'inventories':deepcopy(inventories) if inventories is not None else [{} for _ in range(hands+1)]}
 return farm,private

def obs(farm,private):return {'player':0,'farms':[farm],'private':private}

class NativeCensusTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.engine=load_engine();cls.cfg={'boardSize':10,'turnsPerDay':24,'shedCapacity':100};self_blob=git_blob(ENGINE);assert self_blob==census.ENGINE_GIT_BLOB,(self_blob,census.ENGINE_GIT_BLOB)

 def test_constructed_ordered_pure_chain_fires_detector_and_admission(self):
  f,p=world({'kind':'WEED'},hands=2,seeds={'WHEAT':1}); action={'farmer':['DIG'],'hands':[['PLANT','WHEAT'],['WATER']],'market':[]}
  events=census.analyze_unit_vector(self.engine,f,p,action,step=0,cfg=self.cfg); names=[e['chain'] for e in events]
  self.assertIn('DIG_PLANT',names);self.assertIn('PLANT_WATER',names);self.assertIn('DIG_PLANT_WATER',names)
  got,report=reorder_unit_pipeline(obs(f,p),action,enabled=True);self.assertEqual(1,report['eligible_groups']);self.assertEqual(0,report['changed_groups']);self.assertEqual(action,got)

 def test_constructed_backward_pure_chain_is_admission_opportunity(self):
  f,p=world({'kind':'WEED'},hands=2,seeds={'WHEAT':1}); action={'farmer':['WATER'],'hands':[['PLANT','WHEAT'],['DIG']],'market':[]}
  self.assertEqual([],census.analyze_unit_vector(self.engine,f,p,action,step=0,cfg=self.cfg))
  got,report=reorder_unit_pipeline(obs(f,p),action,enabled=True);self.assertEqual(1,report['eligible_groups']);self.assertEqual(1,report['changed_groups']);self.assertEqual(['DIG'],got['farmer']);self.assertEqual([['PLANT','WHEAT'],['WATER']],got['hands'])

 def test_constructed_fertilizer_bonus_and_build_place_fire(self):
  plant=self.engine._new_plant('WHEAT',0,24);plant['yield_units']=1;plant['watered_today']=False;plant['consecutive_unwatered']=0
  f,p=world(plant,hands=1,inventories=[{'FERTILIZER':1},{}]); action={'farmer':['FERTILIZE'],'hands':[['WATER']],'market':[]}
  names=[e['chain'] for e in census.analyze_unit_vector(self.engine,f,p,action,step=72,cfg=self.cfg)];self.assertIn('FERTILIZE_WATER_FRESH_BONUS',names)
  f,p=world(None,hands=1,inventories=[{}, {'GOOSE':1}]); action={'farmer':['BUILD_COOP'],'hands':[['PLACE','GOOSE']],'market':[]}
  names=[e['chain'] for e in census.analyze_unit_vector(self.engine,f,p,action,step=0,cfg=self.cfg)];self.assertIn('BUILD_PLACE',names)

 def test_donor_annual_relay_all_3x3_and_cargo_custody(self):
  day=12
  for old in ('WHEAT','CARROT','MELON'):
   for new in ('WHEAT','CARROT','MELON'):
    first=self.engine.CROPS[old]['first_yield_day']; plant=self.engine._new_plant(old,day-first,24);plant['yield_units']=min(3,self.engine.CROPS[old]['max_yield']);plant['watered_today']=True;plant['consecutive_unwatered']=0
    f,p=world(plant,hands=2,seeds={new:1}); rows=[['HARVEST'],['PLANT',new],['WATER']]
    for i,row in enumerate(rows):self.engine._apply_unit_action(f,p,i,row,10,day,24,100)
    self.assertGreater(p['inventories'][0].get(old,0),0);self.assertNotIn(old,p['inventories'][1]);self.assertNotIn(old,p['inventories'][2])
    tile=f['tiles'][4][4];self.assertEqual(new,tile['crop']);self.assertTrue(tile['watered_today']);self.engine._daily_refresh_plants(f,day,24);self.assertEqual('PLANT',f['tiles'][4][4]['kind'])

 def test_donor_reversed_annual_relay_weeds_at_eod(self):
  day=12;old='WHEAT';new='CARROT';first=self.engine.CROPS[old]['first_yield_day'];plant=self.engine._new_plant(old,day-first,24);plant['yield_units']=3;plant['watered_today']=True;plant['consecutive_unwatered']=0
  f,p=world(plant,hands=2,seeds={new:1})
  for i,row in enumerate([['HARVEST'],['WATER'],['PLANT',new]]):self.engine._apply_unit_action(f,p,i,row,10,day,24,100)
  self.assertFalse(f['tiles'][4][4]['watered_today']);self.engine._daily_refresh_plants(f,day,24);self.assertEqual({'kind':'WEED'},f['tiles'][4][4])

if __name__=='__main__':unittest.main()
