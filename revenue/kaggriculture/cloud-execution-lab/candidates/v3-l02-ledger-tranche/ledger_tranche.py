# SPDX-License-Identifier: Apache-2.0
"""State-coherent late-game sale tranches for a single selected TITAN action.

The module is intentionally a selected-action overlay.  It never calls a policy,
never moves an inherited market row, and only mutates quantities inside the
engine's executable first-N prefix or appends into trailing executable slack.
Tracked product changes are reconciled into FrozenSelected's pending/planned
ledger before TitanAgent snapshots that state.  WHEAT is handled separately in
front of the existing feed-stock guard; FERTILIZER is never touched here.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

DAY_FROM = 28
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_EPISODE_STEPS = 720
DEFAULT_MAX_ORDERS = 10

# FrozenSelected owns exactly the non-operating products.  Preserve that split:
# WHEAT is guarded by protect_feed_stock; FERTILIZER is owned by idle fertilizer.
TRACKED_PRODUCTS = (
    "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL",
)
SELL_ALL_WHEN_ABSENT = (
    "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL",
)
CARROT_FLOOR = 32
WHEAT_FLOOR = 57


def _uint(value: Any, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"expected integer >= {minimum}")
    return value


def observation_step(observation: Mapping[str, Any], configuration: Mapping[str, Any] | None = None) -> int:
    cfg = dict(configuration or {})
    raw = observation.get("step")
    if raw is not None:
        return _uint(raw)
    turns = _uint(cfg.get("turnsPerDay", DEFAULT_TURNS_PER_DAY), minimum=1)
    return _uint(observation.get("day")) * turns + _uint(observation.get("hour"))


def _quantity(order: Any) -> int | None:
    if not (isinstance(order, list) and len(order) > 2):
        return None
    value = order[2]
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(0, value)


def _is_sell(order: Any, item: str | None = None) -> bool:
    return (isinstance(order, list) and len(order) > 1 and order[0] == "SELL"
            and isinstance(order[1], str) and (item is None or order[1] == item))


def executable_sales(market: Sequence[Any], shed: Mapping[str, Any], max_orders: int) -> dict[str, int]:
    """Return physical fills in the official first-N order prefix.

    Sale quantity is clipped by the observed post-unit shed in queue order.  The
    helper deliberately does not model price; it is used only for stock/ledger
    identity, where market price cannot change the number of units removed.
    Malformed rows are left to the engine and contribute no invented fill here.
    """
    limit = _uint(max_orders, minimum=1)
    remaining: dict[str, int] = {}
    for item, raw in dict(shed or {}).items():
        try:
            remaining[str(item)] = _uint(raw)
        except (TypeError, ValueError):
            continue
    sold: Counter[str] = Counter()
    for order in list(market or ())[:limit]:
        if not _is_sell(order):
            continue
        quantity = _quantity(order)
        if quantity is None:
            continue
        item = order[1]
        fill = min(quantity, remaining.get(item, 0))
        sold[item] += fill
        remaining[item] = max(0, remaining.get(item, 0) - fill)
    return dict(sold)


def _late_window(step: int, configuration: Mapping[str, Any] | None) -> tuple[bool, int, int]:
    cfg = dict(configuration or {})
    turns = _uint(cfg.get("turnsPerDay", DEFAULT_TURNS_PER_DAY), minimum=1)
    episode = _uint(cfg.get("episodeSteps", DEFAULT_EPISODE_STEPS), minimum=2)
    last = episode - 2
    return step // turns >= DAY_FROM and step < last, turns, last


def _copy_market(market: Sequence[Any]) -> list[Any]:
    # Market rows are tiny, but nested unknown rows must remain byte-equivalent.
    return deepcopy(list(market))


def _raise_active_total(market: list[Any], item: str, target: int, shed: Mapping[str, Any],
                        max_orders: int, *, append_if_absent: bool) -> dict[str, Any]:
    """Raise one product's executable requested total without moving rows."""
    limit = _uint(max_orders, minimum=1)
    before = executable_sales(market, shed, limit).get(item, 0)
    target = max(0, min(_uint(target), _uint(dict(shed).get(item, 0))))
    report = {"item": item, "before": before, "target": target, "after": before,
              "changed": False, "row": None, "reason": "already_at_target"}
    if before >= target or target <= 0:
        return report

    active = market[:limit]
    indices = [index for index, order in enumerate(active) if _is_sell(order, item)]
    if any(_quantity(active[index]) is None for index in indices):
        report["reason"] = "malformed_active_sell"
        return report

    needed = target - before
    if indices:
        index = indices[-1]
        market[index][2] = _quantity(market[index]) + needed
        report.update(changed=True, row=index, reason="enlarged_existing")
    elif append_if_absent and len(market) < limit:
        index = len(market)
        market.append(["SELL", item, needed])
        report.update(changed=True, row=index, reason="appended_trailing_slack")
    else:
        report["reason"] = "no_trailing_executable_slack"
        return report

    after = executable_sales(market, shed, limit).get(item, 0)
    if after < target:
        raise AssertionError("sale edit failed to realize its bounded stock target")
    report["after"] = after
    return report


def apply_product_tranche(selected_action: Mapping[str, Any], shed: Mapping[str, Any],
                          observation: Mapping[str, Any], configuration: Mapping[str, Any] | None = None
                          ) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Apply the L01-derived product tranche inside the seller-owned boundary.

    CARROT is raised to at most 32 physical units.  Other tracked products are
    offered in full only when the inherited active prefix has no SELL for that
    product, matching the leader-derived L01 arm while eliminating its stale
    seller-state defect.  Existing rows and the inactive tail never move.
    """
    cfg = dict(configuration or {})
    try:
        step = observation_step(observation, cfg)
        enabled, _turns, last = _late_window(step, cfg)
        limit = _uint(cfg.get("maxMarketOrdersPerTurn", DEFAULT_MAX_ORDERS), minimum=1)
    except (TypeError, ValueError) as exc:
        return selected_action, {"changed": False, "reason": "invalid_configuration",
                                 "error": f"{type(exc).__name__}: {exc}"}
    report: dict[str, Any] = {"changed": False, "reason": "outside_late_window",
                              "step": step, "last": last, "max_orders": limit,
                              "edits": [], "changed_items": []}
    if not enabled:
        return selected_action, report
    market = selected_action.get("market")
    if not isinstance(market, list) or not isinstance(shed, Mapping):
        report["reason"] = "unsupported_action_or_shed"
        return selected_action, report

    candidate = _copy_market(market)
    inactive_before = deepcopy(market[limit:])
    # Fail closed on any malformed active SELL for a tracked product before any edit.
    # Partial commits across products violate the selected-state transaction contract.
    for order in candidate[:limit]:
        if not _is_sell(order):
            continue
        item = order[1]
        if item not in TRACKED_PRODUCTS and item != "WHEAT":
            continue
        if _quantity(order) is None:
            report["reason"] = "malformed_active_sell"
            report["error"] = f"malformed active SELL for {item!r}"
            return selected_action, report
    try:
        carrot_stock = _uint(dict(shed).get("CARROT", 0))
        if carrot_stock > 0:
            edit = _raise_active_total(candidate, "CARROT", min(CARROT_FLOOR, carrot_stock),
                                       shed, limit, append_if_absent=True)
            report["edits"].append(edit)
        for item in SELL_ALL_WHEN_ABSENT:
            stock = _uint(dict(shed).get(item, 0))
            if stock <= 0:
                continue
            # L01 left an inherited active sale untouched for these products.
            active_has_item = any(_is_sell(order, item) for order in candidate[:limit])
            if active_has_item:
                report["edits"].append({"item": item, "before": executable_sales(
                    candidate, shed, limit).get(item, 0), "target": stock,
                    "after": executable_sales(candidate, shed, limit).get(item, 0),
                    "changed": False, "row": None, "reason": "inherited_active_sell"})
                continue
            edit = _raise_active_total(candidate, item, stock, shed, limit,
                                       append_if_absent=True)
            report["edits"].append(edit)
    except (TypeError, ValueError, AssertionError) as exc:
        report.update(reason="fail_closed", error=f"{type(exc).__name__}: {exc}")
        return selected_action, report

    if market[limit:] != inactive_before or candidate[limit:] != inactive_before:
        raise AssertionError("inactive market tail changed")
    changed_items = [edit["item"] for edit in report["edits"] if edit.get("changed")]
    if not changed_items:
        report["reason"] = "no_safe_edit"
        return selected_action, report
    out = dict(selected_action)
    out["market"] = candidate
    report.update(changed=True, reason="applied", changed_items=changed_items,
                  active_before=executable_sales(market, shed, limit),
                  active_after=executable_sales(candidate, shed, limit),
                  inherited_rows=len(market), returned_rows=len(candidate),
                  inactive_tail_preserved=True)
    return out, report


def _trim_future(rows: Iterable[Any], remaining: int, step: int) -> list[tuple[int, int]]:
    left = _uint(remaining)
    kept: list[tuple[int, int]] = []
    for raw in list(rows or ()):
        if not (isinstance(raw, (list, tuple)) and len(raw) == 2):
            raise ValueError("malformed planned sale row")
        when, quantity = raw
        when = _uint(when)
        quantity = _uint(quantity)
        if when <= step or quantity <= 0 or left <= 0:
            continue
        take = min(quantity, left)
        kept.append((when, take))
        left -= take
    return kept


def reconciled_ledger(planned: Mapping[str, Sequence[Any]], pending: Mapping[str, Any],
                      shed: Mapping[str, Any], market: Sequence[Any], step: int,
                      max_orders: int, changed_items: Iterable[str]
                      ) -> tuple[dict[str, list[tuple[int, int]]], dict[str, int], dict[str, Any]]:
    """Return a checkpoint-ready seller ledger matching the emitted active queue."""
    step = _uint(step)
    limit = _uint(max_orders, minimum=1)
    fills = executable_sales(market, shed, limit)
    new_planned = {str(item): [tuple(row) for row in rows]
                   for item, rows in dict(planned or {}).items()}
    new_pending: dict[str, int] = {}
    for item, raw in dict(pending or {}).items():
        new_pending[str(item)] = _uint(raw)
    item_reports = []
    for item in dict.fromkeys(changed_items):
        if item not in TRACKED_PRODUCTS:
            raise ValueError(f"unsupported ledger item {item!r}")
        stock = _uint(dict(shed).get(item, 0))
        sold = min(stock, max(0, int(fills.get(item, 0))))
        remaining = stock - sold
        before_rows = list(new_planned.get(item, ()))
        after_rows = _trim_future(before_rows, remaining, step)
        new_pending[item] = remaining
        if after_rows:
            new_planned[item] = after_rows
        else:
            new_planned.pop(item, None)
        item_reports.append({"item": item, "stock": stock, "active_sold": sold,
                             "pending_before": dict(pending or {}).get(item),
                             "pending_after": remaining,
                             "planned_before": before_rows,
                             "planned_after": after_rows})
    return new_planned, new_pending, {"items": item_reports, "active_fills": fills,
                                      "first_n": limit}


def apply_and_reconcile(consumer: Any, selected_action: Mapping[str, Any],
                        shed: Mapping[str, Any], observation: Mapping[str, Any],
                        configuration: Mapping[str, Any] | None = None
                        ) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Atomically apply an action edit and its FrozenSelected state update."""
    out, report = apply_product_tranche(selected_action, shed, observation, configuration)
    if not report.get("changed"):
        return out, report
    cfg = dict(configuration or {})
    try:
        step = observation_step(observation, cfg)
        limit = _uint(cfg.get("maxMarketOrdersPerTurn", DEFAULT_MAX_ORDERS), minimum=1)
        planned, pending, ledger = reconciled_ledger(
            consumer.planned, consumer.pending, shed, out["market"], step, limit,
            report["changed_items"])
    except (AttributeError, TypeError, ValueError) as exc:
        failed = dict(report)
        failed.update(changed=False, reason="ledger_reconciliation_failed",
                      error=f"{type(exc).__name__}: {exc}")
        return selected_action, failed
    # Commit only after every item validates, so action/state cannot diverge.
    consumer.planned = planned
    consumer.pending = pending
    report["ledger"] = ledger
    return out, report


def apply_wheat_before_feed_guard(selected_action: Mapping[str, Any], shed: Mapping[str, Any],
                                  observation: Mapping[str, Any], configuration: Mapping[str, Any] | None = None
                                  ) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Raise late WHEAT inside active slack, before the existing feed guard runs."""
    cfg = dict(configuration or {})
    try:
        step = observation_step(observation, cfg)
        enabled, _turns, last = _late_window(step, cfg)
        limit = _uint(cfg.get("maxMarketOrdersPerTurn", DEFAULT_MAX_ORDERS), minimum=1)
    except (TypeError, ValueError) as exc:
        return selected_action, {"changed": False, "reason": "invalid_configuration",
                                 "error": f"{type(exc).__name__}: {exc}"}
    report = {"changed": False, "reason": "outside_late_window", "step": step,
              "last": last, "max_orders": limit}
    if not enabled:
        return selected_action, report
    market = selected_action.get("market")
    if not isinstance(market, list) or not isinstance(shed, Mapping):
        report["reason"] = "unsupported_action_or_shed"
        return selected_action, report
    candidate = _copy_market(market)
    inactive_before = deepcopy(market[limit:])
    try:
        stock = _uint(dict(shed).get("WHEAT", 0))
        edit = _raise_active_total(candidate, "WHEAT", min(WHEAT_FLOOR, stock),
                                   shed, limit, append_if_absent=True)
    except (TypeError, ValueError, AssertionError) as exc:
        report.update(reason="fail_closed", error=f"{type(exc).__name__}: {exc}")
        return selected_action, report
    if not edit.get("changed"):
        report.update(reason=edit.get("reason", "no_safe_edit"), edit=edit)
        return selected_action, report
    if candidate[limit:] != inactive_before:
        raise AssertionError("inactive market tail changed")
    out = dict(selected_action)
    out["market"] = candidate
    report.update(changed=True, reason="proposed_before_feed_guard", edit=edit,
                  inactive_tail_preserved=True)
    return out, report


def _matching_snapshot(agent: Any, observation: Mapping[str, Any], selected: Mapping[str, Any]):
    consumer = getattr(agent, "consumer", None)
    pair = getattr(consumer, "selected_post_units", None)
    binding = getattr(consumer, "selected_post_units_binding", None)
    if pair is None or binding is None:
        return None
    try:
        expected = (observation_step(observation), int(observation["player"]),
                    selected.get("farmer"), selected.get("hands", []))
    except (KeyError, TypeError, ValueError):
        return None
    if tuple(binding[:2]) != expected[:2] or tuple(binding[2:]) != expected[2:]:
        return None
    return pair


def _wrap_consumer(agent: Any, state: MutableMapping[str, Any]) -> None:
    consumer = getattr(agent, "consumer", None)
    if consumer is None or getattr(consumer, "_l02_wrapped", False):
        return
    original = consumer.transform

    def transform(observation, configuration, selected):
        cfg = dict(configuration or {})
        try:
            step = observation_step(observation, cfg)
            late, _turns, _last = _late_window(step, cfg)
        except (TypeError, ValueError):
            late = False
        previous_capture = bool(getattr(consumer, "capture_post_units", False))
        if late:
            consumer.capture_post_units = True
        try:
            returned = original(observation, configuration, selected)
        finally:
            consumer.capture_post_units = previous_capture
        report: dict[str, Any] = {"changed": False, "reason": "no_matching_post_unit_snapshot"}
        pair = _matching_snapshot(agent, observation, returned)
        if pair is not None:
            returned, report = apply_and_reconcile(
                consumer, returned, pair[1].get("shed", {}), observation, cfg)
        state["last_product_report"] = deepcopy(report)
        if report.get("changed"):
            state["product_changed_turns"] = state.get("product_changed_turns", 0) + 1
            state["product_units_added"] = state.get("product_units_added", 0) + sum(
                max(0, int(edit.get("after", 0)) - int(edit.get("before", 0)))
                for edit in report.get("edits", ()) if edit.get("changed"))
        diagnostics = getattr(consumer, "diagnostics", None)
        if isinstance(diagnostics, dict):
            diagnostics["l02_product_tranche"] = deepcopy(report)
        if isinstance(getattr(agent, "diagnostics", None), dict):
            agent.diagnostics["l02_product_tranche"] = deepcopy(report)
        return returned

    consumer.transform = transform
    consumer._l02_wrapped = True


def install(agent: Any) -> Any:
    """Install one producer-preserving overlay on a TitanAgent instance."""
    if getattr(agent, "_l02_installed", False):
        return agent
    state: dict[str, Any] = {"product_changed_turns": 0, "product_units_added": 0,
                             "wheat_changed_turns": 0}
    original_initialize = agent._initialize
    original_feed = agent._feed_stock_selected

    def initialize():
        original_initialize()
        _wrap_consumer(agent, state)

    def feed_stock(observation, configuration, selected):
        report: dict[str, Any] = {"changed": False, "reason": "no_matching_post_unit_snapshot"}
        pair = _matching_snapshot(agent, observation, selected)
        proposed = selected
        feed_guard_enabled = bool(getattr(getattr(agent, "features", None),
                                          "operating_stock", False))
        if pair is not None and feed_guard_enabled:
            proposed, report = apply_wheat_before_feed_guard(
                selected, pair[1].get("shed", {}), observation, configuration)
        elif pair is not None:
            report = {"changed": False, "reason": "feed_guard_disabled"}
        guarded = original_feed(observation, configuration, proposed)
        if report.get("changed"):
            state["wheat_changed_turns"] += 1
            limit = int(dict(configuration or {}).get("maxMarketOrdersPerTurn", DEFAULT_MAX_ORDERS))
            stock = pair[1].get("shed", {}) if pair is not None else {}
            report["after_feed_guard"] = executable_sales(
                guarded.get("market", []), stock, max(1, limit)).get("WHEAT", 0)
        state["last_wheat_report"] = deepcopy(report)
        if isinstance(getattr(agent, "diagnostics", None), dict):
            agent.diagnostics["l02_wheat_tranche"] = deepcopy(report)
        return guarded

    agent._initialize = initialize
    agent._feed_stock_selected = feed_stock
    agent._l02_state = state
    agent._l02_installed = True
    return agent
