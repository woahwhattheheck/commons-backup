"""Pure raw-slot certificate for adjacent BUY_PRODUCT phasing.

This module belongs to TITAN V4's existing lockstep-scale research authority.
It is an admission checker only: it does not predict an opponent action, estimate
profit, select an order, or authorize runtime activation.

The pinned official interpreter truncates the raw market list before parsing and
then processes equal raw indexes across players in lockstep.  Therefore swapping
one existing executable BUY_PRODUCT row with an adjacent literal no-op changes
only that row's lockstep phase when every other raw slot is preserved exactly.
This certificate proves only that narrow structural fact.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

BUYABLE_PRODUCTS = frozenset(("WHEAT", "FERTILIZER"))
_LITERAL_NOOPS = (None, [], ["PASS"])


@dataclass(frozen=True)
class RawPhaseCertificate:
    admitted: bool
    reason: str
    direction: str | None = None
    item: str | None = None
    quantity: int | None = None
    source_slot: int | None = None
    target_slot: int | None = None
    effective_cap: int | None = None
    before_sha256: str | None = None
    after_sha256: str | None = None
    conditional_only: bool = True
    activation_authority: bool = False


def _json_value(value: Any) -> None:
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
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(value: Any) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def _is_literal_noop(row: Any) -> bool:
    return row is None or (type(row) is list and (not row or row == ["PASS"]))


def _buy_row(row: Any) -> tuple[str, int] | None:
    # Use a stricter shape than the engine parser: exact three-field literal,
    # exact executable product domain, and plain positive integer quantity.
    if type(row) is not list or len(row) != 3 or row[0] != "BUY_PRODUCT":
        return None
    item, quantity = row[1], row[2]
    if type(item) is not str or item not in BUYABLE_PRODUCTS:
        return None
    if type(quantity) is not int or quantity <= 0:
        return None
    return item, quantity


def certify_adjacent_buy_phase(
    before: dict,
    after: dict,
    *,
    max_orders: Any = 10,
) -> RawPhaseCertificate:
    """Certify one exact adjacent BUY_PRODUCT/no-op raw-slot swap.

    Accepted edits are one-step only and preserve queue length, all other raw
    indexes, and every non-market field byte-for-byte in canonical JSON form.
    The BUY source and destination must both remain inside the official
    executable raw-prefix boundary.  ``max_orders`` is deliberately stricter
    than Python/engine coercion: only a plain integer is admitted.

    A PASS result is *conditional evidence only*.  It says nothing about whether
    a rival order will occupy the corresponding phase, whether the BUY fills,
    whether funding/capacity remain favorable, or whether the change improves an
    episode.  Those are downstream full-interpreter/economic obligations.
    """
    if type(before) is not dict or type(after) is not dict:
        return RawPhaseCertificate(False, "invalid_action_type")
    if type(max_orders) is not int:
        return RawPhaseCertificate(False, "invalid_market_cap")
    cap = max(1, max_orders)
    try:
        before_sha = _digest(before)
        after_sha = _digest(after)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return RawPhaseCertificate(False, "invalid_json_or_cap", effective_cap=cap)

    def result(ok: bool, reason: str, **kwargs: Any) -> RawPhaseCertificate:
        return RawPhaseCertificate(
            ok,
            reason,
            effective_cap=cap,
            before_sha256=before_sha,
            after_sha256=after_sha,
            **kwargs,
        )

    if "market" not in before or "market" not in after:
        return result(False, "market_field_required")
    old = before["market"]
    new = after["market"]
    if type(old) is not list or type(new) is not list:
        return result(False, "market_must_be_list")
    if len(old) != len(new):
        return result(False, "raw_queue_length_changed")

    before_rest = {k: v for k, v in before.items() if k != "market"}
    after_rest = {k: v for k, v in after.items() if k != "market"}
    if _encoded(before_rest) != _encoded(after_rest):
        return result(False, "nonmarket_fields_changed")

    changed = [
        i for i, (left, right) in enumerate(zip(old, new))
        if _encoded(left) != _encoded(right)
    ]
    if len(changed) != 2:
        return result(False, "exactly_two_raw_slots_must_change")
    lo, hi = changed
    if hi != lo + 1:
        return result(False, "phase_swap_must_be_adjacent")

    candidates: list[tuple[int, int, str, int]] = []
    for source, target in ((lo, hi), (hi, lo)):
        parsed = _buy_row(old[source])
        if parsed is None or not _is_literal_noop(old[target]):
            continue
        if _encoded(new[source]) != _encoded(old[target]):
            continue
        if _encoded(new[target]) != _encoded(old[source]):
            continue
        item, quantity = parsed
        candidates.append((source, target, item, quantity))

    if len(candidates) != 1:
        return result(False, "not_exact_buy_noop_swap")
    source, target, item, quantity = candidates[0]
    executable_stop = min(len(old), cap)
    if source >= executable_stop or target >= executable_stop:
        return result(False, "phase_swap_crosses_executable_prefix")

    # Defense in depth: all untouched rows must retain exact JSON scalar types.
    for index in range(len(old)):
        if index in (source, target):
            continue
        if _encoded(old[index]) != _encoded(new[index]):
            return result(False, "other_raw_slot_changed")

    direction = "delay_one_slot" if target > source else "advance_one_slot"
    return result(
        True,
        "adjacent_buy_noop_phase_only",
        direction=direction,
        item=item,
        quantity=quantity,
        source_slot=source,
        target_slot=target,
    )
