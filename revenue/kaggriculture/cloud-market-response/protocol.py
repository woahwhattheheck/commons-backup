# SPDX-License-Identifier: MIT
"""Full-game replication through pinned file loading and isolated JSON actors."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
HERE=Path(__file__).resolve().parent

def imported(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def run(engine_dir,output,expected_dir):
    ev=imported(HERE.parent/'cloud-eval/evaluate.py','t12_protocol_eval')
    pack=imported(HERE.parent/'cloud-pack/pack.py','t12_protocol_pack')
    result=[]
    with tempfile.TemporaryDirectory(prefix='t12-protocol-') as td:
        td=Path(td);candidate=td/'response.py';pack.write_adapter(candidate,HERE/'main.py')
        for rival in ('arlene','apex'):
            target=(HERE.parent/'cloud-titan-composition/vendor/sell/reference/next-panel/vendor/arlene.py'
                    if rival=='arlene' else HERE.parent/'cloud-frontier-policy/next-panel/vendor/apex/main.py')
            opponent=td/(rival+'.py');pack.write_adapter(opponent,target)
            for seat in (0,1):
                engine,hashes=ev.get_engine(engine_dir)
                specs=[str(opponent),str(opponent)];specs[seat]=str(candidate)
                row=ev.play(engine,specs,engine_dir,ev.LOADER,9840001,seat,
                            action_timeout=1.0,startup_timeout=10.0,game_timeout=180.0)
                row['opponent']=rival
                assert row['status']=='complete' and row['steps']==719, row.get('failure')
                expected=json.loads((expected_dir/f'response-{rival}-9840001-{seat}.json').read_text())
                assert row['scores']==expected['scores'], 'Instrumented/in-process versus isolated score mismatch'
                row['matches_inprocess_scores']=True
                result.append(row)
                print(rival,seat,row['scores'],row['actors'][seat]['max_call_seconds'],flush=True)
    output.write_text(json.dumps({'complete':True,'games':result,
        'kind':'development-seed replication, not fresh held results',
        'engine_sha256':hashes,'contract':'pinned official local-file loader; fresh JSON actor subprocesses; 1s call deadline including first-call setup'},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-dir',type=Path,required=True)
    a=p.parse_args();run(a.engine_dir,a.output,a.expected_dir)
