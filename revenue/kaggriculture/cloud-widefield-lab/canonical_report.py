#!/usr/bin/env python3
"""Compact canonical archive comparison; raw evaluator results stay authoritative."""
import argparse, json, statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--summary',type=Path,required=True);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
s=json.loads(a.summary.read_text());f=json.loads(a.freeze.read_text());out={'source':f,'complete':s['complete'],'expected_games_including_reused_controls':s['expected_games'],'errors':s['errors'],'arms':{}}
for arm,rec in s['summary'].items():
 r={k:rec[k] for k in ('W','T','L','completed','failed','mean_own_cash','mean_rival_cash','max_candidate_call_seconds','by_opponent','mirror_dependence')}
 if 'paired' in rec:r['paired_vs_frozen_sell']={k:v for k,v in rec['paired'].items() if k!='rows'}
 games=[]
 for x in s['reports']:
  if x['arm']==arm:games.extend(json.loads(Path(x['path']).read_text())['games'])
 tails=sorted(g['actors'][g['candidate_seat']]['max_rpc_seconds'] for g in games if g['status']=='complete')
 r['per_game_max_rpc_seconds']={'p50':statistics.median(tails),'p95':tails[min(len(tails)-1,int(.95*len(tails)))],'max':max(tails)} if tails else {}
 r['losses']=[{'seed':g['seed'],'opponent':g['opponent'],'seat':g['candidate_seat'],'own':g['scores'][g['candidate_seat']],'rival':g['scores'][1-g['candidate_seat']],'trace_sha256':g['trace_sha256']} for g in games if g['status']=='complete' and g['scores'][g['candidate_seat']]<g['scores'][1-g['candidate_seat']]]
 out['arms'][arm]=r
canonical=s['summary'].get('canonical-default-70554dc0',{}).get('paired',{}).get('rows',[])
committed=s['summary'].get('committed-envelope',{}).get('paired',{}).get('rows',[])
idx={(r['seed'],r['seat'],r['opponent']):r for r in committed};deltas=[];flips={}
for r in canonical:
 b=idx.get((r['seed'],r['seat'],r['opponent']))
 if b:
  deltas.append((r['d_own']-b['d_own'],r['d_rival']-b['d_rival']))
  if r['arm_verdict']!=b['arm_verdict']:
   key=b['arm_verdict']+'->'+r['arm_verdict'];flips[key]=flips.get(key,0)+1
if deltas:out['canonical_vs_retained_committed']={'paired_count':len(deltas),'mean_d_own':statistics.fmean(x[0] for x in deltas),'mean_d_rival':statistics.fmean(x[1] for x in deltas),'flips':flips}
out['limitations']=['Development evidence; no leaderboard or held claim.','Two lonespear modes share one lineage; mirror seats are dependent.','Timing percentiles are across per-game maxima, not individual actions.','External RPC errors are retained; internal deadline fallback counts are not exposed by this evaluator.','Prior controls reused without executing them again.']
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
