"""Offline exact-source tests and market receipts; never used by runtime detector."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import behavior


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load supplied Python source')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def source(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != behavior.SOURCE_SHA256:
        raise ValueError('Lonespear source differs from the declared revision')
    return load(path, 'iris_lonespear_source')


def source_orders(module, observation, actor, private):
    # Evaluation labels only. The runtime predictor never receives this private.
    farm = copy.deepcopy(observation['farms'][actor])
    survey = module._survey(farm['tiles'], observation['day'])
    return module._market_orders(copy.deepcopy(observation), farm, copy.deepcopy(private), survey, {})


def run_market(engine, observation, privates, actions, configuration=None):
    """Run the unmodified market once on copies; record BOTH actors' receipts."""
    obs = copy.deepcopy(observation)
    farms = obs['farms']
    private = copy.deepcopy(privates)
    original_commit, original_hire, original_land = engine._commit_unit, engine._do_hire, engine._do_buy_land
    receipts = []
    def player(farm):
        return 0 if farm is farms[0] else 1
    def commit(op, item, price, farm, priv, market, capacity=100):
        before = farm['money']
        ok = original_commit(op, item, price, farm, priv, market, capacity)
        receipts.append(dict(player=player(farm), op=op, item=item, quote=price,
                             filled=bool(ok), cash_delta=farm['money']-before))
        return ok
    def hire(farm, priv, board, mult=1):
        before, n = farm['money'], farm['hires_today']
        result = original_hire(farm, priv, board, mult)
        receipts.append(dict(player=player(farm), op='HIRE', item=None,
                             quote=engine._hire_cost(n, mult),
                             filled=farm['hires_today'] != n, cash_delta=farm['money']-before))
        return result
    def land(farm, board):
        before = farm['money']
        result = original_land(farm, board)
        receipts.append(dict(player=player(farm), op='BUY_LAND', item=None,
                             filled=farm['money'] != before, cash_delta=farm['money']-before))
        return result
    state = [SimpleNamespace(action=copy.deepcopy(actions[i]), observation=SimpleNamespace(
                 farms=farms, market=obs['market'], private=private[i])) for i in (0, 1)]
    try:
        engine._commit_unit, engine._do_hire, engine._do_buy_land = commit, hire, land
        engine._process_market(state, SimpleNamespace(configuration=configuration or {}))
    finally:
        engine._commit_unit, engine._do_hire, engine._do_buy_land = original_commit, original_hire, original_land
    before_cash = [observation['farms'][i]['money'] for i in (0, 1)]
    after_cash = [f['money'] for f in farms]
    for i in (0, 1):
        if sum(r['cash_delta'] for r in receipts if r['player'] == i) != after_cash[i]-before_cash[i]:
            raise ValueError('Market receipt cash does not reconcile')
    return dict(before_cash=before_cash, after_cash=after_cash, receipts=receipts,
                farms=farms, privates=private, market=obs['market'])
