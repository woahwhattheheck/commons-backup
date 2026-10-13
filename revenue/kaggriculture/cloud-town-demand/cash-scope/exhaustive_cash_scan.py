"""Offline experiment over an existing saved observation and unchanged peers.

Enumerates explicit shop-identity sequences. It is not a new market simulator,
route selector, actor, stochastic forecast or full-game evaluation. This script
uses the exact OSPREY/HAZEL/FLOW/DATE package plus the original AMBER package.
"""
from __future__ import annotations
import argparse, gzip, hashlib, importlib.util, itertools, json, os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys, time
from types import SimpleNamespace

STATE = None

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sha(value): return hashlib.sha256(canonical(value)).hexdigest()

def module(name, filename):
    spec=importlib.util.spec_from_file_location(name, filename)
    obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj
    spec.loader.exec_module(obj);return obj

def prepare(osprey_root, amber_root):
    base, amber=Path(osprey_root),Path(amber_root)
    sys.path.insert(0,str(amber))
    import town_demand as td
    rq=module('cash_scan_reached',base/'source/cloud-capital-bundles/reached_quote_case.py')
    deps=rq.load_dependencies(base/'source')
    row=json.loads((base/'evidence/saved-226-row.json').read_text())
    safe=deps.inputs.actor_input(row,row['seat'])
    obs,cfg=safe['observation'],safe['configuration']
    raw=json.loads((amber/'rules.json').read_text())['rules']
    rules=td.DemandRules(tuple((n,tuple(p)) for n,p in raw['shops']),tuple(raw['products']),
                         tuple(raw['center_products']),raw['max_instances'])
    family=td.scenario_family(obs,cfg,rules,products=['WOOL'])
    programs=deps.programs.routes()
    ids=(deps.hazel.MAIN,deps.hazel.SHEEP)
    offers=tuple(deps.hazel.quote_program(r,programs[r],obs,cfg,deps.mechanics) for r in ids)
    return SimpleNamespace(deps=deps,td=td,rq=rq,raw=row,safe=safe,obs=obs,cfg=cfg,
                           rules=rules,family=family,offers=offers,ids=ids,
                           shop_names=tuple(n for n,_ in rules.shops))

def init_worker(osprey_root,amber_root):
    global STATE
    STATE=prepare(osprey_root,amber_root)

def path_at(index, names, count):
    out=[]
    for _ in range(count):
        index,d=divmod(index,len(names));out.append(names[d])
    if index: raise ValueError('Index outside complete enumeration')
    return tuple(reversed(out))

def spec_for(s,path,name):
    # Explicit experiment inputs for FLOW's EXISTING first-active-turn API.
    # Town absorption remains exclusively inside FLOW; no AMBER delta is added.
    return {'name':name,'shop_additions':{
        str(t+1):[shop] for t,shop in zip(s.family.unlock_after_steps,path)
        if t+1<=int(s.cfg['episodeSteps'])-2},
        'description':'Declared shop-identity path, no rival orders; not a prediction'}

def evaluate_one(s,index):
    path=path_at(index,s.shop_names,len(s.family.unlock_after_steps))
    spec=spec_for(s,path,'identity-'+str(index))
    scenario=s.rq.make_scenarios([spec],s.deps.flow)[0]
    rows=[s.deps.flow.value_route(o,s.obs,s.cfg,s.deps.mechanics,scenario,
                                seconds=None,max_units=1_000_000,retain_trace=False) for o in s.offers]
    all_out=[]
    keep=('route_id','initial_cash','final_marked_cash','minimum_marked_cash','first_negative',
          'own_receipts','own_product_spend','fixed_costs','rival_receipts','rival_product_spend',
          'final_market_inventory')
    for row in rows:
        item={k:row[k] for k in keep}
        item['dynamic_cash_rows']=len(row['cash_flow_rows'])
        item['complete_flow_sha256']=sha(row)
        # Lossless signed settlements: step, slot, delta, supplied quantity.
        item['settlements']=[[r['step'],r['slot'],r['total_own_cash_delta'],r['assumed_filled_quantity']]
                             for r in row['cash_flow_rows']]
        all_out.append(item)
    return {'index':index,'path':list(path),
            'wool_signature':''.join('1' if name=='YARN_STORE' else '0' for name in path),
            'rows':all_out,
            'paired_own_cash_change':rows[1]['final_marked_cash']-rows[0]['final_marked_cash']}

def shard(task):
    start,stop,dest=task;s=STATE;t=time.perf_counter()
    output=Path(dest)/f'scenarios-{start:05d}-{stop-1:05d}.jsonl.gz'
    with output.open('xb') as raw:
        with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as zipped:
            for i in range(start,stop): zipped.write(canonical(evaluate_one(s,i))+b'\n')
    return {'start':start,'stop':stop,'count':stop-start,'file':output.name,
            'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'seconds':time.perf_counter()-t}

def summarize(paths,s):
    groups={}; seen=set(); elapsed_count=0
    for p in paths:
        with gzip.open(p,'rt') as stream:
            for line in stream:
                row=json.loads(line);index=row['index']
                if index in seen:raise ValueError('Duplicate enumeration cell')
                seen.add(index)
                if row['path']!=list(path_at(index,s.shop_names,len(s.family.unlock_after_steps))):
                    raise ValueError('Wrong path binding')
                key=row['wool_signature'];gain=row['paired_own_cash_change']
                g=groups.setdefault(key,{'count':0,'min_gain':gain,'max_gain':gain,
                                        'min_index':index,'max_index':index,'representative':None})
                g['count']+=1
                if gain<g['min_gain']:g.update(min_gain=gain,min_index=index)
                if gain>g['max_gain']:g.update(max_gain=gain,max_index=index)
                if all(n in ('BAKERY','YARN_STORE') for n in row['path']):
                    if g['representative'] is not None:raise ValueError('Duplicate projected representative')
                    g['representative']={'index':index,'gain':gain}
    total=len(s.shop_names)**len(s.family.unlock_after_steps)
    if seen!=set(range(total)):raise ValueError('Incomplete complete-scenario enumeration')
    for key,g in groups.items():
        if g['count']!=7**key.count('0') or g['representative'] is None:
            raise ValueError('Incorrect WOOL class coverage')
        g['within_class_gain_range']=g['max_gain']-g['min_gain']
    minimum=min(g['min_gain'] for g in groups.values())
    maximum=max(g['max_gain'] for g in groups.values())
    projected_min=min(g['representative']['gain'] for g in groups.values())
    largest=max(groups,key=lambda k:groups[k]['within_class_gain_range'])
    return {'complete':True,'identity_paths':len(seen),'route_scenario_pairs':2*len(seen),
            'projected_classes':len(groups),'minimum_paired_own_cash_change':minimum,
            'maximum_paired_own_cash_change':maximum,
            'wool_representatives_minimum':projected_min,
            'projected_minimum_overstatement':projected_min-minimum,
            'largest_within_class_range':{'signature':largest,**groups[largest]},
            'groups':dict(sorted(groups.items()))}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--osprey-root',type=Path,required=True)
    ap.add_argument('--amber-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--batch',type=int,default=256)
    a=ap.parse_args()
    if not 1<=a.workers<=8 or not 1<=a.batch<=1024:ap.error('Use 1..8 workers and 1..1024 cells per batch')
    s=prepare(a.osprey_root,a.amber_root); total=len(s.shop_names)**len(s.family.unlock_after_steps)
    a.output.mkdir(parents=True,exist_ok=False); shards=a.output/'shards';shards.mkdir()
    from cash_scope_audit import inspect_cash_projection
    manifest={'schema':'town-demand.exhaustive-fixed-flow.v1','input_sha256':sha(s.safe),
              'origin':json.loads((a.osprey_root/'evidence/ORIGIN.json').read_text()),
              'source_pins':s.deps.pins,
              'amber_source_sha256':hashlib.sha256((a.amber_root/'town_demand.py').read_bytes()).hexdigest(),
              'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'audit_sha256':hashlib.sha256(Path(__file__).with_name('cash_scope_audit.py').read_bytes()).hexdigest(),
              'audit':inspect_cash_projection(s.family,s.rules,s.offers),
              'future_draw_after_steps':list(s.family.unlock_after_steps),'shop_names':list(s.shop_names),
              'rival_orders':{},'probabilities':None,'new_games':0,'actor_calls':0,
              'scope':'exhaustive declared shop paths, fixed conditional program quantities; no rival trading or physical fill claim',
              'workers':a.workers,'cells':total,'complete':False}
    (a.output/'RUN.json').write_bytes(canonical(manifest)+b'\n')
    jobs=[(i,min(total,i+a.batch),str(shards)) for i in range(0,total,a.batch)]
    t=time.perf_counter();done=[];count=0
    with ProcessPoolExecutor(max_workers=a.workers,initializer=init_worker,
                             initargs=(str(a.osprey_root),str(a.amber_root))) as pool:
        futures=[pool.submit(shard,job) for job in jobs]
        for future in as_completed(futures):
            receipt=future.result();done.append(receipt);count+=receipt['count']
            if count%2048==0 or count==total:
                print(json.dumps({'completed_paths':count,'total':total,'seconds':time.perf_counter()-t}),flush=True)
    summary=summarize(sorted(shards.glob('*.gz')),s)
    manifest.update(complete=True,wall_seconds=time.perf_counter()-t,shards=sorted(done,key=lambda r:r['start']))
    (a.output/'RUN.json').write_bytes(canonical(manifest)+b'\n')
    (a.output/'SUMMARY.json').write_bytes(canonical(summary)+b'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='groups'},indent=2),flush=True)

if __name__=='__main__': main()
