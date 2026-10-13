#!/usr/bin/env python3
"""Bounded checkpoint consumer using existing evaluator, with failed-request capture."""
import argparse,copy,gzip,hashlib,importlib.util,json,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();c=json.loads(a.config.read_text());a.output.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('checkpoint_evaluator',c['evaluator']);e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e);engine,hashes=e.get_engine(Path(c['engine']),e.LOADER)
original=e.Actor.act;calls=[];events=[]
original_close=e.Actor.close
def close(self):
 try:
  if c.get("spatial_telemetry"):
   event_path=Path(self.directory.name)/"spatial-events.json"
   if event_path.exists():events.append({"agent_spec":self.spec,"events":json.loads(event_path.read_text())})
 except (OSError,ValueError) as error:
  events.append({'agent_spec':self.spec,'telemetry_error':repr(error)})
 finally:
  original_close(self)
e.Actor.close=close
def capture(self,observation,configuration,timeout):
 started=time.perf_counter();response=original(self,observation,configuration,timeout)
 row={'step':observation['step'],'seat':observation['player'],'agent_spec':self.spec,'rpc_seconds':time.perf_counter()-started,'response':copy.deepcopy(response)}
 if c.get('capture_observations') or response.get('kind')!='action':row.update(observation=copy.deepcopy(observation),configuration=copy.deepcopy(configuration))
 calls.append(row);return response
e.Actor.act=capture
reports=[]
for opponent,definition in c['opponents'].items():
 for seed in definition['seeds']:
  for seat in (0,1):
   dest=a.output/f'{opponent}-{seed}-{seat}.json';trace=a.output/f'{opponent}-{seed}-{seat}.calls.json.gz'
   if dest.exists():raise RuntimeError(f'Preserve existing attempt: {dest}')
   calls.clear();events.clear();candidate=e.resolve_spec(c['candidate']);rival=e.resolve_spec(definition['path']);pair=[candidate,rival] if seat==0 else [rival,candidate]
   game=e.play(engine,pair,Path(c['engine']),e.LOADER,seed,seat);game['opponent']=opponent
   with gzip.open(trace,'wt') as f:json.dump(calls,f,separators=(',',':'))
   report={'archive_sha256':c['archive_sha256'],'features':c['features'],'engine_ref':e.ENGINE_REF,'engine_sha256':hashes,'evaluator_sha256':e.sha256(c['evaluator']),'loader_sha256':e.sha256(e.LOADER),'candidate':e.fingerprint(candidate),'opponent':e.fingerprint(rival),'agent_rng_seed':20260907,'limits':{'action_rpc_seconds':1,'startup_seconds':10,'game_seconds':120},'trace_file':trace.name,'trace_file_sha256':e.sha256(trace),'game':game,'spatial_events':list(events)}
   report['experiment']=c.get('experiment');report['source_files']={str(path):e.sha256(path) for path in c.get('source_files',[])}
   dest.write_text(json.dumps(report,indent=2)+'\n');reports.append({'path':dest.name,'sha256':e.sha256(dest),'seed':seed,'seat':seat,'opponent':opponent,'status':game['status']});(a.output/'checkpoint.json').write_text(json.dumps(reports,indent=2)+'\n')
   print(json.dumps({k:game[k] for k in ['seed','candidate_seat','opponent','status','scores','failure']}),flush=True)
