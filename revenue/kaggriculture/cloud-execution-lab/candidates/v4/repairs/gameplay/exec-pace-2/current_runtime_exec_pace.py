# SPDX-License-Identifier: Apache-2.0
"""Current-runtime EXEC-PACE-2 state and conservative sale-advance gate.

This module is deliberately independent of the legacy r04 router/materializer.
It preserves the landed detector's seven goods, 25 contiguous observations and
0.03 endpoint-slope threshold, but owns the state per runtime consumer instance.
The plan gate blocks only schedules that move cumulative units earlier than the
current scheduler reference while a product is rising.  Forced-feasibility and
all other policy decisions remain caller-owned.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

SLOPE_THRESHOLD = 0.03
HIST_WINDOW = 25
GOODS = ("WOOL", "MILK", "STRAWBERRY", "MELON", "EGG", "CARROT", "TOMATO")


class PriceTrendState:
    """Per-consumer contiguous public-price evidence.

    Invalid stream identity clears all evidence.  A missing/invalid quote clears
    only that product.  Identical duplicate callbacks are idempotent; conflicting
    same-step callbacks, gaps, rewinds or seat changes restart warmup.
    """

    __slots__ = ("_hist", "_last_step", "_last_player", "_last_prices")

    def __init__(self):
        self._hist = {}
        self._last_step = -1
        self._last_player = None
        self._last_prices = None

    def reset(self):
        self._hist.clear()
        self._last_step = -1
        self._last_player = None
        self._last_prices = None

    def note_prices(self, observation):
        try:
            if not isinstance(observation, Mapping):
                self.reset()
                return False
            step = observation.get("step")
            player = observation.get("player")
            market = observation.get("market")
            if (type(step) is not int or step < 0 or type(player) is not int
                    or player not in (0, 1) or not isinstance(market, Mapping)):
                self.reset()
                return False
            prices = market.get("prices")
            if not isinstance(prices, Mapping):
                self.reset()
                return False
            values = tuple(prices.get(good) for good in GOODS)
            values = tuple(px if type(px) is int and px >= 1 else None for px in values)

            if player == self._last_player and step == self._last_step:
                if values == self._last_prices:
                    return True
                self.reset()
            elif player != self._last_player or step != self._last_step + 1:
                self.reset()

            self._last_step = step
            self._last_player = player
            self._last_prices = values
            for good, px in zip(GOODS, values):
                if px is None:
                    self._hist.pop(good, None)
                    continue
                hist = self._hist.setdefault(good, [])
                hist.append(px)
                if len(hist) > HIST_WINDOW:
                    del hist[:-HIST_WINDOW]
            return True
        except Exception:
            self.reset()
            return False

    def slope(self, good):
        try:
            hist = self._hist.get(good)
            if hist is None or len(hist) != HIST_WINDOW:
                return None
            value = (hist[-1] - hist[0]) / (HIST_WINDOW - 1)
            return value if math.isfinite(value) else None
        except Exception:
            return None

    def rising(self, good):
        value = self.slope(good)
        return value is not None and value > SLOPE_THRESHOLD

    def diagnostics(self):
        return {
            "last_step": self._last_step,
            "last_player": self._last_player,
            "warm": {good: len(self._hist.get(good, ())) == HIST_WINDOW for good in GOODS},
            "slopes": {good: self.slope(good) for good in GOODS},
        }


def _normalized_plan(plan):
    """Return a sorted integer schedule, rejecting malformed/negative rows."""
    if not isinstance(plan, Sequence) or isinstance(plan, (str, bytes, bytearray)):
        raise ValueError("plan must be a sequence")
    merged = {}
    for row in plan:
        if (not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray))
                or len(row) != 2):
            raise ValueError("plan row must be (step, quantity)")
        step, quantity = row
        if type(step) is not int or type(quantity) is not int or step < 0 or quantity < 0:
            raise ValueError("plan values must be nonnegative literal integers")
        merged[step] = merged.get(step, 0) + quantity
    return tuple((step, merged[step]) for step in sorted(merged) if merged[step])


def cumulative_advance(reference, candidate):
    """Return the first prefix where candidate sells more units earlier.

    This detects a true temporal advance even when the candidate does not add
    quantity at the current step (e.g. t+5 -> t+2).  Total quantity differences
    fail closed as non-comparable rather than being called an advance.
    """
    ref = _normalized_plan(reference)
    cand = _normalized_plan(candidate)
    ref_total = sum(q for _t, q in ref)
    cand_total = sum(q for _t, q in cand)
    if ref_total != cand_total:
        return None
    ref_map = dict(ref)
    cand_map = dict(cand)
    ref_seen = cand_seen = 0
    for step in sorted(set(ref_map) | set(cand_map)):
        ref_seen += ref_map.get(step, 0)
        cand_seen += cand_map.get(step, 0)
        if cand_seen > ref_seen:
            return {
                "step": step,
                "candidate_cumulative": cand_seen,
                "reference_cumulative": ref_seen,
                "delta": cand_seen - ref_seen,
            }
    return None


def gate_plan(state, item, reference, candidate):
    """Conservatively veto a temporal sale advance for a rising product.

    The caller must bypass this gate for forced-feasibility plans.  Malformed
    plans fail open to the existing scheduler (with a diagnostic) because this
    optional experiment must never invalidate a plan the current runtime needs.
    """
    report = {
        "item": item,
        "rising": False,
        "blocked": False,
        "reason": "not-rising",
        "slope": None,
        "advance": None,
    }
    if state is None or item not in GOODS:
        report["reason"] = "unsupported-or-disabled"
        return candidate, report
    report["slope"] = state.slope(item)
    report["rising"] = state.rising(item)
    if not report["rising"]:
        return candidate, report
    try:
        advance = cumulative_advance(reference, candidate)
    except Exception as error:
        report["reason"] = "noncomparable-plan"
        report["error"] = type(error).__name__
        return candidate, report
    report["advance"] = advance
    if advance is None:
        report["reason"] = "no-temporal-advance"
        return candidate, report
    report["blocked"] = True
    report["reason"] = "rising-product-temporal-advance"
    return reference, report


def apply_candidate(state, item, reference, candidate, info):
    """Apply EXEC-PACE to one optimizer candidate without changing loop control.

    Forced-feasibility always bypasses the timing gate.  A blocked candidate is
    replaced by the exact reference schedule and marked ineligible through the
    scheduler's existing ``accepted`` contract, so the caller can continue its
    ordinary diagnostics/ranking path rather than jumping over loop semantics.
    """
    current_info = dict(info or {})
    if current_info.get("forced_feasibility", False):
        current_info["exec_pace"] = {
            "item": item, "rising": False, "blocked": False,
            "reason": "forced-feasibility-bypass", "slope": None, "advance": None,
        }
        return candidate, current_info
    selected, report = gate_plan(state, item, reference, candidate)
    current_info["exec_pace"] = report
    if report.get("blocked"):
        selected = reference
        current_info["plan"] = list(reference)
        current_info["accepted"] = False
        current_info["acceptance_rule"] = "exec_pace_block"
    return selected, current_info
