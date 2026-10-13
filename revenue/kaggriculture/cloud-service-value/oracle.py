"""Observation-only, exact-mechanics action-bundle cash oracle for TITAN T04.

Inject the pinned official kaggriculture module. Unknown rival trades, new shops,
and weed spawns are explicit scenario inputs, never an environment seed. This is
conditional cash valuation, not a claim to predict unobserved future outcomes.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Mapping

Action = dict[str, Any]
Plan = Mapping[int, Action] | Callable[[dict[str, Any]], Action]


class Record(dict):
    """The engine accepts mappings with attribute access at the outer boundary."""
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


@dataclass(frozen=True)
class Scenario:
    # Net external inventory movement immediately before our market action.
    # Simultaneous lockstep rival trading requires a richer two-player model.
    market_deltas: Mapping[int, Mapping[str, int]] = field(default_factory=dict)
    # New shops/weed coordinates are inserted only at their specified EOD step.
    new_shops: Mapping[int, tuple[str, ...]] = field(default_factory=dict)
    new_weeds: Mapping[int, tuple[tuple[int, int], ...]] = field(default_factory=dict)
    label: str = "known shops only; no rival trades, new shops, or new weeds"


def _configuration(configuration: Mapping[str, Any]) -> SimpleNamespace:
    values = dict(boardSize=10, turnsPerDay=24, episodeSteps=720,
                  shedCapacity=100, maxMarketOrdersPerTurn=10,
                  farmHandCostMult=1, townShopSellInterval=4,
                  townCenterSellInterval=24)
    values.update(dict(configuration))
    cfg = SimpleNamespace(**values)
    if int(cfg.turnsPerDay) < 1 or int(cfg.episodeSteps) < 2:
        raise ValueError("Invalid episode duration")
    return cfg


def _discarded(before: dict, after: dict) -> Counter:
    """Infer overflow only across a pure DROP or EOD deposit operation."""
    moved = Counter()
    for inv in before["inventories"]:
        moved.update({k: max(0, v) for k, v in inv.items()})
    for inv in after["inventories"]:
        moved.subtract({k: max(0, v) for k, v in inv.items()})
    for item in set(before["shed"]) | set(after["shed"]):
        moved[item] -= after["shed"].get(item, 0) - before["shed"].get(item, 0)
    return Counter({k: v for k, v in moved.items() if v > 0})


def simulate_bundle(engine: Any, observation: Mapping[str, Any],
                    configuration: Mapping[str, Any], plan: Plan, *,
                    end_step: int, scenario: Scenario | None = None,
                    record_actions: bool = False) -> dict:
    """Replay a joint own-worker plan using official unit/market/production code.

    Mapping plans default to PASS at omitted decisions. A callable receives an
    independent full observation, with rival farms frozen at their observed
    state. All our workers, carried inventories, real movement, input ordering,
    shed overflow, quote rounding, finite crop output, decay, daily resets and
    the final decision boundary are executed. No terminal stock liquidation is
    invented. The caller must supply a pinned, trusted engine module.
    """
    cfg = _configuration(configuration)
    start = int(observation.get("step", 0))
    last = int(cfg.episodeSteps) - 2
    if not start <= end_step <= last:
        raise ValueError(f"Require {start} <= end_step <= final decision {last}")
    scenario = scenario or Scenario()
    player = int(observation["player"])
    view = deepcopy(dict(observation))
    farm = deepcopy(view["farms"][player])
    private = deepcopy(view["private"])
    market, town = deepcopy(view["market"]), deepcopy(view["town"])
    # Only own private state exists here. No opponent private state is fabricated.
    obs = Record(farms=[farm], private=private, market=market, town=town,
                 player=0, day=start // cfg.turnsPerDay,
                 hour=start % cfg.turnsPerDay, step=start)
    state = [Record(observation=obs, action={}, status="ACTIVE", reward=0)]
    env = SimpleNamespace(configuration=cfg)
    initial_cash = farm["money"]
    ledger, consumed, discarded = [], Counter(), Counter()
    actions = {}
    labor = 0
    for step in range(start, end_step + 1):
        day = step // cfg.turnsPerDay
        view["farms"][player], view["private"] = farm, private
        view.update(market=market, town=town, step=step,
                    day=day, hour=step % cfg.turnsPerDay)
        action = plan(deepcopy(view)) if callable(plan) else plan.get(step, {})
        action = deepcopy(action) if isinstance(action, dict) else {}
        if record_actions:
            actions[step] = deepcopy(action)
        hands = action.get("hands", [])
        hands = hands if isinstance(hands, list) else []
        units = [action.get("farmer", ["PASS"]), *hands]
        demand = Counter(a[1] for a in units
                         if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT")
        blocked = {crop for crop, n in demand.items()
                   if n > private.get("seeds", {}).get(crop, 0)}
        for idx, unit in enumerate(units):
            if engine._farmer_position(farm, idx) is None:
                continue
            if isinstance(unit, list) and len(unit) >= 2 and unit[0] == "PLANT" and unit[1] in blocked:
                unit = ["PASS"]
            op = unit[0] if isinstance(unit, list) and unit else "PASS"
            labor += int(op != "PASS")
            before = deepcopy(private) if op == "DROP" else None
            inv = engine._farmer_inventory(private, idx)
            resource = {"FEED": "WHEAT", "FERTILIZE": "FERTILIZER"}.get(op)
            available = inv.get(resource, 0) if resource else 0
            engine._apply_unit_action(farm, private, idx, unit, cfg.boardSize,
                                      day, cfg.turnsPerDay, cfg.shedCapacity)
            if resource:
                used = available - engine._farmer_inventory(private, idx).get(resource, 0)
                if used > 0:
                    consumed[resource] += used
            if before is not None:
                discarded.update(_discarded(before, private))
        for item, delta in scenario.market_deltas.get(step, {}).items():
            market["inventory"][item] += delta
        engine._refresh_prices(market)
        before_cash, before_shed = farm["money"], dict(private["shed"])
        state[0].action = action
        obs.step, obs.day, obs.hour = step, day, step % cfg.turnsPerDay
        engine._process_market(state, env)
        cash = farm["money"] - before_cash
        net_stock = {k: private["shed"].get(k, 0) - before_shed.get(k, 0)
                     for k in set(private["shed"]) | set(before_shed)
                     if private["shed"].get(k, 0) != before_shed.get(k, 0)}
        if cash or net_stock:
            ledger.append(dict(step=step, cash_delta=cash, shed_delta=net_stock))
        engine._town_consume(env, state, step)
        engine._decay_plants(farm, step)
        if (step + 1) % cfg.turnsPerDay == 0:
            engine._daily_refresh_plants(farm, day, cfg.turnsPerDay)
            engine._daily_refresh_animals(farm, day)
            for x, y in scenario.new_weeds.get(step, ()):
                if farm["tiles"][y][x] is None:
                    farm["tiles"][y][x] = {"kind": "WEED"}
            before = deepcopy(private)
            engine._drop_inventories_to_shed(private, cfg.shedCapacity)
            discarded.update(_discarded(before, private))
            farm["farmer"] = list(engine._default_spawn(cfg.boardSize))
            farm["hands"], farm["hires_today"] = [], 0
            private["inventories"] = [{}]
            town.setdefault("unlocked_shops", []).extend(scenario.new_shops.get(step, ()))
    return dict(start_step=start, end_step=end_step,
                cash_gain=farm["money"] - initial_cash, cash_ledger=ledger, actions=actions,
                consumed_inputs=dict(consumed), discarded_stock=dict(discarded),
                labor_actions=labor, farm=farm, private=private, market=market,
                town=town, scenario=scenario.label,
                scope="exact own-worker mechanics conditional on specified exogenous scenario; not simultaneous rival lockstep")


def value_bundle(engine: Any, observation: Mapping[str, Any],
                 configuration: Mapping[str, Any], control: Plan, candidate: Plan,
                 *, end_step: int, scenario: Scenario | None = None,
                 labor_unit_cost: float = 0,
                 control_unpriced_opportunity_cost: float = 0,
                 candidate_unpriced_opportunity_cost: float = 0) -> dict:
    """Value dated incremental cash, including real paid inputs and displacement.

    Optional shadow costs cover ONLY costs not already reflected in purchases,
    control sales, capacity displacement or the cash ledger; do not count them
    twice. Unsold held/carried/deposited stock has zero terminal cash value.
    """
    a = simulate_bundle(engine, observation, configuration, control,
                        end_step=end_step, scenario=scenario)
    b = simulate_bundle(engine, observation, configuration, candidate,
                        end_step=end_step, scenario=scenario)
    cash = b["cash_gain"] - a["cash_gain"]
    labor = labor_unit_cost * (b["labor_actions"] - a["labor_actions"])
    other = candidate_unpriced_opportunity_cost - control_unpriced_opportunity_cost
    return dict(incremental_cash=cash, labor_opportunity_cost=labor,
                other_opportunity_cost=other, value=cash - labor - other,
                control=a, candidate=b)
