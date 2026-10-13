#!/usr/bin/env python3
"""Replay only incomplete cells once, using the unchanged official evaluator."""
import argparse, importlib.util, json, sys, hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--panel',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
c=json.loads(a.config.read_text());spec=importlib.util.spec_from_file_location('widefield_replica_evaluator',c['evaluator']);e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)
engine,hashes=e.get_engine(Path(c['engine']),e.LOADER);opponents=dict(x.split('=',1) for x in c['opponents']);manifest=[]
for path in sorted((a.panel/'raw').glob('*/*.json')):
 r=json.loads(path.read_text());failed=[g for g in r['games'] if g['status']!='complete']
 if not failed:continue
 target=a.output/path.parent.name/path.name;target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():raise RuntimeError(f'Preserve prior attempt: {target}')
 games=[]
 for g in failed:
  seat=g['candidate_seat'];candidate=e.resolve_spec(c['arms'][path.parent.name]);rival=e.resolve_spec(opponents[g['opponent']]);pair=[candidate,rival] if seat==0 else [rival,candidate]
  q=e.play(engine,pair,Path(c['engine']),e.LOADER,g['seed'],seat);q['opponent']=g['opponent'];games.append(q)
  report={'archive_sha256':c['archive_sha256'],'features':c['features'],'original_report':str(path),'original_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'engine_sha256':hashes,'method':'single-worker replay of original failed cells only; no source or timeout changes','games':games}
  target.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:q[k] for k in ('seed','candidate_seat','opponent','status','failure','scores')}),flush=True)
 manifest.append({'report':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
