# SPDX-License-Identifier: Apache-2.0
"""Observable, one-unit economic transform. No production controller or forecast.

The default is a bounded research candidate, not the selected TITAN policy.
It preserves every supplied unit action and declines occupied market queues.
Only own immediate cash/inventory restoration is guaranteed by its conditions;
subsequent opponent affordability and full-game W/T/L need paired measurement.
"""
from copy import deepcopy

from market_math import MARKET_PARAMS, market_price


class LiquidityCycle:
    def __init__(self, *, require_flat=True):
        self.require_flat = require_flat
        self.calls = 0
        self.overrides = 0
        self.last_decision = {"reason": "not_called"}

    def transform(self, observation, configuration, base_action, *, reservations=None):
        """Return a copied action. All inputs are current observable values.

        reservations: optional {'market_slots': [indices], 'stock': {item: n}}.
        Reserved operating stock is excluded even though a successful cycle
        restores its unit in the same market phase. Cash is never borrowed.
        The parent is called by the caller exactly once, before this method.
        """
        self.calls += 1
        result = deepcopy(base_action)
        self.last_decision = {"reason": "no_condition"}
        cfg = configuration or {}
        reserve = reservations or {}
        if result.get("market") or reserve.get("market_slots"):
            self.last_decision = {"reason": "occupied_market"}
            return result
        if int(cfg.get("maxMarketOrdersPerTurn", 10)) < 2:
            self.last_decision = {"reason": "two_slots_required"}
            return result
        player = observation.get("player")
        farms = observation.get("farms", [])
        if player not in (0, 1) or len(farms) != 2:
            return result
        market = observation.get("market", {})
        params = market.get("params") or MARKET_PARAMS
        if params != MARKET_PARAMS:
            self.last_decision = {"reason": "unmeasured_market_override"}
            return result
        shed = observation.get("private", {}).get("shed", {})
        cap = int(cfg.get("shedCapacity", 100))
        # Unit actions precede market. Do not count future DROP/PLACE deposits;
        # subtract all requested relevant pickups, including impossible ones.
        unit_actions = [result.get("farmer", [])] + list(result.get("hands", []))
        for item in ("WHEAT", "FERTILIZER"):
            available = int(shed.get(item, 0)) - int(reserve.get("stock", {}).get(item, 0))
            for action in unit_actions:
                if len(action) >= 2 and action[:2] == ["PICKUP", item]:
                    available -= max(0, int(action[2]) if len(action) >= 3 else 1)
            if available < 1 or sum(shed.values()) > cap:
                continue
            inventory = market.get("inventory", {}).get(item)
            if inventory is None:
                continue
            sale = market_price(item, inventory, params)
            buy = market_price(item, inventory - 1, params)
            # A rival BUY in slot 0 must fail at its first unit. Other slot-0
            # orders cannot also buy this product. SELL may fund slot 1.
            if farms[1-player].get("money", 0) >= buy or sale <= 1:
                continue
            # Exclude the floor-admission boundary over any legal rival shed.
            if market_price(item, inventory + cap + 1, params) <= 1:
                continue
            # The flat condition removes the zero-flow rival slot-1 discount.
            if self.require_flat and sale != buy:
                continue
            result["market"] = [["SELL", item, 1], ["BUY_PRODUCT", item, 1]]
            self.overrides += 1
            self.last_decision = {"reason": "cycle", "item": item,
                                  "inventory": inventory, "sale_quote": sale,
                                  "slot0_buy_quote": buy,
                                  "rival_cash": farms[1-player].get("money", 0)}
            return result
        return result


def transform(observation, configuration, base_action, *, reservations=None):
    """Stateless convenience interface for whole-agent composition."""
    return LiquidityCycle().transform(observation, configuration, base_action,
                                     reservations=reservations)
