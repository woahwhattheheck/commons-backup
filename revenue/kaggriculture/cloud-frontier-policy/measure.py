"""Use existing cloud-eval; add passive action/transaction diagnostics only."""
import argparse
import collections
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine-dir', type=Path, required=True)
    p.add_argument('--candidate', type=Path, default=HERE/'candidate.py')
    p.add_argument('--seeds', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location('frontier_existing_eval', HERE.parent/'cloud-eval/evaluate.py')
    ev = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ev
    spec.loader.exec_module(ev)
    engine, hashes = ev.get_engine(args.engine_dir)
    candidate = str(args.candidate.resolve())
    parents = {name: str(HERE/'vendor'/file) for name, file in
               [('kaito_v43', 'kaito_v43.py'), ('igor_multiroute', 'igor_multiroute.py')]}
    report = {'engine_ref': ev.ENGINE_REF, 'engine_sha256': hashes,
              'evaluator_sha256': ev.sha256(ev.__file__),
              'measurement_sha256': ev.sha256(__file__),
              'candidate': ev.fingerprint(candidate),
              'parents': {n: ev.fingerprint(f) for n, f in parents.items()},
              'method': 'Existing process-isolated cloud-eval.play, full 719 rounds. Passive hooks count actual official interpreter calls and successful market commits; no substitute transition logic. Not hosted rating.',
              'games': []}
    original_unit, original_commit, original_interpreter = engine._apply_unit_action, engine._commit_unit, engine.interpreter
    for seed in map(int, args.seeds.split(',')):
        for opponent, path in parents.items():
            for seat in (0, 1):
                diagnostics = [dict(unit_actions=collections.Counter(), unchanged_nonpass=collections.Counter(),
                                    market_units=collections.Counter(), market_cash=collections.Counter()) for _ in range(2)]
                farm_ids = {}
                final = {}
                def unit(farm, private, idx, action, *a, **kw):
                    player = farm_ids[id(farm)]
                    op = action[0] if isinstance(action, list) and action else 'EMPTY'
                    before = (copy.deepcopy(farm), copy.deepcopy(private))
                    result = original_unit(farm, private, idx, action, *a, **kw)
                    diagnostics[player]['unit_actions'][op] += 1
                    if op != 'PASS' and before == (farm, private):
                        diagnostics[player]['unchanged_nonpass'][op] += 1
                    return result
                def commit(op, item, price, farm, private, *a, **kw):
                    result = original_commit(op, item, price, farm, private, *a, **kw)
                    if result:
                        d = diagnostics[farm_ids[id(farm)]]
                        d['market_units'][op+':'+item] += 1
                        d['market_cash'][op+':'+item] += price
                    return result
                def interpreter(state, env):
                    if state[0].observation.get('farms'):
                        farm_ids.update({id(f): i for i, f in enumerate(state[0].observation.farms)})
                    result = original_interpreter(state, env)
                    farms = state[0].observation.farms
                    farm_ids.update({id(f): i for i, f in enumerate(farms)})
                    if all(s.status == 'DONE' for s in state):
                        final['farms'] = copy.deepcopy(farms)
                        final['private'] = [copy.deepcopy(s.observation.private) for s in state]
                        final['town'] = copy.deepcopy(state[0].observation.town)
                    return result
                engine._apply_unit_action, engine._commit_unit, engine.interpreter = unit, commit, interpreter
                pair = [candidate, path] if seat == 0 else [path, candidate]
                game = ev.play(engine, pair, args.engine_dir, ev.LOADER, seed, seat)
                game.update(opponent=opponent, diagnostics=diagnostics, terminal=final)
                report['games'].append(game)
                report['summary'] = ev.summarize(report['games'])
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2)+'\n')
                print(json.dumps({k: game[k] for k in ('seed', 'opponent', 'candidate_seat', 'scores', 'status', 'failure')}), flush=True)
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
