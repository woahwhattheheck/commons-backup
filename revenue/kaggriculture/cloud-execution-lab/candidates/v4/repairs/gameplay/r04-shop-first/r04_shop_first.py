# SPDX-License-Identifier: Apache-2.0
"""R04-SHOP-FIRST: reserve shed inventory for live town-shop procurement.

Source-only/default-OFF component.  The filter may REDUCE positive SELL
quantities for shop-demand products; it never invents orders, never reorders
rows, and never increases a quantity.  Engine-inert suffix rows are preserved
byte-for-byte.

Mechanism (live-only, measured from Kaggle replays — NOT in the pinned
reference engine): town shops auto-buy player shed inventory at large premiums
over market quotes (ep 108114108: WOOL $123/u vs $1.93 market, STRAWBERRY $92
vs $2.04, MELON $79 vs $1.67, ...; our d27-29 bulk market dumps realize
~$0.6/u).  Opponents running the SHOP-FARMER archetype keep the shed stocked
for shop ticks and route ~everything through them; we empty the shed into
market dumps.  This lane keeps a per-product reserve floor in the shed for
shop ticks and only SELLs the overflow.

Fail-closed: the lane engages only after the composer-observed ShopLedger has
seen at least one shop tick within SHOP_LIVENESS_STEPS.  On the pinned engine
(no shed-procurement mechanic) the ledger never fires, so the filter is a
provable no-op there.  Malformed observations, missing shed state, or a
disabled/missing config key all yield the action object unchanged.
"""
from __future__ import annotations

import math

CONFIG_KEY = "r04_shop_first"

# Priority by replay-measured absolute premium ($/u): WOOL 123, STRAWBERRY 92,
# MELON 79, EGG 52, TOMATO 50, CARROT 49, FERTILIZER 47, WHEAT 42, MILK 40.
# See MEASUREMENT.md.  (MILK's 4000x multiple is the largest relative premium
# but its absolute $40/u ranks last; absolute dollars drive the reserve.)
SHOP_PRIORITY = (
    "WOOL",
    "STRAWBERRY",
    "MELON",
    "EGG",
    "TOMATO",
    "CARROT",
    "FERTILIZER",
    "WHEAT",
    "MILK",
)

# Replay-measured shop buy prices ($/u, ep 108114108).  Used by the
# replay-derived shop model (shop_model.py); the filter itself needs only the
# reserve floors below, not prices.
SHOP_PRICES = {
    "WOOL": 123.0,
    "STRAWBERRY": 92.0,
    "MELON": 79.0,
    "EGG": 52.0,
    "TOMATO": 50.0,
    "CARROT": 49.0,
    "FERTILIZER": 47.0,
    "WHEAT": 42.0,
    "MILK": 40.0,
}

# Units of each product to keep in the shed for shop ticks.  Anchored to the
# observed tick size (ep 108114108 step 341->342 cleared 24 WOOL + 8 STRAWBERRY
# = 32 units in one tick).  Top-premium products get the largest floors.
# These are floors on SELLing, not targets to acquire: if the shed holds fewer
# units, the filter simply sells nothing of that product.
SHOP_RESERVE = {
    "WOOL": 24,
    "STRAWBERRY": 24,
    "MELON": 20,
    "EGG": 12,
    "TOMATO": 12,
    "CARROT": 12,
    "FERTILIZER": 8,
    "WHEAT": 8,
    "MILK": 8,
}

# Shop procurement counts as "live" only if a tick was observed within this
# many steps.  Pinned-engine default townShopSellInterval is 4, so 48 steps =
# 12 missed ticks of silence before reserves release and normal dumping
# resumes.  Prevents holding inventory forever if the mechanic is absent.
SHOP_LIVENESS_STEPS = 48


def _plain_int(value):
    return type(value) is int


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(float(value))


def _shed_of(observation):
    """Extract the private shed dict, or None if malformed."""
    if not isinstance(observation, dict):
        return None
    private = observation.get("private")
    if not isinstance(private, dict):
        return None
    shed = private.get("shed")
    if not isinstance(shed, dict):
        return None
    return shed


def _step_of(observation):
    step = observation.get("step") if isinstance(observation, dict) else None
    if type(step) is not int or step < 0:
        return None
    return step


class ShopLedger:
    """Composer-owned per-step shop-tick detector.

    Feed once per step, at observation time (before market-order
    construction), via note_step().  A shop tick is a shed decrease that the
    step's own SELL quantities cannot explain, coincident with a positive
    money delta — i.e. the live engine bought from the shed outside the
    market.  (Market SELL settlement is delayed several steps, so same-step
    money deltas do not come from our own SELLs.)

    Before any tick is ever observed, shop_live() is False and the filter is
    a no-op: this is what makes the lane provably inert on the pinned engine.
    """

    def __init__(self):
        self._last_tick_step = None
        self._ticks_seen = 0

    def note_step(self, step, shed_before, shed_after, sells_issued,
                  money_delta):
        """Record one step transition.

        step: int, current observation step.
        shed_before / shed_after: dicts product -> int units.
        sells_issued: dict product -> int units issued as SELL this step.
        money_delta: float, money(step) - money(step-1).
        """
        if type(step) is not int or step < 0:
            raise ValueError("step must be a non-negative int")
        if not isinstance(shed_before, dict) or not isinstance(shed_after, dict):
            raise ValueError("shed_before/after must be dicts")
        if not isinstance(sells_issued, dict):
            raise ValueError("sells_issued must be a dict")
        if not _finite_number(money_delta):
            raise ValueError("money_delta must be a finite number")

        tick = False
        for product in SHOP_PRIORITY:
            before = shed_before.get(product, 0)
            after = shed_after.get(product, 0)
            if type(before) is not int or type(after) is not int:
                continue
            drop = before - after
            if drop <= 0:
                continue
            sold = sells_issued.get(product, 0)
            if type(sold) is not int:
                sold = 0
            unexplained = drop - max(0, sold)
            if unexplained > 0 and float(money_delta) > 0:
                tick = True
                break
        if tick:
            self._last_tick_step = step
            self._ticks_seen += 1
        return tick

    @property
    def ticks_seen(self):
        return self._ticks_seen

    @property
    def last_tick_step(self):
        return self._last_tick_step

    def shop_live(self, step):
        """True iff a shop tick was observed within SHOP_LIVENESS_STEPS."""
        if type(step) is not int or step < 0:
            return False
        if self._last_tick_step is None:
            return False
        return 0 <= step - self._last_tick_step <= SHOP_LIVENESS_STEPS

    def snapshot(self):
        return {
            "ticks_seen": self._ticks_seen,
            "last_tick_step": self._last_tick_step,
        }


def _cap_sells_for_reserve(market_rows, shed):
    """Cap positive SELL quantities so the reserve floor survives.

    Returns a new market row list; the input is never mutated.  Rows that are
    not well-formed positive SELLs of shop-demand products pass through
    untouched.
    """
    remaining = {}
    for product in SHOP_PRIORITY:
        qty = shed.get(product, 0)
        remaining[product] = qty if type(qty) is int and qty > 0 else 0

    out = []
    for row in market_rows:
        if (
            isinstance(row, (list, tuple))
            and len(row) >= 3
            and row[0] == "SELL"
            and isinstance(row[1], str)
            and row[1] in SHOP_RESERVE
            and type(row[2]) is int
            and row[2] > 0
        ):
            product = row[1]
            reserve = SHOP_RESERVE[product]
            can_sell = remaining[product] - reserve
            if can_sell < 0:
                can_sell = 0
            new_qty = row[2] if row[2] <= can_sell else can_sell
            remaining[product] -= new_qty
            new_row = list(row)
            new_row[2] = new_qty
            out.append(new_row)
        else:
            out.append(row)
    return out


def filter_market_orders(action, observation, cfg, ledger=None):
    """Apply the shop-first reserve at the market-order surface.

    Returns the action object unchanged unless ALL of the following hold:
      - cfg[CONFIG_KEY] is exactly True (default OFF),
      - observation carries a well-formed step and private shed,
      - ledger is a ShopLedger with shop_live(step) True.

    Otherwise SELL quantities of shop-demand products are capped so the
    SHOP_RESERVE floor remains in the shed for shop ticks.
    """
    if not isinstance(cfg, dict) or cfg.get(CONFIG_KEY) is not True:
        return action
    if not isinstance(action, dict):
        return action
    market = action.get("market")
    if not isinstance(market, list):
        return action
    shed = _shed_of(observation)
    if shed is None:
        return action
    step = _step_of(observation)
    if step is None:
        return action
    if not isinstance(ledger, ShopLedger) or not ledger.shop_live(step):
        return action

    capped = _cap_sells_for_reserve(market, shed)
    if capped == market:
        return action
    new_action = dict(action)
    new_action["market"] = capped
    return new_action
