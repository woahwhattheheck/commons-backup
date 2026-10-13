# SPDX-License-Identifier: Apache-2.0
"""V4 C5 public WHEAT buy-signal rider.

This is the repaired C5 theorem from V3.1, packaged as a default-off V4
post-processing helper. It observes only public market/town state plus our own
previous returned action.

For WHEAT, public inventory transitions conservatively prove gross rival
BUY_PRODUCT(WHEAT) units:

    rival_buy >= previous_inventory - current_inventory
                 - town_consume - own_buy_requested_upper_bound

Successful visible SELLs only make that lower bound smaller. The official
engine's $1 SELL floor can hide SELL supply from public inventory, so this helper
does not claim to prove rival *net* demand.

After a positive prior-step lower bound, C5 may relocate exactly one already
authored executable WHEAT SELL to a later executable market slot. Quantity,
all other rows, worker actions, and purchases are unchanged. A later cash
spend vetoes the move so an earlier sale can never be removed from purchase
funding. Malformed or ambiguous evidence fails closed to the exact parent.
"""
from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

DEFAULT_MAX_ORDERS = 10
WHEAT = "WHEAT"
BUY_OPS = {"HIRE", "BUY_LAND", "BUY_PRODUCT", "BUY_SEED", "BUY_ANIMAL"}
SHOPS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _strict_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be a JSON integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    number = _strict_int(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def _interval(configuration: Any, key: str, default: int) -> int:
    value = _get(configuration, key, default) if configuration is not None else default
    return _positive_int(value, key)


def _market_cap(configuration: Any = None) -> int:
    """Strict official-cap subset: exact ints clamp to >=1; others fail closed."""
    value = (
        _get(configuration, "maxMarketOrdersPerTurn", DEFAULT_MAX_ORDERS)
        if configuration is not None
        else DEFAULT_MAX_ORDERS
    )
    return max(1, _strict_int(value, "maxMarketOrdersPerTurn"))


def _step_player(observation: Any) -> tuple[int, int]:
    step = _strict_int(_get(observation, "step", None), "step")
    player = _strict_int(_get(observation, "player", None), "player")
    if step < 0 or player not in (0, 1):
        raise ValueError("invalid step/player")
    return step, player


def _product_value(container: Any, product: str, label: str) -> int:
    if isinstance(container, Mapping):
        if product not in container:
            raise ValueError(f"missing {label}")
        value = container[product]
    else:
        sentinel = object()
        value = getattr(container, product, sentinel)
        if value is sentinel:
            raise ValueError(f"missing {label}")
    return _strict_int(value, label)


def _wheat_inventory(observation: Any) -> int:
    market = _get(observation, "market", None)
    inventory = _get(market, "inventory", None)
    if inventory is None:
        raise ValueError("missing public market inventory")
    return _product_value(inventory, WHEAT, "market.inventory.WHEAT")


def _wheat_price(observation: Any) -> int:
    market = _get(observation, "market", None)
    prices = _get(market, "prices", None)
    if prices is None:
        raise ValueError("missing public market prices")
    return _product_value(prices, WHEAT, "market.prices.WHEAT")


def _town_wheat_consumption(observation: Any, configuration: Any = None) -> int:
    """Exact deterministic WHEAT units consumed after this step's market phase."""
    step, _ = _step_player(observation)
    shop_interval = _interval(configuration, "townShopSellInterval", 4)
    center_interval = _interval(configuration, "townCenterSellInterval", 24)
    town = _get(observation, "town", None)
    shops = _get(town, "unlocked_shops", None)
    if not isinstance(shops, (list, tuple)):
        raise ValueError("town.unlocked_shops must be a sequence")

    consume = 0
    if step % shop_interval == 0:
        for shop in shops:
            if type(shop) is not str or shop not in SHOPS:
                raise ValueError(f"unknown shop {shop!r}")
            if WHEAT in SHOPS[shop]:
                consume += 1
    else:
        for shop in shops:
            if type(shop) is not str or shop not in SHOPS:
                raise ValueError(f"unknown shop {shop!r}")
    if step % center_interval == 0:
        consume += 1
    return consume


def _market_rows(action: Mapping[str, Any], executable_cap: int) -> list[Any]:
    market = _get(action, "market", None)
    if not isinstance(market, list):
        raise ValueError("action.market must be a list")
    if type(executable_cap) is not int or executable_cap < 1:
        raise ValueError("executable cap must be a positive integer")
    return market[:executable_cap]


def _own_wheat_buy_upper(action: Mapping[str, Any], executable_cap: int) -> int:
    total = 0
    for order in _market_rows(action, executable_cap):
        # The official interpreter executes market rows only when they are lists.
        if not isinstance(order, list) or not order:
            continue
        if order[0] != "BUY_PRODUCT" or len(order) < 2 or order[1] != WHEAT:
            continue
        if len(order) < 3:
            raise ValueError("malformed own WHEAT BUY_PRODUCT")
        total += _positive_int(order[2], "own WHEAT BUY quantity")
    return total


def _rival_wheat_buy_lower_bound(
    previous_inventory: int,
    current_inventory: int,
    previous_town_consume: int,
    previous_own_buy_upper: int,
) -> int:
    return (
        int(previous_inventory)
        - int(current_inventory)
        - int(previous_town_consume)
        - int(previous_own_buy_upper)
    )


def _cash_spending(order: Any) -> bool:
    # Match the official market parser: tuple-shaped rows are inert.
    return isinstance(order, list) and bool(order) and order[0] in BUY_OPS


def _relocate_wheat_sell(
    action: Mapping[str, Any], executable_cap: int
) -> tuple[Mapping[str, Any], dict[str, int] | None]:
    """Move one executable WHEAT SELL to a new executable tail without shifting peers."""
    market = _market_rows(action, executable_cap)
    if len(market) >= executable_cap:
        return action, None

    wheat_rows: list[tuple[int, Sequence[Any]]] = []
    for index, order in enumerate(market):
        # A tuple that names WHEAT is engine-inert, but treating it as an
        # executable candidate would move a row the engine would never parse.
        if not isinstance(order, list):
            if isinstance(order, tuple) and len(order) >= 2 and order[1] == WHEAT:
                return action, None
            continue
        if not order or len(order) < 2:
            continue
        if order[1] != WHEAT:
            continue
        if order[0] != "SELL" or len(order) < 3:
            return action, None
        try:
            _positive_int(order[2], "WHEAT SELL quantity")
        except ValueError:
            return action, None
        wheat_rows.append((index, order))

    if len(wheat_rows) != 1:
        return action, None
    index, _ = wheat_rows[0]
    if any(_cash_spending(row) for row in market[index + 1 :]):
        return action, None

    result = copy.deepcopy(action)
    result_market = result["market"]
    moved = copy.deepcopy(result_market[index])
    result_market[index] = []
    result_market.append(moved)
    return result, {
        "from_index": index,
        "to_index": len(result_market) - 1,
        "quantity": _positive_int(moved[2], "moved WHEAT SELL quantity"),
    }


class WheatDemandRider:
    """Per-player public-transition detector + final-action sale-row transform."""

    def __init__(self, enabled: bool = False):
        self.enabled = bool(enabled)
        self.players: dict[int, dict[str, int]] = {}
        self.telemetry = {
            "confirmed_rival_buy_transitions": 0,
            "relocations": 0,
            "moved_units": 0,
            "last_rival_buy_lower_bound": 0,
            "last_from_index": None,
            "last_to_index": None,
        }

    def reset(self) -> None:
        self.players.clear()
        self.telemetry.update({
            "confirmed_rival_buy_transitions": 0,
            "relocations": 0,
            "moved_units": 0,
            "last_rival_buy_lower_bound": 0,
            "last_from_index": None,
            "last_to_index": None,
        })

    def _begin(self, observation: Any) -> tuple[int, int, int]:
        step, player = _step_player(observation)
        current_inventory = _wheat_inventory(observation)
        previous = self.players.get(player)
        if previous is None or step != previous["step"] + 1:
            return step, player, 0
        lower = _rival_wheat_buy_lower_bound(
            previous["inventory"],
            current_inventory,
            previous["town_consume"],
            previous["own_buy_upper"],
        )
        return step, player, lower

    def _current_record(
        self,
        observation: Any,
        action: Mapping[str, Any],
        configuration: Any = None,
    ) -> tuple[int, dict[str, int], int, int]:
        step, player = _step_player(observation)
        executable_cap = _market_cap(configuration)
        price = _wheat_price(observation)
        record = {
            "step": step,
            "inventory": _wheat_inventory(observation),
            "town_consume": _town_wheat_consumption(observation, configuration),
            "own_buy_upper": _own_wheat_buy_upper(action, executable_cap),
        }
        return player, record, price, executable_cap

    def _forget_player(self, observation: Any) -> None:
        """Invalidate stale evidence even when the callback clock is malformed."""
        try:
            player = _strict_int(_get(observation, "player", None), "player")
        except (AttributeError, KeyError, TypeError, ValueError):
            self.players.clear()
            return
        if player in (0, 1):
            self.players.pop(player, None)
        else:
            self.players.clear()

    def apply(
        self,
        observation: Any,
        parent_action: Mapping[str, Any],
        configuration: Any = None,
    ) -> Mapping[str, Any]:
        try:
            _, player, lower = self._begin(observation)
            current_player, current_record, current_price, executable_cap = self._current_record(
                observation, parent_action, configuration
            )
            if current_player != player:
                raise ValueError("player changed while materializing evidence")
        except (AttributeError, KeyError, TypeError, ValueError):
            self._forget_player(observation)
            return parent_action

        result: Mapping[str, Any] = parent_action
        if lower > 0:
            self.telemetry["confirmed_rival_buy_transitions"] += 1
            self.telemetry["last_rival_buy_lower_bound"] = lower
            if self.enabled and current_price > 1:
                try:
                    candidate, moved = _relocate_wheat_sell(parent_action, executable_cap)
                    if moved is not None:
                        result = candidate
                        self.telemetry["relocations"] += 1
                        self.telemetry["moved_units"] += moved["quantity"]
                        self.telemetry["last_from_index"] = moved["from_index"]
                        self.telemetry["last_to_index"] = moved["to_index"]
                except (AttributeError, KeyError, TypeError, ValueError):
                    result = parent_action

        self.players[player] = current_record
        return result


RIDER = WheatDemandRider(enabled=True)


def reset_state() -> None:
    RIDER.reset()


def apply_c5_wheat_demand(
    observation: Any,
    parent_action: Mapping[str, Any],
    configuration: Any = None,
    *,
    enabled: bool = True,
) -> Mapping[str, Any]:
    """Apply the V4 C5 rider; disabled mode is exact parent identity."""
    if not enabled:
        return parent_action
    return RIDER.apply(observation, parent_action, configuration)


telemetry = RIDER.telemetry
