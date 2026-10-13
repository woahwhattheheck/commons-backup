import json, os, statistics, hashlib
from collections import Counter
from pathlib import Path
from s05_event_macros import build_library,library_sha256
from s05_completeness import completeness_errors, expected_per_variant, expected_total, nseeds_from
root=Path(os.environ['S05_RUNTIME_ROOT']);report=json.load(open(os.environ['S05_RESULT_PATH']));games=report['games'];lib=build_library(root/'reference/next-panel/vendor/arlene.py')
by={v:[g for g in games if g['variant']==v] for v in ('control','shadow','prior')}
def candidate_cash(g):return float(g['scores'][g['candidate_seat']])
def opp_cash(g):return float(g['scores'][1-g['candidate_seat']])
def summary(rows):
 complete=[g for g in rows if g.get('status')=='complete' and g.get('scores')];m=[candidate_cash(g)-opp_cash(g) for g in complete]
 return {'games':len(rows),'complete':len(complete),'failures':len(rows)-len(complete),'wtl':[sum(x>0 for x in m),sum(x==0 for x in m),sum(x<0 for x in m)],'mean_candidate_cash':statistics.mean(candidate_cash(g) for g in complete) if complete else None,'worst_margin':min(m) if m else None,'best_margin':max(m) if m else None,'max_candidate_call_seconds':max((g.get('actors') or [{},{}])[g['candidate_seat']].get('max_call_seconds',0) for g in complete) if complete else None,'max_peak_rss_kib':max((g.get('actors') or [{},{}])[g['candidate_seat']].get('peak_rss_kib',0) for g in complete) if complete else None}
def paired(v):
 c={(g['index'],g['candidate_seat']):g for g in by['control']};rows=[]
 for g in by[v]:
  b=c[(g['index'],g['candidate_seat'])];delta=candidate_cash(g)-candidate_cash(b) if g.get('scores') and b.get('scores') else None
  rows.append((g,b,delta))
 ds=[x[2] for x in rows if x[2] is not None]
 return {'cells':len(rows),'score_mismatches':sum(g.get('scores')!=b.get('scores') for g,b,_ in rows),'trace_mismatches':sum(g.get('trace_sha256')!=b.get('trace_sha256') for g,b,_ in rows),'cash_delta':{'min':min(ds) if ds else None,'mean':statistics.mean(ds) if ds else None,'max':max(ds) if ds else None,'nonzero':sum(d!=0 for d in ds)}}
shadow=[g.get('macro_trace') or {} for g in by['shadow']];prior=[g.get('macro_trace') or {} for g in by['prior']]
ptr=json.load(open(root/'SOURCE.json'));archive_sha=os.environ.get('S05_ARCHIVE_SHA')
out={'schema':1,'operation':report['operation'],'dispatch_main':report.get('dispatch_main'),'archive_sha256':archive_sha,'source_manifest_sha256':hashlib.sha256((root/'SOURCE.json').read_bytes()).hexdigest(),'runtime_files':len(ptr.get('runtime',{})),'library':{'macros':len(lib),'sha256':library_sha256(lib),'families':dict(sorted(Counter(m['family'] for m in lib).items())),'route_memberships':sum(len(m['routes']) for m in lib)},'variants':{v:summary(by[v]) for v in by},'paired_vs_control':{'shadow':paired('shadow'),'prior':paired('prior')},'shadow':{'candidates':sum(x.get('candidates',0) for x in shadow),'preserved_candidates':sum(x.get('preserved_candidates',0) for x in shadow),'fires':sum(x.get('fires',0) for x in shadow),'revalidations':sum(x.get('revalidations',0) for x in shadow),'revalidation_failures':sum(x.get('revalidation_failures',0) for x in shadow),'beam_checks':sum(x.get('beam_checks',0) for x in shadow),'changed_recommendations':sum(x.get('changed_recommendations',0) for x in shadow),'fire_families':{k:sum((x.get('fire_families') or {}).get(k,0) for x in shadow) for k in ('reset','unlock','hire','escape','maturity','pickup_drop','settlement')}},'prior':{'switches':sum(x.get('switches',0) for x in prior),'revalidations':sum(x.get('revalidations',0) for x in prior),'revalidation_failures':sum(x.get('revalidation_failures',0) for x in prior),'rollbacks':sum(x.get('rollbacks',0) for x in prior)},'wall_seconds':report.get('wall_seconds')}
nseeds=nseeds_from(report, os.environ);errors=completeness_errors(report, nseeds)
out['completeness']={'nseeds':nseeds,'expected_total':expected_total(nseeds) if nseeds>0 else 0,'expected_per_variant':expected_per_variant(nseeds) if nseeds>0 else 0,'ok':not errors,'errors':errors}
Path(os.environ['S05_SUMMARY_PATH']).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('S05_SUMMARY_JSON='+json.dumps(out,sort_keys=True,separators=(',',':')))
if errors: raise SystemExit('S05_INCOMPLETE '+';'.join(errors[:24]))
