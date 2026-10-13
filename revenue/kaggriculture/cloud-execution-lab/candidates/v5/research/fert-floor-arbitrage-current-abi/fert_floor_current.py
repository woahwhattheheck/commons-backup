# SPDX-License-Identifier: Apache-2.0
"""Current-V5 evidence adapter for source-real low-price fertilizer use.

Fresh re-author from durable mechanism authority; not a reconstruction of the
lost ``r04_fert_arbitrage`` payload.  The historical positive configuration
used ``buy_price=2`` while the official interpreter quotes BUY_PRODUCT at the
*post-buy* inventory.  This file therefore binds the authenticated default
engine's exact low-price boundary instead of guessing from the public price:

* pre-buy FERT inventory >= 10,489 => one-unit post-buy quote <= $2;
* pre-buy FERT inventory >= 10,494 => one-unit post-buy quote == $1 floor.

The adapter is selected-action-only, default-disconnected, and never invents
PICKUP routing.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Mapping

ITEM = "FERTILIZER"
ENGINE_PRICE_FLOOR = 1
MAX_BUY_PRICE = 2
FERT_PRICE2_PREBUY_INVENTORY = 10_489
FERT_PRICE1_PREBUY_INVENTORY = 10_494
# At 10,493 the public quote has rounded to $1, while the post-buy quote is
# still $2. This is why public-price equality is not a correct buy authority.
FERT_PUBLIC_PRICE1_INVENTORY = 10_493

MAX_MARKET_ORDERS = 10
TURNS_PER_DAY = 24
EPISODE_STEPS = 720

OFFICIAL_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
MECHANISM_SOURCE_PATH = (
    "revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/"
    "fwd-buy-census/fert_floor_apply.py"
)
MECHANISM_SOURCE_BLOB = "a32160a2298e9d92a824b52bc272535583a85a67"
MECHANISM_PR = 13057
MECHANISM_FOLLOWUP = "d8fa49ccbedf2a51c65431bae51a7f99e648da20"


def _finite_number(value: Any) -> bool:
    return (
        type(value) is int
        or (type(value) is float and math.isfinite(value))
    )


def _nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _identity(selected: Any, reason: str, **extra: Any):
    report = {
        "changed": False,
        "reason": reason,
        "buy_added": False,
        "fertilize_actor_indices": (),
        "max_buy_price": MAX_BUY_PRICE,
        "official_engine_blob": OFFICIAL_ENGINE_BLOB,
        "mechanism_source_blob": MECHANISM_SOURCE_BLOB,
    }
    report.update(extra)
    return selected, report


def _configuration(configuration: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if configuration is None:
        return {
            "maxMarketOrdersPerTurn": MAX_MARKET_ORDERS,
            "turnsPerDay": TURNS_PER_DAY,
            "episodeSteps": EPISODE_STEPS,
        }
    if not isinstance(configuration, Mapping):
        return None
    cfg = dict(configuration)
    expected = {
        "maxMarketOrdersPerTurn": MAX_MARKET_ORDERS,
        "turnsPerDay": TURNS_PER_DAY,
        "episodeSteps": EPISODE_STEPS,
    }
    for key, default in expected.items():
        value = cfg.get(key, default)
        if type(value) is not int or value != default:
            return None
    if cfg.get("marketParams") not in (None, {}):
        return None
    return cfg


def _eligible_plant(tile: Any, day: int) -> bool:
    if not isinstance(tile, Mapping) or tile.get("kind") != "PLANT":
        return False
    crop = tile.get("crop")
    covered = tile.get("fertilized_until_day", -1)
    if type(crop) is not str or not crop or type(covered) is not int:
        return False
    if tile.get("dead") is True:
        return False
    return covered < day + 2


def _board_has_opportunity(tiles: Any, day: int) -> bool:
    return (
        isinstance(tiles, list)
        and bool(tiles)
        and all(isinstance(row, list) for row in tiles)
        and any(_eligible_plant(tile, day) for row in tiles for tile in row)
    )


def _actor_tile(tiles: list[list[Any]], position: Any) -> Any:
    if (
        not isinstance(position, list)
        or len(position) != 2
        or any(type(value) is not int for value in position)
    ):
        return None
    x, y = position
    if y < 0 or y >= len(tiles) or x < 0 or x >= len(tiles[y]):
        return None
    return tiles[y][x]


def _fert_qty(inventory: Any) -> int | None:
    if not isinstance(inventory, Mapping):
        return None
    value = inventory.get(ITEM, 0)
    return value if _nonnegative_int(value) else None


def _source_public_price(fert_inventory: int) -> int | None:
    """Exact authenticated public quote inside the low-price candidate region."""
    if type(fert_inventory) is not int or fert_inventory < FERT_PRICE2_PREBUY_INVENTORY:
        return None
    return (
        ENGINE_PRICE_FLOOR
        if fert_inventory >= FERT_PUBLIC_PRICE1_INVENTORY
        else MAX_BUY_PRICE
    )


def _source_postbuy_price(fert_inventory: int) -> int | None:
    """Exact one-unit BUY_PRODUCT quote for the authenticated low-price region."""
    if type(fert_inventory) is not int or fert_inventory < FERT_PRICE2_PREBUY_INVENTORY:
        return None
    return (
        ENGINE_PRICE_FLOOR
        if fert_inventory >= FERT_PRICE1_PREBUY_INVENTORY
        else MAX_BUY_PRICE
    )


def _parse(observation: Any, selected: Any, configuration: Mapping[str, Any] | None):
    cfg = _configuration(configuration)
    if cfg is None or not isinstance(observation, Mapping) or not isinstance(selected, Mapping):
        return None, "malformed_envelope"
    player = observation.get("player")
    step = observation.get("step")
    farms = observation.get("farms")
    private = observation.get("private")
    market_state = observation.get("market")
    if (
        type(player) is not int
        or player not in (0, 1)
        or type(step) is not int
        or not 0 <= step < EPISODE_STEPS
        or not isinstance(farms, list)
        or player >= len(farms)
        or not isinstance(private, Mapping)
        or not isinstance(market_state, Mapping)
    ):
        return None, "malformed_observation"

    farm = farms[player]
    if not isinstance(farm, Mapping):
        return None, "malformed_farm"
    farmer = farm.get("farmer")
    hands = farm.get("hands")
    tiles = farm.get("tiles")
    money = farm.get("money")
    inventories = private.get("inventories")
    shed = private.get("shed")
    prices = market_state.get("prices")
    market_inventory = market_state.get("inventory")
    if (
        not isinstance(farmer, list)
        or not isinstance(hands, list)
        or not isinstance(tiles, list)
        or not isinstance(inventories, list)
        or len(inventories) != len(hands) + 1
        or not isinstance(shed, Mapping)
        or not isinstance(prices, Mapping)
        or not isinstance(market_inventory, Mapping)
        or not _finite_number(money)
        or money < 0
    ):
        return None, "malformed_farm_state"

    selected_farmer = selected.get("farmer")
    selected_hands = selected.get("hands")
    selected_market = selected.get("market")
    if (
        not isinstance(selected_farmer, list)
        or not selected_farmer
        or not isinstance(selected_hands, list)
        or len(selected_hands) != len(hands)
        or not isinstance(selected_market, list)
        or len(selected_market) > MAX_MARKET_ORDERS
        or any(
            not isinstance(command, list) or not command
            for command in [selected_farmer, *selected_hands]
        )
        or any(not isinstance(order, list) or not order for order in selected_market)
    ):
        return None, "selected_action_invalid"

    fert_price = prices.get(ITEM)
    fert_market_inventory = market_inventory.get(ITEM)
    if not _finite_number(fert_price) or fert_price < 0:
        return None, "malformed_fertilizer_price"
    if not _nonnegative_int(fert_market_inventory):
        return None, "malformed_fertilizer_market_inventory"

    shed_fert = _fert_qty(shed)
    actor_fert = [_fert_qty(inventory) for inventory in inventories]
    if shed_fert is None or any(value is None for value in actor_fert):
        return None, "malformed_fertilizer_inventory"

    return {
        "cfg": cfg,
        "player": player,
        "step": step,
        "day": step // TURNS_PER_DAY,
        "positions": [farmer, *hands],
        "tiles": tiles,
        "money": money,
        "inventories": inventories,
        "shed_fert": shed_fert,
        "actor_fert": actor_fert,
        "fert_price": fert_price,
        "fert_market_inventory": fert_market_inventory,
        "selected_market": selected_market,
    }, None


def _market_mentions_fertilizer(market: list[list[Any]]) -> bool:
    return any(len(order) >= 2 and order[1] == ITEM for order in market)


def _floor_buy_authority(parsed: Mapping[str, Any]) -> tuple[bool, str, int | None]:
    inventory = parsed["fert_market_inventory"]
    expected_public = _source_public_price(inventory)
    postbuy = _source_postbuy_price(inventory)
    if postbuy is None:
        return False, "fertilizer_postbuy_quote_above_ceiling", None
    if parsed["fert_price"] != expected_public:
        return False, "fertilizer_market_authority_drift", postbuy
    if parsed["money"] < postbuy:
        return False, "insufficient_cash_for_source_quote", postbuy
    return True, "authorized", postbuy


class FertFloorArbitrageCurrentABI:
    """Default-disconnected selected-action research adapter."""

    def __init__(self, *, buy: bool = True, apply: bool = True):
        if type(buy) is not bool or type(apply) is not bool:
            raise TypeError("buy and apply must be exact bool")
        self.buy = buy
        self.apply = apply

    def transform(
        self,
        observation: Any,
        selected: Any,
        configuration: Mapping[str, Any] | None = None,
    ):
        parsed, error = _parse(observation, selected, configuration)
        if parsed is None:
            return _identity(
                selected,
                error or "malformed_envelope",
                buy_enabled=self.buy,
                apply_enabled=self.apply,
            )

        action = deepcopy(selected)
        commands = [action["farmer"], *action["hands"]]
        fertilized: list[int] = []

        if self.apply:
            for index, (position, inventory) in enumerate(
                zip(parsed["positions"], parsed["inventories"])
            ):
                qty = _fert_qty(inventory)
                tile = _actor_tile(parsed["tiles"], position)
                if (
                    commands[index] == ["PASS"]
                    and qty is not None
                    and qty > 0
                    and _eligible_plant(tile, parsed["day"])
                ):
                    commands[index] = ["FERTILIZE"]
                    fertilized.append(index)

        action["farmer"] = commands[0]
        action["hands"] = commands[1:]

        buy_added = False
        buy_authorized = False
        buy_reason = "buy_disabled"
        source_postbuy_price = None
        if self.buy:
            buy_authorized, buy_reason, source_postbuy_price = _floor_buy_authority(parsed)
            owned_fert = parsed["shed_fert"] + sum(parsed["actor_fert"])
            can_buy = (
                buy_authorized
                and owned_fert == 0
                and len(action["market"]) < MAX_MARKET_ORDERS
                and not _market_mentions_fertilizer(action["market"])
                and _board_has_opportunity(parsed["tiles"], parsed["day"])
            )
            if can_buy:
                action["market"].append(["BUY_PRODUCT", ITEM, 1])
                buy_added = True

        changed = action != selected
        if not changed:
            reason = "identity"
            owned_fert = parsed["shed_fert"] + sum(parsed["actor_fert"])
            if self.buy and not buy_authorized:
                reason = buy_reason
            elif self.buy and owned_fert > 0:
                reason = "owned_fertilizer_already_present"
            elif self.buy and _market_mentions_fertilizer(parsed["selected_market"]):
                reason = "parent_fertilizer_market_intent"
            elif self.buy and len(parsed["selected_market"]) >= MAX_MARKET_ORDERS:
                reason = "market_capacity_full"
            elif self.buy and not _board_has_opportunity(parsed["tiles"], parsed["day"]):
                reason = "no_live_fertilizer_opportunity"
            return _identity(
                selected,
                reason,
                buy_enabled=self.buy,
                apply_enabled=self.apply,
                observed_fertilizer_price=parsed["fert_price"],
                fertilizer_market_inventory=parsed["fert_market_inventory"],
                source_postbuy_price=source_postbuy_price,
            )

        return action, {
            "changed": True,
            "reason": "fert_floor_arbitrage_current_transform",
            "buy_enabled": self.buy,
            "apply_enabled": self.apply,
            "buy_added": buy_added,
            "fertilize_actor_indices": tuple(fertilized),
            "max_buy_price": MAX_BUY_PRICE,
            "observed_fertilizer_price": parsed["fert_price"],
            "fertilizer_market_inventory": parsed["fert_market_inventory"],
            "source_postbuy_price": source_postbuy_price,
            "official_engine_blob": OFFICIAL_ENGINE_BLOB,
            "mechanism_source_blob": MECHANISM_SOURCE_BLOB,
        }
