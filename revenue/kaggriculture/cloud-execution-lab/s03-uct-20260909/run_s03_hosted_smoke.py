from pathlib import Path
import importlib.util,json,sys,time
ROOT=Path('/tmp/s03-runtime');EVAL=ROOT/'checks/reference/evaluator/evaluate.py';ENGINE=ROOT/'checks/reference/engine';LOADER=ROOT/'checks/reference/evaluator/loader.py';OPP=str(ROOT/'main.py')+'::agent'
variants={'control':OPP,'prior64':str(ROOT/'s03_prior_64.py')+'::agent','prior128':str(ROOT/'s03_prior_128.py')+'::agent','prior256':str(ROOT/'s03_prior_256.py')+'::agent','shadow64':str(ROOT/'s03_shadow_64.py')+'::agent'}
spec=importlib.util.spec_from_file_location('s03_host_eval',EVAL);ev=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ev;spec.loader.exec_module(ev);engine,_=ev.get_engine(ENGINE,LOADER)
seed=194505610;out=[];started=time.time()
for v,cand in variants.items():
 for seat in (0,1):
  pair=[cand,OPP] if seat==0 else [OPP,cand]
  g=ev.play(engine,pair,ENGINE,LOADER,seed,seat,20260909,1.0,10.0,120.0,None)
  out.append({'variant':v,'seed':seed,'candidate_seat':seat,**g});print(json.dumps({'variant':v,'seat':seat,'status':g.get('status'),'scores':g.get('scores')},sort_keys=True),flush=True)
Path('/tmp/S03-HOSTED-SMOKE.json').write_text(json.dumps({'schema':1,'dispatch':'ff5ff0197def292d0d86b22091ad67dc84ba5547','archive_sha256':'3b4b083ec2647bb0e715978c2565e916da0ee94c08b234902e3a7e4d3418c320','seed':seed,'games':out,'wall_seconds':time.time()-started},indent=2)+'\n')
