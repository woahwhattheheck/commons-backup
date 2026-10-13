# SPDX-License-Identifier: Apache-2.0
"""Pure certificates for bounded worker-job payback.

The route owner supplies only facts it has already certified: an exact worker
action stream, attributed input purchases, attributed sale receipts, and market
slots proved free of baseline obligations.  This module does not mutate a route,
forecast a market, inspect opponent-private state, or infer future fills.

A valid report can therefore rank or admit a worker job without stealing custody
from the route/finalizer.  Missing, malformed, or temporally ambiguous evidence
fails closed with ``complete=False`` / ``admitted=False``.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


MOVES = frozenset(("NORTH", "SOUTH", "EAST", "WEST"))
SUPPORTED_ACTIONS = MOVES | frozenset((
    "PASS", "WATER", "CARE", "FEED", "HARVEST", "COLLECT_FERTILIZER",
    "DROP", "PICKUP", "PLANT", "FERTILIZE", "DIG",
))
# Only actions whose successful returned execution can directly materialize the
# certified output in the worker's inventory.  This stays intentionally narrow:
# FEED/CARE can create future opportunity but are not themselves sale provenance.
OUTPUT_PRODUCERS = frozenset(("HARVEST", "COLLECT_FERTILIZER"))


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value: Any, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} cannot be a boolean")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return result


def _item(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _action_ops(actions: Sequence[Sequence[Any]]) -> list[str]:
    if isinstance(actions, (str, bytes)) or not isinstance(actions, Sequence):
        raise ValueError("actions must be a sequence")
    result = []
    for index, action in enumerate(actions):
        if (isinstance(action, (str, bytes)) or not isinstance(action, Sequence)
                or not action or not isinstance(action[0], str)):
            raise ValueError(f"action {index} must use the official list schema")
        op = action[0]
        if op not in SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported worker action {op}")
        result.append(op)
    return result


def _stock(value: Mapping[str, Any], name: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    result = {}
    for item, quantity in value.items():
        result[_item(item, f"{name} item")] = _integer(quantity, f"{name} quantity")
    return result


def _free_slots(value: Mapping[Any, Any], max_slots: int) -> dict[int, frozenset[int]]:
    if not isinstance(value, Mapping):
        raise ValueError("free_market_slots must be a mapping")
    result = {}
    for raw_step, raw_slots in value.items():
        step = _integer(raw_step, "free-slot step")
        if isinstance(raw_slots, (str, bytes, Mapping)):
            raise ValueError("free-slot rows must be iterables of slot integers")
        try:
            slots = frozenset(_integer(slot, "free market slot") for slot in raw_slots)
        except TypeError as exc:
            raise ValueError("free-slot rows must be iterable") from exc
        if any(slot >= max_slots for slot in slots):
            raise ValueError("free market slot exceeds configured slot bound")
        result[step] = slots
    return result


def _requirements(requirements: Sequence[Mapping[str, Any]], *, kind: str,
                  start_step: int, ops: Sequence[str]) -> list[dict[str, Any]]:
    if isinstance(requirements, (str, bytes)) or not isinstance(requirements, Sequence):
        raise ValueError(f"{kind} requirements must be a sequence")
    result = []
    collected_steps = set()
    end_step = start_step + len(ops) - 1
    for raw in requirements:
        if not isinstance(raw, Mapping):
            raise ValueError(f"{kind} requirement must be a mapping")
        item = _item(raw.get("item"), f"{kind} item")
        quantity = _integer(raw.get("quantity"), f"{kind} quantity", minimum=1)
        if kind == "input":
            step = _integer(raw.get("needed_step"), "input needed_step")
            action = _item(raw.get("consumer"), "input consumer")
            if not start_step <= step <= end_step:
                raise ValueError("input needed_step lies outside worker action stream")
            if action not in SUPPORTED_ACTIONS or ops[step-start_step] != action:
                raise ValueError("input consumer does not match worker action stream")
            result.append({"item": item, "quantity": quantity,
                           "needed_step": step, "consumer": action})
        else:
            produced = _integer(raw.get("produced_step"), "output produced_step")
            ready = _integer(raw.get("sale_ready_step"), "output sale_ready_step")
            producer = _item(raw.get("producer", "HARVEST"), "output producer")
            if not start_step <= produced <= end_step or not produced <= ready <= end_step:
                raise ValueError("output production/deposit lies outside worker action stream")
            if producer not in OUTPUT_PRODUCERS:
                raise ValueError("output producer is not a certified materializing action")
            if ops[produced-start_step] != producer:
                raise ValueError("output producer does not match worker action stream")
            if producer == "COLLECT_FERTILIZER":
                # The official engine has an exact postimage: one successful
                # collection flips fertilizer_available and materializes exactly
                # one FERTILIZER in this worker's inventory.  Do not let the
                # certificate relabel, multiply, or reuse that physical unit.
                if item != "FERTILIZER" or quantity != 1:
                    raise ValueError("COLLECT_FERTILIZER certifies one FERTILIZER")
                if produced in collected_steps:
                    raise ValueError("COLLECT_FERTILIZER produced_step reused")
                collected_steps.add(produced)
            if ops[ready-start_step] != "DROP":
                raise ValueError("output sale_ready_step is not an explicit DROP action")
            result.append({"item": item, "quantity": quantity, "producer": producer,
                           "produced_step": produced, "sale_ready_step": ready})
    return result


def evaluate_worker_job(*, start_step: int, actions: Sequence[Sequence[Any]],
                        available_unit_steps: int, payback_deadline_step: int,
                        required_services: Mapping[str, Any],
                        input_requirements: Sequence[Mapping[str, Any]],
                        owned_inputs: Mapping[str, Any],
                        expected_outputs: Sequence[Mapping[str, Any]],
                        market_events: Sequence[Mapping[str, Any]],
                        free_market_slots: Mapping[Any, Any],
                        starting_cash: Any, reserved_cash: Any = 0,
                        max_market_slots: int = 10, minimum_gain: Any = 0) -> dict[str, Any]:
    """Evaluate one already-authored worker job from explicit bounded evidence.

    Input purchases are credited only when they execute *before* their consuming
    unit action because Kaggriculture unit actions precede the market queue.
    Output receipts are credited only when a certified materializing action
    (HARVEST by default, or explicit COLLECT_FERTILIZER) is followed by a DROP
    and a provenance-attributed sale at/after that deposit.  A collection can
    certify only the engine's exact one-unit FERTILIZER postimage and only once.
    Each physical input or sale unit can satisfy at most one certified
    requirement/output.  Market events must use caller-certified free slots.

    ``receipt_floor`` and ``cost_upper`` are deliberately caller-provided bounds;
    this helper never predicts a future quote or fill.  ``value_per_step`` is strict net
    cash payback per occupied worker step, so travel and service time both reduce
    otherwise-equal jobs without inventing a monetary wage.
    """
    report: dict[str, Any] = {"complete": False, "admitted": False,
                              "reason": "invalid_input"}
    try:
        start = _integer(start_step, "start_step")
        available = _integer(available_unit_steps, "available_unit_steps")
        deadline = _integer(payback_deadline_step, "payback_deadline_step")
        slots = _integer(max_market_slots, "max_market_slots", minimum=1)
        gain = _number(minimum_gain, "minimum_gain")
        cash = _number(starting_cash, "starting_cash")
        reserve = _number(reserved_cash, "reserved_cash")
        if cash < reserve:
            report.update(complete=True, reason="starting_cash_below_reserve")
            return report

        ops = _action_ops(actions)
        if not ops:
            raise ValueError("worker job must contain at least one action row")
        end_step = start + len(ops) - 1
        if len(ops) > available:
            report.update(complete=True, reason="unit_action_budget_exceeded")
            return report
        if deadline < end_step:
            report.update(complete=True, reason="payback_deadline_precedes_route_rejoin")
            return report

        if not isinstance(required_services, Mapping):
            raise ValueError("required_services must be a mapping")
        service_counts: dict[str, int] = {}
        for op in ops:
            if op not in MOVES and op != "PASS":
                service_counts[op] = service_counts.get(op, 0) + 1
        for raw_op, raw_count in required_services.items():
            op = _item(raw_op, "required service")
            count = _integer(raw_count, f"required {op} count")
            if op not in SUPPORTED_ACTIONS or op in MOVES or op == "PASS":
                raise ValueError("required service must be a supported non-move action")
            if service_counts.get(op, 0) < count:
                report.update(complete=True, reason="required_service_missing",
                              missing_service=op)
                return report

        inputs = _requirements(input_requirements, kind="input", start_step=start, ops=ops)
        outputs = _requirements(expected_outputs, kind="output", start_step=start, ops=ops)
        if not outputs:
            report.update(complete=True, reason="no_certified_output")
            return report
        owned = _stock(owned_inputs, "owned_inputs")
        free = _free_slots(free_market_slots, slots)

        if isinstance(market_events, (str, bytes)) or not isinstance(market_events, Sequence):
            raise ValueError("market_events must be a sequence")
        events = []
        occupied = set()
        for raw in market_events:
            if not isinstance(raw, Mapping):
                raise ValueError("market event must be a mapping")
            kind = raw.get("kind")
            if kind not in ("input", "sale"):
                raise ValueError("market event kind must be input or sale")
            step = _integer(raw.get("step"), "market event step")
            slot = _integer(raw.get("slot"), "market event slot")
            if slot >= slots:
                raise ValueError("market event slot exceeds configured slot bound")
            if not start <= step <= deadline:
                raise ValueError("market event lies outside job payback horizon")
            key = (step, slot)
            if key in occupied:
                raise ValueError("two worker-job events occupy the same market slot")
            occupied.add(key)
            if slot not in free.get(step, frozenset()):
                report.update(complete=True, reason="market_slot_not_certified_free",
                              step=step, slot=slot)
                return report
            item = _item(raw.get("item"), "market event item")
            quantity = _integer(raw.get("quantity"), "market event quantity", minimum=1)
            if kind == "input":
                amount = _number(raw.get("cost_upper"), "input cost_upper")
                events.append({"kind": kind, "step": step, "slot": slot, "item": item,
                               "quantity": quantity, "amount": amount})
            else:
                amount = _number(raw.get("receipt_floor"), "sale receipt_floor")
                events.append({"kind": kind, "step": step, "slot": slot, "item": item,
                               "quantity": quantity, "amount": amount})
        events.sort(key=lambda event: (event["step"], event["slot"]))

        # Physical input coverage. Same-step buys are deliberately too late, and
        # each owned/purchased unit can satisfy only one consuming action.
        consumed_inputs: dict[str, int] = {}
        for requirement in sorted(inputs, key=lambda row: (row["needed_step"], row["item"])):
            item = requirement["item"]
            need = requirement["quantity"]
            purchased = sum(event["quantity"] for event in events
                            if event["kind"] == "input" and event["item"] == item
                            and event["step"] < requirement["needed_step"])
            supplied = owned.get(item, 0) + purchased
            used = consumed_inputs.get(item, 0)
            if supplied - used < need:
                report.update(complete=True, reason="required_input_not_available",
                              item=item, needed_step=requirement["needed_step"],
                              required_quantity=used + need,
                              available_quantity=supplied)
                return report
            consumed_inputs[item] = used + need

        # Provenance-attributed output must reach certified sales after DROP.
        # Allocate each sale unit once, servicing latest-ready output first so
        # earlier/flexible output cannot consume capacity needed by a later DROP.
        sale_remaining = [event["quantity"] if event["kind"] == "sale" else 0
                          for event in events]
        for output in sorted(outputs,
                             key=lambda row: (row["sale_ready_step"], row["produced_step"]),
                             reverse=True):
            remaining = output["quantity"]
            for index, event in enumerate(events):
                if (remaining and event["kind"] == "sale"
                        and event["item"] == output["item"]
                        and event["step"] >= output["sale_ready_step"]
                        and sale_remaining[index]):
                    used = min(remaining, sale_remaining[index])
                    sale_remaining[index] -= used
                    remaining -= used
            if remaining:
                report.update(complete=True, reason="output_not_realized_in_sale",
                              item=output["item"], sale_ready_step=output["sale_ready_step"],
                              required_quantity=output["quantity"],
                              unmatched_quantity=remaining)
                return report
        for index, event in enumerate(events):
            if event["kind"] == "sale" and sale_remaining[index]:
                report.update(complete=True, reason="sale_not_attributed_to_output",
                              item=event["item"], sale_step=event["step"],
                              unmatched_quantity=sale_remaining[index])
                return report

        input_cost = 0.0
        sale_receipt = 0.0
        minimum_cash = cash
        incremental = 0.0
        cumulative = []
        cash_trace = []
        for event in events:
            if event["kind"] == "input":
                cash -= event["amount"]
                incremental -= event["amount"]
                input_cost += event["amount"]
            else:
                cash += event["amount"]
                incremental += event["amount"]
                sale_receipt += event["amount"]
            minimum_cash = min(minimum_cash, cash)
            cash_trace.append({"step": event["step"], "slot": event["slot"], "cash": cash})
            cumulative.append(incremental)
            if cash < reserve:
                report.update(complete=True, reason="cash_reserve_breached",
                              minimum_cash=minimum_cash, input_cost=input_cost,
                              sale_receipt=sale_receipt)
                return report

        net_gain = sale_receipt - input_cost
        if net_gain <= gain:
            report.update(complete=True, reason="no_strict_realized_payback",
                          net_gain=net_gain, input_cost=input_cost,
                          sale_receipt=sale_receipt, minimum_cash=minimum_cash)
            return report

        payback_step = None
        for index, event in enumerate(events):
            if cumulative[index] > gain and min(cumulative[index:]) > gain:
                payback_step = event["step"]
                break
        if payback_step is None:
            # Defensive: final strict gain should make the final event durable.
            raise ValueError("strict payback has no durable payback step")

        travel_steps = sum(op in MOVES for op in ops)
        active_steps = sum(op != "PASS" for op in ops)
        service_steps = active_steps - travel_steps
        span = len(ops)
        report.update(
            complete=True,
            admitted=True,
            reason="strict_realized_payback",
            start_step=start,
            end_step=end_step,
            payback_step=payback_step,
            span_steps=span,
            active_steps=active_steps,
            travel_steps=travel_steps,
            service_steps=service_steps,
            service_counts=service_counts,
            input_cost=input_cost,
            sale_receipt=sale_receipt,
            net_gain=net_gain,
            value_per_step=net_gain / span,
            minimum_cash=minimum_cash,
            cash_trace=cash_trace,
            market_slots_used=len(events),
        )
        return report
    except (KeyError, TypeError, ValueError, OverflowError):
        return report