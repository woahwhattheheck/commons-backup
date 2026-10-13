#!/usr/bin/env python3
"""Collect immutable original shards and explicitly tracked failed-cell replays."""
import argparse,copy,hashlib,json,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=True);changes=[];incidents=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for panel in ['panel','panel-next24']:
 source=a.runtime/panel;shutil.copytree(source,out/panel,dirs_exist_ok=True)
 for f in sorted((source/'raw').glob('*/*.json')):
  r=json.loads(f.read_text());rep=a.runtime/'replications'/f.parent.name/f.name;replica=json.loads(rep.read_text()) if rep.exists() else {'games':[]};resolved=copy.deepcopy(r)
  for i,g in enumerate(r['games']):
   if g['status']=='complete':continue
   incident={'seed':g['seed'],'opponent':g['opponent'],'candidate_seat':g['candidate_seat'],'failure':g['failure'],'actors':g['actors'],'original_report':str(f),'original_sha256':sha(f)};incidents.append(incident)
   matches=[x for x in replica['games'] if (x['seed'],x['opponent'],x['candidate_seat'])==(g['seed'],g['opponent'],g['candidate_seat'])]
   if len(matches)==1 and matches[0]['status']=='complete':resolved['games'][i]=matches[0];changes.append({**incident,'replication_report':str(rep),'replication_sha256':sha(rep),'resolution':'Only failed original cell replaced; successful original games unchanged'})
  resolved['original_summary']=resolved.pop('summary',None)
  resolved['resolution_note']='Original summary is retained separately; aggregate the explicit games list after isolated replacements.'
  dest=out/'resolved/raw'/f.parent.name/f.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(resolved,indent=2)+'\n')
if (a.runtime/'replications').exists():shutil.copytree(a.runtime/'replications',out/'replications',dirs_exist_ok=True)
(out/'runtime-resolution.json').write_text(json.dumps({'archive_sha256':'70554dc01f8e84336ede169cf109f3d61152e169dce8ad5265b9625216fe52cb','original_incidents':incidents,'replacements':changes,'note':'Successful isolation does not erase original operational failures or establish their cause.'},indent=2)+'\n')
print('original failures',len(incidents),'successful isolated replacements',len(changes))
