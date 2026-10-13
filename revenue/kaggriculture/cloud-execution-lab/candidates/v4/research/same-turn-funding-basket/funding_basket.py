# SPDX-License-Identifier: Apache-2.0
"""Opt-in, bounded multi-source completion of native same-turn financing.

One experimental adapter for the existing FrozenSelected call site.  No policy
key, archive rewrite, or default activation.  Certificates concern our fixed
market queue under the native SELL stress model, not whole-game profitability.
"""
from __future__ import annotations

import copy
import functools
import hashlib
from pathlib import Path
from typing import Iterator

NATIVE_SHA256 = "5ca1bc39efed756de71207f46926744ea69f9d2f300dd7b9c1a8cc4dbefeb9ef"
MAX_ROWS = 16
MAX_UNITS = 256


def _integer(value, lower=0, upper=MAX_UNITS):
    return type(value) is int and lower <= value <= upper


def _allocations(caps: tuple[int, ...], total: int) -> Iterator[tuple[int, ...]]:
    """Enumerate one moved-unit layer; no materialized Cartesian product."""
    if len(caps) == 1:
        if 0 <= total <= caps[0]:
            yield (total,)
        return
    tail_capacity = sum(caps[1:])
    for quantity in range(max(0, total - tail_capacity), min(caps[0], total) + 1):
        for tail in _allocations(caps[1:], total - quantity):
            yield (quantity,) + tail


def _candidate(prefix, groups, allocation, target):
    result = copy.deepcopy(prefix)
    empty = [i for i in range(target) if not prefix[i]]
    moves = []
    for (item, sources, _capacity), quantity in zip(groups, allocation):
        if not quantity:
            continue
        same = [i for i in range(target)
                if prefix[i] and prefix[i][0] == "SELL" and prefix[i][1] == item]
        if same:
            destination = same[-1]
        elif empty:
            destination = empty.pop()
        else:
            return None, None
        if result[destination]:
            result[destination][2] += quantity
        else:
            result[destination] = ["SELL", item, quantity]
        remaining = quantity
        for source in sources:
            moved = min(remaining, prefix[source][2])
            if moved:
                after = prefix[source][2] - moved
                result[source] = ["SELL", item, after] if after else []
                moves.append({"source_index": source, "destination_index": destination,
                              "item": item, "quantity": moved})
                remaining -= moved
            if not remaining:
                break
    return result, moves


def bind(native, *, enabled: bool = False, max_states: int = 256):
    """Return the SAME native callable when OFF; capture it once when ON.

    Usage in an isolated evaluation process only::
        fs.fund_same_turn_acquisition = bind(fs, enabled=True)

    The caller still supplies FrozenSelected's post-unit farm/private snapshot.
    Do not install twice or pass pre-unit shed data.  A new native source requires
    a fresh port and new tests, rather than silently bypassing this source pin.
    """
    prior = native.fund_same_turn_acquisition
    if not enabled:
        return prior
    if type(enabled) is not bool:
        raise ValueError("enabled must be a boolean")
    if not _integer(max_states, 1, 4096):
        raise ValueError("max_states must be an integer in [1, 4096]")
    if getattr(prior, "_funding_basket", False):
        raise ValueError("funding basket is already installed")
    if hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest() != NATIVE_SHA256:
        raise ValueError("native funding source drift")
    wrapped = functools.partial(_fund, native, prior, max_states)
    wrapped._funding_basket = True
    return wrapped


def _fund(native, prior, budget, orders, farm, private, market, shops, config,
          now, targets, rival_quantity):
    def skip(reason, visited=0):
        return orders, {"applied": False, "reason": reason,
                        "mechanism": "same-turn-funding-basket", "states": visited}

    # Raw cap before parsing: never use or compact an engine-dead suffix.
    cap = config.get("maxMarketOrdersPerTurn", 10)
    if type(cap) is not int or max(1, cap) > MAX_ROWS:
        return skip("outside-domain")
    cap = max(1, cap)
    if type(orders) is not list:
        return skip("outside-domain")
    prefix = orders[:cap]
    if not prefix:
        return orders, None
    for row in prefix:
        if type(row) is not list:
            return skip("outside-domain")
        if not row:
            continue
        op = row[0]
        if op in ("HIRE", "BUY_LAND") and len(row) == 1:
            continue
        if (len(row) != 3 or type(op) is not str or type(row[1]) is not str
                or not _integer(row[2])):
            return skip("outside-domain")
        universe = {"SELL": native.m.PRODUCTS, "BUY_PRODUCT": ("WHEAT", "FERTILIZER"),
                    "BUY_SEED": native.m.CROPS, "BUY_ANIMAL": native.m.ANIMALS}
        if op not in universe or row[1] not in universe[op]:
            return skip("outside-domain")
    try:
        if (not _integer(farm["money"], 0, 10**9)
                or not _integer(farm["hires_today"], 0, 32)
                or not _integer(config.get("shedCapacity", 100), 1)
                or not _integer(config.get("farmHandCostMult", 1), 1, 1000)
                or any(not _integer(q) for q in private["shed"].values())):
            return skip("outside-domain")
        # Freeze the public rival estimate once per product, including callable
        # predictors. Search order must not change this input or leak rival state.
        rival = {item: rival_quantity(item) if callable(rival_quantity)
                 else (rival_quantity or {}).get(item, 0) for item in native.m.PRODUCTS}
        if any(not _integer(q, 0, 10000) for q in rival.values()):
            return skip("outside-domain")
        selected, info = prior(prefix, farm, private, market, shops, config, now,
                               targets, rival)
        if not info or info.get("reason") != "no-safe-prefix-sale":
            return (orders if selected == prefix else selected + orders[cap:]), info
        # Unlike the single-source predecessor, this new fallback makes no claim
        # across *any* dynamic-price buy in the live queue, including later buys.
        if any(row and row[0] == "BUY_PRODUCT" for row in prefix):
            return skip("live-buy-product")
        target = info["target_index"]
        baseline = native._market_prefix_state(prefix, farm, private, market,
                         shops, config, now, rival, len(prefix) - 1)
        totals = native.sale_quantities(prefix)
        if any(q > private["shed"].get(item, 0) for item, q in totals.items()):
            return skip("sale-exceeds-post-unit-stock")
        by_item = {}
        eligible = set(targets).intersection(native.PRODUCTS)
        for source in range(target + 1, len(prefix)):
            row = prefix[source]
            if row and row[0] == "SELL" and row[1] in eligible and row[2] > 0:
                by_item.setdefault(row[1], []).append(source)
        groups = tuple((item, tuple(sources), sum(prefix[s][2] for s in sources))
                       for item, sources in sorted(by_item.items()))
        if not groups:
            return skip("no-basket-sources")
        capacities = tuple(group[2] for group in groups)
        if sum(capacities) > MAX_UNITS:
            return skip("outside-domain")
        visited = 0
        for total in range(2, sum(capacities) + 1):
            best = None
            for allocation in _allocations(capacities, total):
                if visited >= budget:
                    # No best-so-far: an unfinished layer has no complete
                    # deterministic minimum-movement/tie-break certificate.
                    return skip("search-budget-exhausted", visited)
                visited += 1
                candidate, moves = _candidate(prefix, groups, allocation, target)
                if candidate is None or len(moves) < 2:
                    continue
                if native.sale_quantities(candidate) != totals:
                    continue
                at_target = native._market_prefix_state(candidate, farm, private,
                                    market, shops, config, now, rival, target)
                outcome = at_target["outcomes"].get(target, {})
                if outcome.get("completed", 0) < baseline["outcomes"][target]["required"]:
                    continue
                final = native._market_prefix_state(candidate, farm, private,
                                market, shops, config, now, rival, len(prefix) - 1)
                # Financing a new early buy must not silently steal an already
                # completed later buy (including partial baseline fills).
                if any(final["outcomes"].get(i, {}).get("completed", 0) < old["completed"]
                       for i, old in baseline["outcomes"].items()):
                    continue
                rank = (-at_target["money"], allocation)
                if best is None or rank < best[0]:
                    best = (rank, candidate, moves, at_target, final)
            if best is not None:
                _, candidate, moves, at_target, final = best
                return candidate + orders[cap:], {
                    "applied": True, "mechanism": "same-turn-funding-basket",
                    "target_index": target, "target_order": copy.deepcopy(prefix[target]),
                    "baseline_completed": baseline["outcomes"][target]["completed"],
                    "funded_completed": at_target["outcomes"][target]["completed"],
                    "moved_quantity": total, "moves": moves, "states": visited,
                    "remaining_cash_after_target": at_target["money"],
                    "final_modeled_cash": final["money"],
                    "baseline_modeled_cash": baseline["money"],
                    "sale_quantities_preserved": True,
                    "baseline_acquisition_fills_preserved": True,
                    "search_complete_through_moved_units": total,
                    "scope": "fixed-queue native stress model; not terminal-cash dominance"}
        return skip("no-certified-basket", visited)
    except (KeyError, TypeError, ValueError, OverflowError, IndexError):
        return skip("outside-domain")
