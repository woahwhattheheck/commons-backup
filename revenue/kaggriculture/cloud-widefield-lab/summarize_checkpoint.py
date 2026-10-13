#!/usr/bin/env python3
"""Summarize exact checkpoint originals and their per-action timing records."""
import argparse,collections,gzip,hashlib,json,math,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();c=json.loads(a.config.read_text());rows=[];times=collections.defaultdict(list);cold=[];identities=[];failures=[]
for opponent,definition in c['opponents'].items():
 for seed in definition['seeds']:
  for seat in (0,1):
   path=a.input/f'{opponent}-{seed}-{seat}.json';r=json.loads(path.read_text());g=r['game'];row={'opponent':opponent,'seed':seed,'candidate_seat':seat,'status':g['status'],'failure':g['failure'],'trace_sha256':g['trace_sha256'],'actors':g['actors'],'steps':g['steps'],'wall_seconds':g['wall_seconds']}
   if g['status']=='complete':
    own,rival=g['scores'][seat],g['scores'][1-seat];row.update(own_cash=own,rival_cash=rival,margin=own-rival,verdict='W' if own>rival else 'L' if own<rival else 'T')
   else:failures.append(row)
   rows.append(row);identities.append({'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'trace_path':r['trace_file'],'trace_sha256':r['trace_file_sha256']})
   with gzip.open(a.input/r['trace_file'],'rt') as f:records=json.load(f)
   for x in records:
    if x['seat']!=seat:continue
    times['external_rpc_seconds'].append(x['rpc_seconds']);res=x['response']
    if res['kind']=='action':
     times['returned_child_wall_seconds'].append(res['call_seconds']);times['returned_child_cpu_seconds'].append(res['call_cpu_seconds'])
    if x['step']==0:cold.append({'opponent':opponent,'seed':seed,'seat':seat,'external_rpc_seconds':x['rpc_seconds'],'child_wall_seconds':res.get('call_seconds'),'child_cpu_seconds':res.get('call_cpu_seconds')})
def quantiles(v):
 v=sorted(v);return {'count':len(v),'mean':statistics.fmean(v),'p50':v[math.ceil(.5*len(v))-1],'p95':v[math.ceil(.95*len(v))-1],'p99':v[math.ceil(.99*len(v))-1],'max':max(v)}
by={}
for opp in c['opponents']:
 rr=[x for x in rows if x['opponent']==opp and x['status']=='complete'];by[opp]={v:sum(x['verdict']==v for x in rr) for v in ['W','T','L']};by[opp].update(mean_own=statistics.fmean(x['own_cash'] for x in rr) if rr else None,mean_rival=statistics.fmean(x['rival_cash'] for x in rr) if rr else None)
summary={'config':c,'original_attempts':len(rows),'completed':sum(x['status']=='complete' for x in rows),'errors':len(failures),'WTL':{v:sum(x.get('verdict')==v for x in rows) for v in ['W','T','L']},'by_opponent':by,'candidate_action_timing':{k:quantiles(v) for k,v in times.items()},'cold_start_calls':cold,'games':rows,'source_results':identities,'limitations':['Six development seeds, paired seats; no held or hosted-rank claim.','No ancestor panels rerun; frozen SELL is the opponent in four new games.','Timing wrapper surrounds existing Actor.act; evaluator RPC limits remain unchanged.','Full failed requests are captured if any; internal runtime stage/fallback telemetry is not exported by the existing worker.']};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:summary[k] for k in ['original_attempts','completed','errors','WTL','by_opponent','candidate_action_timing']},indent=2))
