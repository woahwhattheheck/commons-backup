# SPDX-License-Identifier: Apache-2.0
"""Controlled future-buyer sensitivity, not the missing HAZEL226 observations.

Two explicit future-shop streams share the same conditional observation at226.
This composes the existing T04 oracle and landed full-controller consumer only.
"""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path

from check_existing import load, blob
from physical_replay import ReplayLimits, replay_routes


def run(source_root, oracle_path, engine_root, observation_path):
    source_root = Path(source_root)
    evaluator = load(source_root / 'cloud-eval/evaluate.py', 'sensitivity_evaluator')
    engine, engine_hashes = evaluator.get_engine(engine_root)
    oracle = load(oracle_path, 'sensitivity_oracle')
    arlene_path = source_root / 'cloud-frontier-policy/next-panel/vendor/arlene.py'
    if hashlib.sha256(arlene_path.read_bytes()).hexdigest() != '1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4':
        raise ValueError('Use the documented existing Arlene source')
    if blob(oracle_path) != '49640c27862d3d132c828fbafc6a8b4957527736':
        raise ValueError('Use the documented existing T04 oracle')
    arlene = load(arlene_path, 'sensitivity_arlene')
    raw = Path(observation_path).read_bytes()
    document = json.loads(raw)
    initial = document['observation']
    if initial['step'] != 121 or initial['town']['unlocked_shops'] != ['BRUNCH_SPOT']:
        raise ValueError('This experiment uses only the documented T10 fixture')
    cfg = {k: v.get('default') if isinstance(v, dict) else v
           for k, v in engine.specification['configuration'].items()}
    cfg['seed'] = None
    controller = arlene.Agent()
    # These are explicit hypothetical draws at the normal schedule, not observed
    # past events recovered from the original game or a calibrated distribution.
    prefix_scenario = oracle.Scenario(new_shops={143: ('BRUNCH_SPOT',), 215: ('BRUNCH_SPOT',)},
                                      label='declared BRUNCH draws at144 and216; no rival flow or weeds')
    prefix = oracle.simulate_bundle(engine, initial, cfg, controller.act,
                                    end_step=225, scenario=prefix_scenario, record_actions=True)
    obs = deepcopy(initial)
    obs['farms'][int(obs['player'])] = prefix['farm']
    for key in ('private', 'market', 'town'):
        obs[key] = prefix[key]
    obs.update(step=226, day=9, hour=10)
    # Same observation and controller state in both futures. Subsequent draws are
    # declared before evaluating any route, with all8 shop instances represented.
    common = {step: ('BRUNCH_SPOT',) for step in (287, 359, 431, 503, 575)}
    yarn = dict(common); yarn[287] = ('YARN_STORE',)
    scenarios = {
        'brunch_future': oracle.Scenario(new_shops=common,
                         label='all remaining draws BRUNCH; no rival flow or weeds'),
        'yarn_at288': oracle.Scenario(new_shops=yarn,
                      label='YARN public at288; other remaining draws BRUNCH; no rival flow or weeds'),
    }
    report = replay_routes(controller, [arlene.MAIN, 'dc76e4003029ac51'], obs, cfg,
                           engine, oracle.simulate_bundle, scenarios=scenarios,
                           end_step=718, limits=ReplayLimits(seconds=20, decisions=3000))
    if not report['complete']:
        raise AssertionError([(c['status'], c.get('reason')) for c in report['cases']])
    summaries = []
    for case in report['cases']:
        summaries.append({
            'route': case['offered_route'], 'scenario': case['scenario_id'],
            'final_cash': case['final_cash'], 'cash_gain': case['cash_gain'],
            'active_route_at_end': case['active_routes'][-1]['active_route'],
            'action_sha256': case['action_sha256'],
            'discarded_stock': case['result']['discarded_stock'],
        })
    paired = {}
    for name in scenarios:
        rows = [c for c in summaries if c['scenario'] == name]
        main = next(c for c in rows if c['route'] == arlene.MAIN)
        sheep = next(c for c in rows if c['route'] != arlene.MAIN)
        paired[name] = {'main_cash': main['final_cash'], 'yarn_cash': sheep['final_cash'],
                        'yarn_minus_main_cash': sheep['final_cash'] - main['final_cash']}
    report['experiment'] = {
        'kind': 'controlled conditional own-state continuations; not full games or original HAZEL cases',
        'input_file_sha256': hashlib.sha256(raw).hexdigest(),
        'engine_sha256': engine_hashes,
        'oracle_blob': blob(oracle_path),
        'declared_prefix': {'start': 121, 'end': 225, 'shop_draws': prefix_scenario.new_shops},
        'conditional_observation_226': obs,
        'same_observation_for_every_future': True,
        'future_draw_first_difference_available_at': 288,
        'rival_flow': 'none in both conditional models; no rival cash utility',
        'scenario_probabilities': None,
        'paired_cash': paired, 'summaries': summaries,
        'full_games': 0, 'game_seeds_initialized': [],
    }
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--oracle', required=True)
    parser.add_argument('--engine-root', required=True)
    parser.add_argument('--observation', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = run(args.source_root, args.oracle, args.engine_root, args.observation)
    Path(args.output).write_text(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')
    print(json.dumps({'paired_cash': result['experiment']['paired_cash'],
                      'complete': result['complete'], 'wall_seconds': result['wall_seconds'],
                      'decisions_executed': result['decisions_executed']}, indent=2))
