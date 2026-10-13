"""Is a cap-harvest plan worth its storage and displacement cost?

The frozen candidate accepts a plan on the gross output the cap would destroy.
That is not the cash it earns. On development seed 9600011 its +2 own cash is
+2 EGG sold (+84) less 2 WHEAT sold (-82): the extra cargo competed with the
incumbent's cargo and with shed capacity, and nearly all of the gross was given
back.

This prices a candidate the way the engine settles it, on the seat's own economy:

  ordered unit transfers   the plan's ops are replayed in interpreter order on
                           scratch state, so a PICKUP or DROP earlier in the turn
                           is visible to a later one
  shed capacity            the end-of-day deposit obeys shedCapacity and DISCARDS
                           the overflow (_drop_inventories_to_shed), so cargo that
                           cannot land is worth nothing and can push out incumbent
                           goods
  market reservations      what the incumbent's own remaining SELL orders intend to
                           draw from the shed is reserved before the plan's cargo
                           is credited with anything
  dated marginal receipts  units are priced one at a time up the shared curve at the
                           inventory they would actually meet, never units x spot

The value returned is INCREMENTAL: the plan's own receipts minus the receipts it
displaces. It is an estimate of the seat's own settlement, not a claim about the
rival or about the final scoreboard -- the paired full game decides that.
"""

import copy

import native_motifs as NM
import run_cards


def _shed_room(priv, cap):
    return max(0, int(cap) - sum(int(v) for v in (priv.get("shed") or {}).values()))


def route_sell_reservations(agent, step, horizon=None):
    """What the rest of the tape still intends to SELL, per product.

    Arlene's own `future_sells` answers this for the current tail; it is read here
    directly so the reservation covers the whole remaining route rather than one
    turn, and so a product the incumbent has already committed to sell is not
    counted as room the plan may use.
    """
    route = agent.R[agent.cur]
    end = len(route) if horizon is None else min(len(route), step + 1 + horizon)
    out = {}
    for t in range(step + 1, end):
        for o in ((route[t] or {}).get("market") or []):
            if o and o[0] == "SELL" and len(o) > 2:
                out[o[1]] = out.get(o[1], 0) + int(o[2])
    return out


def marginal_receipts(K, market, item, units, inventory_offset=0):
    """Dated receipts for `units`, priced one at a time up the shared curve."""
    if units <= 0:
        return 0.0
    inv = dict(market.get("inventory") or {})
    return run_cards.marginal_revenue(
        K, {"inventory": dict(inv, **{item: int(inv.get(item, 0)) + inventory_offset}),
            "params": market.get("params")}, item, units)


def assess(K, obs, cfg, seat, agent, step, unit, target, credited_units):
    """Incremental value of running this errand, priced the way the engine settles.

    The errand is not executable where the worker currently stands -- it has to walk
    there first -- so pricing the op in place values nothing. What is priced instead
    is the OUTCOME: the harvest puts `target["units"]` of cargo on that worker, and
    that whole load competes for shed capacity at the end-of-day deposit, while only
    `credited_units` of it is incremental. The rest is stock the incumbent route
    collects anyway; the credited part is what the output cap would otherwise
    destroy.

    Capacity is the mechanism that makes the two differ. `_drop_inventories_to_shed`
    fills the shed in unit order to `shedCapacity` and DISCARDS the overflow, so
    added cargo can push an equal amount of other produce out of the deposit
    entirely. Both sides are priced with dated marginal receipts, one unit at a time
    up the shared curve.
    """
    cap = int(cfg.get("shedCapacity", 100) or 100)
    market = obs["market"]
    priv = obs["private"]
    product = target["product"]
    cargo = int(target.get("units", 0))

    def deposit(extra_item=None, extra_n=0):
        """The engine's automatic end-of-day deposit, with its discard."""
        shed = {k: int(v) for k, v in (priv.get("shed") or {}).items()}
        room = max(0, cap - sum(shed.values()))
        discarded = {}
        invs = [dict(i) for i in (priv.get("inventories") or [])]
        while len(invs) <= unit:
            invs.append({})
        if extra_item and extra_n:
            invs[unit][extra_item] = invs[unit].get(extra_item, 0) + int(extra_n)
        for inv in invs:
            for item, n in inv.items():
                n = int(n)
                take = min(n, room)
                if take > 0:
                    shed[item] = shed.get(item, 0) + take
                    room -= take
                if n - take:
                    discarded[item] = discarded.get(item, 0) + (n - take)
        return shed, discarded

    shed_b, lost_b = deposit()
    shed_t, lost_t = deposit(product, cargo)

    gained, displaced = {}, {}
    for item in set(shed_b) | set(shed_t):
        d = shed_t.get(item, 0) - shed_b.get(item, 0)
        if d > 0:
            gained[item] = d
        elif d < 0:
            displaced[item] = -d
    for item in set(lost_t) | set(lost_b):
        extra_lost = lost_t.get(item, 0) - lost_b.get(item, 0)
        if extra_lost > 0 and item != product:
            displaced[item] = displaced.get(item, 0) + extra_lost

    # Credit only the incremental units, and only as far as they actually landed.
    landed = min(int(credited_units), gained.get(product, 0))
    add = marginal_receipts(K, market, product, landed) or 0.0
    drop = 0.0
    for item, n in displaced.items():
        drop += marginal_receipts(K, market, item, n) or 0.0

    reserved = route_sell_reservations(agent, step)
    return {
        "unit": unit, "target": list(target["at"]), "product": product,
        "cargo": cargo, "credited_units": int(credited_units),
        "credited_landed": landed,
        "gained": gained, "displaced": displaced,
        "receipts_added": round(add, 1), "receipts_displaced": round(drop, 1),
        "incremental": round(add - drop, 1),
        "overflow_discarded_base": sum(lost_b.values()),
        "overflow_discarded_trial": sum(lost_t.values()),
        "shed_room_before": _shed_room(priv, cap),
        "reserved_by_route": {k: v for k, v in reserved.items()
                              if k in gained or k in displaced},
    }
