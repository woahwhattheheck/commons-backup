"""Bounded terminal shed-admission search over supplied actions and engine primitives.

No controller is constructed or called by ``optimize_terminal_admission``.
RivalScenario contains a hypothesis about *post-unit* stock and orders, never
an assertion that the opponent's private inventory is observable. Guarantees
in the report apply only to the explicitly supplied, complete sale scenarios.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import math
import time
from typing import Any, Callable, Mapping, Sequence


class _Record(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


@dataclass(frozen=True)
class RivalScenario:
    """Caller-supplied possible rival terminal sales; not a probability model."""
    name: str
    shed: Mapping[str, int]
    market: Sequence[Sequence[Any]]
    provenance: str


@dataclass
class _Node:
    farm: dict
    private: dict
    units: list
    farm_key: str = ""


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _units(action: Mapping[str, Any]) -> list:
    return [copy.deepcopy(action.get('farmer', ['PASS'])),
            *copy.deepcopy(action.get('hands', []))]


def _action(selected: Mapping[str, Any], units: list) -> dict:
    result = copy.deepcopy(dict(selected))
    result['farmer'], result['hands'] = units[0], units[1:]
    return result


def _apply(engine: Any, node: _Node, idx: int, unit: list,
           config: Mapping[str, Any], step: int, blocked: set) -> _Node:
    # Storage actions cannot mutate the farm. Keep that exact immutable object
    # while copying the private ledgers the engine is allowed to mutate.
    storage = (isinstance(unit, list) and bool(unit) and
               (unit[0] in ('PASS', 'DROP', 'PICKUP') or
                (unit[0] == 'PLACE' and len(unit) > 1 and unit[1] in engine.PRODUCTS)))
    farm = node.farm if storage else copy.deepcopy(node.farm)
    private = copy.deepcopy(node.private)
    actual = (['PASS'] if isinstance(unit, list) and len(unit) >= 2 and unit[0] == 'PLANT'
              and unit[1] in blocked else unit)
    engine._apply_unit_action(farm, private, idx, actual,
                             int(config.get('boardSize', 10)),
                             step // int(config.get('turnsPerDay', 24)),
                             int(config.get('turnsPerDay', 24)),
                             int(config.get('shedCapacity', 100)))
    farm_key = node.farm_key if storage else json.dumps(farm, separators=(',', ':'))
    return _Node(farm, private, node.units + [copy.deepcopy(unit)], farm_key)


def _choices(engine: Any, node: _Node, idx: int, original: list,
             config: Mapping[str, Any]) -> list:
    """Exact order/quantity alternatives for adjacent storage-only actions."""
    board = int(config.get('boardSize', 10))
    pos = engine._farmer_position(node.farm, idx)
    op = original[0] if isinstance(original, list) and original else None
    products = set(engine.PRODUCTS)
    if pos is None or not engine._is_shed_adjacent(pos, board):
        return [original], False
    if op not in ('PASS', 'DROP', 'PLACE', 'PICKUP'):
        return [original], False
    if op in ('PLACE', 'PICKUP') and (len(original) < 2 or original[1] not in products):
        return [original], False  # Animal placement and other production stay intact.
    inv = node.private['inventories'][idx]
    capacity = int(config.get('shedCapacity', 100))
    options = [original, ['PASS'], ['DROP']]
    future = []
    for other in node.private['inventories'][idx+1:]:
        future.append(sum(max(0,int(n)) for p,n in other.items() if p in products))
    room = max(0,capacity-sum(node.private['shed'].values()))
    # Large lots use explicit capacity/arrival breakpoints. Small cases retain
    # every integer quantity; the caller records sampling, never an optimum.
    sampled = False
    def quantities(maximum, pickup):
        nonlocal sampled
        if maximum <= 16:
            return range(1,maximum+1)
        sampled = True
        cumulative = 0
        points = {1,maximum}
        for qty in future:
            cumulative += qty
            for need in (qty,cumulative):
                point = need-room if pickup else room-need
                if 1 <= point <= maximum: points.add(point)
        return sorted(points)
    for item in engine.PRODUCTS:
        options.extend(['PLACE', item, n] for n in
                       quantities(min(capacity,int(inv.get(item,0))),False))
        options.extend(['PICKUP', item, n] for n in
                       quantities(min(capacity,int(node.private['shed'].get(item,0))),True))
    unique = {}
    for option in options:
        unique.setdefault(json.dumps(option, separators=(',', ':')), option)
    return list(unique.values()), sampled


def _state_key(node: _Node) -> str:
    # Do not sort inventory keys: DROP's iteration order is consequential.
    private = dict(node.private)
    # A worker acts only once this turn. Its completed inventory cannot feed a
    # later worker or this market, and there is no later market after terminal.
    private['inventories'] = node.private['inventories'][len(node.units):]
    return node.farm_key + json.dumps(private, separators=(',', ':'))


def _liquidate(engine: Any, selected: Mapping[str, Any], node: _Node,
               config: Mapping[str, Any]) -> dict:
    """Keep existing slots; fill each product's first SELL and append missing ones."""
    action = _action(selected, node.units)
    limit = max(1, int(config.get('maxMarketOrdersPerTurn', 10)))
    queue = copy.deepcopy(list(selected.get('market', []))[:limit])
    seen = set()
    for index, order in enumerate(queue):
        if isinstance(order, list) and len(order) >= 3 and order[0] == 'SELL' and order[1] in engine.PRODUCTS:
            # Slots are separate execution occurrences, even when the caller
            # reuses one order list. Detach before sizing or zeroing a SELL.
            order = copy.deepcopy(order)
            queue[index] = order
            item = order[1]
            order[2] = max(0, int(node.private['shed'].get(item, 0))) if item not in seen else 0
            seen.add(item)
    for item in engine.PRODUCTS:
        qty = max(0, int(node.private['shed'].get(item, 0)))
        if qty and item not in seen and len(queue) < limit:
            queue.append(['SELL', item, qty])
            seen.add(item)
    action['market'] = queue
    return action


def _validate_scenarios(engine: Any, scenarios: Sequence[RivalScenario],
                        config: Mapping[str, Any]) -> None:
    capacity = int(config.get('shedCapacity', 100))
    limit = max(1, int(config.get('maxMarketOrdersPerTurn', 10)))
    names = set()
    for scenario in scenarios:
        if not scenario.name or scenario.name in names or not scenario.provenance:
            raise ValueError('Each scenario needs a unique name and explicit provenance')
        names.add(scenario.name)
        total = 0
        for item, n in scenario.shed.items():
            if item not in engine.PRODUCTS:
                raise ValueError('Sale scenarios contain only engine products')
            total += _integer(n, 'scenario stock')
        if total > capacity:
            raise ValueError('Scenario post-unit stock exceeds shed capacity')
        if len(scenario.market) > limit:
            raise ValueError('Scenario orders exceed the configured market limit')
        for order in scenario.market:
            if not isinstance(order, (list, tuple)) or len(order) != 3 or order[0] != 'SELL' or order[1] not in engine.PRODUCTS:
                raise ValueError('This component models complete SELL-only rival queues')
            _integer(order[2], 'scenario sale quantity')


def market_receipts(engine: Any, observation: Mapping[str, Any],
                    config: Mapping[str, Any], node: _Node, action: Mapping[str, Any],
                    scenario: RivalScenario) -> tuple[int, int]:
    """Execute the existing exact paired market; never mutate caller state."""
    player = int(observation['player'])
    farms = copy.deepcopy(observation['farms'])
    farms[player] = copy.deepcopy(node.farm)
    market = copy.deepcopy(observation['market'])
    private = [None, None]
    private[player] = copy.deepcopy(node.private)
    rival = 1 - player
    private[rival] = {'shed': dict(scenario.shed), 'seeds': {},
                      'inventories': [{} for _ in range(1 + len(farms[rival]['hands']))]}
    orders = [None, None]
    orders[player] = copy.deepcopy(dict(action))
    orders[rival] = {'market': [list(o) for o in scenario.market]}
    before = [farm['money'] for farm in farms]
    states = [_Record(observation=_Record(farms=farms, market=market, private=private[i]),
                      action=orders[i]) for i in range(2)]
    engine._process_market(states, _Record(configuration=_Record(config)))
    return (int(farms[player]['money'] - before[player]),
            int(farms[rival]['money'] - before[rival]))


def optimize_terminal_admission(
        engine: Any, observation: Mapping[str, Any], config: Mapping[str, Any],
        selected_action: Mapping[str, Any], scenarios: Sequence[RivalScenario], *,
        max_states: int = 32, max_candidates: int = 32,
        time_budget_s: float = 0.15) -> tuple[dict, dict]:
    """Search terminal storage-only worker choices, then compare exact receipts.

    ``engine`` is the already-loaded pinned engine (or compatible extracted
    primitives), not a simulator installed or constructed here. Search may be
    truncated; it never reports global optimality after a truncation. Promotion
    requires strictly better own-minus-rival receipts than BOTH the supplied
    complete action and the same-workers liquidation control in every supplied
    scenario. The deadline is cooperative, not a hard interruption mechanism.
    """
    original = copy.deepcopy(dict(selected_action))
    report = {'changed': False, 'reason': 'nonterminal', 'complete_search': False,
              'scenario_scope': 'caller-supplied sale-only hypotheses; no calibrated probabilities',
              'nodes_expanded': 0, 'candidates_scored': 0}
    step = int(observation['step'])
    if step != int(config.get('episodeSteps', 720)) - 2:
        return original, report
    _integer(max_states, 'max_states', 1)
    _integer(max_candidates, 'max_candidates', 1)
    if not math.isfinite(time_budget_s) or time_budget_s <= 0:
        raise ValueError('time_budget_s must be finite and positive')
    if not scenarios:
        report['reason'] = 'no_explicit_rival_scenarios'
        return original, report
    _validate_scenarios(engine, scenarios, config)
    # Preserve economically active non-SELL queues; this is not a purchase optimizer.
    for order in original.get('market', []):
        if not isinstance(order, list) or not order:
            continue
        if order[0] in ('HIRE', 'BUY_LAND') or (isinstance(order[0], str) and order[0].startswith('BUY_') and len(order) > 2 and int(order[2]) > 0):
            report['reason'] = 'active_non_sale_order'
            return original, report
    start = time.perf_counter()
    deadline = start + time_budget_s
    player = int(observation['player'])
    initial = _Node(copy.deepcopy(observation['farms'][player]),
                    copy.deepcopy(observation['private']), [])
    initial.farm_key = json.dumps(initial.farm, separators=(',', ':'))
    units = _units(original)
    # This consumer only optimizes capacity competition. With enough space for
    # every currently carried item plus the shed, it preserves the parent and
    # avoids manufacturing a mere liquidation change. This sufficient fast
    # path is conservative: even inaccessible carry is included in the bound.
    stock_bound = sum(max(0,int(n)) for n in initial.private['shed'].values()) + sum(
        max(0,int(n)) for inv in initial.private['inventories'] for n in inv.values())
    if stock_bound <= int(config.get('shedCapacity',100)):
        report.update(reason='no_capacity_pressure',stock_upper_bound=stock_bound,
                      elapsed_s=time.perf_counter()-start,
                      search_truncated=False,budget_exhausted=False,
                      baseline_post_unit_shed=None,selected_post_unit_shed=None)
        return original, report
    demand = {}
    for unit in units:
        if isinstance(unit, list) and len(unit) > 1 and unit[0] == 'PLANT':
            demand[unit[1]] = demand.get(unit[1], 0) + 1
    blocked = {item for item, n in demand.items() if n > initial.private['seeds'].get(item, 0)}
    baseline = initial
    for idx, unit in enumerate(units):
        baseline = _apply(engine, baseline, idx, unit, config, step, blocked)
    control = _liquidate(engine, original, baseline, config)
    old_scores = [market_receipts(engine, observation, config, baseline, original, s) for s in scenarios]
    control_scores = [market_receipts(engine, observation, config, baseline, control, s) for s in scenarios]
    # The heuristic only orders/prunes candidates. Exact market receipts choose the action.
    prices = {p: engine.market_price(p, observation['market']['inventory'][p],
                                    observation['market'].get('params')) for p in engine.PRODUCTS}
    def heuristic(node: _Node) -> int:
        # Give cleared space its potential later-worker value; otherwise a
        # PICKUP prefix disappears before the subsequent profitable deposit.
        shed = node.private['shed']
        value = sum(max(0, int(n)) * prices.get(item, 0) for item, n in shed.items())
        room = max(0, int(config.get('shedCapacity',100))-sum(shed.values()))
        future = []
        for idx in range(len(node.units), len(units)):
            pos = engine._farmer_position(node.farm, idx)
            if pos is not None and engine._is_shed_adjacent(pos,int(config.get('boardSize',10))):
                future.extend((prices.get(p,0),int(n)) for p,n in
                              node.private['inventories'][idx].items() if p in engine.PRODUCTS)
        for price, qty in sorted(future, reverse=True):
            added = min(room,max(0,qty))
            value += price*added
            room -= added
        return value
    frontier = [initial]
    truncated = False
    exhausted = False
    for idx, unit in enumerate(units):
        next_nodes = {}
        for node in frontier:
            options, quantity_sampled = _choices(engine, node, idx, unit, config)
            truncated |= quantity_sampled
            for option in options:
                if time.perf_counter() >= deadline:
                    exhausted = True
                    break
                child = _apply(engine, node, idx, option, config, step, blocked)
                report['nodes_expanded'] += 1
                next_nodes.setdefault(_state_key(child), child)
            if exhausted:
                break
        if exhausted:
            # No further engine work after the cooperative budget expires.
            frontier = []
            break
        ordered = sorted(next_nodes.values(), key=heuristic, reverse=True)
        truncated |= len(ordered) > max_states
        frontier = ordered[:max_states]
    candidates = sorted(frontier, key=heuristic, reverse=True)
    truncated |= len(candidates) > max_candidates
    best = original
    best_node = baseline
    best_scores = old_scores
    best_key = (0, 0)
    for node in candidates[:max_candidates]:
        if time.perf_counter() >= deadline:
            exhausted = True
            break
        action = _liquidate(engine, original, node, config)
        scores = [market_receipts(engine, observation, config, node, action, s) for s in scenarios]
        report['candidates_scored'] += 1
        vs_old = [(a-b) - (x-y) for (a,b),(x,y) in zip(scores,old_scores)]
        vs_control = [(a-b) - (x-y) for (a,b),(x,y) in zip(scores,control_scores)]
        key = (min(vs_old + vs_control), sum(vs_control))
        if key[0] > 0 and key > best_key:
            best, best_node, best_scores, best_key = action, node, scores, key
    report.update(changed=best != original,
                  reason='admission_improvement' if best != original else 'no_strict_admission_improvement',
                  complete_search=not truncated and not exhausted,
                  search_truncated=truncated, budget_exhausted=exhausted,
                  elapsed_s=time.perf_counter()-start,
                  baseline_post_unit_shed=baseline.private['shed'],
                  selected_post_unit_shed=best_node.private['shed'],
                  same_workers_liquidation_action=control,
                  scenarios=[{'name':s.name,'provenance':s.provenance,
                              'original_own':a,'original_rival':b,
                              'control_own':c,'control_rival':d,
                              'selected_own':e,'selected_rival':f,
                              'margin_gain_vs_original':(e-f)-(a-b),
                              'margin_gain_vs_liquidation':(e-f)-(c-d)}
                             for s,(a,b),(c,d),(e,f) in zip(scenarios,old_scores,control_scores,best_scores)])
    return best, report


class TerminalAdmissionAgent:
    """Optional one-call consumer; nonterminal play is exactly the supplied agent."""
    def __init__(self, producer: Callable, engine: Any, scenario_model: Callable, **search_options: Any):
        self.producer, self.engine, self.scenario_model = producer, engine, scenario_model
        self.search_options = search_options
        self.last_report = None

    def act(self, observation: Mapping[str, Any],
            config: Mapping[str, Any] | None = None) -> dict:
        # Preserve the supplied parent's invocation/input contract. Normalize
        # only the detached admission view, after the single original call.
        selected = self.producer(observation, config)
        # Preserve the existing callback's Mapping implementation and identity;
        # structured configurations may also expose attribute-style access.
        cfg = config if config is not None else {}
        step = observation.get('step')
        if step is None:
            step = (int(observation['day']) * int(cfg.get('turnsPerDay', 24))
                    + int(observation['hour']))
        step = int(step)
        if step != int(cfg.get('episodeSteps', 720)) - 2:
            self.last_report = {'changed':False,'reason':'nonterminal'}
            return selected
        normalized = dict(observation)
        normalized['step'] = step
        scenarios = self.scenario_model(normalized, cfg)
        action, self.last_report = optimize_terminal_admission(
            self.engine, normalized, cfg, selected, scenarios, **self.search_options)
        return action
