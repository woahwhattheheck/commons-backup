# SPDX-License-Identifier: Apache-2.0
"""R04-EXPANDTAX: conservative BUY_LAND weed-tax gate.

Source-only/default-OFF component.  The filter may remove executable BUY_LAND
rows; it never invents or reorders market rows.  Engine-inert suffix rows are
preserved byte-for-byte and at most one executable BUY_LAND is admitted per
callback, because one pre-callback economic verdict cannot authenticate the
next sequential unlock price.
"""
from __future__ import annotations

import math

TILES_PER_QUADRANT = 25
LAND_ORDER = ("NW", "NE", "SW", "SE")
LAND_PRICES = (1000, 2000, 4000)
DEFAULT_MARKET_LIMIT = 10

# Measured on the pinned official engine; see MEASUREMENT.md.
WEED_TAX_ACTIONS_PER_TILE_DAY = 0.013


def _plain_int(value):
    return type(value) is int


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(float(value))


def should_expand(unlock_price, expected_dollars_per_tile_day,
                  dollars_per_action, days_remaining):
    """Return a gate verdict only from strictly typed finite evidence."""
    if not _finite_number(unlock_price):
        return False
    if not _finite_number(expected_dollars_per_tile_day):
        return False
    if not _finite_number(dollars_per_action):
        return False
    if not _finite_number(days_remaining):
        return False

    C = float(unlock_price)
    E = float(expected_dollars_per_tile_day)
    A = float(dollars_per_action)
    D = float(days_remaining)
    if not (C > 0 and D > 0 and E > 0):
        return False
    weed_tax_dollars = WEED_TAX_ACTIONS_PER_TILE_DAY * max(0.0, A)
    amortized = C / (TILES_PER_QUADRANT * D)
    return E > weed_tax_dollars + amortized


class TrailingBooks:
    """Strict trailing books from cumulative daily notes."""

    WINDOW = 3

    def __init__(self):
        self._days = []  # (money, planted_tiles, actions_total)

    def note_day(self, money, planted_tiles, actions_total):
        if not _finite_number(money):
            raise ValueError("money must be a finite plain number")
        if not _plain_int(planted_tiles) or planted_tiles < 0:
            raise ValueError("planted_tiles must be a plain non-negative int")
        if not _plain_int(actions_total) or actions_total < 0:
            raise ValueError("actions_total must be a plain non-negative int")
        if self._days and actions_total < self._days[-1][2]:
            raise ValueError("actions_total must be monotone")
        self._days.append((float(money), planted_tiles, actions_total))
        del self._days[:-self.WINDOW - 1]

    def _deltas(self):
        out = []
        for (m1, p1, a1), (m0, _p0, a0) in zip(self._days[1:], self._days[:-1]):
            out.append((m1 - m0, p1, a1 - a0))
        return out

    @property
    def rev_per_tile_day(self):
        ds = self._deltas()
        if not ds:
            return 0.0
        vals = [max(0.0, dm) / max(1, p) for dm, p, _ in ds]
        return sum(vals) / len(vals)

    @property
    def dollars_per_action(self):
        ds = self._deltas()
        if not ds:
            return 0.0
        vals = [dm / max(1, da) for dm, _, da in ds]
        return sum(vals) / len(vals)

    def snapshot(self):
        return {
            "rev_per_tile_day": self.rev_per_tile_day,
            "dollars_per_action": self.dollars_per_action,
            "days": len(self._days),
        }


def _market_prefix_limit(configuration):
    value = configuration.get("maxMarketOrdersPerTurn", DEFAULT_MARKET_LIMIT)
    if not _plain_int(value):
        raise ValueError("maxMarketOrdersPerTurn must be a plain int")
    return max(1, value)


def _farm_of(observation):
    if not isinstance(observation, dict):
        raise ValueError("observation must be a dict")
    if "farm" in observation:
        farm = observation["farm"]
    else:
        farms = observation.get("farms")
        player = observation.get("player")
        if not isinstance(farms, list) or not _plain_int(player):
            raise ValueError("observation must bind farm or farms/player")
        if player < 0 or player >= len(farms):
            raise ValueError("player outside farms")
        farm = farms[player]
    if not isinstance(farm, dict):
        raise ValueError("farm must be a dict")
    return farm


def _canonical_unlocked(observation):
    farm = _farm_of(observation)
    unlocked = farm.get("unlocked_quadrants")
    if not isinstance(unlocked, list):
        raise ValueError("unlocked_quadrants must be a list")
    if not 1 <= len(unlocked) <= len(LAND_ORDER):
        raise ValueError("unlocked_quadrants length is impossible")
    expected = list(LAND_ORDER[:len(unlocked)])
    if unlocked != expected:
        raise ValueError("unlocked_quadrants must be the canonical prefix")
    return unlocked


def next_unlock_price(observation):
    """Price of the next canonical quadrant, or None when all are unlocked.

    Malformed observations raise ValueError so callers cannot confuse malformed
    custody with the all-unlocked state.
    """
    unlocked = _canonical_unlocked(observation)
    paid_unlocks = len(unlocked) - 1
    if paid_unlocks >= len(LAND_PRICES):
        return None
    return LAND_PRICES[paid_unlocks]


def _days_remaining(observation, configuration):
    tpd = configuration.get("turnsPerDay", 24)
    steps = configuration.get("episodeSteps", 720)
    if not _plain_int(tpd) or tpd <= 0:
        raise ValueError("turnsPerDay must be a plain positive int")
    if not _plain_int(steps) or steps <= 0:
        raise ValueError("episodeSteps must be a plain positive int")

    if not isinstance(observation, dict):
        raise ValueError("observation must be a dict")
    day = observation.get("day")
    step = observation.get("step")
    if day is not None and (not _plain_int(day) or day < 0):
        raise ValueError("day must be a plain non-negative int")
    if step is not None and (not _plain_int(step) or step < 0):
        raise ValueError("step must be a plain non-negative int")
    if day is None:
        if step is None:
            raise ValueError("observation must bind day or step")
        day = step // tpd
    elif step is not None and day != step // tpd:
        raise ValueError("day/step mismatch")
    total_days = steps // tpd
    return max(0, total_days - day)


def _is_buy_land(order):
    return isinstance(order, list) and bool(order) and order[0] == "BUY_LAND"


def _filter_prefix(prefix, *, allow_one):
    kept = []
    land_kept = False
    for order in prefix:
        if not _is_buy_land(order):
            kept.append(order)
            continue
        if allow_one and not land_kept:
            kept.append(order)
            land_kept = True
    return kept


def filter_market_orders(action, observation, configuration, books):
    """Conservatively gate executable BUY_LAND rows.

    OFF is exact identity.  When enabled, only the official executable market
    prefix may change and its relative order is preserved.  A trustworthy
    pre-callback verdict may admit only the first executable BUY_LAND; later
    BUY_LAND rows require a post-commit price/state that this source-only gate
    deliberately does not fabricate.
    """
    if not isinstance(configuration, dict):
        return action
    if configuration.get("r04_expandtax") is not True:
        return action
    if not isinstance(action, dict):
        return action
    market = action.get("market")
    if not isinstance(market, list) or not market:
        return action

    try:
        limit = _market_prefix_limit(configuration)
    except (ValueError, TypeError, OverflowError):
        return action

    stop = min(len(market), limit)
    prefix = market[:stop]
    suffix = market[stop:]
    if not any(_is_buy_land(order) for order in prefix):
        return action

    try:
        price = next_unlock_price(observation)
        if price is None:
            allow_one = False
        else:
            if not isinstance(books, TrailingBooks):
                allow_one = False
            else:
                E = books.rev_per_tile_day
                A = books.dollars_per_action
                D = _days_remaining(observation, configuration)
                allow_one = should_expand(price, E, A, D)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError):
        # The feature is enabled, but evidence custody is malformed. Never mint
        # a positive expansion verdict from ambiguous evidence.
        allow_one = False

    kept_prefix = _filter_prefix(prefix, allow_one=allow_one)
    new_market = kept_prefix + suffix
    if new_market == market:
        return action
    out = dict(action)
    out["market"] = new_market
    return out
