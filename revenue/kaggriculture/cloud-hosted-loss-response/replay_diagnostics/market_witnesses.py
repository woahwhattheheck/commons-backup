"""Offline market/seed witnesses. No hidden-seed rerun or policy promotion.

The order candidate reads only own observed goods and public market curves.
The path comparison intentionally consumes a recorded future action tape and
public random outcomes: NEVER import that tape as an agent-runtime input.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

import diagnostics as d


def impact_order(observation, base_action, engine, configuration=None):
    """Rank only the initial SELL prefix by an explicit mirrored-lot stress.

    Compare selling the owned available lot now versus after an equally sized
    hypothetical competing lot. This is an observable scenario, not a forecast
    of the rival's private goods. All quantities and non-prefix slots survive.
    """
    _, private, _ = d._owned_phase(observation, base_action, engine, configuration or {})
    out = copy.deepcopy(base_action)
    orders = out.get('market', [])
    if not isinstance(orders, list):
        return out, []
    available = Counter(private['shed'])
    params = observation['market'].get('params')
    scores = []
    def sell(item, inventory, n):
        cash = 0
        for _ in range(n):
            price = engine.market_price(item, inventory, params)
            cash += price
            if price > 1:
                inventory += 1
        return cash, inventory
    for index, order in enumerate(orders):
        if not (isinstance(order, list) and len(order) >= 3 and order[0] == 'SELL'):
            break
        item = order[1]
        if item not in observation['market']['inventory']:
            return out, []
        q = min(available[item], max(0, int(order[2])))
        available[item] -= q
        inventory = observation['market']['inventory'][item]
        first, after_competing = sell(item, inventory, q)
        later, _ = sell(item, after_competing, q)
        scores.append({'original_index': index, 'item': item, 'owned_quantity': q,
                       'mirrored_lot_receipt_risk': first-later})
    ranking = sorted(scores, key=lambda row: -row['mirrored_lot_receipt_risk'])
    original = copy.deepcopy(orders)
    for index, row in enumerate(ranking):
        orders[index] = original[row['original_index']]
    return out, scores


def _execute(before, actions, engine, ev, cfg, info):
    shared = ev.structify(copy.deepcopy(before[0]))
    state = []
    for player, obs in enumerate(before):
        visible = ev.structify(copy.deepcopy(obs))
        visible.farms, visible.market, visible.town = shared.farms, shared.market, shared.town
        state.append(ev.Struct(observation=visible, action=copy.deepcopy(actions[player]), status='ACTIVE', reward=0))
    env = ev.Struct(configuration=ev.structify(copy.deepcopy(cfg)), done=False, info=copy.deepcopy(info))
    engine.interpreter(state, env)
    return state


def carry_path(replay, own, replacements, engine, ev, *, seed_item='WHEAT', trace_module=None):
    """Carry cash/one seed delta; stop on ANY other deterministic divergence.

    Reconstruct each turn from its recorded public state plus the propagated
    financial deltas. A baseline audit is rerun at every transition. Random
    boundary fields are also compared when the public replay includes its seed.
    Otherwise weeds/new shop draws follow the recorded exogenous path, not a
    guessed seed. Only paths matching every compared field may continue.
    """
    d._seat(own)
    tm = trace_module or d.load_trace_module()
    steps = replay['steps']
    if not replacements:
        raise ValueError('At least one replacement action is needed')
    known = {tm.observations(steps[i-1])[0]['step']: i for i in range(1, len(steps))}
    if not set(replacements).issubset(known):
        raise ValueError('Replacement step is outside this replay')
    first = min(known[step] for step in replacements)
    cfg = {k: v.get('default') if isinstance(v, dict) else v for k, v in engine.specification['configuration'].items()}
    cfg.update(replay.get('configuration', {}))
    cash_delta = [0, 0]
    seed_delta = 0
    changes = []
    compared = 0
    excluded_boundaries = []
    seed_available = 'seed' in replay.get('info', {})
    for frame in range(first, len(steps)):
        before = tm.observations(steps[frame-1])
        after = tm.observations(steps[frame])
        step = before[0]['step']
        actions = [row.get('action') or {} for row in tm.frame_rows(steps[frame])]
        audit = tm.audit_transition(engine, ev, before, after, actions, cfg, step, replay.get('info', {}))
        if audit['status'] != 'RECONCILED':
            return {'status': 'BASELINE_'+audit['status'], 'frame': frame, 'audit': audit}
        alternative = copy.deepcopy(actions)
        if step in replacements:
            alternative[own] = copy.deepcopy(replacements[step])
            changes.append({'action_step': step, 'original': actions[own], 'replacement': alternative[own]})
        modified = copy.deepcopy(before)
        for obs in modified:
            for player in (0, 1):
                obs['farms'][player]['money'] += cash_delta[player]
        modified[own]['private']['seeds'][seed_item] = modified[own]['private']['seeds'].get(seed_item, 0) + seed_delta
        if modified[own]['private']['seeds'][seed_item] < 0:
            return {'status': 'NEGATIVE_SEED_STATE', 'frame': frame}
        actual = _execute(modified, alternative, engine, ev, cfg, replay.get('info', {}))
        boundary = (step+1) % cfg['turnsPerDay'] == 0
        random_unknown = boundary and not seed_available
        checks = {}
        for player in (0, 1):
            farm = tm.economic_farm(actual[0].observation.farms[player], random_unknown)
            recorded = tm.economic_farm(after[0]['farms'][player], random_unknown)
            farm.pop('money'); recorded.pop('money')
            checks[f'farm_{player}'] = farm == recorded
            private = copy.deepcopy(actual[player].observation.private)
            recorded_private = copy.deepcopy(after[player]['private'])
            if player == own:
                private['seeds'].pop(seed_item, None)
                recorded_private['seeds'].pop(seed_item, None)
            checks[f'private_{player}'] = private == recorded_private
        checks['market'] = actual[0].observation.market == after[0]['market']
        checks['town'] = actual[0].observation.town == after[0]['town'] if not random_unknown else True
        if not all(checks.values()):
            return {'status': 'NONFINANCIAL_DIVERGENCE', 'frame': frame, 'action_step': step,
                    'checks': checks, 'equivalent_transitions_before_failure': compared}
        cash_delta = [actual[0].observation.farms[p]['money']-after[0]['farms'][p]['money'] for p in (0, 1)]
        seed_delta = actual[own].observation.private['seeds'].get(seed_item, 0)-after[own]['private']['seeds'].get(seed_item, 0)
        compared += 1
        if random_unknown:
            excluded_boundaries.append(step)
    terminal = tm.observations(steps[-1])[0]['farms']
    return {'status': 'RECORDED_PATH_EQUIVALENT_EXCEPT_CASH_AND_SEEDS', 'own_seat': own,
            'changes': changes, 'compared_transitions': compared,
            'terminal_cash_delta_by_seat': cash_delta,
            'terminal_cash_by_seat': [f['money']+cash_delta[p] for p, f in enumerate(terminal)],
            'relative_cash_gain': cash_delta[own]-cash_delta[1-own],
            'terminal_seed_delta': {seed_item: seed_delta},
            'seed_available_for_offline_engine': seed_available,
            'excluded_random_boundaries': excluded_boundaries,
            'limitation': 'Recorded future actions held fixed. Available public replay seed is interpreter-only, never a runtime policy input. Missing random metadata follows the recorded exogenous path. Not a reactive-opponent game or held evaluation.'}


def run(path, engine_dir, own):
    tm = d.load_trace_module()
    replay, source = tm.load_replay(path)
    ev = tm.evaluator()
    engine, engine_hashes = ev.get_engine(engine_dir)
    cfg = {k: v.get('default') if isinstance(v, dict) else v for k,v in engine.specification['configuration'].items()}
    cfg.update(replay.get('configuration', {}))
    # These two exploratory indices come from the hosted-loss diagnosis. They
    # are NOT defaults for a deployable policy or a general future-route model.
    changes = {}
    for step, retained in ((600, 2), (624, 0)):
        frame = next(i for i in range(1,len(replay['steps'])) if tm.observations(replay['steps'][i-1])[0]['step']==step)
        action = copy.deepcopy(tm.frame_rows(replay['steps'][frame])[own]['action'])
        matching = [i for i,o in enumerate(action.get('market', [])) if len(o)>2 and o[:2]==['BUY_SEED','WHEAT']]
        if len(matching) != 1:
            raise ValueError('The targeted witness expects one WHEAT seed purchase at each diagnosed step')
        action['market'][matching[0]][2] = retained
        changes[step] = action
    order_cases = []
    for step in (529, 577, 601, 697, 717, 718):
        frame = next(i for i in range(1,len(replay['steps'])) if tm.observations(replay['steps'][i-1])[0]['step']==step)
        before = tm.observations(replay['steps'][frame-1])[own]
        action = tm.frame_rows(replay['steps'][frame])[own]['action']
        alternative, scores = impact_order(before, action, engine, cfg)
        comparison = d.counterfactual_transition(replay, frame, own, alternative, engine, ev, tm)
        order_cases.append({'step': step, 'scenario_scores': scores, 'counterfactual': comparison})
    return {'schema': 't13.market-witness.v1', 'source': source,
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'engine_sha256': engine_hashes, 'episode_id': replay.get('info',{}).get('EpisodeId'),
            'own_seat': own, 'seed_path': carry_path(replay, own, changes, engine, ev, trace_module=tm),
            'order_cases': order_cases,
            'selection_limit': 'Diagnosed steps selected from these two hosted losses; exploratory in-sample witnesses, not held policy evidence.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('replay', type=Path)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument(
        '--own-seat', type=int, choices=(0,1),
        required=True,
    )
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.replay, args.engine_dir, args.own_seat)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'episode_id': result['episode_id'], 'seed_path': result['seed_path']['status'],
                      'relative_gain': result['seed_path'].get('relative_cash_gain')}))


if __name__ == '__main__':
    main()
