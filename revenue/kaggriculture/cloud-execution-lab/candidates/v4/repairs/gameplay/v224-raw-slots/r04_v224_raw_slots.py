# SPDX-License-Identifier: Apache-2.0
"""Raw-slot-preserving V224 SELL ordering for TITAN V4.

Frozen V3.1 V224 first filters its market vector and then bubbles SELL rows
left. Filtering removes falsey / zero / malformed rows, but the official
engine executes both players' market orders in lockstep by raw row index.
Those placeholders are therefore timing barriers, not cosmetic whitespace.

This helper keeps V224's useful contiguous SELL bubbling while preserving the
raw executable prefix. Falsey, malformed and non-positive rows are barriers;
same-item BUY_PRODUCT / BUY_ANIMAL remain barriers exactly as in V224.
"""

from __future__ import annotations

MAX_ORDERS = 10
_PRODUCTS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
             "EGG", "MILK", "WOOL", "FERTILIZER"}
_BUY_PRODUCTS = {"WHEAT", "FERTILIZER"}
_SEEDS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"}
_ANIMALS = {"GOOSE", "COW", "SHEEP"}
_ITEM_DOMAINS = {
    "BUY_PRODUCT": _BUY_PRODUCTS,
    "BUY_ANIMAL": _ANIMALS,
    "BUY_SEED": _SEEDS,
    "SELL": _PRODUCTS,
}


def _positive_effect(row):
    if not isinstance(row, list) or not row or type(row[0]) is not str:
        return False
    verb = row[0]
    if verb in ("HIRE", "BUY_LAND"):
        return True
    domain = _ITEM_DOMAINS.get(verb)
    if domain is None or len(row) < 3:
        return False
    return (type(row[1]) is str and row[1] in domain
            and type(row[2]) is int and row[2] > 0)


def _sell_item(row):
    if not _positive_effect(row) or row[0] != "SELL":
        return None
    return row[1]


def _crossable(row, sell_item):
    """Whether V224 may swap ``sell_item`` one raw slot left across ``row``."""
    if not _positive_effect(row):
        return False
    if row[0] == "SELL":
        return False
    if row[0] in ("BUY_PRODUCT", "BUY_ANIMAL") and len(row) > 1 and row[1] == sell_item:
        return False
    return True


def _frozen_projection(original):
    """Return frozen V224's projected prefix, or None if its code would raise.

    This is used only to preserve one outer side effect of the frozen wrapper:
    when V224 would have changed the executable prefix, it published that prefix
    and thereby hid rows beyond the engine's market-order cap from later R04
    wrappers. The repaired lane must not make those non-executable rows visible.
    """
    try:
        orders = [list(row) for row in original
                  if row and (row[0] in ("HIRE", "BUY_LAND")
                              or (len(row) >= 3 and int(row[2]) > 0))]
        for index in range(len(orders)):
            order = orders[index]
            if order[0] != "SELL":
                continue
            cursor = index
            while cursor > 0:
                previous = orders[cursor - 1]
                if previous[0] == "SELL":
                    break
                if (previous[0] in ("BUY_PRODUCT", "BUY_ANIMAL")
                        and previous[1] == order[1]):
                    break
                orders[cursor - 1], orders[cursor] = orders[cursor], orders[cursor - 1]
                cursor -= 1
        return orders
    except (IndexError, KeyError, OverflowError, TypeError, ValueError):
        return None


def sales_first_raw_slots(action, *, max_orders=MAX_ORDERS):
    """Apply V224 ordering without deleting or crossing raw-slot barriers.

    The exact parent object is returned when no safe swap is available, except
    when frozen V224 would already have published a changed executable prefix;
    in that case rows beyond ``max_orders`` stay hidden from downstream wrappers.
    When a swap occurs, V224's existing executable-prefix behavior is retained.
    """
    if not isinstance(action, dict):
        return action
    market = action.get("market")
    if not isinstance(market, list) or type(max_orders) is not int or max_orders <= 0:
        return action

    original = market[:max_orders]
    rows = [list(row) if isinstance(row, list) else row for row in original]
    changed = False

    for index in range(len(rows)):
        item = _sell_item(rows[index])
        if item is None:
            continue
        cursor = index
        while cursor > 0 and _crossable(rows[cursor - 1], item):
            rows[cursor - 1], rows[cursor] = rows[cursor], rows[cursor - 1]
            cursor -= 1
            changed = True

    publish_prefix = changed
    if not publish_prefix and len(market) > max_orders:
        frozen = _frozen_projection(original)
        publish_prefix = frozen is not None and frozen != original

    if not publish_prefix:
        return action
    result = dict(action)
    result["market"] = rows
    return result
