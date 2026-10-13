#!/usr/bin/env python3
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, json, sys
from pathlib import Path

def load(path: Path):
    name='_shed_relay_'+path.stem+str(abs(hash(str(path))))
    spec=importlib.util.spec_from_file_location(name, path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def snapshot(private):
    return {'shed':dict(private['shed']), 'inventories':[dict(x) for x in private['inventories']]}

def base(engine, board=10):
    farm=engine._new_farm(board,3000); private=engine._new_private()
    farm['farmer']=[4,4]; farm['hands']=[[5,4]]
    private['inventories']=[{},{}]
    return farm,private

def apply(engine,farm,priv,idx,action,cap=100):
    engine._apply_unit_action(farm,priv,idx,action,10,0,24,cap)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True,type=Path); ap.add_argument('--output',type=Path); a=ap.parse_args()
    root=a.root.resolve(); sys.path.insert(0,str(root))
    ev=load(root/'checks/reference/evaluator/evaluate.py')
    eng, hashes=ev.get_engine(root/'checks/reference/engine', root/'checks/reference/evaluator/loader.py')
    engine_path=root/'checks/reference/engine/kaggriculture.py'
    out={'schema':'titan-v4-shed-relay-oracle/v1','engine_sha256':hashlib.sha256(engine_path.read_bytes()).hexdigest(),'engine_loader_hashes':hashes,'cases':{}}

    # Forward DROP -> PICKUP: later hand must see the same-callback deposit.
    f,p=base(eng); p['inventories'][0]={'WHEAT':3}; before=snapshot(p)
    apply(eng,f,p,0,['DROP']); mid=snapshot(p); apply(eng,f,p,1,['PICKUP','WHEAT',2]); after=snapshot(p)
    out['cases']['forward_drop_pickup']={'before':before,'mid':mid,'after':after,'pass':mid['shed']['WHEAT']==3 and after['shed']['WHEAT']==1 and after['inventories'][1].get('WHEAT')==2}

    # Reverse order cannot time-travel: PICKUP before DROP sees an empty shed.
    f,p=base(eng); p['inventories'][0]={'WHEAT':3}; before=snapshot(p)
    apply(eng,f,p,1,['PICKUP','WHEAT',2]); mid=snapshot(p); apply(eng,f,p,0,['DROP']); after=snapshot(p)
    out['cases']['reverse_pickup_drop']={'before':before,'mid':mid,'after':after,'pass':mid['inventories'][1].get('WHEAT',0)==0 and after['shed']['WHEAT']==3}

    # PLACE at a shed-access tile is also an immediate partial shed writer.
    f,p=base(eng); p['inventories'][0]={'MILK':3}; before=snapshot(p)
    apply(eng,f,p,0,['PLACE','MILK',2]); mid=snapshot(p); apply(eng,f,p,1,['PICKUP','MILK',2]); after=snapshot(p)
    out['cases']['forward_place_pickup']={'before':before,'mid':mid,'after':after,'pass':mid['shed']['MILK']==2 and mid['inventories'][0].get('MILK')==1 and after['shed']['MILK']==0 and after['inventories'][1].get('MILK')==2}

    # Requested item must match; unrelated deposits do not satisfy pickup.
    f,p=base(eng); p['inventories'][0]={'WHEAT':2}; apply(eng,f,p,0,['DROP']); mid=snapshot(p); apply(eng,f,p,1,['PICKUP','MELON',1]); after=snapshot(p)
    out['cases']['item_mismatch']={'mid':mid,'after':after,'pass':after['inventories'][1].get('MELON',0)==0 and after['shed']['WHEAT']==2}

    # Both operations require exact shed-access positions.
    f,p=base(eng); f['farmer']=[0,0]; p['inventories'][0]={'WHEAT':2}; apply(eng,f,p,0,['DROP']); after=snapshot(p)
    out['cases']['writer_not_adjacent']={'after':after,'pass':after['shed']['WHEAT']==0 and after['inventories'][0].get('WHEAT')==2}
    f,p=base(eng); f['hands'][0]=[0,0]; p['shed']['WHEAT']=2; apply(eng,f,p,1,['PICKUP','WHEAT',2]); after=snapshot(p)
    out['cases']['reader_not_adjacent']={'after':after,'pass':after['shed']['WHEAT']==2 and after['inventories'][1].get('WHEAT',0)==0}

    # Capacity hazard: DROP clears the whole source inventory even when only part fits.
    f,p=base(eng); p['shed']['MELON']=99; p['inventories'][0]={'WHEAT':3}; apply(eng,f,p,0,['DROP'],100); after=snapshot(p)
    out['cases']['drop_capacity_loss']={'after':after,'pass':after['shed']['WHEAT']==1 and after['inventories'][0].get('WHEAT',0)==0,'cargo_lost':2}

    out['pass']=all(c['pass'] for c in out['cases'].values())
    txt=json.dumps(out,indent=2,sort_keys=True)+'\n'
    if a.output:a.output.write_text(txt)
    print(json.dumps({'pass':out['pass'],'engine_sha256':out['engine_sha256'],'cases':{k:v['pass'] for k,v in out['cases'].items()}},sort_keys=True))
if __name__=='__main__':main()
