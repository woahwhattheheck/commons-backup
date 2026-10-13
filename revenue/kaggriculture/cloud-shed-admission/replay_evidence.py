"""Re-evaluate retained final states without replaying their full-game prefixes."""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import statistics
import sys
import time
import zipfile
from evaluate_terminal import sale_stress
from market_primitives import make_primitives
from terminal_admission import optimize_terminal_admission


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,required=True)
    parser.add_argument('--engine-dir',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if zipfile.is_zipfile(args.archive):
        with zipfile.ZipFile(args.archive) as archive:
            raw=archive.read('complete-evidence.json.xz')
    else:
        raw=args.archive.read_bytes()
        if args.archive.name.endswith('.b64'): raw=base64.b64decode(raw,validate=False)
    documents=json.loads(lzma.decompress(raw))
    root=args.repo_root/'revenue/kaggriculture'
    spec=importlib.util.spec_from_file_location('admission_replay_existing_eval',root/'cloud-eval/evaluate.py')
    ev=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ev;spec.loader.exec_module(ev)
    engine,hashes=ev.get_engine(args.engine_dir)
    mechanics=ev.import_file(root/'cloud-titan-composition/vendor/sell/mechanics.py','admission_replay_mechanics')
    runtime=make_primitives(mechanics)
    records=documents.get('terminal_records',[])
    if not records:
        for name in ('games/traces.json','games-retry/traces.json'):
            records.extend(r for r in json.loads(documents[name]) if 'final_states' in r)
    rows=[]
    for record in records:
        states,env=ev.structify(record['final_states']),ev.structify(record['final_env'])
        player=record['player']
        obs=copy.deepcopy(states[player].observation)
        original=copy.deepcopy(states[player].action)
        hypotheses=sale_stress(obs,env.configuration,runtime.PRODUCTS)
        started=time.perf_counter()
        action,report=optimize_terminal_admission(runtime,obs,env.configuration,original,hypotheses)
        wall_s=time.perf_counter()-started
        # Evaluator alone consumes the real rival action and private state.
        outcomes={}
        for label,choice in [('original',original),('admission',action)]:
            trial,e=copy.deepcopy((states,env));trial[player].action=choice
            engine.interpreter(trial,e)
            if not all(s.status=='DONE' for s in trial):
                raise AssertionError('reached terminal continuation did not finish')
            outcomes[label]=[trial[player].reward,trial[1-player].reward]
        bank=record['last_original_bank'] if 'last_original_bank' in record else record['trace'][-1]['bank']
        if outcomes['original'] != [bank[player],bank[1-player]]:
            raise AssertionError('unchanged terminal continuation differs from retained trace')
        rows.append({k:record[k] for k in ('seed','player','opponent')} | {
            'changed':action!=original,'reason':report['reason'],'outcomes':outcomes,
            'whole_call_s':wall_s,'reported_elapsed_s':report.get('elapsed_s'),
            'v1_reported_elapsed_s':record['v1_elapsed_s'] if 'v1_elapsed_s' in record else record['report'].get('elapsed_s')})
    result={'kind':'saved development terminal states; zero new full games',
            'engine_hashes':hashes,'archive_sha256':hashlib.sha256(raw).hexdigest(),
            'runtime_sha256':hashlib.sha256(Path(__file__).with_name('terminal_admission.py').read_bytes()).hexdigest(),
            'rows':rows,'changed':sum(r['changed'] for r in rows),
            'max_whole_call_s':max(r['whole_call_s'] for r in rows),
            'median_whole_call_s':statistics.median(r['whole_call_s'] for r in rows),
            'timing_scope':'whole optimizer call only; excludes producer, scenario construction and cold import'}
    text=json.dumps(result,indent=2)+'\n'
    if args.out:args.out.write_text(text)
    print(text,end='')


if __name__=='__main__':main()
