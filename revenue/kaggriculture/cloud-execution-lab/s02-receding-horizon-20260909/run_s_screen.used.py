from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import importlib.util, json, random, sys, time, hashlib
ROOT=Path('/mnt/data/s02_candidate')
EVAL=ROOT/'checks/reference/evaluator/evaluate.py'
ENGINE=ROOT/'checks/reference/engine'
LOADER=ROOT/'checks/reference/evaluator/loader.py'
OPP=str(ROOT/'main.py')+'::agent'
CANDS={
 'control':str(ROOT/'main.py')+'::agent',
 'h6':str(ROOT/'s02_agent_h6.py')+'::agent',
 'h12':str(ROOT/'s02_agent_h12.py')+'::agent',
 'h24':str(ROOT/'s02_agent_h24.py')+'::agent',
}

def load_eval(tag):
 spec=importlib.util.spec_from_file_location('s02_eval_'+tag,EVAL)
 m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def one(job):
 variant,idx,seed,seat=job
 ev=load_eval(f'{variant}_{idx}_{seat}_{seed}')
 engine,_=ev.get_engine(ENGINE,LOADER)
 cand=CANDS[variant]
 pair=[cand,OPP] if seat==0 else [OPP,cand]
 g=ev.play(engine,pair,ENGINE,LOADER,seed,seat,20260909,1.0,10.0,120.0,None)
 return {'variant':variant,'index':idx,'opponent':'current_f8_source_equivalent','seed':seed,'candidate_seat':seat,**g}

def main():
 rng=random.Random(20260909)
 seeds=[]
 while len(seeds)<16:
  x=rng.randrange(1,2**31-1)
  if x not in seeds:seeds.append(x)
 jobs=[(v,i,s,seat) for v in CANDS for i,s in enumerate(seeds) for seat in (0,1)]
 out=[]; started=time.time()
 progress=Path('/mnt/data/s02_results/s02-S-progress.jsonl'); progress.write_text('')
 with ProcessPoolExecutor(max_workers=4) as ex:
  futs={ex.submit(one,j):j for j in jobs}
  for fut in as_completed(futs):
   j=futs[fut]
   try:r=fut.result()
   except BaseException as e:
    r={'variant':j[0],'index':j[1],'seed':j[2],'candidate_seat':j[3],'status':'launcher_error','failure':f'{type(e).__name__}: {e}','scores':None}
   out.append(r)
   short={k:r.get(k) for k in ('variant','index','seed','candidate_seat','status','scores','failure')}
   with progress.open('a') as f:f.write(json.dumps(short,sort_keys=True)+'\n')
   print(json.dumps(short,sort_keys=True),flush=True)
 out.sort(key=lambda r:(list(CANDS).index(r['variant']),r['index'],r['candidate_seat']))
 report={'schema':1,'operation':'titan-v25-orders-20260909-S02','dispatch_main':'fb449442fe515b7912d81d886402e54a990b6d3c','canonical_archive_sha256':'f8f1750266b3cfaea0ebfe663f287aa9c5a2682f6fc47bc932957e1d48e63f1c','materialization_note':'runtime-functional reconstruction from dispatch predecessor 6ac plus exact E12 operating_stock blob 781aa90d/aade61ed; PR11102 CURRENT-SOURCE diff shows operating_stock.py is the only runtime code hash changed','variants':CANDS,'opponent':OPP,'seeds':seeds,'games':out,'wall_seconds':time.time()-started}
 Path('/mnt/data/s02_results/S02-S-SCREEN.json').write_text(json.dumps(report,indent=2)+'\n')
 print('DONE',len(out),report['wall_seconds'],flush=True)
if __name__=='__main__':main()
