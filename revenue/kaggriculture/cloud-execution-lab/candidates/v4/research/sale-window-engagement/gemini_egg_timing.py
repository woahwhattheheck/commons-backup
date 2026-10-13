#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Corrected Gemini EGG scarcity-timing frontier for canonical TITAN V4.

This is research/admission infrastructure, not a seller.  It deliberately does
*not* implement the falsified "buy EGG out of the market" short squeeze.  The
official engine only permits BUY_PRODUCT for WHEAT/FERTILIZER.  Instead, this
module searches a narrow corrected descendant: move an already-planned literal
EGG SELL to a later market slot and let the existing full-interpreter
sale-window harness measure the realized open-loop result.

The search is intentionally conservative:
* only one existing positive literal EGG SELL may move;
* only later PASS/append destinations inside the live market-order cap are used;
* opponent actions and all non-market actions remain byte-for-byte unchanged;
* rankings require an actually realized retiming, not merely changed syntax;
* scarcity-price positives require the same sold units and a strictly larger
  sale-specific receipt; total window cash is reported separately and cannot
  substitute for EGG receipt improvement.

The engine executes player market orders before town consumption.  Therefore a
sale on a town-consumption tick does not capture that tick's scarcity; moving to
a later turn can.  `sale_window.compare` remains the sole transition/economic
measurement authority here.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "titan.v4.gemini-egg-townclock-frontier/v1"
ITEM = "EGG"
DEFAULT_MAX_DELAY = 24
DEFAULT_MARKET_CAP = 10


def _exact_int(value: Any, *, minimum: int, label: str) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an exact int >= {minimum}")
    return value


def _market_cap(env: Any) -> int:
    cfg = getattr(env, "configuration", None)
    if cfg is None:
        return DEFAULT_MARKET_CAP
    getter = getattr(cfg, "get", None)
    raw = getter("maxMarketOrdersPerTurn", DEFAULT_MARKET_CAP) if callable(getter) else DEFAULT_MARKET_CAP
    if type(raw) is not int:
        raise ValueError("maxMarketOrdersPerTurn must be an exact int")
    return max(1, raw)


def _action_market(tape: list, turn: int, seat: int) -> list:
    try:
        pair = tape[turn]
        action = pair[seat]
    except (IndexError, TypeError):
        raise ValueError("malformed tape/turn/seat") from None
    if not isinstance(pair, list) or len(pair) != 2 or not isinstance(action, dict):
        raise ValueError("tape must contain two action dictionaries per turn")
    market = action.get("market", [])
    if not isinstance(market, list):
        raise ValueError("market must be a list")
    return market


def source_row(tape: list, seat: int, source_turn: int, source_row_index: int) -> list:
    """Return and authenticate the one EGG SELL this frontier is allowed to move."""
    _exact_int(seat, minimum=0, label="seat")
    if seat not in (0, 1):
        raise ValueError("seat must be 0 or 1")
    _exact_int(source_turn, minimum=0, label="source_turn")
    _exact_int(source_row_index, minimum=0, label="source_row")
    market = _action_market(tape, source_turn, seat)
    if source_row_index >= len(market):
        raise ValueError("source row absent")
    row = market[source_row_index]
    if not (
        isinstance(row, list)
        and len(row) == 3
        and row[0] == "SELL"
        and row[1] == ITEM
        and type(row[2]) is int
        and row[2] > 0
    ):
        raise ValueError("source must be a positive literal EGG SELL")
    return row


def destination_row(tape: list, seat: int, target_turn: int, cap: int) -> int | None:
    """Choose the first legal destination without displacing inherited economics."""
    _exact_int(cap, minimum=1, label="cap")
    market = _action_market(tape, target_turn, seat)
    for index, row in enumerate(market[:cap]):
        if row == ["PASS"]:
            return index
    if len(market) < cap:
        return len(market)
    return None


def candidate_destinations(
    tape: list,
    *,
    seat: int,
    source_turn: int,
    max_delay: int = DEFAULT_MAX_DELAY,
    cap: int = DEFAULT_MARKET_CAP,
) -> list[tuple[int, int]]:
    """Return later `(turn,row)` destinations in increasing delay order."""
    _exact_int(max_delay, minimum=1, label="max_delay")
    _exact_int(source_turn, minimum=0, label="source_turn")
    end = min(len(tape), source_turn + max_delay + 1)
    out: list[tuple[int, int]] = []
    for target_turn in range(source_turn + 1, end):
        row = destination_row(tape, seat, target_turn, cap)
        if row is not None:
            out.append((target_turn, row))
    return out


def _row_metric(
    result: dict, branch: str, turn: int, seat: int, row: int, metric: str
) -> int | None:
    try:
        rows = result[branch]["reports"][turn]["rows"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(rows, list):
        return None
    matches = []
    for record in rows:
        if not isinstance(record, dict):
            return None
        if record.get("seat") == seat and record.get("row") == row:
            matches.append(record)
    if len(matches) != 1:
        return None
    value = matches[0].get(metric)
    return value if type(value) is int and value >= 0 else None


def _filled_units(result: dict, branch: str, turn: int, seat: int, row: int) -> int | None:
    return _row_metric(result, branch, turn, seat, row, "sold")


def _sale_cash(result: dict, branch: str, turn: int, seat: int, row: int) -> int | None:
    return _row_metric(result, branch, turn, seat, row, "sale_cash")


def _load_sale_window():
    # Lazy import keeps pure shape helpers independently testable/compilable.
    import sale_window  # type: ignore

    return sale_window


def search(
    engine: Any,
    state: Any,
    env: Any,
    tape: list,
    *,
    start_step: int,
    seat: int,
    source_turn: int,
    source_row_index: int,
    max_delay: int = DEFAULT_MAX_DELAY,
) -> dict:
    """Measure all legal later EGG-sale placements under one fixed action tape.

    Every candidate is evaluated by the canonical full-interpreter sale-window
    counterfactual.  The opponent remains fixed/open-loop exactly as required by
    that harness.  `best_positive` means the same positive EGG units actually
    sold later for a strictly larger sale-specific receipt.  Net window cash is
    retained as a separate consequence metric because intervening purchases can
    succeed or fail solely due to the sale's timing.
    """
    _exact_int(start_step, minimum=0, label="start_step")
    src = source_row(tape, seat, source_turn, source_row_index)
    cap = _market_cap(env)
    sw = _load_sale_window()

    candidates = []
    for target_turn, target_row in candidate_destinations(
        tape, seat=seat, source_turn=source_turn, max_delay=max_delay, cap=cap
    ):
        moved = sw.shift_sale(
            tape, seat, source_turn, source_row_index, target_turn, target_row
        )
        result = sw.compare(engine, state, env, tape, moved, start_step, seat)
        source_filled = _filled_units(
            result, "baseline", source_turn, seat, source_row_index
        )
        target_filled = _filled_units(result, "candidate", target_turn, seat, target_row)
        source_sale_cash = _sale_cash(
            result, "baseline", source_turn, seat, source_row_index
        )
        target_sale_cash = _sale_cash(
            result, "candidate", target_turn, seat, target_row
        )
        units_valid = type(source_filled) is int and type(target_filled) is int
        receipts_valid = type(source_sale_cash) is int and type(target_sale_cash) is int
        realized = bool(
            units_valid and source_filled > 0 and target_filled == source_filled
        )
        receipt_evidence_valid = bool(realized and receipts_valid)
        sale_cash_delta = (
            target_sale_cash - source_sale_cash if receipt_evidence_valid else 0
        )
        own_delta = result["window_cash_delta"][seat]
        margin_delta = result["window_margin_delta"]
        row = {
            "target_turn": target_turn,
            "target_step": start_step + target_turn,
            "target_row": target_row,
            "delay_turns": target_turn - source_turn,
            "engagement": result["engagement"],
            "source_filled_units": source_filled,
            "target_filled_units": target_filled,
            "realized_retiming": realized,
            "receipt_evidence_valid": receipt_evidence_valid,
            "source_sale_cash": source_sale_cash,
            "target_sale_cash": target_sale_cash,
            "sale_cash_delta": sale_cash_delta,
            "own_cash_delta": own_delta,
            "window_margin_delta": margin_delta,
            "terminal_margin_delta": result["terminal_margin_delta"],
        }
        candidates.append(row)

    ranked = sorted(
        candidates,
        key=lambda row: (
            not row["realized_retiming"],
            -row["sale_cash_delta"],
            -row["own_cash_delta"],
            -row["window_margin_delta"],
            row["delay_turns"],
            row["target_turn"],
        ),
    )
    positive = [
        row
        for row in ranked
        if row["realized_retiming"]
        and row["receipt_evidence_valid"]
        and row["sale_cash_delta"] > 0
    ]
    return {
        "schema": SCHEMA,
        "item": ITEM,
        "source_turn": source_turn,
        "source_step": start_step + source_turn,
        "source_row": source_row_index,
        "source_requested_units": src[2],
        "max_delay": max_delay,
        "market_cap": cap,
        "candidate_count": len(candidates),
        "candidates": ranked,
        "best_positive": positive[0] if positive else None,
        "positive_definition": (
            "equal positive EGG sold units and target_sale_cash > source_sale_cash"
        ),
        "policy_claim": False,
        "optimality_claim": False,
        "runtime_mutation": False,
        "literal_direct_egg_short_squeeze_supported": False,
        "interpretation": (
            "bounded full-interpreter open-loop search over later placements of one existing EGG SELL; "
            "sale-specific receipt improvement is scarcity-timing evidence, while net window cash is a separate consequence metric"
        ),
    }
