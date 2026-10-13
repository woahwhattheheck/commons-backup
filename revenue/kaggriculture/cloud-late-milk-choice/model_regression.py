# SPDX-License-Identifier: Apache-2.0
"""Run only two model candidates on the retained original development regime.

Original frozen-SELL controls are read, never re-executed. This is regression
coverage on an already-observed loss, not new independent evaluation.
"""
from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
import panel
from model_panel import entry_factory, load, source


def run(args):
    root=args.source_root.resolve()
    out=args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh result directory')
    out.mkdir(parents=True,exist_ok=True)
    original=json.loads(args.original_results.read_text())
    evaluator=load(root/'cloud-eval/evaluate.py','prism_regression_evaluator')
    loader=root/'20260907-offline-agent/evaluate.py'
    engine,hashes=evaluator.get_engine(args.engine_dir,loader=loader,prepare=False)
    writer=entry_factory(source_root=root,engine_dir=args.engine_dir.resolve(),
        oracle_path=args.oracle.resolve(),replay_path=args.physical_replay.resolve(),seconds=0.6)
    implementation=Path(__file__).resolve().parent
    arlene=root/'cloud-frontier-policy/next-panel/vendor/arlene.py'
    sell=root/'cloud-titan-composition/vendor/sell'
    document={'classification':'already-used development consumer regression',
        'seed':9982019,'opponent':'arlene','new_candidate_games':2,
        'reexecuted_control_games':0,'independent_validation':False,
        'original_results_source':source(args.original_results),
        'dependencies':{'model':source(implementation/'model_choice.py'),
            'replay':source(args.physical_replay),'oracle':source(args.oracle),
            'scheduler':source(sell/'scheduler.py'),'arlene':source(arlene),
            'entry_factory':source(implementation/'model_panel.py'),'recorder':source(implementation/'panel.py')},
        'engine_hashes':hashes,'games':[],'complete':False}
    panel.atomic_json(out/'results.json',document)
    for position in (0,1):
        control=next(g for g in original['games'] if g['seed']==9982019
            and g['opponent']=='arlene' and g['candidate_seat']==position and g['arm']=='frozen_sell_control')
        identity=f'9982019-arlene-p{position}-modeled_regression'
        entry=out/(identity+'.py'); telemetry=out/(identity+'.choices.jsonl')
        writer(entry,sell_dir=sell,implementation=implementation,enabled=True,telemetry=telemetry)
        trace=out/(identity+'.trace.jsonl.gz')
        with gzip.open(trace,'wb',compresslevel=6) as stream:
            recorded=panel.RecordedEngine(engine,stream)
            specs=[str(arlene)]*2;specs[position]=str(entry)
            result=evaluator.play(recorded,specs,args.engine_dir.resolve(),loader,9982019,position)
        result.update(identity=identity,trace_file=trace.name,trace_sha256=panel.sha(trace),
            full_transition_sha256=recorded.all.hexdigest(),
            prefix_through_576_sha256=recorded.prefix.hexdigest(),interpreter_calls=recorded.calls,
            choices=[json.loads(x) for x in telemetry.read_text().splitlines()] if telemetry.exists() else [],
            original_control={'identity':control['identity'],'scores':control['scores'],
                'full_transition_sha256':control['full_transition_sha256'],
                'prefix_through_576_sha256':control['prefix_through_576_sha256']},
            same_prefix=recorded.prefix.hexdigest()==control['prefix_through_576_sha256'],
            same_full_transition=recorded.all.hexdigest()==control['full_transition_sha256'],
            same_terminal_cash=result.get('scores')==control['scores'])
        document['games'].append(result)
        panel.atomic_json(out/'results.json',document)
        print(json.dumps({k:result.get(k) for k in ['identity','status','scores','failure','same_prefix','same_full_transition','same_terminal_cash']},sort_keys=True),flush=True)
    document['complete']=all(g['status']=='complete' for g in document['games'])
    panel.atomic_json(out/'results.json',document)
    return 0 if document['complete'] else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--engine-dir',type=Path,required=True)
    p.add_argument('--oracle',type=Path,required=True)
    p.add_argument('--physical-replay',type=Path,required=True)
    p.add_argument('--original-results',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    return run(p.parse_args())

if __name__=='__main__':raise SystemExit(main())
