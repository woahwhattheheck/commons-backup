"""Conditional execution-preservation gate for seed-reduction proposals.

No controller/seed-demand inference. Supply authoritative post-unit own state
and named hypothetical rival market scenarios. This is not a universal guarantee.
"""
from __future__ import annotations

from copy import deepcopy
import math
from collections.abc import Mapping
from market_kernel import bind_market


class Struct(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("cash must be a finite number")
    if not math.isfinite(value) or value < 0:
        raise ValueError("cash must be finite and nonnegative")
    return value


def _physical(farm, private):
    return ({k: deepcopy(v) for k, v in farm.items() if k != "money"},
            {k: deepcopy(v) for k, v in private.items() if k != "seeds"})


def _seed_reductions(selected, proposed, crops):
    """Require identical unit actions and fixed-position non-seed orders."""
    if not isinstance(selected, Mapping) or not isinstance(proposed, Mapping):
        raise ValueError("actions must be mappings")
    if {k: v for k, v in selected.items() if k != "market"} != {
            k: v for k, v in proposed.items() if k != "market"}:
        raise ValueError("non-market actions changed")
    old, new = selected.get("market", []), proposed.get("market", [])
    if not isinstance(old, list) or not isinstance(new, list) or len(old) != len(new):
        raise ValueError("market slot positions changed")
    changed = set()
    for slot, (a, b) in enumerate(zip(old, new)):
        if a == b:
            continue
        if (not isinstance(a, list) or len(a) < 3 or a[0] != "BUY_SEED"
                or a[1] not in crops or type(a[2]) is not int or a[2] <= 0):
            raise ValueError("only valid seed purchases may change")
        if b == [] or b == ["PASS"]:
            quantity = 0
        elif (isinstance(b, list) and len(b) == len(a) and b[:2] == a[:2]
              and b[3:] == a[3:] and type(b[2]) is int):
            quantity = b[2]
        else:
            raise ValueError("changed seed order has invalid shape")
        if not 0 <= quantity <= a[2]:
            raise ValueError("proposal is not a seed reduction")
        changed.add(slot)
    return changed


class SeedExecutionGuard:
    """Return a copied proposal only if every supplied market scenario passes.

    `post_units` is ATLAS's packet['post_units'] for THIS selected unit stage.
    `scenarios` entries require name, rival_market, rival_shed_assumption and
    rival_cash_assumption. These are explicit hypotheses, not hidden observations.
    Current-turn fill/physical preservation does not validate future planting.
    """
    def __init__(self, mechanics, *, max_scenarios=8, max_order_units=10000):
        self.mechanics = mechanics
        self.process_market = bind_market(mechanics)
        self.max_scenarios = max_scenarios
        self.max_order_units = max_order_units
        self.last_report = {}

    def _state(self, obs, post_units, scenario, action):
        seat = obs["player"]
        if type(seat) is not int or seat not in (0, 1):
            raise ValueError("invalid player")
        if not isinstance(scenario["name"], str) or not scenario["name"].strip():
            raise ValueError("scenario needs a name")
        if not isinstance(scenario["rival_market"], list):
            raise ValueError("rival market must be explicit")
        farms = deepcopy(obs["farms"])
        if len(farms) != 2:
            raise ValueError("exactly two public farms required")
        farms[seat] = deepcopy(post_units["farm"])
        own = deepcopy(post_units["private"])
        _number(farms[seat]["money"])
        farms[1-seat]["money"] = _number(scenario["rival_cash_assumption"])
        shed = scenario["rival_shed_assumption"]
        allowed = set(self.mechanics.PRODUCTS) | set(self.mechanics.ANIMALS)
        if (not isinstance(shed, Mapping) or set(shed) - allowed
                or any(type(n) is not int or n < 0 for n in shed.values())):
            raise ValueError("invalid explicit rival shed hypothesis")
        rival = {"shed": dict(shed), "seeds": {},
                 "inventories": [{} for _ in range(len(farms[1-seat]["hands"])+1)]}
        market = deepcopy(obs["market"])
        private = [None, None]
        private[seat], private[1-seat] = own, rival
        queues = [None, None]
        queues[seat] = deepcopy(action.get("market", []))
        queues[1-seat] = deepcopy(scenario["rival_market"])
        state = [Struct(observation=Struct(farms=farms, market=market, private=p),
                        action={"market": []}) for p in private]
        return state, queues

    def project(self, obs, cfg, action, *, post_units, scenario):
        """Run exact ordered market slots on private copies; no unit execution."""
        state, queues = self._state(obs, post_units, scenario, action)
        seat = obs["player"]
        limit = max(1, int(cfg.get("maxMarketOrdersPerTurn", 10)))
        queues = [q[:limit] for q in queues]
        for q in queues:
            for order in q:
                if isinstance(order, list) and len(order) >= 3:
                    try:
                        quantity = int(order[2])
                    except (ValueError, TypeError, OverflowError):
                        quantity = 0  # The actual parser decides invalid orders.
                    if quantity > self.max_order_units:
                        raise ValueError("market projection exceeds unit budget")
        env = Struct(configuration=cfg)
        farms = state[0].observation.farms
        slots = []
        for slot in range(max(map(len, queues), default=0)):
            before = farms[seat]["money"]
            for player in (0, 1):
                state[player].action = {"market": queues[player][slot:slot+1]}
            self.process_market(state, env)
            slots.append({
                "slot": slot,
                "own_cash_delta": farms[seat]["money"] - before,
                "own_physical": _physical(farms[seat], state[seat].observation.private),
                "rival": deepcopy((farms[1-seat], state[1-seat].observation.private)),
                "market": deepcopy(state[0].observation.market),
            })
        return {"slots": slots, "own_cash": _number(farms[seat]["money"]),
                "farms": deepcopy(farms),
                "privates": [deepcopy(s.observation.private) for s in state],
                "market": deepcopy(state[0].observation.market)}

    def transform(self, obs, cfg, selected_action, proposed_action, *, post_units, scenarios):
        """Fail closed to the selected action, not to an invented PASS action."""
        fallback = deepcopy(selected_action)
        self.last_report = {"status": "fallback_unknown", "scenarios": []}
        try:
            changed = _seed_reductions(selected_action, proposed_action, self.mechanics.CROPS)
            if not changed:
                self.last_report["status"] = "unchanged"
                return fallback
            if (not isinstance(scenarios, (list, tuple))
                    or not 1 <= len(scenarios) <= self.max_scenarios):
                raise ValueError("bounded explicit scenario set required")
            names = [s["name"] for s in scenarios]
            if len(set(names)) != len(names):
                raise ValueError("scenario names must be unique")
            for scenario in scenarios:
                base = self.project(obs, cfg, selected_action, post_units=post_units, scenario=scenario)
                candidate = self.project(obs, cfg, proposed_action, post_units=post_units, scenario=scenario)
                mismatch = []
                for a, b in zip(base["slots"], candidate["slots"]):
                    for field in ("own_physical", "rival", "market"):
                        if a[field] != b[field]:
                            mismatch.append({"slot": a["slot"], "field": field})
                    if a["slot"] not in changed and a["own_cash_delta"] != b["own_cash_delta"]:
                        mismatch.append({"slot": a["slot"], "field": "own_cash_delta"})
                saving = candidate["own_cash"] - base["own_cash"]
                self.last_report["scenarios"].append({"name": scenario["name"],
                    "baseline_cash": base["own_cash"], "proposal_cash": candidate["own_cash"],
                    "cash_delta": saving, "mismatches": mismatch})
                if mismatch or saving < 0:
                    self.last_report["status"] = "fallback_changed_execution"
                    return fallback
            self.last_report["status"] = "preserved_on_supplied_scenarios"
            return deepcopy(proposed_action)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
            self.last_report["error_type"] = type(exc).__name__
            return fallback
