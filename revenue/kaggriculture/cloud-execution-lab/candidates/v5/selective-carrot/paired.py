#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Matched crop-choice games using the existing Linux evaluator and bank."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kg-root', type=Path, required=True)
    p.add_argument('--engine-dir', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seeds', default='2051966578,1209125501')
    p.add_argument('--seats', default='0,1')
    p.add_argument('--opponents', default='apex_v7,arlene_v14')
    p.add_argument('--max-active', type=int, choices=[4,8,12], default=4)
    args = p.parse_args()
    if sys.platform != 'linux':
        p.error('Use a Linux VM for this process-isolated benchmark')
    root = args.kg_root.resolve(strict=True)
    existing = root/'cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py'
    h = load(existing, 'existing_v5_bench_helpers')
    if h.digest(args.baseline) != h.BASELINE_SHA256:
        raise ValueError('expected exact submitted V4 archive')
    baseline = h.archive_members(args.baseline)
    candidate = {str(f.relative_to(args.candidate_dir)).replace('\\','/'): f.read_bytes()
                 for f in args.candidate_dir.rglob('*') if f.is_file()
                 and '__pycache__' not in f.parts and f.suffix != '.pyc'}
    here = Path(__file__).resolve().parent
    expected = dict(baseline)
    expected['baseline_main.py'] = expected['main.py']
    builder = load(here/'build.py', 'carrot_profile_builder')
    expected['main.py'] = builder.entry_bytes(args.max_active)
    expected['selective_carrot.py'] = (here/'selective_carrot.py').read_bytes()
    if candidate != expected:
        raise ValueError('candidate must contain exact V4 plus the two published hook files')
    seeds = [int(s) for s in args.seeds.split(',')]
    seats = [int(s) for s in args.seats.split(',')]
    opponents = args.opponents.split(',')
    if not set(seats) <= {0,1} or not set(opponents) <= {'apex_v7','arlene_v14'}:
        p.error('supported seats0/1; opponents apex_v7/arlene_v14')
    args.output.mkdir(parents=True, exist_ok=False)
    evaluator = load(root/h.EVALUATOR, 'carrot_existing_evaluator')
    pack = load(root/'cloud-pack/pack.py', 'carrot_existing_pack')
    bridge = load(root/h.BANK/'reference_policies.py', 'carrot_existing_bank')
    loader = root/'20260907-offline-agent/evaluate.py'
    engine_hashes = evaluator.verify_sources(args.engine_dir)
    runtime = {}; opponent_receipts = {}
    for opponent in opponents:
        runtime[opponent] = args.output/'opponents'/opponent
        opponent_receipts[opponent] = bridge.prepare(opponent, root, runtime[opponent])
    run = {'schema':'astra.v5.selective-carrot.paired.v1', 'engine':engine_hashes,
           'max_active':args.max_active,
           'baseline_sha256':h.digest(args.baseline),
           'candidate_members':{k:hashlib.sha256(v).hexdigest() for k,v in sorted(candidate.items())},
           'opponents':opponent_receipts,'seeds':seeds,'seats':seats,
           'method':'Fresh full official-interpreter games; same seed/seat/opponent; alternating order. Linux 1.25s IPC action limit; canonical policy retains its own1s deadline. Not hosted Kaggle rating.'}
    h.write_json(args.output/'run.json', run)
    cells = []
    for opponent in opponents:
        for seed in seeds:
            for seat in seats:
                cell_id = f'{opponent}-s{seed}-p{seat}'
                cell = {'cell_id':cell_id,'opponent':opponent,'seed':seed,'seat':seat,'games':{}}
                order = ['baseline','candidate'] if len(cells)%2 == 0 else ['candidate','baseline']
                for label in order:
                    with tempfile.TemporaryDirectory(prefix=cell_id+'-'+label+'-', dir=args.output) as temp:
                        directory = Path(temp); payload = directory/'payload'
                        h.extract_members(baseline if label == 'baseline' else candidate, payload)
                        adapter = directory/'adapter.py'
                        pack.write_adapter(adapter, payload/'main.py')
                        rival = runtime[opponent]/'adapter.py'
                        specs = [str(adapter),str(rival)] if seat == 0 else [str(rival),str(adapter)]
                        engine, _ = evaluator.get_engine(args.engine_dir, loader)
                        interpret = engine.interpreter
                        plant_events = []
                        def counted_interpreter(state, env):
                            obs = state[0].observation
                            farms = obs.get('farms') or []
                            before = ({(x,y):(tile.get('crop'),tile.get('planted_day'))
                                       for y,row in enumerate(farms[seat]['tiles']) for x,tile in enumerate(row)
                                       if isinstance(tile,dict)} if farms else {})
                            result = interpret(state,env)
                            after_farms = state[0].observation.get('farms') or []
                            if farms and after_farms:
                                for y,row in enumerate(after_farms[seat]['tiles']):
                                    for x,tile in enumerate(row):
                                        if (isinstance(tile,dict) and tile.get('crop') == 'CARROT'
                                                and before.get((x,y)) != ('CARROT',tile.get('planted_day'))):
                                            plant_events.append({'step':obs.get('step'),'site':[x,y],
                                                                 'planted_day':tile.get('planted_day')})
                            return result
                        engine.interpreter = counted_interpreter
                        game = evaluator.play(engine, specs, args.engine_dir, loader,
                                              seed, seat, 20260912, 1.25, 10.0, 900.0)
                        game['actual_carrot_plant_events'] = plant_events
                    cell['games'][label] = game
                    h.write_json(args.output/f'{cell_id}-{label}.json', game)
                    print(json.dumps({'cell_id':cell_id,'arm':label,'status':game['status'],
                                      'steps':game['steps'],'scores':game['scores']}), flush=True)
                cell['baseline_margin'] = h.margin(cell['games']['baseline'],seat)
                cell['candidate_margin'] = h.margin(cell['games']['candidate'],seat)
                a,b = cell['baseline_margin'],cell['candidate_margin']
                cell['margin_delta'] = b-a if a is not None and b is not None else None
                cells.append(cell)
                h.write_json(args.output/'report.json', {'run':run,'cells':cells,'summary':h.summarize(cells)})
                print('PAIR '+json.dumps({k:v for k,v in cell.items() if k != 'games'}), flush=True)


if __name__ == '__main__':
    main()
