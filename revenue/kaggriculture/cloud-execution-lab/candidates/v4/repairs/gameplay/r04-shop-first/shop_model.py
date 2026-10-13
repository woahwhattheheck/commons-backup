# SPDX-License-Identifier: Apache-2.0
"""Replay-derived town-shop procurement model for r04_shop_first.

The pinned reference engine has NO shed->shop procurement mechanic, so the
standard frozen 16-cell engine gate cannot measure this lane.  This harness
implements option (a): a replay-derived shop model with DOCUMENTED
assumptions, measuring the lane's d27-29 dump-window decision
(reserve-for-shop vs dump-to-market) on our own replay-measured production.

This is a MODEL measurement, not a full-engine gate.  It is honest about what
it is: every assumption is listed in ASSUMPTIONS below with its replay
source.  No part of this output may be presented as an engine-gate margin.

ASSUMPTIONS
-----------
A1. Shop tick cadence: every 24 steps.  Source: ep 108114108 replay, 37
    detected major shed-procurement ticks, modal gap 24 steps (matches the
    pinned config default townCenterSellInterval=24).  Minor 4-step ticks are
    NOT modeled (conservative: understates lane value).
A2. Per-tick, per-product cap: 32 units.  Source: ep 108114108 step 341->342
    tick cleared 24 WOOL + 8 STRAWBERRY = 32 units in one tick.
A3. Shop buy prices ($/u): WOOL 123, STRAWBERRY 92, MELON 79, EGG 52,
    TOMATO 50, CARROT 49, FERTILIZER 47, WHEAT 42, MILK 40.
    Source: loss-forensics autopsy measurement on ep 108114108 (step-400
    quotes vs observed shop receipts).
A4. Finite shop demand: $100,000 total shop spend per game.  Source: ep
    108114108 observed op ~$73k + us ~$19k ~= $92k; rounded up.
A5. Production schedule: our (us-seat) replay shed-inflow totals, arriving
    uniformly over steps 0..671:
    WHEAT 638, FERTILIZER 307, WOOL 136, MELON 12, MILK 116,
    STRAWBERRY 95, CARROT 47.  Source: ep 108114108 shed-inflow proxy.
    (Lower bound: wool bypasses the shed in replays; conservative.)
A6. Market dump realization: $0.60/unit.  Source: autopsy, our d27-29 bulk
    dumps realize ~$0.6-0.66/u.
A7. Scope: the modeled decision is the recurring market-dump choice (every 24
    steps, offset 12 from shop ticks): OFF empties the shed at $0.60/u
    (current behavior); ON sells only overflow above the SHOP_RESERVE floor.
    The shop tick fires first at each boundary, so both policies face the
    same live mechanic; only the reserve decision differs.
A8. Shop buys in SHOP_PRIORITY order each tick (WOOL first).  Demand-capped:
    once cumulative shop spend hits $100k, ticks stop buying.

POLICIES
--------
OFF: at each dump step, SELL the entire shed at $0.60/u (current behavior:
     empty the shed into market dumps).
ON:  at each dump step, SELL only overflow above the lane's SHOP_RESERVE
     floor per product at $0.60/u; shop ticks consume the reserve at
     premium prices.  (The lane's liveness gate is satisfied: ticks are
     observed from the first tick, so the filter is engaged throughout.)

METRIC: total revenue (shop + market) ON minus OFF, in dollars.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r04_shop_first import (
    SHOP_PRIORITY, SHOP_PRICES, SHOP_RESERVE, _cap_sells_for_reserve,
)

# --- replay-derived parameters (see ASSUMPTIONS) ---
TICK_EVERY = 24          # A1
TICK_CAP_PER_PRODUCT = 32  # A2
SHOP_DEMAND_CAP = 100_000.0  # A4
MARKET_REALIZED = 0.60   # A6: our measured FULL-GAME average market
                         # realization (ep 108114108: $69,860 / 118,294u)
DUMP_EVERY = 24          # market dump cadence (both policies)
DUMP_OFFSET = 12         # dumps land midway between shop ticks
PRODUCTION = {  # A5: us-seat shed inflow, ep 108114108
    "WHEAT": 638, "FERTILIZER": 307, "WOOL": 136, "MELON": 12,
    "MILK": 116, "STRAWBERRY": 95, "CARROT": 47,
}
PROD_END = 671
N_STEPS = 720


def run(policy_on):
    shed = {p: 0 for p in SHOP_PRIORITY}
    shop_spent = 0.0
    shop_rev = 0.0
    market_rev = 0.0
    # uniform production schedule
    prod_rate = {p: PRODUCTION.get(p, 0) / (PROD_END + 1) for p in SHOP_PRIORITY}
    carry = {p: 0.0 for p in SHOP_PRIORITY}

    for step in range(N_STEPS):
        # production arrives
        if step <= PROD_END:
            for p in SHOP_PRIORITY:
                carry[p] += prod_rate[p]
                whole = int(carry[p])
                if whole:
                    shed[p] += whole
                    carry[p] -= whole
        # shop tick (live mechanic, both policies)
        if step > 0 and step % TICK_EVERY == 0 and shop_spent < SHOP_DEMAND_CAP:
            for p in SHOP_PRIORITY:
                if shop_spent >= SHOP_DEMAND_CAP:
                    break
                take = min(shed[p], TICK_CAP_PER_PRODUCT)
                if take <= 0:
                    continue
                # respect the demand cap in dollars
                max_by_cap = int((SHOP_DEMAND_CAP - shop_spent) // SHOP_PRICES[p])
                take = min(take, max_by_cap)
                if take <= 0:
                    continue
                shed[p] -= take
                rev = take * SHOP_PRICES[p]
                shop_rev += rev
                shop_spent += rev
        # market dump: OFF empties the shed (current behavior);
        # ON applies the lane's actual reserve filter to the dump SELLs.
        if step > 0 and step % DUMP_EVERY == DUMP_OFFSET:
            rows = [["SELL", p, shed[p]] for p in SHOP_PRIORITY if shed[p] > 0]
            if policy_on:
                rows = _cap_sells_for_reserve(
                    rows, {p: shed[p] for p in SHOP_PRIORITY})
            for row in rows:
                p, qty = row[1], row[2]
                shed[p] -= qty
                market_rev += qty * MARKET_REALIZED

    # terminal: leftover shed valued at market (both policies)
    terminal = sum(shed[p] * MARKET_REALIZED for p in SHOP_PRIORITY)
    return {
        "shop_rev": shop_rev,
        "market_rev": market_rev,
        "terminal": terminal,
        "total": shop_rev + market_rev + terminal,
        "shop_spent": shop_spent,
    }


def main():
    off = run(False)
    on = run(True)
    print("replay-derived shop model (assumptions A1-A8 in module docstring)")
    print(f"  OFF: shop=${off['shop_rev']:,.0f} market=${off['market_rev']:,.0f} "
          f"terminal=${off['terminal']:,.0f} total=${off['total']:,.0f}")
    print(f"  ON : shop=${on['shop_rev']:,.0f} market=${on['market_rev']:,.0f} "
          f"terminal=${on['terminal']:,.0f} total=${on['total']:,.0f}")
    delta = on["total"] - off["total"]
    print(f"  DELTA(ON-OFF) = ${delta:,.0f}")
    # sensitivity: halved demand cap
    return delta


if __name__ == "__main__":
    main()
