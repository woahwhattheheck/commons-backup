"""One fixed experiment consumer of the existing cloud-eval.play; no engine fork."""
from __future__ import annotations
import argparse
import copy
import datetime
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent

def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

class RecordedEngine:
    """Passive before/after copies outside actor RPC; forwards to exact interpreter."""
    def __init__(self, engine, stream):
        self.engine, self.stream, self.count = engine, stream, 0
    def __getattr__(self, key):
        return getattr(self.engine, key)
    def interpreter(self, state, env):
        before = copy.deepcopy([s.observation for s in state])
        actions = copy.deepcopy([s.action for s in state])
        returned = self.engine.interpreter(state, env)
        row = {'kind': 'initial' if not before[0] else 'transition',
               'index': self.count, 'before': before, 'actions': actions,
               'after': [s.observation for s in state],
               'status': [s.status for s in state], 'rewards': [s.reward for s in state]}
        self.stream.write(json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n')
        self.count += 1
        return returned

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--label', default='current-a8af2b83')
    parser.add_argument('--bank', type=Path)
    parser.add_argument('--engine-dir', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seeds', default='9926001,9926002')
    args = parser.parse_args()
    for key in ('candidate','bank','engine_dir','output'):
        if getattr(args,key) is None:
            parser.error('--'+key.replace('_','-')+' must be supplied')
    seeds = [int(s) for s in args.seeds.split(',')]
    if len(seeds)!=len(set(seeds)):
        parser.error('Duplicate development seeds')
    args.output.mkdir(parents=True, exist_ok=False)
    evaluation = load(HERE/'evaluate.py', 'orbit_existing_evaluation')
    loader = HERE/'engine_loader.py'
    engine, hashes = evaluation.get_engine(args.engine_dir, loader)
    report = {'schema':'orbit.current-lonespear-slice.v1', 'candidate_label':args.label,
              'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'candidate_entry_sha256':digest(args.candidate),
              'evaluator_sha256':digest(HERE/'evaluate.py'),
              'loader_sha256':digest(loader), 'engine_sha256':hashes,
              'bank_sha256':digest(args.bank/'BANK.json'),
              'limits':{'rpc_seconds':1.0,'startup_seconds':10.0,'game_seconds':180.0,
                        'remaining_overage':0,'concurrent_games':1},
              'seed_role':'development','seeds':seeds,'games':[],
              'method':'Unmodified official interpreter via existing process-isolated cloud-eval.play. Passive complete transition capture is outside agent RPC. Not hosted Kaggle scoring; no retries.'}
    evaluation.write_report(args.output/'report.json',report)
    for mode in ('greedy','scipy'):
        opponent = args.bank/('lonespear-v18-'+mode+'.py')
        for seed in seeds:
            for seat in (0,1):
                name = f'{mode}-{seed}-p{seat}'
                trace = args.output/(name+'.jsonl.gz')
                pair = [str(args.candidate.resolve()),str(opponent.resolve())]
                if seat: pair.reverse()
                with gzip.open(trace,'xt',encoding='utf-8',compresslevel=3) as output:
                    recorded = RecordedEngine(engine, output)
                    result = evaluation.play(recorded,pair,args.engine_dir,loader,seed,seat,
                                             rng_seed=20260907,action_timeout=1.0,
                                             startup_timeout=10.0,game_timeout=180.0)
                result.update(opponent='lonespear-v18-'+mode, candidate_label=args.label,
                              retained_trace=trace.name,retained_trace_sha256=digest(trace),
                              retained_rows=recorded.count)
                evaluation.write_report(args.output/(name+'.json'),result)
                report['games'].append(result)
                report['summary']=evaluation.summarize(report['games'])
                evaluation.write_report(args.output/'report.json',report)
                print(json.dumps({k:result.get(k) for k in ('candidate_label','opponent','seed','candidate_seat','status','scores','failure','steps','wall_seconds')}),flush=True)
    report['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['complete_grid']=len(report['games'])==2*len(seeds)*2
    evaluation.write_report(args.output/'report.json',report)
    return int(any(g['status']!='complete' for g in report['games']))

if __name__=='__main__':
    raise SystemExit(main())
