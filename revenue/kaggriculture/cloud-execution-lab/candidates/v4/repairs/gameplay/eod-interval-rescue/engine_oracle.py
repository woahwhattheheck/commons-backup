# SPDX-License-Identifier: Apache-2.0
"""Literal function excerpts, not a substitute full-game evaluator.

Copied without logic changes from official engine Git blob
3c202c7ee921da239356789e266b694635103fc4, read through the GitHub connector.
Only SELL/drop transition evidence is claimed when these excerpts run.
"""


def _drop_inventories_to_shed(private, capacity):
    """Drop every per-farmer inventory into the shed up to `capacity`; overflow is discarded.
    Seeds are tracked separately in private["seeds"] and don't pass through the shed."""
    shed = private["shed"]
    for inv in private["inventories"]:
        for item, n in list(inv.items()):
            if n <= 0:
                del inv[item]
                continue
            current = sum(v for k, v in shed.items())
            room = max(0, capacity - current)
            take = min(n, room)
            if take > 0:
                shed[item] = shed.get(item, 0) + take
            del inv[item]


def _commit_unit(op, item, price, farm, private, market, shed_capacity=100):
    if op == "SELL":
        if private["shed"].get(item, 0) <= 0:
            return False
        private["shed"][item] -= 1
        farm["money"] += price
        # Sales at $1 do not increase market supply.
        if price > 1:
            market["inventory"][item] += 1
        return True
    if op == "BUY_PRODUCT":
        if farm["money"] < price:
            return False
        # Bought goods land in the shed, which obeys shedCapacity like every
        # other deposit path (pickup, shed-drop, end-of-day drop).
        if sum(private["shed"].values()) >= shed_capacity:
            return False
        farm["money"] -= price
        private["shed"][item] = private["shed"].get(item, 0) + 1
        market["inventory"][item] -= 1
        return True
    if op == "BUY_SEED":
        if farm["money"] < price:
            return False
        farm["money"] -= price
        private["seeds"][item] = private["seeds"].get(item, 0) + 1
        return True
    if op == "BUY_ANIMAL":
        if farm["money"] < price:
            return False
        if sum(private["shed"].values()) >= shed_capacity:
            return False
        farm["money"] -= price
        private["shed"][item] = private["shed"].get(item, 0) + 1
        return True
    return False
