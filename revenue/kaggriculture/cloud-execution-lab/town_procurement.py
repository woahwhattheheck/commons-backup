# SPDX-License-Identifier: Apache-2.0
"""Receipt-safe retiming of six already-authored WHEAT purchases.

TOWNPROCURE never creates a new market row.  On six source-bound callbacks it
moves part of the *next* authored WHEAT buy two callbacks earlier by increasing
an already-existing WHEAT buy at the target callback.  The later authored buy
is reduced only by the extra units actually observed in the private shed on the
next callback.  Partial fills therefore suppress only partial source quantity.

The state is module-global on purpose: the canonical entrypoint reconstructs a
TitanAgent after a deadline cancellation, while the Python actor process and
this completed module remain alive.  Public next-observation receipt evidence,
not an in-flight controller object, owns the suppression decision.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

SCHEMA = "titan.v4.town-procurement/v1"

# target_step -> (source_step, quantity_to_advance)
# Every target is a default town-shop callback (step % 4 == 0), every source is
# exactly two callbacks later, and both callbacks already carry the same WHEAT
# purchase in every authenticated retained Arlene route.  The opening WHEAT13
# collision and the crop input repair (>455) are intentionally outside scope.
MOVES = {
    200: (202, 3),
    204: (206, 3),
    220: (222, 3),
    252: (254, 5),
    272: (274, 3),
    276: (278, 3),
}
SOURCE_TO_TARGET = {source: (target, qty) for target, (source, qty) in MOVES.items()}


def is_target_step(step: Any) -> bool:
    return type(step) is int and step in MOVES


@dataclass
class _Pending:
    target: int
    source: int
    move_qty: int
    baseline_qty: int
    post_unit_wheat: int


# One actor normally owns one player, but keying avoids accidental cross-seat
# state contamination in direct/unit tests.
_STATE: dict[int, dict[str, Any]] = {}


def _player(observation: Any) -> int:
    value = observation.get("player", 0) if isinstance(observation, dict) else getattr(observation, "player", 0)
    if type(value) is not int or value not in (0, 1):
        raise ValueError("town procurement requires public player 0 or 1 as a plain integer")
    return value


def _step(observation: Any) -> int:
    value = observation.get("step") if isinstance(observation, dict) else getattr(observation, "step", None)
    if type(value) is not int or value < 0:
        raise ValueError("town procurement requires nonnegative plain-int observation.step")
    return value


def _shed_wheat(observation: Any) -> int:
    private = observation.get("private", {}) if isinstance(observation, dict) else getattr(observation, "private", {})
    private = private or {}
    shed = private.get("shed", {}) if isinstance(private, dict) else getattr(private, "shed", {})
    shed = shed or {}
    value = shed.get("WHEAT", 0) if isinstance(shed, dict) else getattr(shed, "WHEAT", 0)
    if type(value) is not int or value < 0:
        raise ValueError("invalid private WHEAT inventory")
    return value


def _state(player: int) -> dict[str, Any]:
    return _STATE.setdefault(player, {"last_step": None, "pending": None, "confirmed": {}})


def reset(*, player: int | None = None) -> None:
    if player is None:
        _STATE.clear()
    else:
        _STATE.pop(int(player), None)


def observe(observation: Any) -> dict[str, Any]:
    """Reconcile the immediately previous target from public private-shed state.

    This runs at canonical entrypoint start, before a new controller is built or
    any deadline timer can cancel finalization.  It never mutates an action.
    """
    player = _player(observation)
    step = _step(observation)
    if step == 0:
        reset(player=player)
    state = _state(player)
    last = state["last_step"]
    if last is not None and step < int(last):
        # Episode/replay rewind: stale receipts have no authority.
        reset(player=player)
        state = _state(player)

    # A suppression is useful only on its exact authored source callback.  Once
    # that callback is in the past, drop it.  Keep current-step entries so both
    # normal finalization and an outer fallback can apply the same idempotent cut.
    state["confirmed"] = {
        int(source): int(qty)
        for source, qty in state["confirmed"].items()
        if int(source) >= step and int(qty) > 0
    }

    report = {
        "schema": SCHEMA,
        "step": step,
        "player": player,
        "status": "no_pending_receipt",
        "confirmed_source": None,
        "confirmed_qty": 0,
    }
    pending = state.get("pending")
    if isinstance(pending, _Pending):
        if step == pending.target + 1:
            current = _shed_wheat(observation)
            filled_total = max(0, current - pending.post_unit_wheat)
            extra = max(0, min(pending.move_qty, filled_total - pending.baseline_qty))
            if extra:
                state["confirmed"][pending.source] = max(
                    int(state["confirmed"].get(pending.source, 0)), extra
                )
            report.update(
                status="receipt_reconciled",
                source=pending.source,
                target=pending.target,
                requested_extra=pending.move_qty,
                baseline_qty=pending.baseline_qty,
                observed_total_fill=filled_total,
                confirmed_source=pending.source if extra else None,
                confirmed_qty=extra,
            )
            state["pending"] = None
        elif step > pending.target + 1:
            # The authoritative next observation was missed.  Do not infer a
            # fill from a later state that may contain unrelated WHEAT changes.
            report.update(status="receipt_window_missed", source=pending.source, target=pending.target)
            state["pending"] = None
        elif step <= pending.target:
            # Same-step re-entry is harmless; retain the pending target.
            report.update(status="receipt_pending", source=pending.source, target=pending.target)

    state["last_step"] = step
    return report


def _market_quantity(row: Any, op: str, item: str) -> int | None:
    """Parse one market row with the pinned engine's positive-quantity grammar."""
    if not (isinstance(row, list) and len(row) >= 3
            and row[0] == op and row[1] == item):
        return None
    try:
        quantity = int(row[2])
    except (TypeError, ValueError):
        return None
    return quantity if quantity > 0 else None


def _prefix_limit(action: Any, configuration: Any = None) -> int:
    """Return the engine-effective market prefix without widening bad configs."""
    cfg = configuration or {}
    value = (cfg.get("maxMarketOrdersPerTurn", 10) if isinstance(cfg, dict)
             else getattr(cfg, "maxMarketOrdersPerTurn", 10))
    try:
        return max(1, int(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid maxMarketOrdersPerTurn") from exc


def _unique_wheat_buy(action: Any, configuration: Any = None) -> tuple[int, int] | None:
    """Return one executable WHEAT buy; inert suffix duplicates do not conflict."""
    if not isinstance(action, dict):
        return None
    market = action.get("market")
    if not isinstance(market, list):
        return None
    prefix_limit = _prefix_limit(action, configuration)
    prefix_hits = [
        (index, quantity)
        for index, row in enumerate(market[:prefix_limit])
        if (quantity := _market_quantity(row, "BUY_PRODUCT", "WHEAT")) is not None
    ]
    if len(prefix_hits) == 1:
        return prefix_hits[0]
    if prefix_hits:
        return None

    # Preserve the existing inert-suffix diagnostic when no executable WHEAT
    # buy exists, but never let suffix duplicates invalidate a unique prefix.
    suffix_hits = [
        (index, quantity)
        for index, row in enumerate(market[prefix_limit:], start=prefix_limit)
        if (quantity := _market_quantity(row, "BUY_PRODUCT", "WHEAT")) is not None
    ]
    return suffix_hits[0] if len(suffix_hits) == 1 else None


def suppress_confirmed(observation: Any, action: Any, configuration: Any = None) -> tuple[Any, dict[str, Any]]:
    """Idempotently reduce the exact current source buy by confirmed moved fill."""
    step = _step(observation)
    player = _player(observation)
    state = _state(player)
    confirmed = int(state["confirmed"].get(step, 0))
    report = {
        "schema": SCHEMA,
        "step": step,
        "player": player,
        "status": "no_confirmed_source",
        "confirmed_qty": confirmed,
        "suppressed_qty": 0,
        "changed": False,
    }
    if step not in SOURCE_TO_TARGET or confirmed <= 0:
        return action, report
    hit = _unique_wheat_buy(action, configuration)
    if hit is None:
        report["status"] = "source_shape_drift"
        return action, report
    index, qty = hit
    if index >= _prefix_limit(action, configuration):
        # The later authored row is not executable under the current engine cap,
        # so there is no duplicate economic buy to suppress.
        report["status"] = "source_row_inert_suffix"
        return action, report
    expected_target, expected_qty = SOURCE_TO_TARGET[step]
    if confirmed > expected_qty:
        report["status"] = "confirmed_qty_out_of_contract"
        return action, report
    use = min(qty, confirmed)
    if use <= 0:
        return action, report
    out = deepcopy(action)
    # Preserve row topology even when every source unit is suppressed.  The
    # engine slices the market list to its order cap before parsing; deleting
    # this row could promote an unrelated suffix order into execution.  A
    # zero-quantity BUY_PRODUCT parses as inert, so it safely occupies the slot.
    out["market"][index][2] = qty - use
    report.update(
        status="source_suppressed",
        target=expected_target,
        source=step,
        source_qty_before=qty,
        suppressed_qty=use,
        source_qty_after=qty - use,
        changed=True,
    )
    return out, report


def _target_pre_market_wheat(observation: Any, action: Any) -> int | None:
    if not isinstance(action, dict):
        return None
    unit_rows = []
    farmer = action.get("farmer")
    if isinstance(farmer, list):
        unit_rows.append(farmer)
    hands = action.get("hands")
    if isinstance(hands, list):
        unit_rows.extend(row for row in hands if isinstance(row, list))
    for row in unit_rows:
        if not row:
            continue
        if row[0] == "DROP":
            return None
        if row[0] == "PICKUP" and len(row) > 1 and row[1] == "WHEAT":
            return None
    try:
        return _shed_wheat(observation)
    except ValueError:
        return None


def apply(observation: Any, action: Any, configuration: Any = None, *, completed: bool) -> tuple[Any, dict[str, Any]]:
    """Apply source suppression or initiate one exact target advance.

    Source suppression is receipt-owned and may run on completed or fallback
    actions.  A new target advance starts only from a completed current action
    whose unit stage cannot change shed WHEAT and whose market already contains
    the source-bound WHEAT buy row.
    """
    step = _step(observation)
    player = _player(observation)

    suppressed, report = suppress_confirmed(observation, action, configuration)
    if report["changed"] or step in SOURCE_TO_TARGET:
        return suppressed, report

    if step not in MOVES:
        report["status"] = "not_townprocure_step"
        return action, report
    if not completed:
        report["status"] = "target_requires_completed_action"
        return action, report

    hit = _unique_wheat_buy(action, configuration)
    if hit is None:
        report["status"] = "target_shape_drift"
        return action, report
    index, baseline_qty = hit
    prefix_limit = _prefix_limit(action, configuration)
    if index >= prefix_limit:
        report.update(status="target_wheat_inert_suffix", row_index=index, prefix_limit=prefix_limit)
        return action, report
    for row in action.get("market", [])[:prefix_limit]:
        if _market_quantity(row, "SELL", "WHEAT") is not None:
            report["status"] = "target_wheat_sale_conflict"
            return action, report
    source, move_qty = MOVES[step]
    # The source-authenticated route bank binds these target purchases to the
    # same quantity as the source.  Refuse any runtime shape drift rather than
    # changing a different purchase intent.
    if baseline_qty != move_qty:
        report.update(
            status="target_quantity_drift",
            baseline_qty=baseline_qty,
            expected_qty=move_qty,
        )
        return action, report

    post_wheat = _target_pre_market_wheat(observation, action)
    if post_wheat is None:
        report["status"] = "target_unit_wheat_ambiguous"
        return action, report

    state = _state(player)
    pending = state.get("pending")
    if pending is not None:
        report["status"] = "target_pending_receipt_conflict"
        return action, report

    out = deepcopy(action)
    out["market"][index][2] = baseline_qty + move_qty
    state["pending"] = _Pending(
        target=step,
        source=source,
        move_qty=move_qty,
        baseline_qty=baseline_qty,
        post_unit_wheat=post_wheat,
    )
    report.update(
        status="target_advanced",
        changed=True,
        target=step,
        source=source,
        baseline_qty=baseline_qty,
        advanced_qty=move_qty,
        requested_qty=baseline_qty + move_qty,
        post_unit_wheat=post_wheat,
    )
    return out, report
