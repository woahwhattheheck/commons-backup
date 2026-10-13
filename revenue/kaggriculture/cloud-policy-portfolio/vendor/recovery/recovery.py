# SPDX-License-Identifier: Apache-2.0
"""Observed weed-disrupted planting recovery; no opponent or hidden-state inputs.

The frozen parent is called once. A same-day planting-only suffix may insert the
missed strawberry plant/water pair and omit its final wheat plant/water pair.
It never shifts a route across the daily reset. This is a measured policy
hypothesis, not a claim that current-price valuation predicts future receipts.
"""
from collections import Counter
from copy import deepcopy

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
TAIL_OPS = MOVES | {"PLANT", "WATER", "PASS"}


def units(action):
    return [list(action.get("farmer") or ["PASS"])] + [list(a) for a in action.get("hands", [])]


def replace_unit(action, unit, replacement):
    result = deepcopy(action)
    if unit == 0:
        result["farmer"] = list(replacement)
    else:
        hands = result.setdefault("hands", [])
        while len(hands) < unit:
            hands.append(["PASS"])
        hands[unit - 1] = list(replacement)
    return result


class RecoveryController:
    """Decorate an intact Agent; expose effective future rows only to SELL.

    ``base.R`` and its branch-prefix comparisons are never modified. ``R`` here
    is a projection used by SELL, so its stock/receipt simulation sees the same
    pending unit actions that this controller will actually emit.
    """
    def __init__(self, base, parent_module, mechanics, enabled=True):
        self.base = base
        self.parent_module = parent_module
        self.mechanics = mechanics
        self.enabled = enabled
        self.configuration = {}
        self.plan = None
        self.events = []
        self.calls = 0
        self._projected = None

    @property
    def cur(self):
        return self.base.cur

    @property
    def R(self):
        return self._projected if self._projected is not None else self.base.R

    def future_sells(self, item, step):
        return self.base.future_sells(item, step)

    def _clear(self):
        self.plan = None
        self._projected = None

    def _simulate(self, obs, route, start, end, unit, replacements=None):
        """Exact owned unit primitives, with atomic seed-demand accounting.

        Admitted windows have no market acquisitions and no hiring. Sales cannot
        change seeds or worker movement. This check is a feasibility comparison,
        not a market rollout. We require identical inventories and all unrelated
        tiles in both arms, so no hypothetical receipts are admitted as stock.
        """
        m = self.mechanics
        farm = deepcopy(obs["farms"][int(obs.get("player", 0))])
        private = deepcopy(obs["private"])
        day = start // 24
        positions = []
        blocked_events = []
        for step in range(start, end):
            actions = units(route[step])
            actors = [farm["farmer"]] + farm["hands"]
            for idx in range(min(len(actions), len(actors))):
                x, y = actors[idx]
                tile = farm["tiles"][y][x]
                inv = private["inventories"][idx]
                if (isinstance(tile, dict) and tile.get("kind") == "WEED"
                        and self.parent_module._noop(actions[idx], tile, inv,
                            private["seeds"], x, y, len(farm["tiles"]))):
                    actions[idx] = ["DIG"]
            if replacements is not None:
                actions[unit] = replacements[step - start]
            positions.append(list(actors[unit]))
            demand = Counter(a[1] for a in actions if len(a) > 1 and a[0] == "PLANT")
            blocked = {crop for crop, n in demand.items() if n > private["seeds"].get(crop, 0)}
            if blocked:
                blocked_events.append((step, sorted(blocked)))
            for idx, action in enumerate(actions):
                if len(action) > 1 and action[0] == "PLANT" and action[1] in blocked:
                    action = ["PASS"]
                m._apply_unit_action(farm, private, idx, action, len(farm["tiles"]),
                                     day, 24, int(self.configuration.get("shedCapacity", 100)))
            m._decay_plants(farm, step)
        return farm, private, positions, blocked_events

    def _proposal(self, obs, actual, step):
        cfg = self.configuration
        if int(cfg.get("turnsPerDay", 24)) != 24 or int(cfg.get("boardSize", 10)) != 10:
            return None
        route = self.base.R[self.cur]
        end = (step // 24 + 1) * 24
        if step + 4 >= end or end > len(route):
            return None
        # Never suppress an intact parent's compatible branch decision.
        if any(step < decision[0] < end for decision in self.parent_module.DECISIONS):
            return None
        last_day = (int(cfg.get("episodeSteps", 720)) - 2) // 24
        if step // 24 + 16 >= last_day:
            return None
        prices = obs["market"]["prices"]
        proxy_gain = 4 * prices.get("STRAWBERRY", 0) - 6 * prices.get("WHEAT", 0)
        if proxy_gain <= 0:
            return None
        # Acquisitions/hiring would require a different reservation model.
        for row in route[step:end]:
            if any(order and order[0] != "SELL" for order in row.get("market", [])):
                return None
        farm = obs["farms"][int(obs.get("player", 0))]
        current = units(actual)
        original = units(route[step])
        for unit, position in enumerate([farm["farmer"]] + farm["hands"]):
            if unit >= len(original) or original[unit] != ["PLANT", "STRAWBERRY"]:
                continue
            x, y = position
            tile = farm["tiles"][y][x]
            if not (isinstance(tile, dict) and tile.get("kind") == "WEED"
                    and unit < len(current) and current[unit] == ["DIG"]):
                continue
            tail = []
            for row in route[step:end]:
                actions = units(row)
                if unit >= len(actions):
                    break
                tail.append(actions[unit])
            if len(tail) != end - step or tail[1] != ["WATER"]:
                continue
            if tail[-2:] != [["PLANT", "WHEAT"], ["WATER"]]:
                continue
            if any(not a or a[0] not in TAIL_OPS for a in tail[1:]):
                continue
            proposed = [["DIG"], ["PLANT", "STRAWBERRY"], ["WATER"]] + tail[2:-2] + [["PASS"]]
            old_farm, old_private, old_positions, old_blocked = self._simulate(obs, route, step, end, unit)
            new_farm, new_private, positions, blocked = self._simulate(obs, route, step, end, unit, proposed)
            if blocked != old_blocked:
                continue
            omitted = old_positions[-2]
            ox, oy = omitted
            restored = new_farm["tiles"][y][x]
            displaced = old_farm["tiles"][oy][ox]
            if not (old_farm["tiles"][y][x] is None
                    and isinstance(restored, dict) and restored.get("crop") == "STRAWBERRY"
                    and restored.get("planted_day") == step // 24 and restored.get("watered_today")
                    and new_farm["tiles"][oy][ox] is None
                    and isinstance(displaced, dict) and displaced.get("crop") == "WHEAT"
                    and displaced.get("planted_day") == step // 24):
                continue
            # Only the intended two assets and their seed consumption may differ.
            compared = deepcopy(new_farm)
            compared["tiles"][y][x] = deepcopy(old_farm["tiles"][y][x])
            compared["tiles"][oy][ox] = deepcopy(old_farm["tiles"][oy][ox])
            normalized_private = deepcopy(new_private)
            normalized_private["seeds"]["STRAWBERRY"] = normalized_private["seeds"].get("STRAWBERRY", 0) + 1
            normalized_private["seeds"]["WHEAT"] = normalized_private["seeds"].get("WHEAT", 0) - 1
            if compared != old_farm or normalized_private != old_private:
                continue
            return dict(start=step, end=end, unit=unit, route=self.cur,
                        actions=proposed, positions=positions, source_tile=list(position),
                        omitted_tile=omitted, current_price_proxy_gain=proxy_gain,
                        fallback=False)
        return None

    def act(self, obs):
        self.calls += 1
        actual = self.base.act(obs)  # Exactly one authoritative parent call.
        step = int(obs.get("step", int(obs.get("day", 0)) * 24 + int(obs.get("hour", 0))))
        if self.plan and step >= self.plan["end"]:
            self._clear()
        if not self.enabled:
            return actual
        if self.plan is None:
            self.plan = self._proposal(obs, actual, step)
            if self.plan:
                self.events.append({k: deepcopy(v) for k, v in self.plan.items()
                                    if k not in ("actions", "positions", "fallback")})
                self._projected = dict(self.base.R)
                r = list(self.base.R[self.cur])
                for t in range(self.plan["start"], self.plan["end"]):
                    r[t] = replace_unit(r[t], self.plan["unit"], self.plan["actions"][t - self.plan["start"]])
                self._projected[self.cur] = r
        if self.plan:
            plan = self.plan
            offset = step - plan["start"]
            farm = obs["farms"][int(obs.get("player", 0))]
            actors = [farm["farmer"]] + farm["hands"]
            if (offset < 0 or offset >= len(plan["positions"]) or plan["unit"] >= len(actors)
                    or actors[plan["unit"]] != plan["positions"][offset] or self.cur != plan["route"]):
                # Do not jump into a displaced movement tape. Hold this actor only
                # until the observed daily reset, then resume from the real spawn.
                plan["fallback"] = True
            action = ["PASS"] if plan["fallback"] else plan["actions"][offset]
            if plan["fallback"]:
                r = self._projected[plan["route"]]
                for t in range(max(step, plan["start"]), plan["end"]):
                    r[t] = replace_unit(r[t], plan["unit"], ["PASS"])
            return replace_unit(actual, plan["unit"], action)
        return actual
