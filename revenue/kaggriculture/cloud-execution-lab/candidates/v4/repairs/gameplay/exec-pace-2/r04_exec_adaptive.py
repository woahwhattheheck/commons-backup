# SPDX-License-Identifier: Apache-2.0
"""EXEC-PACE-2 contiguous-public-price state repair; not runtime activation.

Same 25-sample endpoint slope and 0.03 threshold as raw/ donor 0ef55114.
Only complete, consecutive observations for one public player may certify a
trend. Missing/invalid quotes break that good's history, not synthesize zero.
Invalid time/player/market state clears all evidence. Rewinds, gaps, player
changes and conflicting same-step observations restart warmup. Identical
same-step observations are idempotent. Call reset() at known game boundaries;
no public-only observer can distinguish every reused-process/new-game case.

This package does not install the helper, change the existing default-OFF
key, or establish that delaying any sale improves competitive margin.
"""
from __future__ import annotations

from collections.abc import Mapping
import math

SLOPE_THRESHOLD = 0.03
HIST_WINDOW = 25
GOODS = ("WOOL", "MILK", "STRAWBERRY", "MELON", "EGG", "CARROT", "TOMATO")

_phist = {}
_last_step = [-1]
_last_player = [None]
_last_prices = [None]


def reset():
    """Invalidate all observation evidence at a known game boundary."""
    _phist.clear()
    _last_step[0] = -1
    _last_player[0] = None
    _last_prices[0] = None


def note_prices(observation):
    """Record one public observation, failing closed without input mutation."""
    try:
        if not isinstance(observation, Mapping):
            reset()
            return
        step = observation.get("step")
        player = observation.get("player")
        market = observation.get("market")
        if (type(step) is not int or step < 0 or type(player) is not int
                or player not in (0, 1) or not isinstance(market, Mapping)):
            reset()
            return
        prices = market.get("prices")
        if not isinstance(prices, Mapping):
            reset()
            return
        # Official engine public quotes are positive literal integers.
        values = tuple(prices.get(good) for good in GOODS)
        values = tuple(px if type(px) is int and px >= 1 else None
                       for px in values)
        if player == _last_player[0] and step == _last_step[0]:
            if values == _last_prices[0]:
                return
            reset()
        elif player != _last_player[0] or step != _last_step[0] + 1:
            reset()
        _last_step[0] = step
        _last_player[0] = player
        _last_prices[0] = values
        for good, px in zip(GOODS, values):
            if px is None:
                _phist.pop(good, None)
                continue
            hist = _phist.setdefault(good, [])
            hist.append(px)
            if len(hist) > HIST_WINDOW:
                del hist[:-HIST_WINDOW]
    except Exception:
        reset()


def slope(good):
    """Return the unchanged endpoint slope, or None without complete evidence."""
    try:
        hist = _phist.get(good)
        if hist is None or len(hist) != HIST_WINDOW:
            return None
        value = (hist[-1] - hist[0]) / (HIST_WINDOW - 1)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def rising(good):
    """True only for a complete eligible window with slope strictly over 0.03."""
    value = slope(good)
    return value is not None and value > SLOPE_THRESHOLD
