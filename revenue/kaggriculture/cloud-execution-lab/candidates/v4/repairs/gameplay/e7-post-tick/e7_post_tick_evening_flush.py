#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""E7 experiment: move only safe hour-23 R04 evening-flush extras past the town tick.

The official interpreter executes player market rows first, then town consumption, then
refreshes prices.  Live R04 adds an outer EVENING_FLUSH layer at hours 21, 22 and 23 for
WOOL/MILK/STRAWBERRY/MELON.  E7 preserves the complete inner POLICY_AGENT/E184 path and
replaces only that outer layer:

* hours 21-22 are delegated byte-semantically to R04's existing ``evening_flush``;
* hour 23 may withhold only the *extra* rows that R04 evening_flush would have prepended;
* withholding is allowed only when exact own state proves no worker inventory transfer,
  no inventory-producing worker action, and no shed-adding market buy can make the
  retained units change end-of-day shed-overflow behavior;
* parent market rows must be explicit list rows with no falsey placeholders; ambiguous raw
  lockstep-slot semantics fail closed to incumbent evening flush;
* at next-day hour 1, after the hour-0 town tick, E7 sells at most the withheld quantity
  still present in projected shed stock. Existing same-item SELL rows are topped up in
  place; otherwise a new row is appended only when a literal trailing slot is available;
* withholding requires the release callback to fit through episodeSteps - 2;
* release rechecks the supported configuration and reports partial shortfalls;
* existing native/E184 rows are never removed, compacted, reduced, or reindexed.

This is deliberately an experiment, not a theorem that post-tick prices always improve:
a rival can still trade at hour 0.  Telemetry records the observed pre/post quote delta
so the paired economics gate can decide the lane.  Unknown/nonstandard configuration or
unsafe capacity/market shape preserves incumbent behavior.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
V4 = HERE.parents[2]
OVERLAY = V4 / "donor" / "overlay"
ROUTER_PATH = OVERLAY / "r04_full_router.py"
ROUTER_BLOB_SHA = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"


def _git_blob_sha(path):
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


if not ROUTER_PATH.is_file():
    raise ImportError(f"canonical V4 R04 donor missing: {ROUTER_PATH}")
if _git_blob_sha(ROUTER_PATH) != ROUTER_BLOB_SHA:
    raise ImportError("canonical V4 R04 donor drifted from the authenticated E7 dependency")
if str(OVERLAY) not in sys.path:
    sys.path.insert(0, str(OVERLAY))

import r04_full_router as r04  # noqa: E402

try:
    _R04_LOADED_FROM = Path(r04.__file__).resolve()
except (AttributeError, TypeError):
    raise ImportError("r04_full_router resolved without a canonical source path") from None
if _R04_LOADED_FROM != ROUTER_PATH.resolve():
    raise ImportError(
        f"r04_full_router shadowed: expected {ROUTER_PATH}, got {_R04_LOADED_FROM}"
    )

TURNS_PER_DAY = 24
SHED_CAPACITY = 100
MAX_ORDERS = 10
WITHHOLD_HOUR = 23
RELEASE_HOUR = 1
DEFAULT_EPISODE_STEPS = 720
UNSAFE_WORK = {"HARVEST", "PICKUP", "DROP", "PLACE", "COLLECT_FERTILIZER"}
SHED_ADDING_MARKET = {"BUY_PRODUCT", "BUY_ANIMAL"}


def _cfg(configuration, name, default):
    if configuration is None:
        return default
    if isinstance(configuration, dict):
        return configuration.get(name, default)
    return getattr(configuration, name, default)


def _exact_int(configuration, name, expected):
    value = _cfg(configuration, name, expected)
    return type(value) is int and value == expected


def _standard_configuration(configuration):
    """Bind only the engine clocks/capacity/default market E7's proof depends on."""
    if not _exact_int(configuration, "turnsPerDay", TURNS_PER_DAY):
        return False
    if not _exact_int(configuration, "shedCapacity", SHED_CAPACITY):
        return False
    if not _exact_int(configuration, "maxMarketOrdersPerTurn", MAX_ORDERS):
        return False
    if not _exact_int(configuration, "townCenterSellInterval", TURNS_PER_DAY):
        return False
    market_params = _cfg(configuration, "marketParams", None)
    return market_params is None or (type(market_params) is dict and not market_params)


def _release_is_executable(configuration, release_step):
    """The official interpreter finishes after action episodeSteps - 2.

    Do not coerce booleans, numeric strings or floats into a horizon proof.
    Equality is valid: a sale can execute on the final action callback.
    """
    episode_steps = _cfg(configuration, "episodeSteps", DEFAULT_EPISODE_STEPS)
    return (
        type(episode_steps) is int
        and episode_steps >= 2
        and release_step <= episode_steps - 2
    )


def _strict_step_player(observation):
    if not isinstance(observation, dict):
        return None
    step = observation.get("step")
    player = observation.get("player")
    if type(step) is not int or type(player) is not int or step < 0 or player < 0:
        return None
    return step, player


def _normalized_market(action):
    """Return a detached market copy only when raw lockstep slots are unambiguous.

    Falsey placeholders are semantically meaningful raw row indexes in the official
    market engine, so E7 deliberately refuses to normalize/compact them.
    """
    if not isinstance(action, dict):
        return None
    raw = action.get("market", [])
    if not isinstance(raw, list):
        return None
    market = []
    for order in raw:
        if not order or not isinstance(order, list):
            return None
        market.append(list(order))
    return market


def _incumbent_flush(observation, action):
    """Restore the live R04 outer layer when E7 declines to intervene."""
    parsed = _strict_step_player(observation)
    if parsed is None:
        return action
    step, _ = parsed
    if step % TURNS_PER_DAY in r04.FLUSH_HOURS:
        return r04.evening_flush(observation, action)
    return action


def _flush_extras(observation, action):
    """Extract only rows prepended by incumbent evening_flush, fail-closed on drift."""
    base_market = _normalized_market(action)
    if base_market is None:
        return None
    live = r04.evening_flush(observation, action)
    live_market = _normalized_market(live)
    if live_market is None or len(live_market) < len(base_market):
        return None
    extra_count = len(live_market) - len(base_market)
    if live_market[extra_count:] != base_market:
        return None
    extras = live_market[:extra_count]
    checked = []
    for row in extras:
        if len(row) < 3 or row[0] != "SELL" or row[1] not in r04.FLUSH_ITEMS:
            return None
        qty = row[2]
        if type(qty) is not int or qty <= 0:
            return None
        checked.append(["SELL", row[1], qty])
    return checked


def _empty_worker_inventories(observation):
    try:
        private = observation["private"]
        inventories = private["inventories"]
    except (KeyError, TypeError):
        return False
    if not isinstance(inventories, list):
        return False
    for inv in inventories:
        if not isinstance(inv, dict):
            return False
        for qty in inv.values():
            if type(qty) is not int or qty < 0:
                return False
            if qty:
                return False
    return True


def _worker_actions_safe(action):
    if not isinstance(action, dict):
        return False
    farmer = action.get("farmer") or ["PASS"]
    hands = action.get("hands") or []
    if not isinstance(hands, list):
        return False
    for work in [farmer, *hands]:
        if not isinstance(work, (list, tuple)) or not work:
            return False
        op = work[0]
        if not isinstance(op, str) or op in UNSAFE_WORK:
            return False
    return True


def _market_does_not_add_shed(action):
    market = _normalized_market(action)
    if market is None or len(market) > MAX_ORDERS:
        return False
    for order in market:
        if not isinstance(order[0], str):
            return False
        if order[0] in SHED_ADDING_MARKET:
            return False
    return True


def _shed_shape_safe(observation):
    try:
        shed = observation["private"]["shed"]
    except (KeyError, TypeError):
        return False
    if not isinstance(shed, dict):
        return False
    total = 0
    for qty in shed.values():
        if type(qty) is not int or qty < 0:
            return False
        total += qty
    return total <= SHED_CAPACITY


def _safe_to_cross_midnight(observation, action, configuration):
    """Conservative sufficient condition: retaining flush stock cannot alter EOD overflow."""
    return (
        _standard_configuration(configuration)
        and _shed_shape_safe(observation)
        and _empty_worker_inventories(observation)
        and _worker_actions_safe(action)
        and _market_does_not_add_shed(action)
    )


def _price_map(observation, items):
    try:
        prices = observation["market"]["prices"]
    except (KeyError, TypeError):
        return None
    if not isinstance(prices, dict):
        return None
    result = {}
    for item in items:
        value = prices.get(item)
        if type(value) is not int or value < 1:
            return None
        result[item] = value
    return result


class PostTickEveningFlush:
    def __init__(self, parent):
        self.parent = parent
        self.players = {}
        self.telemetry = Counter()
        self.events = []

    def _event(self, payload):
        if len(self.events) < 256:
            self.events.append(dict(payload))

    def _state(self, player, step):
        state = self.players.get(player)
        if state is None or step <= state["last_step"]:
            state = {"last_step": -1, "pending": None}
            self.players[player] = state
        state["last_step"] = step
        return state

    def _release(self, observation, action, state, step, configuration=None):
        pending = state.get("pending")
        if not pending or pending["source_step"] + 2 != step:
            return action
        state["pending"] = None
        if not (_standard_configuration(configuration)
                and _release_is_executable(configuration, step)):
            self.telemetry["release_config_reject"] += 1
            return action
        market = _normalized_market(action)
        if market is None or len(market) > MAX_ORDERS:
            self.telemetry["release_malformed_market"] += 1
            return action
        try:
            view = r04.FarmView(observation)
            stock = r04.projected_shed(action, view)
        except (KeyError, TypeError, ValueError, IndexError):
            self.telemetry["release_malformed_state"] += 1
            return action

        selling = {}
        same_item_row = {}
        for idx, row in enumerate(market):
            if len(row) >= 3 and row[0] == "SELL" and row[1] in r04.FLUSH_ITEMS:
                if type(row[2]) is not int or row[2] <= 0:
                    self.telemetry["release_malformed_sell"] += 1
                    return action
                item = row[1]
                selling[item] = selling.get(item, 0) + row[2]
                same_item_row.setdefault(item, idx)

        current_prices = _price_map(observation, [row[1] for row in pending["rows"]])
        if current_prices is None:
            self.telemetry["release_malformed_price"] += 1
            return action

        released = {}
        shortfall = {}
        for _, item, wanted in pending["rows"]:
            available = max(0, int(stock.get(item, 0)) - selling.get(item, 0))
            qty = min(wanted, available)
            if qty <= 0:
                shortfall[item] = wanted
                continue
            idx = same_item_row.get(item)
            if idx is not None:
                market[idx][2] += qty
            elif len(market) < MAX_ORDERS:
                market.append(["SELL", item, qty])
            else:
                shortfall[item] = wanted
                continue
            # Shortfall counts units not incrementally issued by E7, including
            # units already covered by parent SELLs; it is not lost cash/stock.
            if qty < wanted:
                shortfall[item] = wanted - qty
            selling[item] = selling.get(item, 0) + qty
            released[item] = released.get(item, 0) + qty
            self.telemetry["released_rows"] += 1
            self.telemetry["released_units"] += qty
            pre = pending["prices"][item]
            post = current_prices[item]
            self.telemetry["quote_uplift_units"] += qty * (post - pre)

        if shortfall:
            self.telemetry["release_shortfall_rows"] += len(shortfall)
            self.telemetry["release_shortfall_units"] += sum(shortfall.values())
        self._event({
            "kind": "release",
            "step": step,
            "source_step": pending["source_step"],
            "released": released,
            "shortfall": shortfall,
            "pre_prices": pending["prices"],
            "post_prices": current_prices,
        })
        if not released:
            return action
        result = dict(action)
        result["market"] = market
        return result

    def __call__(self, observation, configuration=None):
        action = self.parent(observation, configuration)
        parsed = _strict_step_player(observation)
        if parsed is None:
            self.telemetry["malformed_observation"] += 1
            return action
        step, player = parsed
        state = self._state(player, step)
        pending = state.get("pending")
        if pending and step > pending["source_step"] + 2:
            state["pending"] = None
            self.telemetry["stale_pending"] += 1

        hour = step % TURNS_PER_DAY
        if hour in (21, 22):
            return r04.evening_flush(observation, action)

        if hour == RELEASE_HOUR:
            return self._release(observation, action, state, step, configuration)

        if hour != WITHHOLD_HOUR:
            return action

        live = _incumbent_flush(observation, action)
        if not _standard_configuration(configuration):
            self.telemetry["config_reject"] += 1
            return live
        if not _release_is_executable(configuration, step + 2):
            self.telemetry["horizon_reject"] += 1
            return live
        extras = _flush_extras(observation, action)
        if extras is None:
            self.telemetry["flush_shape_reject"] += 1
            return live
        if not extras:
            return live
        if not _safe_to_cross_midnight(observation, action, configuration):
            self.telemetry["capacity_reject"] += 1
            return live
        prices = _price_map(observation, [row[1] for row in extras])
        if prices is None:
            self.telemetry["price_reject"] += 1
            return live

        state["pending"] = {
            "source_step": step,
            "rows": [list(row) for row in extras],
            "prices": prices,
        }
        units = sum(row[2] for row in extras)
        self.telemetry["withheld_rows"] += len(extras)
        self.telemetry["withheld_units"] += units
        self._event({
            "kind": "withhold",
            "step": step,
            "rows": [list(row) for row in extras],
            "prices": prices,
        })
        # With explicit non-falsey list rows, incumbent flush differs only by its extras.
        return action


def install(parent, enabled=False):
    """Install E7. Only literal True activates; every other value is exact identity."""
    if enabled is not True:
        return parent
    if parent is None or not callable(parent):
        raise TypeError("E7 parent must be callable")
    return PostTickEveningFlush(parent)
