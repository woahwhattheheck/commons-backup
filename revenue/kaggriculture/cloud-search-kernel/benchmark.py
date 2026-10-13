# SPDX-License-Identifier: Apache-2.0
"""Paired complete games; requires the existing offline engine/source pack."""
import argparse, importlib.util, json, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--engine-dir',type=Path,required=True);p.add_argument('--seeds',required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--arms',default='control,candidate')
 p.add_argument('--opponents',default='arlene,apex');p.add_argument('--seats',default='0,1')
 args=p.parse_args();root=HERE.parent
 spec=importlib.util.spec_from_file_location('t06_evaluator',root/'cloud-eval/evaluate.py')
 ev=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ev;spec.loader.exec_module(ev)
 engine,hashes=ev.get_engine(args.engine_dir)
 arms={'control':root/'cloud-titan-composition/vendor/sell/scheduler.py','candidate':HERE/'entrypoint.py'}
 parents={'arlene':root/'cloud-frontier-policy/next-panel/vendor/arlene.py','apex':root/'cloud-frontier-policy/next-panel/vendor/apex/main.py'}
 seeds=list(map(int,args.seeds.split(',')))
 if len(set(seeds))!=len(seeds):raise ValueError('duplicate seeds')
 report={'schema':'t06.paired-games.v1','engine_ref':ev.ENGINE_REF,'engine_hashes':hashes,
  'evaluator_sha256':ev.sha256(ev.__file__),'loader_sha256':ev.sha256(ev.LOADER),
  'source_hashes':{x.name:ev.sha256(x) for x in HERE.glob('*.py')},
  'arms':{n:ev.fingerprint(str(f)) for n,f in arms.items()},
  'opponents':{n:ev.fingerprint(str(f)) for n,f in parents.items()},
  'method':'719-round pinned official interpreter; process-isolated actors; no environment seed exposed; local benchmark, not hosted rating',
  'kernel_limits':{'seconds':0.03,'transitions':3500,'scope':'per optimizer kernel call; baseline scoring and explicit legacy feasibility recovery are outside kernel cap'},'games':[]}
 for seed in seeds:
  for opponent in args.opponents.split(','):
   for seat in map(int,args.seats.split(',')):
    for arm in args.arms.split(','):
     pair=[str(arms[arm]),str(parents[opponent])]
     if seat==1:pair.reverse()
     game=ev.play(engine,pair,args.engine_dir,ev.LOADER,seed,seat,game_timeout=180)
     game.update(opponent=opponent,arm=arm);report['games'].append(game)
     args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
     print(json.dumps({k:game.get(k) for k in ('seed','opponent','candidate_seat','arm','status','scores','steps','failure','wall_seconds')}),flush=True)
if __name__=='__main__':main()
