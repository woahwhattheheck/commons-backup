"""Development-only behavioral mutation controls; not a runtime module."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--engine', type=Path, required=True)
parser.add_argument('--predecessor', type=Path, required=True)
parser.add_argument('--mode', choices=('normal', 'optimized'), required=True)
parser.add_argument('--output-directory', type=Path, required=True)
args=parser.parse_args()
ROOT=Path(__file__).resolve().parent
args.engine=args.engine.resolve()
args.predecessor=args.predecessor.resolve()
args.output_directory.mkdir(parents=True, exist_ok=False)
SOURCE=(ROOT/'r04_cow_fert_salvage.py').read_text()
CHECK=(ROOT/'check_completed_cow_service.py').read_text()
ENGINE=str(args.engine)
MUTANTS={
 'nonliteral_opt_in':('completed_service is True','completed_service'),
 'enabled_by_default':('completed_service=False','completed_service=True'),
 'productive_care_removed':("('fed_today', 'cared_today', 'fertilizer_available')", "('fed_today', 'fertilizer_available')"),
 'productive_feed_removed':("('fed_today', 'cared_today', 'fertilizer_available')", "('cared_today', 'fertilizer_available')"),
 'no_capacity_reserve':('if total + 1 > 100:', 'if total > 100:'),
 'stacked_actor_admitted':('sites.count(sites[i]) == 1','True'),
 'steals_incumbent_harvest':('if selected is None and completed:', 'if completed:'),
 'dead_market_suffix_observed':('for row in market[:10]:','for row in market:'),
 'sheep_takeover':("tile.get('animal') != 'COW'", "tile.get('animal') not in ('COW', 'SHEEP')"),
 'empty_collection':("result['farmer'] = ['COLLECT_FERTILIZER']", "result['farmer'] = ['PASS']"),
}
def h(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
rows=[]
with tempfile.TemporaryDirectory(prefix='cf1-mutants-') as td:
 p=Path(td)
 for mode in (args.mode,):
  for name,(old,new) in MUTANTS.items():
   if old not in SOURCE:raise RuntimeError('missing anchor '+name)
   mutant=SOURCE.replace(old,new)
   mh=h(mutant.encode())
   (p/'r04_cow_fert_salvage.py').write_text(mutant)
   # Rebind ONLY the deliberately changed candidate identity. The unchanged
   # behavioral assertions, predecessor, engine and base-suite pins still run.
   (p/'check_completed_cow_service.py').write_text(CHECK.replace('ef6ab6e795375cf84c5dc7d0bcd43f979bbd0af8',mh))
   (p/'check_cow_fert_salvage.py').write_bytes((ROOT/'check_cow_fert_salvage.py').read_bytes())
   (p/'predecessor.py').write_bytes(args.predecessor.read_bytes())
   # Different mutants can have equal file sizes/mtime: never permit pycache reuse.
   import shutil
   shutil.rmtree(p/'__pycache__',ignore_errors=True)
   cmd=[sys.executable]+(['-O'] if mode=='optimized' else [])+['check_completed_cow_service.py','--engine',ENGINE,'--predecessor','predecessor.py']
   run=subprocess.run(cmd,cwd=p,text=True,capture_output=True,timeout=15)
   output=run.stdout+run.stderr
   (args.output_directory/f'{name}-{mode}.log').write_text(output)
   behavioral=run.returncode!=0 and ('FAIL:' in output or 'ERROR:' in output) and 'identity mismatch' not in output
   rows.append({'name':name,'mode':mode,'candidate_blob':mh,'exit_code':run.returncode,'behaviorally_rejected':behavioral})
   print(mode,name,behavioral,flush=True)
   if not behavioral:raise RuntimeError('mutation not behaviorally rejected '+name+'\n'+output)
(args.output_directory/'mutation-results.json').write_text(json.dumps({'mutants':rows,'count':len(rows),'all_behaviorally_rejected':all(x['behaviorally_rejected'] for x in rows)},indent=2)+'\n')
