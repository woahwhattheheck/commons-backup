"""Observation-only marginal hiring over an incumbent policy's actual shift.

Research policy, not a leaderboard submission. The pinned official interpreter
supplies unit, market, production, decay and overflow mechanics. A forecast
uses current visible shops and no opponent orders; it stops BEFORE unknown
next-day weed/shop draws. Cash estimates are conditional, not actual receipts.
"""
from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
PARENT_REF = "8329e78768906dc6e75ca3712e1690adc1ab2148"
# A schema-valid zero-quantity order: _parse_order returns None. Keeping the
# slot avoids shifting another player's lockstep trades when a hire is removed.
NO_ORDER = ["SELL", "WHEAT", 0]
DEFAULTS = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
            "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
            "farmHandCostMult": 1, "townShopSellInterval": 4,
            "townCenterSellInterval": 24}


class View(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    __setattr__ = dict.__setitem__


def hire_cost(hires_today: int, multiplier: int = 1) -> int:
    """Exact zero-indexed daily Fibonacci cost; zero-cost configurations work."""
    for name, value in (("hires_today", hires_today), ("multiplier", multiplier)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    a, b = 1, 1
    for _ in range(hires_today):
        a, b = b, a + b
    return multiplier * a


def _configuration(configuration: Mapping[str, Any] | None) -> View:
    cfg = View(DEFAULTS)
    if configuration:
        # The hidden episode seed is deliberately NOT copied or consulted.
        cfg.update({k: configuration[k] for k in DEFAULTS if k in configuration})
    for key, value in cfg.items():
        lower = 0 if key == "farmHandCostMult" else 1
        if isinstance(value, bool) or not isinstance(value, int) or value < lower:
            raise ValueError(f"invalid {key}")
    return cfg


def _step(obs: Mapping[str, Any], cfg: Mapping[str, Any]) -> int:
    return int(obs.get("step", int(obs.get("day", 0)) * cfg["turnsPerDay"]
                       + int(obs.get("hour", 0))))


def _clone_parent(parent: Any) -> Any:
    """Arlene's immutable decoded routes/cache are shared; route choice is not."""
    return copy.copy(parent)


@dataclass(frozen=True)
class Projection:
    estimated_cash: float
    minimum_cash: float
    productive_state: dict[str, Any]
    market_inventory: dict[str, Any]
    successful_hires: int
    hiring_outflow: float
    net_nonhire_outflow: float
    net_nonhire_inflow: float
    first_spawn_positions: tuple[tuple[int, int], ...]
    horizon_step: int
    final_cash_only: bool


def _own_state(engine: Any, obs: Mapping[str, Any]) -> tuple[list[View], int]:
    """Copy public farms and only OUR private data; never reconstruct a rival's."""
    farms = copy.deepcopy(obs["farms"])
    me = int(obs.get("player", 0))
    if me < 0 or me >= len(farms) or len(farms) != 2:
        raise ValueError("exactly two farms and a valid player are required")
    shared = {"farms": farms, "market": copy.deepcopy(obs["market"]),
              "town": copy.deepcopy(obs.get("town", {"unlocked_shops": []}))}
    states = []
    for index in range(2):
        private = copy.deepcopy(obs["private"]) if index == me else engine._new_private()
        states.append(View(observation=View(**shared, player=index, private=private),
                           action={"farmer": ["PASS"], "hands": [], "market": []}))
    return states, me


def _units(engine: Any, farm: dict, private: dict, action: dict, cfg: View,
           day: int) -> None:
    """Match interpreter's atomic PLANT rule, including nonexistent hand slots."""
    farmer = action.get("farmer", ["PASS"])
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        hands = []
    acts = [farmer, *hands]
    demand = Counter(a[1] for a in acts if isinstance(a, list)
                     and len(a) >= 2 and a[0] == "PLANT")
    blocked = {crop for crop, n in demand.items()
               if n > private.get("seeds", {}).get(crop, 0)}
    for idx, act in enumerate(acts):
        if (isinstance(act, list) and len(act) >= 2
                and act[0] == "PLANT" and act[1] in blocked):
            act = ["PASS"]
        engine._apply_unit_action(farm, private, idx, act, cfg.boardSize,
                                 day, cfg.turnsPerDay, cfg.shedCapacity)


def project_shift(engine: Any, observation: Mapping[str, Any], parent_after_call: Any,
                  first_action: Mapping[str, Any], configuration: Mapping[str, Any] | None = None
                  ) -> Projection:
    """Replay incumbent tasks through this day, or decision 718, whichever first.

    The parent is already advanced through the current call. Future actions come
    from its own source policy applied to projected OBSERVATIONS, not replays,
    held seeds, private rival inventory, or future provider information.
    """
    cfg = _configuration(configuration)
    states, me = _own_state(engine, observation)
    farm = states[me].observation.farms[me]
    private = states[me].observation.private
    parent = _clone_parent(parent_after_call)
    env = View(configuration=cfg)
    start = _step(observation, cfg)
    last = min((start // cfg.turnsPerDay + 1) * cfg.turnsPerDay - 1,
               cfg.episodeSteps - 2)
    if start < 0 or start > last:
        raise ValueError("observation is beyond the executable episode")
    minimum = float(farm["money"])
    hire_spend = purchase_spend = receipts = 0.0
    successful = 0
    first_spawns: tuple[tuple[int, int], ...] = ()
    for step in range(start, last + 1):
        day = step // cfg.turnsPerDay
        for state in states:
            state.observation.update(step=step, day=day, hour=step % cfg.turnsPerDay)
        action = (copy.deepcopy(dict(first_action)) if step == start
                  else parent.act(copy.deepcopy(states[me].observation)))
        states[me].action = action
        _units(engine, farm, private, action, cfg, day)
        money_before = float(farm["money"])
        before_hires = farm["hires_today"]
        before_hands = len(farm["hands"])
        # Use the real per-order/per-unit market, with an explicit zero-rival-
        # order scenario. No monkeypatching shared engine globals.
        engine._process_market(states, env)
        n = farm["hires_today"] - before_hires
        cost = sum(hire_cost(before_hires + i, cfg.farmHandCostMult) for i in range(n))
        hire_spend += cost
        successful += n
        if step == start:
            first_spawns = tuple(tuple(p) for p in farm["hands"][before_hands:])
        net = float(farm["money"]) - money_before + cost
        # These are NET non-hire flows, not gross trade ledger claims.
        receipts += max(0.0, net)
        purchase_spend += max(0.0, -net)
        minimum = min(minimum, float(farm["money"]))
        engine._town_consume(env, states, step)
        engine._decay_plants(farm, step)
        if (step + 1) % cfg.turnsPerDay == 0:
            # Deterministic production and ordered overflow precede comparison.
            # Stop before random weeds and unknown shop draws. They are NOT
            # replaced by knowledge of the held evaluation seed.
            engine._daily_refresh_plants(farm, day, cfg.turnsPerDay)
            engine._daily_refresh_animals(farm, day)
            engine._drop_inventories_to_shed(private, cfg.shedCapacity)
            farm["farmer"] = list(engine._default_spawn(cfg.boardSize))
            farm["hands"] = []
            farm["hires_today"] = 0
            private["inventories"] = [{}]
    productive = {"farm": {k: copy.deepcopy(v) for k, v in farm.items() if k != "money"},
                  "private": copy.deepcopy(private)}
    return Projection(float(farm["money"]), minimum, productive,
                      copy.deepcopy(states[0].observation.market["inventory"]),
                      successful, hire_spend, purchase_spend, receipts,
                      first_spawns, last, last == cfg.episodeSteps - 2)


def alternatives(action: Mapping[str, Any], max_orders: int, mode: str = "reserve"
                 ) -> list[tuple[str, dict[str, Any]]]:
    """Finite, value-evaluated candidates; no constant hand-count cap."""
    if mode not in ("reserve", "timed"):
        raise ValueError("mode must be reserve or timed")
    original = copy.deepcopy(dict(action))
    queue = original.get("market", [])
    if not isinstance(queue, list):
        return []
    slots = [i for i, q in enumerate(queue[:max_orders])
             if isinstance(q, list) and q and q[0] == "HIRE"]
    out = []
    for removed in range(1, len(slots) + 1):
        candidate = copy.deepcopy(original)
        for slot in slots[-removed:]:
            candidate["market"][slot] = NO_ORDER.copy()
        out.append((f"omit_hire_suffix_{removed}", candidate))
    if mode == "timed" and slots:
        active = copy.deepcopy(queue[:max_orders])
        ordered = [q for q in active if not (isinstance(q, list) and q and q[0] == "HIRE")]
        ordered += [active[i] for i in slots]
        if ordered != active:
            candidate = copy.deepcopy(original)
            candidate["market"] = ordered + copy.deepcopy(queue[max_orders:])
            out.append(("fund_nonhire_orders_first", candidate))
    return out


def choose_projection(control: Projection, candidates: Sequence[tuple[str, Projection]],
                      epsilon: float = 1e-9) -> str | None:
    """Require cash improvement without displacing productive/input state.

    Before the final decision, identical farm, seed, inventory and market state
    is required: the oracle does not price unknown future care or production as
    zero. At the final boundary, only realized projected cash is worth anything.
    This conservative first mechanism can reject potentially good alternatives;
    it does not conclude their underlying ideas cannot work.
    """
    best, best_cash = None, control.estimated_cash
    for name, result in candidates:
        if result.horizon_step != control.horizon_step or result.final_cash_only != control.final_cash_only:
            continue
        if not math.isfinite(result.estimated_cash):
            continue
        if not control.final_cash_only and (
            result.productive_state != control.productive_state
            or result.market_inventory != control.market_inventory
        ):
            continue
        if result.estimated_cash > best_cash + epsilon:
            best, best_cash = name, result.estimated_cash
    return best


class HiringAgent:
    """Compose with an intact Arlene Agent and a pinned official engine module."""
    def __init__(self, parent: Any, engine: Any, *, mode: str = "reserve",
                 configuration: Mapping[str, Any] | None = None):
        self.parent, self.engine = parent, engine
        self.configuration = _configuration(configuration)
        if mode not in ("reserve", "timed"):
            raise ValueError("mode must be reserve or timed")
        self.mode = mode
        self.last_decision: dict[str, Any] = {}
        self.counts = Counter()

    def act(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        baseline = self.parent.act(observation)
        options = alternatives(baseline, self.configuration.maxMarketOrdersPerTurn, self.mode)
        self.last_decision = {"selected": "baseline", "evaluated": 0}
        if not options:
            return baseline
        control = project_shift(self.engine, observation, self.parent, baseline, self.configuration)
        rows = [(name, project_shift(self.engine, observation, self.parent, action, self.configuration))
                for name, action in options]
        selected = choose_projection(control, rows)
        self.last_decision = {"selected": selected or "baseline", "evaluated": len(rows),
                              "control_cash": control.estimated_cash,
                              "candidate_cash": {name: p.estimated_cash for name, p in rows},
                              "horizon_step": control.horizon_step,
                              "scenario": "current visible shops; zero rival orders"}
        self.counts[self.last_decision["selected"]] += 1
        return next(action for name, action in options if name == selected) if selected else baseline
