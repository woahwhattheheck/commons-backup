# SPDX-License-Identifier: Apache-2.0
"""Attribute retained development actions with exact engine market mechanics.

Offline only. Rival stock is reconstructed from recorded actions from step0,
never supplied to a runtime policy. Public random-boundary state stays observed.
"""
from collections import defaultdict
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime import load


def attribute(path):
    evaluator = load(ROOT / 'vendor/cloud-eval/evaluate.py', 't14_r2_ledger_eval')
    engine, _ = evaluator.get_engine(ROOT / 'vendor/engine')
    private = [engine._new_private(), engine._new_private()]
    ledger, cash_curve = [], []
    original_commit, original_hire, original_land = engine._commit_unit, engine._do_hire, engine._do_buy_land
    step = 0
    farms = None
    def record(farm, op, item, quantity, amount):
        ledger.append({'step': step, 'player': 0 if farm is farms[0] else 1,
                       'op': op, 'item': item, 'quantity': quantity, 'cash_delta': amount})
    def commit(op, item, price, farm, priv, market, capacity=100):
        before = farm['money']
        result = original_commit(op, item, price, farm, priv, market, capacity)
        if result:
            record(farm, op, item, 1, farm['money'] - before)
        return result
    def hire(farm, priv, board, mult=1):
        before = farm['money']
        result = original_hire(farm, priv, board, mult)
        if farm['money'] != before:
            record(farm, 'HIRE', None, 1, farm['money'] - before)
        return result
    def land(farm, board):
        before = farm['money']
        result = original_land(farm, board)
        if farm['money'] != before:
            record(farm, 'BUY_LAND', None, 1, farm['money'] - before)
        return result
    engine._commit_unit, engine._do_hire, engine._do_buy_land = commit, hire, land
    checked = 0
    with gzip.open(path, 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            step = row['step']
            obs = deepcopy(row['observation'])
            seat = row['candidate_seat']
            if private[seat] != obs['private']:
                raise ValueError(('Observed private state mismatch', step))
            farms = obs['farms']
            for player, action in enumerate(row['actions']):
                acts = [action.get('farmer', ['PASS']), *action.get('hands', [])]
                demand = defaultdict(int)
                for act in acts:
                    if len(act) > 1 and act[0] == 'PLANT':
                        demand[act[1]] += 1
                blocked = {p for p, q in demand.items() if q > private[player]['seeds'].get(p, 0)}
                for index, act in enumerate(acts):
                    if len(act) > 1 and act[0] == 'PLANT' and act[1] in blocked:
                        act = ['PASS']
                    engine._apply_unit_action(farms[player], private[player], index, act, 10, step // 24, 24, 100)
            state = [SimpleNamespace(action=row['actions'][i], observation=SimpleNamespace(
                         farms=farms, market=obs['market'], private=private[i])) for i in (0, 1)]
            engine._process_market(state, SimpleNamespace(configuration={}))
            actual = [f['money'] for f in farms]
            if actual != row['post_cash']:
                raise ValueError(('Recorded cash mismatch', step, actual, row['post_cash']))
            cash_curve.append({'step': step, 'cash': actual})
            if (step + 1) % 24 == 0:
                for priv in private:
                    engine._drop_inventories_to_shed(priv, 100)
                    priv['inventories'] = [{}]
            checked += 1
    totals = defaultdict(lambda: {'cash': 0, 'units': 0})
    for event in ledger:
        key = str(event['player']) + ':' + event['op'] + ':' + str(event['item'])
        totals[key]['cash'] += event['cash_delta']
        totals[key]['units'] += event['quantity']
    return {'trace': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'checked_transitions': checked, 'cash_residual': 0, 'totals': dict(totals),
            'cash_curve': cash_curve, 'events': ledger,
            'provenance': 'Retained DEVELOPMENT actions only; reconstructed rival stock is offline evidence, not runtime input.'}


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    report = attribute(a.trace)
    a.output.write_text(json.dumps(report, separators=(',', ':')) + '\n')
    print(json.dumps({k: report[k] for k in ('trace', 'checked_transitions', 'cash_residual', 'totals')}))
