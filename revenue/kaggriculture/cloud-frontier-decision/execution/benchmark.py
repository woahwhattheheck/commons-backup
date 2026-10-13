# SPDX-License-Identifier: Apache-2.0
# SORREL adaptation of LARK measurement harness; transitions unchanged.
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
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--seeds', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location('frontier_existing_eval', HERE.parent.parent/'cloud-eval/evaluate.py')
    ev = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ev
    spec.loader.exec_module(ev)
    engine, hashes = ev.get_engine(args.engine_dir)
    candidate = str(args.candidate.resolve())
    parents = {name: str(args.runtime.resolve()/(name+'-adapter.py')) for name in ('arlene', 'apex')}
    report = {'engine_ref': ev.ENGINE_REF, 'engine_sha256': hashes,
              'evaluator_sha256': ev.sha256(ev.__file__),
              'measurement_sha256': ev.sha256(__file__),
              'candidate': ev.fingerprint(candidate),
              'parents': {n: ev.fingerprint(f) for n, f in parents.items()},
              'execution': json.loads((args.runtime/'execution-manifest.json').read_text()),
              'method': 'Existing process-isolated cloud-eval.play, full 719 rounds. Passive hooks count actual official interpreter calls and successful market commits; no substitute transition logic. Not hosted rating.',
              'runtime_manifest': json.loads((args.runtime/'manifest.json').read_text()),
              'games': []}
    base_spec=importlib.util.spec_from_file_location('intact_baseline', HERE.parent.parent/'cloud-frontier-policy/next-panel/vendor/arlene.py')
    baseline=importlib.util.module_from_spec(base_spec);base_spec.loader.exec_module(baseline)
    original_unit, original_commit, original_interpreter = engine._apply_unit_action, engine._commit_unit, engine.interpreter
    for seed in map(int, args.seeds.split(',')):
        for opponent, path in parents.items():
            for seat in (0, 1):
                diagnostics = [dict(unit_actions=collections.Counter(), unchanged_nonpass=collections.Counter(),
                                    market_units=collections.Counter(), market_cash=collections.Counter()) for _ in range(2)]
                farm_ids = {}
                current_step = [-1]
                final = {}
                timeline = []
                shadow=baseline.Agent()
                comparisons=collections.Counter()
                unchanged_events = []
                def unit(farm, private, idx, action, *a, **kw):
                    player = farm_ids[id(farm)]
                    op = action[0] if isinstance(action, list) and action else 'EMPTY'
                    before = (copy.deepcopy(farm), copy.deepcopy(private))
                    result = original_unit(farm, private, idx, action, *a, **kw)
                    diagnostics[player]['unit_actions'][op] += 1
                    if op != 'PASS' and before == (farm, private):
                        diagnostics[player]['unchanged_nonpass'][op] += 1
                        unchanged_events.append({'step': current_step[0], 'seat':player,'unit':idx,'action':action})
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
                    current_step[0] = state[0].observation.get('step', 0)
                    if state[0].observation.get('farms'):
                        expected=shadow.act(state[seat].observation)
                        actual=state[seat].action
                        comparisons['observed_turns']+=1
                        comparisons['unit_action_mismatches']+=int(expected.get('farmer')!=actual.get('farmer') or expected.get('hands')!=actual.get('hands'))
                        comparisons['market_changed_turns']+=int(expected.get('market')!=actual.get('market'))
                        comparisons['non_sell_mismatches']+=int([o for o in expected.get('market',[]) if o and o[0]!='SELL'] != [o for o in actual.get('market',[]) if o and o[0]!='SELL'])
                    if state[0].observation.get('farms') and (current_step[0] % 24 == 0 or current_step[0] >= 716):
                        timeline.append({'step':current_step[0], 'prices':copy.deepcopy(state[0].observation.market), 'shops':copy.deepcopy(state[0].observation.town), 'farms':copy.deepcopy(state[0].observation.farms), 'private':[copy.deepcopy(s.observation.private) for s in state], 'actions':[copy.deepcopy(s.action) for s in state]})
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
                game.update(baseline_action_comparison=dict(comparisons), opponent=opponent, diagnostics=diagnostics, terminal=final, timeline=timeline, unchanged_events=unchanged_events)
                report['games'].append(game)
                report['summary'] = ev.summarize(report['games'])
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2)+'\n')
                print(json.dumps({k: game[k] for k in ('seed', 'opponent', 'candidate_seat', 'scores', 'status', 'failure')}), flush=True)
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
