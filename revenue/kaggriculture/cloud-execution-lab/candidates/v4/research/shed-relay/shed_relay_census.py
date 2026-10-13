#!/usr/bin/env python3
"""One-game authenticated route census for same-callback shed relays."""
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, json, sys
from pathlib import Path

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def apply_units(engine,farm,private,actions,cfg,day,through=None,suppress=None):
    f=copy.deepcopy(farm); p=copy.deepcopy(private)
    for idx,action in enumerate(actions):
        if through is not None and idx>through: break
        if suppress is not None and idx==suppress: action=['PASS']
        engine._apply_unit_action(f,p,idx,action,int(cfg.boardSize),day,int(cfg.turnsPerDay),int(cfg.shedCapacity))
    return f,p

def inv_count(private,idx,item):
    invs=private.get('inventories',[])
    return int(invs[idx].get(item,0)) if idx < len(invs) else 0

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True,type=Path);ap.add_argument('--seed',required=True,type=int);ap.add_argument('--seat',required=True,type=int,choices=(0,1));ap.add_argument('--output',type=Path);a=ap.parse_args()
    root=a.root.resolve();sys.path.insert(0,str(root));ev=load('_relay_eval',root/'checks/reference/evaluator/evaluate.py');engine,engine_hashes=ev.get_engine(root/'checks/reference/engine',root/'checks/reference/evaluator/loader.py');mainmod=load('_relay_main',root/'main.py')
    cfg=ev.Struct({k:v.get('default') if isinstance(v,dict) else v for k,v in engine.specification['configuration'].items()});cfg.seed=a.seed
    env=ev.Struct(configuration=cfg,done=False,info={});states=[ev.Struct(observation=ev.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)];engine.interpreter(states,env)
    structural=0; actual_links=[]; writes=0; pickups=0; drop_actions=0; place_actions=0; callbacks=0
    for step in range(cfg.episodeSteps):
        for i,s in enumerate(states):
            s.observation.step=step;obs=copy.deepcopy(s.observation);action=mainmod.agent(obs,cfg) if i==a.seat else engine.starter_agent(obs)
            if i==a.seat:
                callbacks+=1;actions=[action.get('farmer',['PASS'])]+list(action.get('hands',[]));farm=obs['farms'][a.seat];private=obs['private']; day=int(obs.get('day',0))
                # Discover actual per-actor shed writes and pickups by replaying the unit sequence exactly.
                sf=copy.deepcopy(farm);sp=copy.deepcopy(private);write_events=[]
                for idx,ua in enumerate(actions):
                    if isinstance(ua,list) and ua:
                        if ua[0]=='DROP':drop_actions+=1
                        if ua[0]=='PLACE':place_actions+=1
                    shed_before=dict(sp['shed'])
                    engine._apply_unit_action(sf,sp,idx,ua,int(cfg.boardSize),day,int(cfg.turnsPerDay),int(cfg.shedCapacity))
                    shed_after=dict(sp['shed'])
                    for item,after_n in shed_after.items():
                        delta=after_n-int(shed_before.get(item,0))
                        if delta>0:
                            writes+=1;write_events.append((idx,item,delta,copy.deepcopy(ua)))
                    if isinstance(ua,list) and ua and ua[0]=='PICKUP' and len(ua)>=2:
                        item=ua[1]; before_n=int(shed_before.get(item,0)); after_n=int(shed_after.get(item,0)); got=max(0,before_n-after_n)
                        if got>0: pickups+=1
                        for widx,witem,wqty,wact in write_events:
                            if widx<idx: structural+=1
                            if widx<idx and witem==item and got>0:
                                _,cfp=apply_units(engine,farm,private,actions,cfg,day,through=idx,suppress=widx)
                                actual_recv=inv_count(sp,idx,item); cf_recv=inv_count(cfp,idx,item); causal=max(0,actual_recv-cf_recv)
                                actual_links.append({'step':step,'writer_index':widx,'writer_action':wact,'reader_index':idx,'reader_action':copy.deepcopy(ua),'item':item,'write_units':wqty,'pickup_units':got,'causal_units_vs_writer_suppressed':causal})
            s.action=action
        engine.interpreter(states,env)
        if any(s.status=='DONE' for s in states):break
    source_sha=hashlib.sha256((root/'SOURCE.json').read_bytes()).hexdigest() if (root/'SOURCE.json').exists() else None
    out={'schema':'titan-v4-shed-relay-census-cell/v1','seed':a.seed,'seat':a.seat,'source_manifest_sha256':source_sha,'engine_hashes':engine_hashes,'callbacks':callbacks,'drop_actions':drop_actions,'place_actions':place_actions,'actual_shed_write_events':writes,'actual_pickup_events':pickups,'earlier_write_before_later_pickup_pairs_any_item':structural,'same_item_links':actual_links,'causal_same_item_links':[x for x in actual_links if x['causal_units_vs_writer_suppressed']>0]}
    text=json.dumps(out,indent=2,sort_keys=True)+'\n'
    if a.output:a.output.write_text(text)
    print(json.dumps({'seed':a.seed,'seat':a.seat,'callbacks':callbacks,'drop_actions':drop_actions,'place_actions':place_actions,'actual_shed_write_events':writes,'actual_pickup_events':pickups,'earlier_write_before_later_pickup_pairs_any_item':structural,'same_item_links':len(actual_links),'causal_same_item_links':len(out['causal_same_item_links'])},sort_keys=True))
if __name__=='__main__':main()
