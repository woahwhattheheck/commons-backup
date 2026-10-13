from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import importlib.util, json, os, random, sys, tempfile, time
from s05_completeness import require_complete_panel
ROOT=Path(os.environ['S05_RUNTIME_ROOT']).resolve();EVAL=ROOT/'checks/reference/evaluator/evaluate.py';ENGINE=ROOT/'checks/reference/engine';LOADER=ROOT/'checks/reference/evaluator/loader.py';OPP=str(ROOT/'main.py')+'::agent'
CANDS={'control':OPP,'shadow':str(ROOT/'s05_agent_shadow.py')+'::agent','prior':str(ROOT/'s05_agent_prior.py')+'::agent'}

def load_eval(tag):
 spec=importlib.util.spec_from_file_location('s05_eval_'+tag,EVAL);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def trace_path(variant):
 if variant=='shadow':return Path('/tmp')/f's05-shadow-{os.getpid()}.jsonl'
 if variant=='prior':return Path('/tmp')/f's05-prior-{os.getpid()}.jsonl'
 return None

def trace_summary(variant,path):
 rows=[] if path is None or not path.exists() else [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
 if variant=='shadow':
  return {'rows':len(rows),'candidates':sum(r.get('kind')=='candidate' for r in rows),'preserved_candidates':sum(r.get('kind')=='candidate' and r.get('preserved') for r in rows),'fires':sum(r.get('kind')=='fire' for r in rows),'fire_families':{k:sum(r.get('kind')=='fire' and r.get('family')==k for r in rows) for k in ('reset','unlock','hire','escape','maturity','pickup_drop','settlement')},'revalidations':sum(r.get('kind')=='revalidation' for r in rows),'revalidation_failures':sum(r.get('kind')=='revalidation' and not r.get('ok') for r in rows),'beam_checks':sum(r.get('kind')=='beam' for r in rows),'changed_recommendations':sum(r.get('kind')=='beam' and r.get('changed_recommendation') for r in rows),'changed_beams':[r for r in rows if r.get('kind')=='beam' and r.get('changed_recommendation')]}
 if variant=='prior':
  return {'rows':len(rows),'switches':sum(r.get('kind')=='prior_switch' for r in rows),'revalidations':sum(r.get('kind')=='prior_revalidation' for r in rows),'revalidation_failures':sum(r.get('kind')=='prior_revalidation' and not r.get('ok') for r in rows),'rollbacks':sum(r.get('kind')=='rollback' for r in rows),'events':rows}
 return None

def one(job):
 variant,idx,seed,seat=job;path=trace_path(variant)
 if path:path.unlink(missing_ok=True)
 ev=load_eval(f'{variant}_{idx}_{seat}_{seed}');engine,_=ev.get_engine(ENGINE,LOADER);cand=CANDS[variant];pair=[cand,OPP] if seat==0 else [OPP,cand]
 g=ev.play(engine,pair,ENGINE,LOADER,seed,seat,20260909,1.0,10.0,120.0,None);g['macro_trace']=trace_summary(variant,path)
 if path:path.unlink(missing_ok=True)
 return {'variant':variant,'index':idx,'seed':seed,'candidate_seat':seat,**g}

def main():
 nseeds=int(os.environ.get('S05_SEEDS','16'));workers=int(os.environ.get('S05_WORKERS','2'));rng=random.Random(20260909);seeds=[]
 while len(seeds)<nseeds:
  x=rng.randrange(1,2**31-1)
  if x not in seeds:seeds.append(x)
 jobs=[(v,i,s,seat) for v in CANDS for i,s in enumerate(seeds) for seat in (0,1)];out=[];started=time.time()
 with ProcessPoolExecutor(max_workers=workers) as ex:
  futs={ex.submit(one,j):j for j in jobs}
  for fut in as_completed(futs):
   j=futs[fut]
   try:r=fut.result()
   except BaseException as e:r={'variant':j[0],'index':j[1],'seed':j[2],'candidate_seat':j[3],'status':'launcher_error','failure':f'{type(e).__name__}: {e}','scores':None,'macro_trace':None}
   out.append(r);print(json.dumps({k:r.get(k) for k in ('variant','index','candidate_seat','status','scores','failure')},sort_keys=True),flush=True)
 order={k:i for i,k in enumerate(CANDS)};out.sort(key=lambda r:(order[r['variant']],r['index'],r['candidate_seat']))
 report={'schema':1,'operation':'titan-v25-orders-20260909-S05','dispatch_main':os.environ.get('S05_DISPATCH_MAIN'),'runtime_root':str(ROOT),'seeds':seeds,'games':out,'wall_seconds':time.time()-started}
 dest=Path(os.environ.get('S05_RESULT_PATH','S05-S-SCREEN.json'));dest.write_text(json.dumps(report,indent=2)+'\n');print('S05_SCREEN_DONE',len(out),report['wall_seconds'],flush=True)
 require_complete_panel(report, nseeds)
if __name__=='__main__':main()
