# SPDX-License-Identifier: MIT
"""Compare two frozen prior-backoff event models on retained development data."""
from __future__ import annotations
import argparse
import base64
from copy import deepcopy
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import sys
import tempfile

from backoff import predict_event


def augment(records, calibration, family, split):
    """Score immutable pre-outcome forecast snapshots; preserve ambiguous labels."""
    output=[]; seen=set()
    for original in records:
        r=deepcopy(original); f=r['forecast']
        if f['ticket'] in seen:
            raise ValueError('duplicate forecast outcome')
        seen.add(f['ticket'])
        r['opponent_family'],r['split']=family,split
        r['backoff']={name:predict_event(f,expert=name) for name in ('model','same_phase')}
        if r['label'] is not None:
            if type(r['label']) is not int or r['label'] not in (0,1):
                raise ValueError('invalid identifiable event label')
            for name,result in r['backoff'].items():
                p=result['probability']
                r['scores']['backoff_'+name]={'prediction':p,**calibration._loss(p,r['label'])}
        output.append(r)
    return output


def decode(portfolio, names, assess):
    """Use the existing T14 codec on only the explicitly frozen member names."""
    directory=portfolio/'revision2/artifacts'
    manifest=json.loads((directory/'MANIFEST.json').read_text())
    item=next(a for a in manifest['archives'] if a['name']=='full-traces.xz')
    parts=[]
    for part in item['parts']:
        path=directory/part['name']
        if path.parent.resolve()!=directory.resolve() or assess.sha(path)!=part['sha256']:
            raise ValueError('retained part mismatch')
        parts.append(path.read_bytes())
    raw=base64.b64decode(b''.join(parts),validate=True)
    if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
        raise ValueError('retained compressed archive mismatch')
    payload=json.loads(lzma.decompress(raw))
    codec=assess.load(portfolio/'evidence.py','quill_backoff_codec')
    for name in names:
        member=payload['members'][name]; rows=[]; current=None; h=hashlib.sha256()
        for patch in payload['streams'][member['semantic_sha256']]:
            current=codec.apply(current,patch); h.update(codec.encoded(current)+b'\n')
            rows.append(deepcopy(current))
        if h.hexdigest()!=member['semantic_sha256'] or len(rows)!=member['rows']:
            raise ValueError('retained decoded identity mismatch')
        yield name,member,rows,item['sha256']


def compact(groups):
    return {name:{'windows':g['windows'],'identified':g['identified'],
                  'censored':g['censored'],'positive':g['positive'],
                  'scores':{k:{'n':s['n'],'brier':s['mean_brier'],'log_loss':s['mean_log_loss'],
                                'paired_brier_delta_vs_prior':s['mean_paired_brier_delta_vs_prior']}
                            for k,s in g['scores'].items() if k!='zero'}}
            for name,g in groups.items() if name in ('all','warm','cold') or name.startswith(('product:','game-warm:'))}


def run(portfolio, calibration_dir, design_output, output):
    output.mkdir(parents=True,exist_ok=False)
    frozen=json.loads(Path(__file__).with_name('FROZEN.json').read_text())
    source=Path(__file__).with_name('backoff.py')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=frozen['source_sha256']:
        raise ValueError('backoff source differs from pre-transfer freeze')
    if hashlib.sha256((design_output/'results.json').read_bytes()).hexdigest()!=frozen['original_lonespear_result_sha256']:
        raise ValueError('design assessment differs from the recorded version')
    sys.path.insert(0,str(calibration_dir));sys.path.insert(0,str(portfolio))
    sys.path.insert(0,str(calibration_dir/'development_replay'))
    import assess
    calibration=assess.load(calibration_dir/'calibration.py','quill_backoff_calibration')
    flow=assess.load(portfolio/'revision2/vendor/t12/flow.py','quill_backoff_flow')
    evaluator=assess.load(portfolio/'vendor/cloud-eval/evaluate.py','quill_backoff_evaluator')
    engine,_=evaluator.get_engine(portfolio/'vendor/engine')
    ledger=assess.load(portfolio/'revision2/trace_ledger.py','quill_backoff_ledger')
    inputs={'backoff_sha256':assess.sha(source),'compare_blob':assess.blob(__file__),
            'assessment_blob':assess.blob(calibration_dir/'development_replay/assess.py'),
            'calibration_blob':assess.blob(calibration_dir/'calibration.py'),
            'flow_blob':assess.blob(portfolio/'revision2/vendor/t12/flow.py'),
            'ledger_blob':assess.blob(portfolio/'revision2/trace_ledger.py'),
            'engine_blob':assess.blob(portfolio/'vendor/engine/kaggriculture.py'),
            'freeze':frozen}
    (output/'INPUTS.json').write_bytes(assess.encoded(inputs)+b'\n')
    design=[]
    previous=json.loads((design_output/'results.json').read_text())
    for game in previous['games']:
        path=design_output/(game['game_id']+'.outcomes.json.gz')
        rows=json.loads(gzip.decompress(path.read_bytes()))
        design.extend(augment(rows,calibration,'lonespear-v18-greedy','development-design'))
    design_summary=compact(assess.aggregate(design))
    (output/'lonespear.outcomes.json.gz').write_bytes(gzip.compress(assess.encoded(design),mtime=0))
    print(json.dumps({'group':'lonespear-design','summary':design_summary['all']}),flush=True)
    transfer=[]; games=[]
    for name,member,rows,archive_hash in decode(portfolio,frozen['cok_members'],assess):
        if len(rows)!=719:
            raise ValueError('incomplete planned COK control; do not silently replace it')
        game_id=Path(name).name.removesuffix('.jsonl.gz')
        replay=assess.PublicReplay(engine,flow,calibration,game_id)
        for expected,row in enumerate(rows):
            if row['step']!=expected or row['candidate_seat']!=row['observation']['player']:
                raise ValueError('recorded time/seat mismatch')
            replay.feed(row['observation'],row['actions'][row['candidate_seat']])
        if replay.pending:
            raise ValueError('pending terminal forecast')
        # Current rival actions are used ONLY here, after every prediction froze.
        with tempfile.TemporaryDirectory(prefix='quill-cok-recorded-') as temp:
            p=Path(temp)/(game_id+'.jsonl.gz')
            p.write_bytes(gzip.compress(b''.join(assess.encoded(r)+b'\n' for r in rows),mtime=0))
            audit=ledger.attribute(p)
        checks=assess.truth_check(replay,audit,rows[0]['candidate_seat'])
        outcomes=augment(replay.outcomes,calibration,'cok-v10','development-transfer')
        report={'game_id':game_id,'member':name,'semantic_sha256':member['semantic_sha256'],
                'trace_archive_sha256':archive_hash,'checks':checks,'rows':len(rows),
                'summary':compact(assess.aggregate(outcomes))}
        for label,value in (('outcomes',outcomes),('intervals',replay.intervals),
                            ('own-fills',replay.fills),('offline-audit',audit)):
            (output/f'{game_id}.{label}.json.gz').write_bytes(gzip.compress(assess.encoded(value),mtime=0))
        (output/(game_id+'.json')).write_bytes(assess.encoded(report)+b'\n')
        games.append(report);transfer.extend(outcomes)
        print(json.dumps({'game':game_id,'checks':checks,'summary':report['summary']['all']}),flush=True)
    result={'inputs':inputs,'design':design_summary,'transfer':compact(assess.aggregate(transfer)),
            'transfer_games':games,'new_games':0,'new_seeds':[],'recommended_alpha':0,
            'scope':'Fixed marginal-event refinement chosen from lonespear development, applied to COK development; shared three map seeds, not a new held panel.',
            'probability_scope':'Not a probability distribution over quantities, orders or joint streams; no action/policy invocation.',
            'reliability':calibration.summarize(design+transfer)}
    if assess.sha(source)!=frozen['source_sha256']:
        raise ValueError('frozen source changed during assessment')
    (output/'results.json').write_bytes(assess.encoded(result)+b'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--portfolio',type=Path,required=True)
    p.add_argument('--calibration-dir',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--design-output',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        result=run(a.portfolio.resolve(),a.calibration_dir.resolve(),a.design_output.resolve(),a.output.resolve())
        print(json.dumps({'transfer':result['transfer']['all'],'new_games':0}))
    except (OSError,ValueError,KeyError) as exc:
        p.exit(2,f'comparison failed: {exc}\n')


if __name__=='__main__':
    main()
