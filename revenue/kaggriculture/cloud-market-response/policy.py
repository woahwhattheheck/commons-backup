# SPDX-License-Identifier: MIT
"""T12 causal market-response ablation over the unchanged frozen SELL runtime.

The default entrypoint is the research variant; it is NOT promoted over SELL.
One isolated scheduler module and one Arlene controller per actor/match.
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SELL = HERE.parent / 'cloud-titan-composition' / 'vendor' / 'sell'
FROZEN_SHA256 = '32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9'

def _with_public_clock(observation, configuration=None):
    """Retain an explicit step; otherwise derive it without mutating the caller."""
    if observation.get('step') is not None:
        return observation
    config = {} if configuration is None else configuration
    step = int(observation['day']) * int(config.get('turnsPerDay', 24)) + int(observation['hour'])
    return dict(observation, step=step)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

flow = load(HERE/'flow.py', 't12_flow')
sorrel = load(HERE/'vendor/sorrel_adapter.py', 't12_sorrel')


def frozen_module():
    path = SELL/'scheduler.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != FROZEN_SHA256:
        raise ValueError('Expected explicitly frozen SELL source; update the pin deliberately')
    prior = sys.modules.get('mechanics')
    mechanics = load(SELL/'mechanics.py', 't12_mechanics')
    sys.modules['mechanics'] = mechanics
    try:
        return load(path, 't12_scheduler_'+str(id(mechanics)))
    finally:
        if prior is None:
            sys.modules.pop('mechanics', None)
        else:
            sys.modules['mechanics'] = prior


class ResponsePolicy:
    def __init__(self, enabled=True):
        self.source = frozen_module()
        self.scheduler = self.source.SellScheduler()
        self.original_optimizer = self.source.optimize_lot
        self.source.optimize_lot = self.optimize
        self.enabled = enabled
        self.history = None
        self.previous = self.previous_sales = None
        self.observation = None
        self.calls = self.interventions = 0
        self.last_intervals = []
        self.last_predictions = {}
        self.last_changes = []

    def observe(self, observation, configuration):
        if self.history is None:
            self.history = flow.FlowHistory(configuration.get('turnsPerDay', 24))
        self.last_intervals = []
        if self.previous is not None:
            # Exact own non-operating fills are observable from post-unit shed
            # state. SORREL retains floor admission and buy/sell ambiguity.
            own = {p: self.previous_sales.get(p, 0) for p in self.source.PRODUCTS}
            receipt = sorrel.infer_rival_flow(
                self.previous, observation,
                [['SELL', p, q] for p, q in own.items() if q], configuration,
                quote=lambda p, i: self.source.m.market_price(p, i, self.previous['market'].get('params')),
                shops=self.source.m.SHOPS, center_products=self.source.m.TOWN_CENTER_PRODUCTS,
                own_sale_units=own)
            for item, r in receipt.get('products', {}).items():
                if item not in self.source.PRODUCTS or r['status'] != 'identified_interval':
                    continue
                lo, hi = r['rival_sale_units_range']
                a, b = r['rival_market_supply_units_range']
                reason = 'floor_censored' if r['floor_nonadmission_possible'] else 'identified'
                interval = flow.FlowInterval(int(self.previous['step']), item, lo, hi, a, b, reason)
                self.history.add(interval)
                self.last_intervals.append(interval.as_dict())
        now = int(observation['step'])
        self.last_predictions = {p: self.history.predict(p, now, now=now) for p in self.source.PRODUCTS}

    def optimize(self, **kwargs):
        frozen, info = self.original_optimizer(**kwargs)
        quantity = kwargs['quantity']
        # Receipt comparisons require an explicit complete sale plan, not a
        # virtual carry valuation at a planning boundary.
        if (not self.enabled or not info.get('feasible', False)
                or sum(q for _, q in frozen) != quantity):
            return frozen, info
        now, end = kwargs['now'], kwargs['dates'][-1]
        streams, prediction = self.history.scenarios(kwargs['item'], now, end, capacity=int(kwargs['config'].get('shedCapacity', 100)))
        if not streams:
            return frozen, info
        # Retain the seller's original stress cases in addition to learned paths.
        q = kwargs['rival_quantity']
        guard = [('no_rival', 0, 'paired'), ('standing_paired', q, 'paired'),
                 ('standing_after', q, 'after'), ('standing_before', q, 'before')]
        if end > now: guard.append(('standing_next', ((now+1, q),), 'paired'))
        if end > now+2: guard.append(('standing_end', ((end-1, q),), 'paired'))
        streams = guard+streams
        model = self.source.MarketPath(kwargs['item'], kwargs['inventory'], kwargs['params'],
                                      kwargs['shops'], kwargs['config'], now, end)
        reference = [model.score(frozen, quantity, r, a, True) for _, r, a in streams]
        plans = {tuple(frozen)}
        for first in range(kwargs['minimum_now'], quantity+1):
            for date in kwargs['dates'][1:]:
                plans.add(((now, first), (date, quantity-first)))
        best, key, best_scores = frozen, (0, 0, 0), reference
        for plan in sorted(plans):
            if kwargs['capacity_ok'] and not kwargs['capacity_ok'](plan):
                continue
            scores = [model.score(plan, quantity, r, a, True) for _, r, a in streams]
            deltas = [s[0]-b[0] for s, b in zip(scores, reference)]
            history = deltas[len(guard):]
            candidate = (min(history), sum(history), dict(plan).get(now, 0))
            if min(deltas) >= 0 and min(history) > 0 and candidate > key:
                best, key, best_scores = plan, candidate, scores
        if best == frozen:
            return frozen, info
        # Independently recompute the chosen vector using SORREL's exact queued
        # SELL scorer. All conditional stocks are bounded, no probabilities used.
        checked = self.confirm_receipts(kwargs, frozen, best, streams, reference, best_scores)
        info = dict(info)
        info['frozen_scenarios'] = info.pop('scenarios')
        info.update(plan=list(best), reference=list(frozen),
                    worst_relative_gain=key[0],
                    historical_response=True, prediction=prediction, frozen_plan=list(frozen),
                    response_worst_delta=min(s[0]-b[0] for s,b in zip(best_scores,reference)),
                    gain_scope='worst learned-history delta; original guards separately nonnegative', response_receipts=checked,
                    response_scenarios={name: {
                        'relative_delta': s[0]-b[0], 'own_receipts': s[1], 'rival_receipts': s[2],
                        'reference_own_receipts': b[1], 'reference_rival_receipts': b[2]}
                        for (name, _, _), b, s in zip(streams, reference, best_scores)})
        return best, info

    def confirm_receipts(self, k, frozen, chosen, streams, reference, scores):
        item, now, end = k['item'], k['now'], k['dates'][-1]
        vectors = []
        obs = {'step': now, 'market': {'inventory': {p: k['inventory'] if p == item else 10000 for p in self.source.m.PRODUCTS}},
               'town': {'unlocked_shops': k['shops']}}
        for (name, rival, alignment), b, c in zip(streams, reference, scores):
            stream = rival if isinstance(rival, tuple) else ((now, rival),)
            own_slot, rival_slot = (1, 0) if alignment == 'before' else (0, 1) if alignment == 'after' else (0, 0)
            def queue(plan, slot):
                return {t: [['PASS']]*slot+[['SELL', item, n]] for t, n in plan if n}
            scenario = {'id': name, 'initial_rival_stock': {item: sum(n for _,n in stream)},
                        'orders': queue(stream, rival_slot), 'arrivals': {}}
            result = sorrel.score_paired_plans(
                obs, k['config'], {item: k['quantity']}, queue(frozen, own_slot),
                queue(chosen, own_slot), {'scenarios': [scenario]}, end,
                quote=lambda p, inv: self.source.m.market_price(p, inv, k['params']),
                shops=self.source.m.SHOPS, center_products=self.source.m.TOWN_CENTER_PRODUCTS)
            row = result['evaluations'][0]
            assert row['baseline']['cash'] == [b[1], b[2]]
            assert row['candidate']['cash'] == [c[1], c[2]]
            vectors.append({key: row[key] for key in ('scenario', 'own_cash_receipt_delta',
                                                     'rival_cash_receipt_delta', 'game_cash_margin_delta')})
        return vectors

    def act(self, observation, configuration=None):
        config = dict(configuration or {})
        observation = _with_public_clock(observation, config)
        self.observe(observation, config)
        self.observation = observation
        self.calls += 1
        action = self.scheduler.act(observation, config)  # authoritative parent once
        chosen = self.scheduler.diagnostics.get('chosen', {})
        self.last_changes = [chosen] if chosen.get('historical_response') else []
        self.interventions += bool(self.last_changes)
        _, private = self.source.post_units(observation, action, config)
        available = dict(private['shed'])
        sales = {}
        for order in action.get('market', [])[:int(config.get('maxMarketOrdersPerTurn', 10))]:
            if order and order[0] == 'SELL' and len(order) >= 3 and order[1] in self.source.PRODUCTS:
                item = order[1]
                n = min(max(0, int(order[2])), max(0, available.get(item, 0)))
                available[item] = available.get(item, 0)-n
                sales[item] = sales.get(item, 0)+n
        self.previous, self.previous_sales = copy.deepcopy(observation), sales
        return action

_INSTANCE = None

def agent(observation, configuration=None):
    global _INSTANCE
    observation = _with_public_clock(observation, configuration)
    if _INSTANCE is None or int(observation['step']) == 0:
        _INSTANCE = ResponsePolicy()
    return _INSTANCE.act(observation, configuration)
