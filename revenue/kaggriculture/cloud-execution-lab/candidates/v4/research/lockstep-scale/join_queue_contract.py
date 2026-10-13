"""Pure raw-slot certificate for the shared TITAN lockstep-join component.

This is an admission CHECK, not a SELL producer, observer, debt ledger or policy.
It imports no runtime and mutates no arguments. A passing certificate proves
only that the one proposed row-0 sale does not move or delete any other raw
market slot. Stock, future obligations, observed fills, opponent forecasts,
resource effects and profitability remain the caller's separate obligations.

An occupied row 0 is never displaced, even when the queue is below its cap.
Literal None, [] and ["PASS"] slots are intentionally the only replaceable
no-ops. Other malformed or conditionally unfilled orders are not empty slots.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

PRODUCTS = frozenset(("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                      "EGG", "MILK", "WOOL", "FERTILIZER"))
RESOURCE_ORDERS = frozenset(("HIRE", "BUY_LAND", "BUY_SEED", "BUY_ANIMAL", "BUY_PRODUCT"))


@dataclass(frozen=True)
class QueueCertificate:
    slot_safe: bool
    reason: str
    before_sha256: str | None = None
    after_sha256: str | None = None
    effective_cap: int | None = None
    resource_sensitive_slots: tuple[int, ...] = ()
    same_product_slots: tuple[int, ...] = ()


def _json_value(value: Any) -> None:
    """Reject non-JSON objects and nonfinite numbers; preserve scalar types."""
    kind = type(value)
    if value is None or kind in (str, bool, int):
        return
    if kind is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite JSON number")
        return
    if kind is list:
        for child in value:
            _json_value(child)
        return
    if kind is dict and all(type(key) is str for key in value):
        for child in value.values():
            _json_value(child)
        return
    raise ValueError("only plain JSON data with string object keys is supported")


def _encoded(value: Any) -> bytes:
    _json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _empty_slot(row: Any) -> bool:
    return row is None or (type(row) is list and (not row or row == ["PASS"]))


def certify_join_queue(before: dict, after: dict, *, item: str, quantity: int,
                       max_orders: Any = 10) -> QueueCertificate:
    """Bind an exact action pair to a conservative row-preservation certificate.

    The only admitted edits are replacing a literal no-op at raw index zero,
    or adding one SELL row to an absent/empty market list. All other action
    fields and ALL remaining rows (including the dead suffix) must match with
    JSON scalar types preserved. Caps use the pinned engine's max(1, int(x)).

    Resource-sensitive and same-product slots are reported even when slot_safe
    is True. Slot safety is NOT fill/capital equivalence or a promotion gate.
    Recompute on the exact returned action; a certificate is not a state commit.
    """
    if type(before) is not dict or type(after) is not dict:
        return QueueCertificate(False, "invalid_action_type")
    if type(item) is not str or item not in PRODUCTS:
        return QueueCertificate(False, "invalid_product")
    if type(quantity) is not int or not 1 <= quantity <= 1000:
        return QueueCertificate(False, "invalid_quantity")
    try:
        cap = max(1, int(max_orders))
        b_bytes, a_bytes = _encoded(before), _encoded(after)
        b_sha, a_sha = (hashlib.sha256(data).hexdigest() for data in (b_bytes, a_bytes))
    except (ValueError, TypeError, OverflowError, RecursionError):
        return QueueCertificate(False, "invalid_json_or_cap")

    def result(ok: bool, why: str, resources=(), same=()) -> QueueCertificate:
        return QueueCertificate(ok, why, b_sha, a_sha, cap, tuple(resources), tuple(same))

    old = before.get("market", [])
    new = after.get("market", [])
    if type(old) is not list or type(new) is not list:
        return result(False, "market_must_be_list")
    if "market" not in after:
        return result(False, "missing_join_market")
    b_rest = {k: v for k, v in before.items() if k != "market"}
    a_rest = {k: v for k, v in after.items() if k != "market"}
    if _encoded(b_rest) != _encoded(a_rest):
        return result(False, "nonmarket_fields_changed")
    if not new or _encoded(new[0]) != _encoded(["SELL", item, quantity]):
        return result(False, "join_row_mismatch")
    if old:
        if not _empty_slot(old[0]):
            return result(False, "occupied_row_zero")
        if len(new) != len(old):
            return result(False, "raw_queue_length_changed")
        if _encoded(new[1:]) != _encoded(old[1:]):
            return result(False, "other_raw_slots_changed")
    elif len(new) != 1:
        return result(False, "extra_rows_added")
    resources, same = [], []
    for slot, row in enumerate(new[1:cap], 1):
        if type(row) is not list or not row or type(row[0]) is not str:
            continue
        if row[0] in RESOURCE_ORDERS:
            resources.append(slot)
        if row[0] in ("SELL", "BUY_PRODUCT") and len(row) > 1 and row[1] == item:
            same.append(slot)
    return result(True, "row_zero_only_no_other_slot_moves", resources, same)
