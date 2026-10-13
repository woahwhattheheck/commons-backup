# SPDX-License-Identifier: Apache-2.0
"""V4 S8: trade an end-of-day goose fertilizer collection for CARE when EGG wins.

The transform is intentionally resource-neutral: it never changes herd size, hands,
movement, structures, land, market orders, or tile occupancy. It only replaces an
already-authored hour-23 ``COLLECT_FERTILIZER`` on a fed/uncared GOOSE with ``CARE``
when public prices strongly favor the one future care-bonus EGG over the fertilizer
that would otherwise auto-drop to the shed at end of day.

H3c goose clipping rescue is expected to run first. A row already changed to
``HARVEST`` is therefore untouched. Conservative no-harvest arithmetic also proves
that the current base production plus the next cared production cannot exceed the
GOOSE four-EGG held cap. Ambiguous or malformed observations preserve the exact
parent action object.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

KEY = "r04_s8_egg_care"
GOOSE_FIRST_YIELD_DAY = 4
GOOSE_MAX_HELD = 4
MIN_FERTILIZER_BUFFER = 4
MIN_PRICE_EDGE = 20
PRICE_RATIO_NUM = 6
PRICE_RATIO_DEN = 5
LAST_CARE_DAY = 27  # day 28 care would mature after the final executable EOD

telemetry = Counter()
_MISSING = object()


def _cfg(configuration: Any, name: str, default: Any):
    if configuration is None:
        return default
    try:
        if isinstance(configuration, dict):
            return configuration.get(name, default)
        return getattr(configuration, name, default)
    except Exception:
        return _MISSING


def _standard_timing(configuration: Any) -> bool:
    turns = _cfg(configuration, "turnsPerDay", 24)
    steps = _cfg(configuration, "episodeSteps", 720)
    return type(turns) is int and turns == 24 and type(steps) is int and steps == 720


def _strict_goose(tile: Any):
    if not isinstance(tile, dict) or tile.get("kind") != "COOP" or tile.get("animal") != "GOOSE":
        return None
    placed = tile.get("placed_day", _MISSING)
    units = tile.get("yield_units", _MISSING)
    unfed = tile.get("consecutive_unfed", _MISSING)
    fed = tile.get("fed_today", _MISSING)
    cared = tile.get("cared_today", _MISSING)
    fert = tile.get("fertilizer_available", _MISSING)
    bonus = tile.get("pending_care_bonus", 0)
    if type(placed) is not int or placed < 0:
        return None
    if type(units) is not int or not 0 <= units <= GOOSE_MAX_HELD:
        return None
    if type(unfed) is not int or unfed < 0:
        return None
    if type(fed) is not bool or type(cared) is not bool or type(fert) is not bool:
        return None
    if type(bonus) is not int or bonus < 0:
        return None
    return placed, units, unfed, fed, cared, fert, bonus


def _rows(action: Any):
    if not isinstance(action, dict):
        return None
    farmer = action.get("farmer", _MISSING)
    hands = action.get("hands", _MISSING)
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if any(not isinstance(command, list) for command in hands):
        return None
    return [farmer, *hands]


def _price_guard(observation: dict[str, Any]) -> tuple[bool, int, int]:
    market = observation.get("market")
    if not isinstance(market, dict):
        return False, 0, 0
    prices = market.get("prices")
    if not isinstance(prices, dict):
        return False, 0, 0
    egg = prices.get("EGG")
    fertilizer = prices.get("FERTILIZER")
    if type(egg) is not int or type(fertilizer) is not int or egg <= 0 or fertilizer <= 0:
        return False, 0, 0
    strong = (egg - fertilizer >= MIN_PRICE_EDGE
              and egg * PRICE_RATIO_DEN >= fertilizer * PRICE_RATIO_NUM)
    return strong, egg, fertilizer


def apply_egg_care(
    observation: Any,
    action: Any,
    configuration: Any = None,
    *,
    enabled: bool = False,
):
    """Return the S8 action; disabled/no-match paths return ``action`` by identity."""
    if not enabled or not isinstance(observation, dict) or not _standard_timing(configuration):
        return action
    step = observation.get("step")
    player = observation.get("player")
    if type(step) is not int or step < 0 or step % 24 != 23:
        return action
    day = step // 24
    if day > LAST_CARE_DAY or type(player) is not int or player not in (0, 1):
        return action

    profitable, egg_price, fertilizer_price = _price_guard(observation)
    if not profitable:
        telemetry["price_block"] += 1
        return action

    farms = observation.get("farms")
    private = observation.get("private")
    if not isinstance(farms, list) or len(farms) != 2 or not isinstance(private, dict):
        return action
    farm = farms[player]
    shed = private.get("shed")
    if not isinstance(farm, dict) or not isinstance(shed, dict):
        return action
    fert_stock = shed.get("FERTILIZER", 0)
    if type(fert_stock) is not int or fert_stock < MIN_FERTILIZER_BUFFER:
        telemetry["fertilizer_buffer_block"] += 1
        return action

    farmer = farm.get("farmer")
    hands = farm.get("hands")
    tiles = farm.get("tiles")
    if (not isinstance(farmer, list) or not isinstance(hands, list)
            or not isinstance(tiles, list)):
        return action
    positions = [farmer, *hands]
    rows = _rows(action)
    if rows is None or len(rows) != len(positions):
        return action

    normalized = []
    actor_tiles = []
    for pos in positions:
        if (not isinstance(pos, list) or len(pos) != 2
                or type(pos[0]) is not int or type(pos[1]) is not int):
            return action
        x, y = pos
        if not (0 <= y < len(tiles) and isinstance(tiles[y], list) and 0 <= x < len(tiles[y])):
            return action
        normalized.append((x, y))
        actor_tiles.append(tiles[y][x])

    candidates = []
    for actor, (command, tile) in enumerate(zip(rows, actor_tiles)):
        if command != ["COLLECT_FERTILIZER"]:
            continue
        goose = _strict_goose(tile)
        if goose is None:
            continue
        placed, units, _unfed, fed, cared, fertilizer_available, pending_bonus = goose
        if not fed or cared or not fertilizer_available or pending_bonus != 0:
            continue
        # Care today is banked after the current EOD production and can first pay
        # on the following EOD. Refuse immature geese whose next EOD is still
        # pre-production; that avoids carrying an unbounded pending bonus.
        if day < placed + GOOSE_FIRST_YIELD_DAY - 2:
            continue
        current_produces = day >= placed + GOOSE_FIRST_YIELD_DAY - 1
        current_add = 1 if current_produces else 0
        # No-harvest upper bound: current base production + next cared production
        # (base 1 + care bonus 1) must fit under max-held=4.
        if units + current_add + 2 > GOOSE_MAX_HELD:
            telemetry["capacity_block"] += 1
            continue
        candidates.append(actor)

    if not candidates:
        return action

    candidate_sites = {actor: normalized[actor] for actor in candidates}
    if len(set(candidate_sites.values())) != len(candidate_sites):
        telemetry["stacked_worker_block"] += 1
        return action
    for actor, site in candidate_sites.items():
        for other, (other_site, other_command) in enumerate(zip(normalized, rows)):
            if other != actor and other_site == site and other_command != ["PASS"]:
                telemetry["stacked_worker_block"] += 1
                return action

    result = copy.deepcopy(action)
    result_rows = [result["farmer"], *result["hands"]]
    for actor in candidates:
        result_rows[actor] = ["CARE"]
        telemetry["activations"] += 1
        telemetry["egg_price_at_activation"] += egg_price
        telemetry["fertilizer_price_at_activation"] += fertilizer_price
        telemetry["fertilizer_units_foregone"] += 1
        telemetry["bonus_egg_units_targeted"] += 1
    result["farmer"], result["hands"] = result_rows[0], result_rows[1:]
    return result
