# SPDX-License-Identifier: MIT
"""Paired five-arm comparison using the existing process-isolated evaluator.

The fifth arm is the unchanged selected SELL reference. No policy receives the
seed. Own cash, rival cash, W/T/L, and interaction terms remain distinct.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import shutil
import sys

HERE = Path(__file__).resolve().parent
ARMS = ('parent','service','labor','both','sell')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verdict(row):
    if row['status'] != 'complete':
        return 'FAILED'
    me = row['candidate_seat']
    margin = row['scores'][me] - row['scores'][1-me]
    return 'W' if margin > 0 else 'L' if margin < 0 else 'T'


def summarize(games):
    summaries = {}
    by_key = {(g['seed'],g['opponent'],g['candidate_seat'],g['arm']):g for g in games}
    paired = []
    for arm in sorted({g['arm'] for g in games}):
        rows = [g for g in games if g['arm']==arm]
        valid = [g for g in rows if g['status']=='complete']
        own = [g['scores'][g['candidate_seat']] for g in valid]
        rival = [g['scores'][1-g['candidate_seat']] for g in valid]
        summaries[arm] = {'games':len(rows),'complete':len(valid),
            'W':sum(verdict(g)=='W' for g in rows),
            'T':sum(verdict(g)=='T' for g in rows),
            'L':sum(verdict(g)=='L' for g in rows),
            'failed':sum(verdict(g)=='FAILED' for g in rows),
            'mean_own_cash':statistics.mean(own) if own else None,
            'mean_rival_cash':statistics.mean(rival) if rival else None,
            'max_action_seconds':max((g['actors'][g['candidate_seat']]['max_call_seconds']
                for g in rows if len(g.get('actors',[]))==2),default=0)}
    for seed,opponent,seat in sorted({(g['seed'],g['opponent'],g['candidate_seat']) for g in games}):
        rows = {a:by_key.get((seed,opponent,seat,a)) for a in ARMS}
        if not all(rows[a] and rows[a]['status']=='complete' for a in ('parent','service','labor','both')):
            continue
        own = {a:g['scores'][seat] for a,g in rows.items() if g and g['status']=='complete'}
        rival = {a:g['scores'][1-seat] for a,g in rows.items() if g and g['status']=='complete'}
        margins = {a:own[a]-rival[a] for a in own}
        deltas = {a:own[a]-own['parent'] for a in own}
        paired.append({'seed':seed,'opponent':opponent,'seat':seat,
            'outcomes':{a:verdict(g) for a,g in rows.items() if g},
            'own_cash':own,'rival_cash':rival,'margins':margins,
            'own_cash_delta_vs_parent':deltas,
            'cash_interaction':deltas['both']-deltas['service']-deltas['labor'],
            'margin_interaction':margins['both']-margins['service']-margins['labor']+margins['parent']})
    return {'arms':summaries,'paired':paired}


def run(runtime, output, seeds, arms=ARMS, reuse=None):
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite experiment: {output}')
    output.mkdir(parents=True)
    ev = load(HERE.parent/'cloud-eval/evaluate.py','keel_panel_eval')
    engine, engine_hashes = ev.get_engine(runtime/'engine')
    games = []
    report = {'schema_version':1,'started_utc':datetime.now(timezone.utc).isoformat(),
        'engine_ref':ev.ENGINE_REF,'engine_sha256':engine_hashes,
        'evaluator_sha256':digest(HERE.parent/'cloud-eval/evaluate.py'),
        'composition_sha256':digest(runtime/'composition.py'),
        'runner_sha256':digest(__file__),'runtime_manifest':json.loads((runtime/'MANIFEST.json').read_text()),
        'seeds':seeds,'arms':list(arms),'games':games,
        'limits':{'action_rpc_seconds':1.0,'game_seconds':180.0,'startup_seconds':10.0},
        'scope':'Offline official interpreter; not Kaggle rating or selected-policy promotion.'}
    controls = {}
    previous = {}
    if reuse is not None:
        old = json.loads(reuse.read_text())
        if old['runtime_manifest']['pins'] != report['runtime_manifest']['pins']:
            raise ValueError('Cannot reuse changed component policies')
        if old['engine_sha256'] != engine_hashes:
            raise ValueError('Cannot reuse a changed engine')
        report['reuse'] = {'report_sha256':digest(reuse),
                           'composition_sha256':old['composition_sha256'],
                           'scope':'Unchanged non-composed controls only; never reuse both arm'}
        previous = {(g['seed'],g['opponent'],g['candidate_seat'],g['arm']):g
                    for g in old['games'] if g['status']=='complete' and g['arm']!='both'}
    def save():
        report['summary'] = summarize(games)
        (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    original = engine.interpreter
    for seed in seeds:
        for opponent in ('arlene','apex'):
            for seat in (0,1):
                for arm in arms:
                    prior = previous.get((seed,opponent,seat,arm))
                    if prior is not None:
                        game = deepcopy(prior)
                        trace_path = reuse.parent/game['trace_file']
                        if digest(trace_path) != game['trace_file_sha256']:
                            raise ValueError('Prior trace changed')
                        shutil.copy2(trace_path,output/trace_path.name)
                        if arm=='parent':
                            controls[(seed,opponent,seat)] = json.loads(gzip.decompress(trace_path.read_bytes()))['actions']
                        game['inherited_from_report_sha256'] = digest(reuse)
                        game['source_composition_sha256'] = old['composition_sha256']
                        games.append(game)
                        save()
                        print(json.dumps({'reused':True,'seed':seed,'opponent':opponent,'seat':seat,'arm':arm,'scores':game['scores']}),flush=True)
                        continue
                    frames, actions = [], []
                    def observe(states, env):
                        if states[0].observation.get('farms'):
                            step = int(states[seat].observation.get('step',0))
                            actions.append(deepcopy(states[seat].action))
                            if step in (121,592,718):
                                frames.append({'step':step,'observation':deepcopy(states[seat].observation),
                                               'actions':[deepcopy(s.action) for s in states]})
                        return original(states,env)
                    engine.interpreter = observe
                    candidate = str(runtime/f'{arm}_adapter.py')
                    rival = str(runtime/f'{opponent}_adapter.py')
                    pair = [candidate,rival] if seat==0 else [rival,candidate]
                    try:
                        game = ev.play(engine,pair,runtime/'engine',ev.LOADER,seed,seat,
                                       action_timeout=1.0,game_timeout=180.0)
                    finally:
                        engine.interpreter = original
                    game.update(arm=arm,opponent=opponent,source_composition_sha256=report['composition_sha256'])
                    game['action_trace_sha256'] = hashlib.sha256(ev.encoded(actions)).hexdigest()
                    key = (seed,opponent,seat)
                    if arm=='parent':
                        controls[key] = actions
                    control = controls.get(key,[])
                    game['action_changes_vs_paired_parent'] = [
                        {'step':step,'parent':a,'candidate':b}
                        for step,(a,b) in enumerate(zip(control,actions)) if a!=b]
                    stem = f'{seed}-{opponent}-{seat}-{arm}'
                    trace_path = output/f'{stem}.json.gz'
                    trace_path.write_bytes(gzip.compress(ev.encoded({'actions':actions,'frames':frames}),mtime=0))
                    game['trace_file'] = trace_path.name
                    game['trace_file_sha256'] = digest(trace_path)
                    games.append(game)
                    save()
                    print(json.dumps({k:game[k] for k in ('seed','opponent','candidate_seat','arm','status','scores','failure')}),flush=True)
                    if game['status'] != 'complete':
                        report['aborted_reason'] = 'First runtime failure; diagnose before further games'
                        save()
                        return report
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    save()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seeds',required=True)
    parser.add_argument('--arms',default=','.join(ARMS))
    parser.add_argument('--reuse',type=Path,help='Preserve completed unchanged non-composed development arms')
    args=parser.parse_args()
    seeds=[int(s) for s in args.seeds.split(',')]
    arms=args.arms.split(',')
    if len(seeds)!=len(set(seeds)) or len(arms)!=len(set(arms)) or any(a not in ARMS for a in arms):
        parser.error('Use distinct seeds and recognized distinct arms')
    report=run(args.runtime.resolve(),args.output.resolve(),seeds,arms,args.reuse)
    print(json.dumps(report['summary'],indent=2))
    sys.exit(int(any(g['status']!='complete' for g in report['games'])))
