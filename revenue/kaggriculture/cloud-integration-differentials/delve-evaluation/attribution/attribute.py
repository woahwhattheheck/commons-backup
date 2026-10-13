"""Cash attribution and explicitly fixed-action suffixes over saved game frames.

Uses the retained official evaluator and interpreter without invoking agents.
Recorded rival commands are offline evidence, never a forecast or policy input.
Run serially: instrumentation is installed on the supplied engine temporarily.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stock(private):
    result = Counter(private.get('shed', {}))
    for inventory in private.get('inventories', []):
        result.update(inventory)
    return result


def replay(engine, ev, rows, own, *, start=0, insertions=None,
           market_overrides=None, require_match=False, record_states=False):
    """Execute complete recorded suffix, optional explicit edits, and cash ledger.

    Every edit is to a market slot only. Both players' subsequent commands remain
    recorded, even when the altered state would cause a live policy to react.
    require_match checks full stored state, not just terminal cash.
    """
    if type(own) is not int or own not in (0, 1):
        raise ValueError('Game position must be 0 or 1')
    if type(start) is not int or not 0 <= start < len(rows)-1:
        raise ValueError('Starting frame is outside the complete trace')
    if len(rows[-1]['state']) != 2 or any(s['status'] != 'DONE' for s in rows[-1]['state']):
        raise ValueError('A complete two-player trace is needed')
    if require_match and (insertions or market_overrides):
        raise ValueError('Baseline comparison cannot include an edit')
    for edits in (insertions or {}, market_overrides or {}):
        if not isinstance(edits, dict):
            raise ValueError('Interventions must map decision indices to edits')
        if any(type(k) is not int or not start <= k < len(rows)-1 for k in edits):
            raise ValueError('Intervention is outside the executed suffix')
    for item, quantity in (insertions or {}).values():
        if not isinstance(item, str) or not item or type(quantity) is not int or quantity <= 0:
            raise ValueError('Inserted sale needs a product and positive integer quantity')
    for queue in (market_overrides or {}).values():
        if not isinstance(queue, list) or not all(isinstance(order, list) for order in queue):
            raise ValueError('Replacement queue must be an ordered list of orders')
    state = ev.structify(copy.deepcopy(rows[start]['state']))
    cfg = ev.structify(copy.deepcopy(rows[start]['configuration']))
    env = ev.Struct(configuration=cfg, info=copy.deepcopy(rows[start]['info']), done=False)
    for actor in state[1:]:
        for key in ('farms', 'market', 'town'):
            actor.observation[key] = state[0].observation[key]
    names = ('_commit_unit', '_do_hire', '_do_buy_land')
    original = {name: getattr(engine, name) for name in names}
    cash, quantities = [Counter(), Counter()], [Counter(), Counter()]
    records, transitions, states = [], [], []
    opening = [state[0].observation.farms[p]['money'] for p in (0, 1)]
    clock = [start]

    def locate(farm):
        for p, candidate in enumerate(state[0].observation.farms):
            if farm is candidate:
                return p
        raise ValueError('Unknown farm in recorded transition')

    def trade(op, item, price, farm, private, market, *args, **kwargs):
        p, before = locate(farm), farm['money']
        ok = original['_commit_unit'](op, item, price, farm, private, market, *args, **kwargs)
        change, key = farm['money']-before, f'{op}:{item}'
        cash[p][key] += change
        if ok:
            quantities[p][key] += 1
        records.append({'step': clock[0], 'position': p, 'cause': key,
                        'cash': change, 'success': bool(ok), 'quote': price})
        return ok

    def capital(name):
        def call(farm, *args, **kwargs):
            p, before = locate(farm), farm['money']
            result = original[name](farm, *args, **kwargs)
            change = farm['money']-before
            cash[p][name] += change
            records.append({'step': clock[0], 'position': p, 'cause': name, 'cash': change})
            return result
        return call

    engine._commit_unit = trade
    engine._do_hire = capital('_do_hire')
    engine._do_buy_land = capital('_do_buy_land')
    exact, applied, t0 = 0, [], time.perf_counter()
    try:
        for step in range(start, len(rows)-1):
            clock[0] = step
            for p in (0, 1):
                state[p].observation.step = step
                state[p].observation.remainingOverageTime = 0
                state[p].action = copy.deepcopy(rows[step+1]['state'][p]['action'])
            if step in (market_overrides or {}):
                replacement = copy.deepcopy(market_overrides[step])
                if len(replacement) > int(cfg.get('maxMarketOrdersPerTurn', 10)):
                    raise ValueError('Market override exceeds slot count')
                state[own].action['market'] = replacement
                applied.append({'step': step, 'market_override': replacement})
            if step in (insertions or {}):
                orders = state[own].action.setdefault('market', [])
                if len(orders) >= int(cfg.get('maxMarketOrdersPerTurn', 10)):
                    raise ValueError('No appended market slot')
                item, quantity = insertions[step]
                orders.append(['SELL', item, quantity])
                applied.append({'step': step, 'item': item, 'requested': quantity, 'slot': len(orders)-1})
            engine.interpreter(state, env)
            expected = rows[step+1]['state']
            equal = state == expected
            exact += int(equal)
            if require_match and not equal:
                changed = [f'{p}.{k}' for p in (0, 1) for k in expected[p]
                           if state[p].get(k) != expected[p][k]]
                raise AssertionError(f'Recorded baseline fails at step{step}: {changed}')
            banks = [state[0].observation.farms[p]['money'] for p in (0, 1)]
            reference = [expected[0]['observation']['farms'][p]['money'] for p in (0, 1)]
            inventory_deltas = []
            for p in (0, 1):
                actual = stock(state[p].observation.private)
                previous = stock(expected[p]['observation']['private'])
                inventory_deltas.append({k: actual[k]-previous[k]
                                         for k in sorted(actual.keys() | previous.keys())
                                         if actual[k] != previous[k]})
            transitions.append({'step': step, 'banks': banks, 'recorded_banks': reference,
                'cash_delta_by_position': [banks[p]-reference[p] for p in (0, 1)],
                'inventory_delta_by_position': inventory_deltas,
                'market_equal': state[0].observation.market == expected[0]['observation']['market'],
                'tiles_equal': [state[0].observation.farms[p]['tiles'] == expected[0]['observation']['farms'][p]['tiles'] for p in (0, 1)]})
            if record_states:
                states.append({'state': copy.deepcopy(state), 'configuration': copy.deepcopy(cfg),
                               'info': copy.deepcopy(env.info)})
            if all(actor.status == 'DONE' for actor in state):
                break
        terminal = [state[0].observation.farms[p]['money'] for p in (0, 1)]
        residual = [terminal[p]-opening[p]-sum(cash[p].values()) for p in (0, 1)]
        if any(residual):
            raise AssertionError(f'Unattributed cash: {residual}')
        if not all(actor.status == 'DONE' for actor in state):
            raise AssertionError('Recorded suffix did not reach DONE')
        return {'start': start, 'decisions': len(transitions), 'own_position': own,
                'opening': opening, 'terminal': terminal,
                'recorded_terminal': [rows[-1]['state'][0]['observation']['farms'][p]['money'] for p in (0, 1)],
                'exact_post_states': exact, 'cash_by_cause': [dict(c) for c in cash],
                'successful_units_by_cause': [dict(c) for c in quantities], 'cash_residual': residual,
                'insertions': applied, 'events': records, 'transitions': transitions,
                'terminal_state': state, 'counterfactual_states': states,
                'wall_seconds': time.perf_counter()-t0,
                'evidence_kind': 'recorded_action_suffix_not_responsive_policy_evaluation'}
    finally:
        for name, function in original.items():
            setattr(engine, name, function)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, out = args.package.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    ev = load('delve_attribution_eval', root/'source/tree/revenue/kaggriculture/cloud-eval/evaluate.py')
    engine, hashes = ev.get_engine(root/'engine/engine', prepare=False)
    summary, results = json.loads((root/'evaluation/SUMMARY.json').read_text()), []
    for cell in summary['cells']:
        seed, own = cell['seed'], cell['player']
        comparison = {'seed': seed, 'own_position': own, 'arms': {}}
        for arm in ('funded', 'sell'):
            path = (root/'evaluation'/cell['arms'][arm]['result_path']).with_suffix('.frames.jsonl.gz')
            value = replay(engine, ev, read_rows(path), own, require_match=True)
            name = f'{seed}-p{own}-{arm}.json.gz'
            data = gzip.compress(json.dumps(value, sort_keys=True, separators=(',', ':')).encode(), mtime=0)
            (out/name).write_bytes(data)
            comparison['arms'][arm] = {k: v for k, v in value.items()
                                      if k not in ('events', 'transitions', 'terminal_state', 'counterfactual_states')}
            comparison['arms'][arm].update(input_sha256=digest(path), report=name,
                                           report_sha256=hashlib.sha256(data).hexdigest())
            print(json.dumps({'seed': seed, 'position': own, 'arm': arm,
                              'exact': value['exact_post_states'], 'terminal': value['terminal']}), flush=True)
        causes = set()
        for arm in comparison['arms'].values():
            for values in arm['cash_by_cause']:
                causes.update(values)
        comparison['funded_minus_sell_cash_causes'] = {
            key: [comparison['arms']['funded']['cash_by_cause'][p].get(key, 0)
                  - comparison['arms']['sell']['cash_by_cause'][p].get(key, 0)
                  for p in (own, 1-own)] for key in sorted(causes)}
        results.append(comparison)
    receipt = {'engine_ref': ev.ENGINE_REF, 'engine_hashes': hashes,
               'driver_sha256': digest(Path(__file__)), 'cells': results}
    (out/'RESULTS.json').write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n')

if __name__ == '__main__':
    main()
