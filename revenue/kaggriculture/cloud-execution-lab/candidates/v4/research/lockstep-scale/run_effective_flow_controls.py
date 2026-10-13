"""Run exact normal/-O suites, semantic mutants, and reference-integrity controls.

Every subprocess is foreground, offline, process-isolated, and time-bounded.
No Actions dispatch, source rewrite, runtime wiring, or configuration changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MUTATIONS = {
    'requested_point_estimator':
        ('(residual - sell[product], residual + buy[product])',
         '(residual - sell[product] + buy[product], residual - sell[product] + buy[product])'),
    'flow_sign_reversal':
        ('(residual - sell[product], residual + buy[product])',
         '(residual + sell[product], residual - buy[product])'),
    'upper_bound_positive_signal':
        ('if interval[0] >= threshold:', 'if interval[1] >= threshold:'),
    'ignore_raw_market_cap':
        ('for row in market[:cap]:', 'for row in market:'),
    'compact_empty_rows_before_cap':
        ('for row in market[:cap]:', 'for row in [x for x in market if x][:cap]:'),
    'unsupported_product_buys':
        ('product in ("WHEAT", "FERTILIZER"):', 'product in PRODUCTS:'),
    'use_next_shops':
        ('_town_demand(step, previous_obs["town"]["unlocked_shops"], cfg)',
         '_town_demand(step, next_obs["town"]["unlocked_shops"], cfg)'),
    'town_tick_off_by_one':
        ('_town_demand(step, previous_obs["town"]["unlocked_shops"], cfg)',
         '_town_demand(step + 1, previous_obs["town"]["unlocked_shops"], cfg)'),
    'clip_town_inventory':
        ('+ demand[product])',
         '+ min(demand[product], max(0, _observed_int(previous[product]))))'),
    'accept_tuple_market_rows':
        ('not isinstance(row, list)', 'not isinstance(row, (list, tuple))'),
    'wrong_unit_loop_limit': ('PER_ROW_UNIT_LIMIT = 99_999', 'PER_ROW_UNIT_LIMIT = 100_000'),
    'accept_nonadjacent_snapshots': ('next_step != step + 1', 'next_step < step + 1'),
}
REFERENCE_FILES = ('evaluator/loader.py','engine/kaggriculture.py',
                   'engine/kaggriculture.json','engine/utils.py')


def digest(path: Path) -> dict:
    data = path.read_bytes()
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
            'git_blob':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}


def invoke(home: Path, reference: Path, optimized: bool) -> dict:
    command = [sys.executable,*(['-O'] if optimized else []),
               str(home/'test_effective_flow_bounds.py'),'--reference-root',str(reference),'-v']
    cp = subprocess.run(command,capture_output=True,text=True,timeout=30)
    output = cp.stdout+cp.stderr
    rows = [line[len('ESTUARY_COUNTERS '):] for line in cp.stdout.splitlines()
            if line.startswith('ESTUARY_COUNTERS ')]
    if len(rows)!=1:
        raise RuntimeError('missing/duplicate counter receipt: '+output[-2000:])
    return {'returncode':cp.returncode,'counters':json.loads(rows[0]),
            'output_sha256':hashlib.sha256(output.encode()).hexdigest(),'output':output}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-root',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    opts=parser.parse_args()
    home=Path(__file__).resolve().parent
    reference=opts.reference_root.resolve()
    opts.out.mkdir(parents=True,exist_ok=True)
    report={'format':'estuary-effective-flow-controls-v1',
            'source':digest(home/'effective_flow_bounds.py'),
            'test_source':digest(home/'test_effective_flow_bounds.py'),
            'runner_source':digest(Path(__file__)),
            'reference':{name:digest(reference/name) for name in REFERENCE_FILES},
            'normal_and_optimized':[],'semantic_mutants':[],'reference_controls':[]}
    for optimized in (False,True):
        name='optimized' if optimized else 'normal'
        run=invoke(home,reference,optimized)
        c=run['counters']
        if run['returncode']!=0 or c['tests']!=17 or c['errors'] or c['failures'] or c['skipped']:
            raise RuntimeError('original suite failed: '+run['output'])
        (opts.out/(name+'.log')).write_text(run.pop('output'))
        report['normal_and_optimized'].append(run)
    original=(home/'effective_flow_bounds.py').read_text()
    with tempfile.TemporaryDirectory(prefix='estuary-controls-') as td:
        root=Path(td)
        for name,(old,new) in MUTATIONS.items():
            if original.count(old)!=1:
                raise RuntimeError('mutation anchor not unique: '+name)
            mutated=original.replace(old,new)
            compile(mutated,name,'exec')
            trial=root/name;trial.mkdir()
            (trial/'effective_flow_bounds.py').write_text(mutated)
            shutil.copyfile(home/'test_effective_flow_bounds.py',trial/'test_effective_flow_bounds.py')
            for optimized in (False,True):
                run=invoke(trial,reference,optimized)
                c=run['counters']
                # A semantic mutant must reach real tests and fail assertions;
                # syntax/import/pin failures alone do not count as a killed mutant.
                if run['returncode']==0 or c['tests']!=17 or c['failures']<1 or c['skipped']:
                    raise RuntimeError('mutant survived or failed wrong gate: '+name+' '+run['output'])
                run.pop('output')
                report['semantic_mutants'].append({'name':name,'optimized':optimized,**run})
        for filename in REFERENCE_FILES:
            for broken in ('missing','modified'):
                trial=root/(filename.replace('/','_')+'_'+broken);trial.mkdir()
                for rel in REFERENCE_FILES:
                    path=trial/rel;path.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(reference/rel,path)
                victim=trial/filename
                if broken=='missing':victim.unlink()
                else:victim.write_bytes(victim.read_bytes()+b'\n')
                for optimized in (False,True):
                    run=invoke(home,trial,optimized)
                    c=run['counters']
                    if (run['returncode']==0 or c['tests']!=0 or c['errors']!=1
                            or 'reference pin mismatch or missing file' not in run['output']):
                        raise RuntimeError('reference gate failed: '+filename+' '+run['output'])
                    run.pop('output')
                    report['reference_controls'].append({'file':filename,'case':broken,
                                                         'optimized':optimized,**run})
    report['status']='PASS'
    report['scope']={'full_transitions_per_mode':463,'random_worlds_per_mode':400,
                    'product_containment_checks_per_mode':4167,
                    'mutants_rejected_per_mode':len(MUTATIONS),
                    'reference_faults_rejected_per_mode':len(REFERENCE_FILES)*2,
                    'native_runtime_wired':False,'full_games':0,'economic_promotion':False}
    output=opts.out/'EFFECTIVE-FLOW-VALIDATION.json'
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':report['status'],'scope':report['scope'],
                      'receipt':str(output),'source':report['source']},sort_keys=True))


if __name__=='__main__':
    main()
