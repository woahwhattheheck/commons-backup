# SPDX-License-Identifier: Apache-2.0
"""Wave-4 F46: suppress only provably dead trailing SELL rows.

F46 deliberately operates *after* unit/route work has produced ``post`` and
before market submission.  ``post['private']['shed']`` is therefore the
authoritative same-callback lower bound for product that can actually be sold.
The guard never guesses about rival state, future fills, cargo routes, or
production that has not reached the shed.

To avoid the row-timing regression class already exposed by the V5 loss
frontier, F46 only removes a contiguous suffix of SELL rows which is proven to
have zero executable own quantity.  Surviving market rows keep their original
indices.  Any malformed or inventory-ambiguous input fails open to the parent
action.
"""
from __future__ import annotations

from copy import deepcopy


def _nonnegative_int(value):
    return type(value) is int and value >= 0


def suppress_dead_sell_suffix(action, post):
    """Return ``(action, report)`` with a proven-dead SELL suffix removed.

    A SELL row is *proven dead* only when its product inventory is known and the
    simulated own shed quantity at that row is zero (or the request itself is
    zero). BUY_PRODUCT makes that product uncertain for later rows because a
    fill is not assumed. Unknown/malformed market rows make all later rows
    uncertain. Partially executable SELL rows are preserved.

    Inputs are never mutated.
    """
    report = {
        "factor": "F46",
        "changed": False,
        "removed_slots": [],
        "blocked_dead_slots": [],
        "reason": "not_engaged",
    }
    original = deepcopy(action)

    if not isinstance(action, dict) or not isinstance(post, dict):
        report["reason"] = "malformed_action_or_post_state"
        return original, report

    orders = action.get("market", [])
    if not isinstance(orders, list):
        report["reason"] = "malformed_market_rows"
        return original, report
    if not orders:
        report["reason"] = "empty_market_rows"
        return original, report

    private = post.get("private")
    shed = private.get("shed") if isinstance(private, dict) else None
    if not isinstance(shed, dict):
        report["reason"] = "missing_post_unit_shed"
        return original, report

    known = {}
    uncertain_products = set()
    for item, quantity in shed.items():
        if not isinstance(item, str) or not item:
            report["reason"] = "malformed_post_unit_shed"
            return original, report
        if _nonnegative_int(quantity):
            known[item] = quantity
        else:
            uncertain_products.add(item)

    dead = [False] * len(orders)
    opaque_tail = False

    for index, row in enumerate(orders):
        if opaque_tail:
            continue
        if not isinstance(row, list) or not row:
            opaque_tail = True
            continue

        op = row[0]
        if op == "SELL":
            if (
                len(row) < 3
                or not isinstance(row[1], str)
                or not row[1]
                or not _nonnegative_int(row[2])
            ):
                if len(row) >= 2 and isinstance(row[1], str):
                    uncertain_products.add(row[1])
                else:
                    opaque_tail = True
                continue

            item, requested = row[1], row[2]
            if item in uncertain_products:
                continue

            available = known.get(item, 0)
            if requested == 0 or available == 0:
                dead[index] = True
                continue

            # A partial sale is still executable and must keep its row.
            known[item] = max(0, available - requested)
            continue

        if op == "BUY_PRODUCT":
            # Never assume the purchase fills. A later SELL of that product is
            # therefore not certifiably dead from local state alone.
            if len(row) >= 2 and isinstance(row[1], str) and row[1]:
                uncertain_products.add(row[1])
            else:
                opaque_tail = True
            continue

        # Unknown market operations may change shed state or row semantics.
        # Preserve them and stop making claims about later rows.
        opaque_tail = True

    trim_start = len(orders)
    while trim_start:
        index = trim_start - 1
        row = orders[index]
        if not (
            dead[index]
            and isinstance(row, list)
            and row
            and row[0] == "SELL"
        ):
            break
        trim_start -= 1

    if trim_start == len(orders):
        report["blocked_dead_slots"] = [
            index for index, is_dead in enumerate(dead) if is_dead
        ]
        report["reason"] = (
            "dead_rows_not_suffix"
            if report["blocked_dead_slots"]
            else "no_proven_dead_sell"
        )
        return original, report

    result = deepcopy(action)
    result["market"] = deepcopy(orders[:trim_start])
    report["changed"] = True
    report["removed_slots"] = list(range(trim_start, len(orders)))
    report["blocked_dead_slots"] = [
        index for index, is_dead in enumerate(dead[:trim_start]) if is_dead
    ]
    report["reason"] = "trimmed_proven_dead_sell_suffix"
    report["original_market_rows"] = len(orders)
    report["final_market_rows"] = trim_start
    return result, report
