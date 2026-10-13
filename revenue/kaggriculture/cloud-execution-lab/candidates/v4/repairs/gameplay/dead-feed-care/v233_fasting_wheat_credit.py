#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""V233-only carry-credit for WHEAT saved by FASTING at the prior EOD.

Pure composition helper. It does not decide FEED suppression; that remains owned by
uncared_eod_feed_skip.py. It records only FASTING changes on V233-owned sheep workers,
then may reduce the *next day's* exact V233 BUY_PRODUCT WHEAT 6 order after custody is
confirmed by a below-cap morning shed. Default-off and fail-closed.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

V233_SITES = frozenset((x, y) for y in (5, 6) for x in range(5, 8))
MAX_DAILY_CREDIT = 2  # V233 owns two dedicated workers per active day.


def _cfg(configuration: Any, key: str) -> Any:
    if isinstance(configuration, dict):
        return configuration.get(key)
    return getattr(configuration, key, None)


def _default_config(configuration: Any) -> bool:
    return all(type(_cfg(configuration, key)) is int and _cfg(configuration, key) == value
               for key, value in (("boardSize", 10), ("turnsPerDay", 24),
                                  ("episodeSteps", 720), ("shedCapacity", 100),
                                  ("maxMarketOrdersPerTurn", 10)))


def _valid_workers(workers: Any) -> dict[int, set[tuple[int, int]]] | None:
    if not isinstance(workers, dict) or len(workers) != 2:
        return None
    normalized: dict[int, set[tuple[int, int]]] = {}
    for actor, targets in workers.items():
        if type(actor) is not int or actor <= 0 or not isinstance(targets, list) or len(targets) != 3:
            return None
        sites: set[tuple[int, int]] = set()
        for target in targets:
            if (not isinstance(target, (list, tuple)) or len(target) != 2
                    or any(type(v) is not int for v in target)):
                return None
            site = (target[0], target[1])
            if site not in V233_SITES:
                return None
            sites.add(site)
        if len(sites) != 3:
            return None
        normalized[actor] = sites
    if set().union(*normalized.values()) != V233_SITES:
        return None
    if normalized[next(iter(sorted(normalized)))] not in ({(5,5),(6,5),(7,5)}, {(5,6),(6,6),(7,6)}):
        return None
    rows = {frozenset(v) for v in normalized.values()}
    if rows != {frozenset((x,5) for x in range(5,8)), frozenset((x,6) for x in range(5,8))}:
        return None
    return normalized


def _farm_private(observation: Any):
    if not isinstance(observation, dict):
        return None, None, None
    step, player = observation.get("step"), observation.get("player")
    farms, private = observation.get("farms"), observation.get("private")
    if (type(step) is not int or type(player) is not int or player not in (0, 1)
            or not isinstance(farms, list) or len(farms) != 2 or not isinstance(private, dict)
            or not isinstance(farms[player], dict)):
        return None, None, None
    return step, farms[player], private


def _six_v233_sheep(farm: dict[str, Any]) -> bool:
    tiles = farm.get("tiles")
    if (not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)):
        return False
    for x, y in V233_SITES:
        tile = tiles[y][x]
        if not isinstance(tile, dict) or tile.get("animal") != "SHEEP":
            return False
    return True


def observe_v233_fasting_skips(state: Any, observation: Any, fasting_changes: Any,
                                configuration: Any, *, enabled: bool = False) -> int:
    """Record prior-EOD V233-owned FASTING wheat savings into ``state``.

    ``fasting_changes`` must be the exact planner output from
    ``plan_uncared_eod_feed_skip`` for the final composed action. No FEED decision is
    made here. Returns the number of newly recorded credits.
    """
    if not enabled or not isinstance(state, dict) or not _default_config(configuration):
        return 0
    step, farm, _private = _farm_private(observation)
    if step is None or step % 24 != 23 or not state.get("committed") or not _six_v233_sheep(farm):
        return 0
    workers = _valid_workers(state.get("workers"))
    if workers is None or not isinstance(fasting_changes, list):
        return 0
    credited: set[tuple[int, tuple[int, int]]] = set()
    for change in fasting_changes:
        if not isinstance(change, dict):
            return 0
        actor, site, saved, species = (change.get("actor"), change.get("site"),
                                       change.get("guaranteed_wheat_saved"), change.get("species"))
        if (type(actor) is not int or actor not in workers or not isinstance(site, list) or len(site) != 2
                or any(type(v) is not int for v in site) or tuple(site) not in workers[actor]
                or saved != 1 or species != "SHEEP"):
            continue
        credited.add((actor, tuple(site)))
    count = min(MAX_DAILY_CREDIT, len(credited))
    if not count:
        return 0
    day = step // 24
    existing_day = state.get("v233_fasting_credit_day")
    existing = state.get("v233_fasting_credit_pending", 0)
    if type(existing) is not int or existing < 0:
        return 0
    if existing_day not in (None, day):
        # Do not merge credits across an unobserved day boundary.
        existing = 0
    state["v233_fasting_credit_day"] = day
    state["v233_fasting_credit_pending"] = min(MAX_DAILY_CREDIT, existing + count)
    return count


def _exact_v233_buy_index(market: Any) -> int | None:
    if not isinstance(market, list) or len(market) > 10:
        return None
    matches = []
    for i in range(max(0, len(market) - 2)):
        if (market[i] == ["BUY_PRODUCT", "WHEAT", 6]
                and market[i + 1] == ["HIRE"] and market[i + 2] == ["HIRE"]):
            matches.append(i)
    if len(matches) != 1:
        return None
    i = matches[0]
    # No other WHEAT market row: ownership would be ambiguous.
    for j, row in enumerate(market):
        if j == i:
            continue
        if isinstance(row, list) and len(row) > 1 and row[1] == "WHEAT":
            return None
    # Prior-day credit only applies after initial V233 investment.
    if any(row and row[0] == "BUY_LAND" for row in market if isinstance(row, list)):
        return None
    if any(row[:2] == ["BUY_ANIMAL", "SHEEP"] for row in market if isinstance(row, list)):
        return None
    return i


def _touches_wheat_units(action: dict[str, Any]) -> bool:
    rows = [action.get("farmer"), *(action.get("hands") if isinstance(action.get("hands"), list) else [])]
    for row in rows:
        if isinstance(row, list) and len(row) > 1 and row[1] == "WHEAT":
            return True
    return False


def _clear_pending_credit(state: dict[str, Any], reason: str) -> None:
    state["v233_fasting_credit_pending"] = 0
    state["v233_fasting_credit_day"] = None
    state["v233_fasting_credit_invalidated"] = state.get("v233_fasting_credit_invalidated", 0) + 1
    state["v233_fasting_credit_last_invalidation"] = reason


def apply_v233_fasting_wheat_credit(action: Any, observation: Any, state: Any,
                                     configuration: Any, *, enabled: bool = False):
    """Reduce the exact next-day V233 WHEAT6 buy by authenticated prior-EOD credits.

    A credit is consumed only when:
      * it was recorded on the immediately preceding EOD from a V233-owned FASTING skip;
      * the first next-day custody observations show a below-cap shed (therefore no EOD clip);
      * shed WHEAT physically contains at least the credit;
      * no intervening current-day unit/market action touches WHEAT before the V233 order;
      * the current action exposes the exact committed V233 ``WHEAT6,HIRE,HIRE`` suffix.

    Ambiguity invalidates the credit rather than carrying it forward. The market row stays
    in the same slot and remains positive (credit <=2), preserving row cardinality/pairing.
    Disabled or unrelated input is exact identity.
    """
    if not enabled or not isinstance(action, dict) or not isinstance(state, dict) or not _default_config(configuration):
        return action
    step, farm, private = _farm_private(observation)
    if step is None:
        return action
    prior_day = state.get("v233_fasting_credit_day")
    credit = state.get("v233_fasting_credit_pending", 0)
    if type(prior_day) is not int or type(credit) is not int or not 1 <= credit <= MAX_DAILY_CREDIT:
        return action
    day, hour = step // 24, step % 24
    if day > prior_day + 1:
        _clear_pending_credit(state, "missed_next_day_window")
        return action
    if day != prior_day + 1:
        return action
    if hour > 2:
        _clear_pending_credit(state, "missed_v233_morning_window")
        return action
    if not state.get("committed") or not _six_v233_sheep(farm):
        _clear_pending_credit(state, "v233_herd_not_intact")
        return action
    shed = private.get("shed")
    if not isinstance(shed, dict):
        _clear_pending_credit(state, "invalid_shed")
        return action
    values = list(shed.values())
    if any(type(v) is not int or v < 0 for v in values):
        _clear_pending_credit(state, "invalid_shed")
        return action
    # Strictly below cap proves the prior EOD drain had spare room; a full shed may have clipped
    # the saved worker WHEAT, so the credit is destroyed immediately and cannot revive later.
    if sum(values) >= 100:
        _clear_pending_credit(state, "eod_custody_ambiguous_full_shed")
        return action
    if type(shed.get("WHEAT", 0)) is not int or shed.get("WHEAT", 0) < credit:
        _clear_pending_credit(state, "saved_wheat_not_physically_present")
        return action

    index = _exact_v233_buy_index(action.get("market"))
    if index is None:
        # Before the V233 order appears, any WHEAT touch can consume/sell the saved unit; never
        # substitute arbitrary remaining parent stock for a lost dedicated credit.
        market = action.get("market")
        market_touches = (isinstance(market, list) and any(
            isinstance(row, list) and len(row) > 1 and row[1] == "WHEAT" for row in market))
        if _touches_wheat_units(action) or market_touches:
            _clear_pending_credit(state, "intervening_wheat_touch")
        return action
    if _touches_wheat_units(action):
        _clear_pending_credit(state, "same_callback_wheat_touch")
        return action
    result = deepcopy(action)
    result["market"][index][2] = 6 - credit
    state["v233_fasting_credit_applied"] = state.get("v233_fasting_credit_applied", 0) + credit
    state["v233_fasting_credit_pending"] = 0
    state["v233_fasting_credit_day"] = None
    return result
