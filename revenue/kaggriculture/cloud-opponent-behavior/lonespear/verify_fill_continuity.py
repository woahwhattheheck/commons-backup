"""Compare public-fill outputs on retained development frames; never execute a policy.

Writes JSON to stdout only. The source modules and supplied gzip traces remain
unchanged. Source hashes and exact input hashes are part of the returned receipt.
"""
from __future__ import annotations
import argparse
import ast
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError('Source is not an importable Python file')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(before: Path, after: Path, development_dir: Path) -> dict:
    old, new = load(before, 'public_fill_before'), load(after, 'public_fill_after')
    old_nodes = {n.name:n for n in ast.parse(before.read_bytes()).body if isinstance(n,ast.FunctionDef)}
    new_nodes = {n.name:n for n in ast.parse(after.read_bytes()).body if isinstance(n,ast.FunctionDef)}
    unaffected=[]
    for name,node in old_nodes.items():
        if name == 'observed_fill':
            continue
        if name not in new_nodes or ast.dump(node)!=ast.dump(new_nodes[name]):
            raise ValueError('Unexpected change outside observed_fill: '+name)
        unaffected.append(name)
    traces = sorted(development_dir.glob('sell-lonespear-*.jsonl.gz'))
    if not traces:
        raise ValueError('No retained SELL/lonespear traces supplied')
    rows=[]
    for path in traces:
        counters={'trace':path.name,'sha256':sha256(path),'observations':0,
            'adjacent_pairs':0,'known_pairs':0,'unknown_pairs':0,'mismatches':0,'mutations':0}
        previous=None
        with gzip.open(path,'rt',encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line); obs=row['observation']; actor=1-obs['player']
                counters['observations']+=1
                if previous is not None:
                    pair=copy.deepcopy((previous,obs))
                    saved=json.dumps(pair,sort_keys=True,allow_nan=False)
                    prior=old.observed_fill(*pair,actor=actor)
                    current=new.observed_fill(*pair,actor=actor)
                    counters['adjacent_pairs']+=1
                    counters['known_pairs' if current['status']=='known' else 'unknown_pairs']+=1
                    counters['mismatches']+=prior!=current
                    counters['mutations']+=saved!=json.dumps(pair,sort_keys=True,allow_nan=False)
                previous=obs
        if sha256(path)!=counters['sha256']:
            raise ValueError('Input changed during verification: '+path.name)
        rows.append(counters)
    totals={k:sum(row[k] for row in rows) for k in
        ('observations','adjacent_pairs','known_pairs','unknown_pairs','mismatches','mutations')}
    return {'schema':'iris.public-fill-shape-continuity.v1',
        'before_sha256':sha256(before),'after_sha256':sha256(after),
        'unchanged_function_bodies':unaffected,'traces':rows,'totals':totals,
        'new_games':0,'policy_calls':0,'engine_calls':0,
        'interpretation':'Repeated retained observations; not independent trials or a game/strength result.'}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--development-dir',type=Path,required=True)
    args=parser.parse_args()
    report=verify(args.before,args.after,args.development_dir)
    print(json.dumps(report,indent=2,allow_nan=False))
    return int(bool(report['totals']['mismatches'] or report['totals']['mutations']))


if __name__=='__main__': raise SystemExit(main())
