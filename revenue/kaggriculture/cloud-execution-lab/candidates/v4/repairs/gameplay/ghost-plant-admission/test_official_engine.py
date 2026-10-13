from __future__ import annotations
import copy, hashlib, importlib.util, os, sys, unittest
from pathlib import Path
from ghost_plant_admission import repair_ghost_plant_poisoning

ROOT_VALUE = os.environ.get('SEEDGHOST_NATIVE_ROOT')
if not ROOT_VALUE:
    raise RuntimeError('SEEDGHOST_NATIVE_ROOT must point at authenticated native runtime artifact')
ROOT=Path(ROOT_VALUE)
ENGINE_PATH=ROOT/'checks/reference/engine'
LOADER_PATH=ROOT/'checks/reference/evaluator/loader.py'

def git_blob(b): return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
assert git_blob((ENGINE_PATH/'kaggriculture.py').read_bytes())=='3c202c7ee921da239356789e266b694635103fc4'
assert git_blob(LOADER_PATH.read_bytes())=='23948e10cfc3d32f46c9abb1321b0d8fc8db21d5'
spec=importlib.util.spec_from_file_location('seedghost_loader',LOADER_PATH); LOADER=importlib.util.module_from_spec(spec); spec.loader.exec_module(LOADER)
ENGINE,_=LOADER.get_engine(ENGINE_PATH)
CALLS=0

def act(farmer=None,hands=None,market=None): return {'farmer':['PASS'] if farmer is None else farmer,'hands':[] if hands is None else hands,'market':[] if market is None else market}

def world(seat, crop, seeds, live_hands):
    global CALLS
    cfg=LOADER.Struct({k:v.get('default') if isinstance(v,dict) else v for k,v in ENGINE.specification['configuration'].items()})
    cfg.update(seed=7331, weedSpawnChance=0)
    env=LOADER.Struct(configuration=cfg,done=False,info={})
    states=[LOADER.Struct(observation=LOADER.Struct(),action=act(),status='ACTIVE',reward=0) for _ in range(2)]
    ENGINE.interpreter(states,env); CALLS+=1
    farm=states[seat].observation.farms[seat]
    positions=[[0,0],[1,0],[2,0],[3,0]][:1+live_hands]
    farm['farmer']=positions[0]; farm['hands']=copy.deepcopy(positions[1:])
    farm['tiles']=[[None for _ in range(10)] for _ in range(10)]
    private=states[seat].observation.private
    private['seeds']={c:0 for c in ENGINE.CROPS}; private['seeds'][crop]=seeds
    private['inventories']=[{} for _ in positions]
    for s in states:
        s.observation.step=10; s.observation.day=0; s.observation.hour=10
    return states,env,positions

def execute(states,env,seat,action):
    global CALLS
    for s in states: s.action=act()
    states[seat].action=copy.deepcopy(action)
    ENGINE.interpreter(states,env); CALLS+=1

def planted(farm,crop):
    return sum(1 for row in farm['tiles'] for t in row if isinstance(t,dict) and t.get('kind')=='PLANT' and t.get('crop')==crop)

class OfficialEngineGhostPlantTests(unittest.TestCase):
    def test_poisoning_is_real_and_repair_restores_two_live_plants_both_seats(self):
        for seat in (0,1):
            states,env,pos=world(seat,'CARROT',2,1)
            parent=act(['PLANT','CARROT'], [['PLANT','CARROT'],['PLANT','CARROT']])
            baseline=copy.deepcopy(states)
            execute(baseline,env,seat,parent)
            self.assertEqual(planted(baseline[seat].observation.farms[seat],'CARROT'),0)
            self.assertEqual(baseline[seat].observation.private['seeds']['CARROT'],2)

            repaired,report=repair_ghost_plant_poisoning(states[seat].observation,parent,enabled=True)
            self.assertTrue(report['certified']); self.assertTrue(report['changed'])
            self.assertEqual(repaired['hands'],[['PLANT','CARROT'],['PASS']])
            execute(states,env,seat,repaired)
            self.assertEqual(planted(states[seat].observation.farms[seat],'CARROT'),2)
            self.assertEqual(states[seat].observation.private['seeds']['CARROT'],0)

    def test_latest_suffix_minimum_edits(self):
        states,env,_=world(0,'WHEAT',2,1)
        parent=act(['PLANT','WHEAT'], [['PLANT','WHEAT'],['PLANT','WHEAT'],['PLANT','WHEAT']])
        out,report=repair_ghost_plant_poisoning(states[0].observation,parent,enabled=True)
        self.assertEqual(report['replaced_hand_indexes'],[1,2])
        self.assertEqual(out['hands'],[['PLANT','WHEAT'],['PASS'],['PASS']])
        execute(states,env,0,out); self.assertEqual(planted(states[0].observation.farms[0],'WHEAT'),2)

    def test_genuine_live_oversubscription_is_untouched(self):
        states,env,_=world(0,'CARROT',2,2)
        parent=act(['PLANT','CARROT'], [['PLANT','CARROT'],['PLANT','CARROT'],['PLANT','CARROT']])
        out,report=repair_ghost_plant_poisoning(states[0].observation,parent,enabled=True)
        self.assertIs(out,parent); self.assertFalse(report['changed'])
        execute(states,env,0,out); self.assertEqual(planted(states[0].observation.farms[0],'CARROT'),0)

    def test_nonpoisoning_surplus_rows_and_market_are_exact_identity(self):
        states,env,_=world(0,'MELON',3,1)
        parent=act(['PLANT','MELON'], [['PLANT','MELON'],['PLANT','MELON'],['NORTH']], [['BUY_SEED','WHEAT',1]])
        saved=copy.deepcopy(parent)
        out,report=repair_ghost_plant_poisoning(states[0].observation,parent,enabled=True)
        self.assertIs(out,parent); self.assertEqual(parent,saved); self.assertFalse(report['changed'])

    def test_multicrop_poisoning_repairs_independently(self):
        states,env,_=world(0,'CARROT',1,1)
        states[0].observation.private['seeds']['TOMATO']=1
        parent=act(['PLANT','CARROT'], [['PLANT','TOMATO'],['PLANT','CARROT'],['PLANT','TOMATO']])
        out,report=repair_ghost_plant_poisoning(states[0].observation,parent,enabled=True)
        self.assertEqual(out['hands'],[['PLANT','TOMATO'],['PASS'],['PASS']])
        self.assertEqual(report['repaired_crops'],['CARROT','TOMATO'])
        execute(states,env,0,out)
        self.assertEqual(planted(states[0].observation.farms[0],'CARROT'),1)
        self.assertEqual(planted(states[0].observation.farms[0],'TOMATO'),1)

    def test_disabled_is_exact_identity(self):
        states,env,_=world(0,'CARROT',2,1)
        parent=act(['PLANT','CARROT'], [['PLANT','CARROT'],['PLANT','CARROT']])
        out,report=repair_ghost_plant_poisoning(states[0].observation,parent,enabled=False)
        self.assertIs(out,parent); self.assertEqual(report['reason'],'disabled')

if __name__=='__main__':
    unittest.main()
