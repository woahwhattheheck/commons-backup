# SPDX-License-Identifier: Apache-2.0
"""Offline native-engine cases and retained-development input consumption.

Evaluation-only recorded actions, terminal inventories and scores never enter
terminal_inputs.build_terminal_inputs or its scenario generation. No full game
or original held panel is executed here. Supply existing local dependencies.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
import importlib.util
import json
import lzma
from pathlib import Path
import random
import sys
import time
from types import SimpleNamespace as NS
from unittest.mock import patch

from terminal_inputs import build_terminal_inputs, fingerprint, market_cell, _config


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dependencies(loader, engine_dir, consumers, core_file):
    for name in ('kaggriculture.py', 'kaggriculture.json', 'utils.py'):
        if not (Path(engine_dir)/name).is_file():
            raise ValueError('Existing engine cache incomplete: '+name)
    reader = load(loader, '_terminal_native_loader')
    engine, hashes = reader.get_engine(engine_dir)
    terminal = load(Path(consumers)/'terminal_utility.py', '_terminal_native_utility')
    score = load(Path(consumers)/'score_endgame.py', '_terminal_native_score')
    previous = sys.modules.get('solver')
    sys.modules['solver'] = load(Path(consumers)/'solver.py', '_terminal_t15_math')
    try:
        selector = load(Path(consumers)/'selector.py', '_terminal_t15_selector')
    finally:
        if previous is None: sys.modules.pop('solver', None)
        else: sys.modules['solver'] = previous
    weighted = load(Path(consumers)/'weighted_selector.py', '_terminal_prism')
    core = load(core_file, '_terminal_poly')
    return NS(engine=engine, engine_hashes=hashes, terminal=terminal, score=score,
              selector=selector, weighted=weighted, core=core)


def make_state(obs, cfg, action, scenario, *, rival_private=None):
    farms, market, town = deepcopy(obs['farms']), deepcopy(obs['market']), deepcopy(obs['town'])
    player = obs['player']
    private = [None, None]
    private[player] = deepcopy(obs['private'])
    private[1-player] = deepcopy(rival_private) if rival_private is not None else {
        'shed': deepcopy(scenario['shed']), 'seeds': {},
        'inventories': [{} for _ in range(1+len(farms[1-player]['hands']))]}
    actions = [None, None]
    actions[player] = deepcopy(action)
    actions[1-player] = {'farmer': ['PASS'], 'hands': [], 'market': deepcopy(scenario['market'])}
    state = [NS(observation=NS(farms=farms, market=market, town=town, player=i,
                              private=private[i], step=obs['step'], day=obs['step']//cfg['turnsPerDay'],
                              hour=obs['step']%cfg['turnsPerDay']),
                action=actions[i], status='ACTIVE', reward=0) for i in range(2)]
    return state, NS(configuration=NS(**cfg), done=False, info={})


def own_unit_snapshot(engine, obs, cfg, action):
    """Evaluation fixture: capture the native interpreter's actual unit boundary.

    This is not shipped runtime projection. The native market is intercepted
    only to capture the already completed units and stop before any market,
    daily refresh or random event. The original method is restored immediately.
    """
    state, env = make_state(obs, cfg, action, {'shed': {}, 'market': []})
    class AtMarket(Exception): pass
    captured = {}
    def capture(current, _env):
        current_obs = current[obs['player']].observation
        captured.update(deepcopy(vars(current_obs)))
        raise AtMarket()
    with patch.object(engine, '_process_market', side_effect=capture):
        try:
            engine.interpreter(state, env)
        except AtMarket:
            pass
    if not captured:
        raise AssertionError('Native unit boundary was not reached')
    return captured


def choose(deps, obs, cfg, action, packet):
    selector = deps.score.make_score_selector(deps.selector.WholePlanSelector,
        deps.weighted.make_selector, deps.terminal.build_table, deps.core.solve_full_table,
        deps.core.verify_certificate, rng=random.Random(5307))
    # All complete candidate actions were run through the native market on this
    # exact own state in every included scenario. This checks that bound set;
    # it makes no statement about future commitments or excluded rival buys.
    valid = {fingerprint(p['action']) for p in packet['plans']} if packet['complete'] else set()
    out = selector.transform_terminal(obs, cfg, action, document=packet['document'],
                                      feasible=lambda a: fingerprint(a) in valid)
    return out, selector


def historical_post_units(record):
    """Evaluation-only inverse of recorded successful final market units.

    At this bank's step718 no end-of-day transfer occurs. Reverse SELL and BUY
    inventory receipts from the actual terminal private state. Do not infer
    baseline intended orders from fills; the recorded full rival queue is used.
    Subsequent exact baseline cash readback is required before counterfactuals.
    """
    frame = record['final_day'][-1]
    cfg, obs = frame['configuration'], frame['observation']
    if frame['step'] != cfg['episodeSteps']-2 or (frame['step']+1)%cfg['turnsPerDay'] == 0:
        raise ValueError('This inverse requires the retained non-EOD final boundary')
    player = obs['player']
    private = deepcopy(record['terminal']['private'][1-player])
    for r in reversed(record['final_day_receipts']):
        if r['step'] != frame['step'] or r['player'] != 1-player:
            continue
        op, item = r['op'], r['item']
        if op == 'SELL': private['shed'][item] = private['shed'].get(item, 0)+1
        elif op in ('BUY_PRODUCT', 'BUY_ANIMAL'): private['shed'][item] -= 1
        elif op == 'BUY_SEED': private['seeds'][item] -= 1
        else: raise ValueError('Unsupported recorded successful market operation '+str(op))
    if any(q < 0 for stock in (private['shed'], private['seeds']) for q in stock.values()):
        raise AssertionError('Negative reconstructed stock')
    return private


def run_reached(deps, archive, *, max_cells=256):
    raw = json.loads(lzma.decompress(Path(archive).read_bytes()))
    results = []
    for filename, text in sorted(raw.items()):
        if not filename.startswith('dev/'):
            continue  # Consumed held data is never selected by this command.
        record = json.loads(text)
        frame = record['final_day'][-1]
        obs, cfg = deepcopy(frame['observation']), deepcopy(frame['configuration'])
        # Remove the evaluator seed, even though the builder itself whitelists
        # only six mechanics settings and cannot use a seed field.
        cfg.pop('seed', None)
        player = obs['player']
        action = deepcopy(frame['actions'][player])
        post = own_unit_snapshot(deps.engine, obs, cfg, action)
        start = time.perf_counter()
        packet = build_terminal_inputs(deps.engine, obs, cfg, action,
            post_unit_observation=post, max_cells=max_cells)
        producer_seconds = time.perf_counter()-start
        start = time.perf_counter()
        output, actor = choose(deps, obs, cfg, action, packet)
        selector_seconds = time.perf_counter()-start
        table = deps.terminal.build_table(packet['document'])
        # Historical source data is used ONLY after the runtime packet/action is
        # frozen. It is never an included scenario or a policy-time feature.
        rp = historical_post_units(record)
        actual = {'id': 'evaluation-only-recorded-rival', 'shed': rp['shed'],
                  'market': deepcopy(frame['actions'][1-player].get('market', []))}
        farms = deepcopy(obs['farms']); farms[player] = deepcopy(post['farms'][player])
        baseline = market_cell(deps.engine, farms, post['private'], obs['market'], _config(cfg),
                               player, action, actual)
        recorded = [record['scores'][player], record['scores'][1-player]]
        if [baseline['own_cash'], baseline['rival_cash']] != recorded:
            raise AssertionError((filename, 'historical baseline cash does not reconcile', baseline, recorded))
        picked = market_cell(deps.engine, farms, post['private'], obs['market'], _config(cfg),
                             player, output, actual)
        def point(a, b): return 1 if a>b else .5 if a==b else 0
        results.append({'record': filename, 'seed': record['seed'], 'arm': record['arm'],
                        'opponent': record['opponent'], 'player': player,
                        'input_sha256': fingerprint({'observation':obs, 'configuration':cfg}),
                        'packet': packet, 'original_action': action, 'output_action': output,
                        'objective': actor.last_objective, 'decision': actor.last_decision,
                        'action_changed': output != action, 'draws': actor.draws,
                        'producer_seconds': producer_seconds, 'selector_seconds': selector_seconds,
                        'baseline_cash_reconciled': True, 'historical_cash': recorded,
                        'counterfactual_cash': [picked['own_cash'], picked['rival_cash']],
                        'historical_points': point(*recorded),
                        'counterfactual_points': point(picked['own_cash'], picked['rival_cash']),
                        'modeled_baseline_points': table['win_points'][0] if table['terminal'] else None})
    return {'schema':'titan.terminal-inputs.reached.v1', 'records': results,
            'summary': {'reused_development_records': len(results),
             'independent_development_seeds': len({r['seed'] for r in results}),
             'unique_observation_payloads': len({r['input_sha256'] for r in results}),
             'historical_baselines_reconciled': sum(r['baseline_cash_reconciled'] for r in results),
             'changed_actions': sum(r['action_changed'] for r in results),
             'native_conditional_market_calls': sum(r['packet']['native_market_calls'] for r in results),
             'evaluation_only_market_calls': 2*len(results),
             'max_producer_seconds': max((r['producer_seconds'] for r in results), default=0),
             'max_selector_seconds': max((r['selector_seconds'] for r in results), default=0),
             'full_games': 0, 'new_game_seeds':0,
             'scope':'Final-market counterfactuals on reused development frames, not new independent full-game WTL.'}}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loader', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--consumers', type=Path, required=True)
    parser.add_argument('--core-file', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    deps = dependencies(args.loader, args.engine_dir, args.consumers, args.core_file)
    result = run_reached(deps, args.archive)
    result['engine_hashes'] = deps.engine_hashes
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2); handle.write('\n')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__': main()
