#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run a bounded shard of recorded opponents through the existing Linux harness."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kg-root',type=Path,required=True)
    p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--index',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--candidate-sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--group',choices=['all','current_top30','previous_top30'],default='all')
    p.add_argument('--shard',type=int,default=0)
    p.add_argument('--shards',type=int,default=1)
    p.add_argument('--limit',type=int)
    p.add_argument('--both-seats',action='store_true',help='Add synthetic seat-swapped stress cases')
    args=p.parse_args()
    if sys.platform!='linux':p.error('Use the existing Linux process evaluator')
    if not 0 <= args.shard < args.shards or (args.limit is not None and args.limit<1):p.error('invalid shard or limit')
    root=args.kg_root.resolve(strict=True)
    h=load(root/'cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py','gauntlet_shared')
    if h.digest(args.candidate)!=args.candidate_sha256:raise ValueError('Candidate archive differs from declared version')
    members=h.archive_members(args.candidate)
    ev=load(root/h.EVALUATOR,'gauntlet_evaluator')
    pack=load(root/'cloud-pack/pack.py','gauntlet_pack')
    loader=root/'20260907-offline-agent/evaluate.py'
    engine_hashes=ev.verify_sources(args.engine_dir)
    index=json.loads(args.index.read_text(encoding='utf-8'))
    rows=[r for r in index['opponents'] if r['kind']=='recorded_trace'
          and (args.group=='all' or any(m['group']==args.group for m in r['memberships']))]
    rows=[r for i,r in enumerate(rows) if i%args.shards==args.shard]
    if args.limit:rows=rows[:args.limit]
    args.output.mkdir(parents=True,exist_ok=False)
    metadata={'candidate_sha256':args.candidate_sha256,'index_sha256':h.digest(args.index),
        'engine':engine_hashes,'evaluator_sha256':h.digest(root/h.EVALUATOR),
        'loader_sha256':h.digest(loader),'selected_fixtures':len(rows),
        'group':args.group,'shard':args.shard,'shards':args.shards,
        'submission_hold':True,'method':'Full official interpreter; persistent per-game processes; canonical internal deadline; 1.25s IPC limit. Recorded opponents do not adapt. These scores are diagnostic, not a leaderboard rating estimate.'}
    h.write_json(args.output/'run.json',metadata)
    for row in rows:
        entry=Path(row['entry'])
        if h.digest(entry)!=row['entry_sha256'] or h.digest(entry.parent/'actions.json')!=row['actions_sha256']:
            raise ValueError('Opponent bytes changed')
        seats=[row['candidate_seat_for_recorded_orientation']]
        if args.both_seats:seats.append(1-seats[0])
        for seat in seats:
            name=row['id']+f'-p{seat}'
            with tempfile.TemporaryDirectory(prefix=name+'-',dir=args.output) as temp:
                directory=Path(temp);payload=directory/'payload';h.extract_members(members,payload)
                adapter=directory/'adapter.py';pack.write_adapter(adapter,payload/'main.py')
                specs=[str(adapter),str(entry)] if seat==0 else [str(entry),str(adapter)]
                engine,_=ev.get_engine(args.engine_dir,loader)
                game=ev.play(engine,specs,args.engine_dir,loader,row['seed'],seat,20260912,1.25,10.0,900.0)
            game.update(opponent=row['id'],submission_id=row['submission_id'],
                family=row['family'],kind='recorded_trace',adaptive=False,
                recorded_orientation=seat==row['candidate_seat_for_recorded_orientation'],
                memberships=row['memberships'],candidate_sha256=args.candidate_sha256)
            h.write_json(args.output/(name+'.json'),game)
            print(json.dumps({k:game[k] for k in ['opponent','submission_id','status','scores','steps','recorded_orientation']}),flush=True)


if __name__=='__main__':main()
