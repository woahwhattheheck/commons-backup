# SPDX-License-Identifier: Apache-2.0
"""Run the late-choice development comparison through the existing evaluator.

The supplied evaluator owns process isolation, public clocks, action dispatch,
seed removal and interpreter execution. This driver only prepares exact actor
entries, records the delegated engine transitions, and checkpoints completed
results. It implements no game mechanics or policy fallback.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encoded(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def entry(path, *, sell_dir, implementation, enabled, telemetry):
    path.write_text(
        '# Generated execution entry; source paths are supplied by panel.py.\n'
        'import json\nimport sys\nfrom pathlib import Path\n'
        f'sys.path.insert(0, {str(sell_dir)!r})\n'
        f'sys.path.insert(0, {str(implementation)!r})\n'
        'from scheduler import SellScheduler\nfrom late_milk import wrap_sell\n'
        f'_actor = wrap_sell(SellScheduler(), enabled={enabled!r})\n'
        f'_telemetry = Path({str(telemetry)!r})\n'
        'def agent(obs, configuration=None):\n'
        '    action = _actor.act(obs, configuration)\n'
        "    if obs['step'] in (0, 433, 576, 577, 718):\n"
        "        row = {'step':obs['step'], 'route':_actor.controller.cur, 'choice':_actor.last_choice,\n"
        "               'milk_inventory':obs['market']['inventory']['MILK'],\n"
        "               'shops':obs.get('town',{}).get('unlocked_shops',[])}\n"
        "        with _telemetry.open('a',encoding='utf-8') as f: f.write(json.dumps(row,sort_keys=True)+'\\n')\n"
        '    return action\n', encoding='utf-8')


class RecordedEngine:
    """Delegate each actual interpreter call once and retain complete outputs."""
    def __init__(self, engine, stream):
        self.original = engine
        self.specification = engine.specification
        self.stream = stream
        self.calls = 0
        self.prefix = hashlib.sha256()
        self.all = hashlib.sha256()
    def interpreter(self, state, env):
        t = self.calls - 1  # First call initializes the actual engine.
        actions = deepcopy([s.action for s in state])
        result = self.original.interpreter(state, env)
        row = {'step': t, 'actions': actions, 'observations': [s.observation for s in state],
               'status': [s.status for s in state], 'rewards': [s.reward for s in state]}
        raw = encoded(row)
        self.stream.write(raw + b'\n')
        self.all.update(raw + b'\n')
        if t < 577: self.prefix.update(raw + b'\n')
        self.calls += 1
        return result


def main(*, entry_factory=None, arms=None, extra_metadata=None):
    write_entry = entry if entry_factory is None else entry_factory
    arms = (('frozen_sell_control', False), ('late_recheck', True)) if arms is None else tuple(arms)
    if len(arms) != 2 or len({name for name, _ in arms}) != 2:
        raise ValueError('Supply one named control and one named candidate')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluator', type=Path, required=True)
    parser.add_argument('--loader', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--sell-dir', type=Path, required=True)
    parser.add_argument('--arlene', type=Path, required=True)
    parser.add_argument('--apex', type=Path, required=True)
    parser.add_argument('--seeds', default='9982001,9982019')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for key in ('evaluator','loader','engine_dir','sell_dir','arlene','apex','output'):
        setattr(args,key,getattr(args,key).resolve())
    root = Path(__file__).resolve().parent
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Use a fresh result directory; do not silently replay cells')
    args.output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('prism_existing_evaluator', args.evaluator)
    evaluator = importlib.util.module_from_spec(spec); sys.modules[spec.name] = evaluator; spec.loader.exec_module(evaluator)
    engine, engine_hashes = evaluator.get_engine(args.engine_dir, loader=args.loader, prepare=False)
    dependencies = {'late_milk.py':sha(root/'late_milk.py'), 'panel.py':sha(Path(__file__)),
                    'evaluator':sha(args.evaluator), 'loader':sha(args.loader),
                    'scheduler':sha(args.sell_dir/'scheduler.py'), 'arlene':sha(args.arlene), 'apex':sha(args.apex)}
    source_closure = {str(p.relative_to(args.sell_dir)):sha(p) for p in args.sell_dir.rglob('*')
                      if p.is_file() and '__pycache__' not in p.parts}
    document = {'schema':'titan.late-milk-panel.v1', 'classification':'development',
                'seeds':[int(s) for s in args.seeds.split(',')], 'dependencies':dependencies,
                'frozen_sell_closure':source_closure,'engine_hashes':engine_hashes,
                'original_evaluator':str(args.evaluator),'limits':{'action_seconds':1.0,'game_seconds':120.0},
                'games':[], 'complete':False, 'held_seeds':[], 'selected_policy_changed':False}
    if extra_metadata:
        document['experiment_metadata'] = deepcopy(extra_metadata)
    atomic_json(args.output/'results.json', document)
    for seed in document['seeds']:
        for opponent, opponent_path in [('arlene',args.arlene),('apex',args.apex)]:
            for seat in (0,1):
                for arm, enabled in arms:
                    identity=f'{seed}-{opponent}-p{seat}-{arm}'
                    candidate=args.output/(identity+'.py')
                    telemetry=args.output/(identity+'.choices.jsonl')
                    write_entry(candidate,sell_dir=args.sell_dir,implementation=root,enabled=enabled,telemetry=telemetry)
                    trace=args.output/(identity+'.trace.jsonl.gz')
                    with gzip.open(trace,'wb',compresslevel=6) as output:
                        recorded=RecordedEngine(engine,output)
                        specs=[str(opponent_path)]*2; specs[seat]=str(candidate)
                        result=evaluator.play(recorded,specs,args.engine_dir,args.loader,seed,seat)
                    result.update(arm=arm,opponent=opponent,identity=identity,
                        entry_sha256=sha(candidate),trace_file=trace.name,trace_sha256=sha(trace),
                        full_transition_sha256=recorded.all.hexdigest(),
                        prefix_through_576_sha256=recorded.prefix.hexdigest(),
                        interpreter_calls=recorded.calls,
                        choices=[json.loads(x) for x in telemetry.read_text().splitlines()] if telemetry.exists() else [])
                    document['games'].append(result)
                    atomic_json(args.output/'results.json',document)
                    print(json.dumps({k:result.get(k) for k in ('identity','status','scores','failure','wall_seconds')},sort_keys=True),flush=True)
    pairs=[]
    for i in range(0,len(document['games']),2):
        control,candidate=document['games'][i:i+2]
        seat=control['candidate_seat']
        pair={'seed':control['seed'],'opponent':control['opponent'],'player':seat,
              'complete':control['status']==candidate['status']=='complete',
              'same_prefix':control['prefix_through_576_sha256']==candidate['prefix_through_576_sha256']}
        choices=[x['choice'] for x in candidate['choices'] if x['step']==577]
        pair['choice']=choices[0] if choices else None
        if pair['complete']:
            a,b=control['scores'],candidate['scores']
            pair.update(own_delta=b[seat]-a[seat],rival_delta=b[1-seat]-a[1-seat],
                        margin_delta=(b[seat]-b[1-seat])-(a[seat]-a[1-seat]),
                        control_margin=a[seat]-a[1-seat],candidate_margin=b[seat]-b[1-seat])
        pairs.append(pair)
    document['pairs']=pairs
    document['complete']=all(g['status']=='complete' for g in document['games'])
    document['summary']={}
    for arm, _enabled in arms:
        games=[g for g in document['games'] if g['arm']==arm and g['status']=='complete']
        margins=[g['scores'][g['candidate_seat']]-g['scores'][1-g['candidate_seat']] for g in games]
        document['summary'][arm]={'complete':len(games),'wins':sum(x>0 for x in margins),
            'ties':sum(x==0 for x in margins),'losses':sum(x<0 for x in margins),
            'max_candidate_call_seconds':max([g['actors'][g['candidate_seat']]['max_call_seconds'] for g in games],default=0)}
    atomic_json(args.output/'results.json',document)
    print(json.dumps(document['summary'],sort_keys=True),flush=True)
    return 0 if document['complete'] else 1

if __name__=='__main__': raise SystemExit(main())
