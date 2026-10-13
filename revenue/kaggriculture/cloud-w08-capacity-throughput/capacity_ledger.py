# SPDX-License-Identifier: Apache-2.0
"""Exact bounded shed-capacity ledger for known own-farm event tapes.

The ledger models only deterministic physical inventory transitions.  It does
not call a policy, estimate an opponent, quote future cash, or infer private
state.  Callers must provide ordered, observed/selected own events.  In return
it proves which deposits, sales, pickups, and capacity-consuming buys actually
complete, accounts for every discarded unit, and checks per-item conservation.

This is intentionally independent of TITAN's top-level planner.  It is a small
oracle that producer transforms can use before claiming a job is complete.
"""
from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

PHASE_ORDER = {"unit": 0, "market": 1, "eod": 2}
_ITEM_OPS = {"HARVEST", "PICKUP", "PLACE", "SELL", "BUY_PRODUCT",
             "BUY_ANIMAL", "CONSUME"}
_OPS = _ITEM_OPS | {"DROP", "EOD_DROP", "PASS"}


def _uint(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _count_map(value: Mapping[str, Any] | None, name: str) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    out: dict[str, int] = {}
    for item, quantity in value.items():
        if not isinstance(item, str) or not item:
            raise ValueError(f"{name} item names must be non-empty strings")
        q = _uint(quantity, f"{name}[{item!r}]")
        if q:
            out[item] = q
    return out


def _order_key(event: Mapping[str, Any]) -> tuple[int, int, int]:
    """Engine-bound ordering key without input-offset tie-breakers."""
    step = _uint(event.get("step"), "event.step")
    phase = event.get("phase")
    if phase not in PHASE_ORDER:
        raise ValueError(f"event.phase must be one of {tuple(PHASE_ORDER)}")
    sequence = _uint(event.get("sequence", 0), "event.sequence")
    return step, PHASE_ORDER[phase], sequence


def _event_key(event: Mapping[str, Any], offset: int) -> tuple[int, int, int, int]:
    step, phase_ord, sequence = _order_key(event)
    return step, phase_ord, sequence, offset


def _normalise_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(events, (str, bytes, Mapping)):
        raise ValueError("events must be an iterable of mappings")
    out: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []
    ids: set[str] = set()
    order_keys: dict[tuple[int, int, int], str] = {}
    for offset, raw in enumerate(events):
        if not isinstance(raw, Mapping):
            raise ValueError(f"event {offset} must be a mapping")
        event = copy.deepcopy(dict(raw))
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError(f"event {offset}.id must be a non-empty string")
        if event_id in ids:
            raise ValueError(f"duplicate event id: {event_id}")
        ids.add(event_id)
        op = event.get("op")
        if op not in _OPS:
            raise ValueError(f"event {event_id!r} has unsupported op {op!r}")
        if op in _ITEM_OPS:
            item = event.get("item")
            if not isinstance(item, str) or not item:
                raise ValueError(f"event {event_id!r}.item must be a non-empty string")
            event["quantity"] = _uint(event.get("quantity", 1),
                                      f"event {event_id!r}.quantity")
            if "available" in event:
                event["available"] = _uint(event["available"],
                                            f"event {event_id!r}.available")
        elif "quantity" in event:
            raise ValueError(f"event {event_id!r} op {op} does not take quantity")
        if op in {"HARVEST", "PICKUP", "PLACE", "CONSUME", "DROP"}:
            event["actor"] = _uint(event.get("actor"), f"event {event_id!r}.actor")
        elif "actor" in event:
            event["actor"] = _uint(event["actor"], f"event {event_id!r}.actor")
        # Shed-oracle boundary: PLACE must be explicitly destination-bound to shed.
        # Engine routes PLACE <ANIMAL> on a matching structure to board placement;
        # only shed-adjacent non-structure PLACE takes the inventory path.
        if op == "PLACE":
            dest = event.get("destination")
            if dest != "shed":
                raise ValueError(
                    f"event {event_id!r} PLACE requires destination='shed' "
                    f"(got {dest!r}); structure/animal board placement is outside "
                    "this shed-capacity oracle"
                )
        key = _event_key(event, offset)
        order = _order_key(event)
        if order in order_keys:
            raise ValueError(
                f"duplicate ordering key {order} for events "
                f"{order_keys[order]!r} and {event_id!r}; "
                "supply distinct engine-bound sequence (actor / market row / EOD) "
                "rather than relying on cross-list insertion order"
            )
        order_keys[order] = event_id
        out.append((key, event))
    out.sort(key=lambda row: row[0])
    return [event for _, event in out]


def _add(counter: dict[str, int], item: str, quantity: int) -> None:
    if quantity <= 0:
        return
    counter[item] = counter.get(item, 0) + quantity


def _take(counter: dict[str, int], item: str, requested: int) -> int:
    quantity = min(requested, counter.get(item, 0))
    if quantity:
        left = counter[item] - quantity
        if left:
            counter[item] = left
        else:
            del counter[item]
    return quantity


def _total(mapping: Mapping[str, int]) -> int:
    return sum(mapping.values())


def _all_carried(carried: Mapping[int, Mapping[str, int]]) -> dict[str, int]:
    out: Counter[str] = Counter()
    for inventory in carried.values():
        out.update(inventory)
    return dict(out)


def _snapshot(shed: Mapping[str, int], carried: Mapping[int, Mapping[str, int]]) -> dict[str, Any]:
    return {
        "shed": copy.deepcopy(dict(shed)),
        "carried": {str(actor): copy.deepcopy(dict(inventory))
                    for actor, inventory in sorted(carried.items())},
        "shed_total": _total(shed),
        "carried_total": sum(_total(inventory) for inventory in carried.values()),
    }


def simulate_capacity(
    *,
    capacity: int,
    initial_shed: Mapping[str, Any] | None,
    initial_carried: Mapping[int, Mapping[str, Any]] | None,
    events: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute a deterministic own-farm capacity tape and return exact receipts.

    ``quantity`` is the amount the selected/observed event attempts.  Optional
    ``available`` is a caller-proven upper bound (for example affordable market
    units or harvestable yield).  Capacity then clips physical completion.

    Engine-faithful distinctions:
    * DROP and EOD_DROP delete overflow from carried inventory.
    * PLACE leaves any unplaced remainder carried; requires destination='shed'.
    * SELL and PICKUP clip to current shed stock.
    * BUY_PRODUCT/BUY_ANIMAL clip to remaining shed room.
    * unit events precede market events at the same step; EOD is last.
    * Duplicate (step, phase, sequence) keys are rejected; order is not
      inferred from baseline-vs-additive list position.
    """
    cap = _uint(capacity, "capacity", 1)
    shed = _count_map(initial_shed, "initial_shed")
    if _total(shed) > cap:
        raise ValueError("initial shed exceeds capacity")
    if initial_carried is None:
        initial_carried = {}
    if not isinstance(initial_carried, Mapping):
        raise ValueError("initial_carried must be a mapping")
    carried: dict[int, dict[str, int]] = {}
    for actor, inventory in initial_carried.items():
        actor_id = _uint(actor, "initial_carried actor")
        carried[actor_id] = _count_map(inventory, f"initial_carried[{actor_id}]")

    ordered = _normalise_events(events)
    initial_items: Counter[str] = Counter(shed)
    initial_items.update(_all_carried(carried))
    sources: Counter[str] = Counter(initial_items)
    sinks: Counter[str] = Counter()
    discarded: Counter[str] = Counter()
    sold: Counter[str] = Counter()
    consumed: Counter[str] = Counter()
    bought: Counter[str] = Counter()
    harvested: Counter[str] = Counter()
    receipts: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []

    def inventory(actor: int) -> dict[str, int]:
        return carried.setdefault(actor, {})

    def record(event: Mapping[str, Any], *, requested: int = 0, realized: int = 0,
               event_discarded: int = 0, reason: str = "complete",
               before: Mapping[str, Any]) -> None:
        after = _snapshot(shed, carried)
        receipt = {
            "id": event["id"], "step": event["step"], "phase": event["phase"],
            "sequence": event.get("sequence", 0), "op": event["op"],
            "actor": event.get("actor"), "item": event.get("item"),
            "requested": requested, "realized": realized,
            "discarded": event_discarded, "reason": reason,
            "shed_before": before["shed_total"], "shed_after": after["shed_total"],
            "carried_before": before["carried_total"],
            "carried_after": after["carried_total"],
        }
        receipts.append(receipt)
        timeline.append({"event": receipt, "state": after})

    for event in ordered:
        before = _snapshot(shed, carried)
        op = event["op"]
        requested = int(event.get("quantity", 0))
        available = int(event.get("available", requested))
        attempted = min(requested, available)
        realized = 0
        lost = 0
        reason = "complete"

        if op == "PASS":
            record(event, before=before)
            continue
        if op == "HARVEST":
            realized = attempted
            _add(inventory(event["actor"]), event["item"], realized)
            sources[event["item"]] += realized
            harvested[event["item"]] += realized
        elif op == "PICKUP":
            realized = _take(shed, event["item"], attempted)
            _add(inventory(event["actor"]), event["item"], realized)
        elif op == "CONSUME":
            realized = _take(inventory(event["actor"]), event["item"], attempted)
            sinks[event["item"]] += realized
            consumed[event["item"]] += realized
        elif op == "PLACE":
            taken = _take(inventory(event["actor"]), event["item"], attempted)
            room = max(0, cap - _total(shed))
            realized = min(taken, room)
            _add(shed, event["item"], realized)
            remainder = taken - realized
            _add(inventory(event["actor"]), event["item"], remainder)
        elif op == "DROP":
            inv = inventory(event["actor"])
            requested = _total(inv)
            for item, quantity in list(inv.items()):
                room = max(0, cap - _total(shed))
                deposited = min(quantity, room)
                _add(shed, item, deposited)
                overflow = quantity - deposited
                if overflow:
                    discarded[item] += overflow
                    sinks[item] += overflow
                    lost += overflow
                realized += deposited
                del inv[item]
        elif op == "SELL":
            realized = _take(shed, event["item"], attempted)
            sold[event["item"]] += realized
            sinks[event["item"]] += realized
        elif op in {"BUY_PRODUCT", "BUY_ANIMAL"}:
            room = max(0, cap - _total(shed))
            realized = min(attempted, room)
            _add(shed, event["item"], realized)
            bought[event["item"]] += realized
            sources[event["item"]] += realized
        elif op == "EOD_DROP":
            for actor in sorted(carried):
                inv = carried[actor]
                requested += _total(inv)
                for item, quantity in list(inv.items()):
                    room = max(0, cap - _total(shed))
                    deposited = min(quantity, room)
                    _add(shed, item, deposited)
                    overflow = quantity - deposited
                    if overflow:
                        discarded[item] += overflow
                        sinks[item] += overflow
                        lost += overflow
                    realized += deposited
                    del inv[item]

        if realized < requested or lost:
            reason = "capacity_or_stock_clipped"
        record(event, requested=requested, realized=realized,
               event_discarded=lost, reason=reason, before=before)
        if _total(shed) > cap:
            raise AssertionError("ledger permitted shed overflow")

    final_carried = Counter(_all_carried(carried))
    final = Counter(shed); final.update(final_carried)
    errors = {
        item: sources[item] - sinks[item] - final[item]
        for item in sorted(set(sources) | set(sinks) | set(final))
        if sources[item] - sinks[item] - final[item]
    }
    if errors:
        raise AssertionError(f"capacity ledger conservation failure: {errors}")
    return {
        "schema": "titan.w08.capacity-ledger.v1",
        "capacity": cap,
        "events": len(ordered),
        "receipts": receipts,
        "timeline": timeline,
        "final": _snapshot(shed, carried),
        "summary": {
            "harvested": dict(sorted(harvested.items())),
            "bought": dict(sorted(bought.items())),
            "sold": dict(sorted(sold.items())),
            "consumed": dict(sorted(consumed.items())),
            "discarded": dict(sorted(discarded.items())),
            "discarded_total": sum(discarded.values()),
        },
        "conservation_errors": errors,
    }


def _copy_event_sequence(value: Any, name: str) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of mappings")
    out: list[dict[str, Any]] = []
    for offset, event in enumerate(value):
        if not isinstance(event, Mapping):
            raise ValueError(f"{name}[{offset}] must be a mapping")
        out.append(copy.deepcopy(dict(event)))
    return out


def _required_event_ids(value: Any) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("required_complete must be a sequence of additive event IDs")
    out: list[str] = []
    seen: set[str] = set()
    for offset, event_id in enumerate(value):
        if not isinstance(event_id, str) or not event_id:
            raise ValueError(f"required_complete[{offset}] must be a non-empty string")
        if event_id in seen:
            raise ValueError(f"duplicate required_complete event id: {event_id}")
        seen.add(event_id)
        out.append(event_id)
    return out


def admit_additive_events(
    *,
    capacity: int,
    initial_shed: Mapping[str, Any] | None,
    initial_carried: Mapping[int, Mapping[str, Any]] | None,
    baseline_events: Sequence[Mapping[str, Any]],
    additive_events: Sequence[Mapping[str, Any]],
    required_complete: Sequence[str],
) -> dict[str, Any]:
    """Prove an additive job preserves every baseline physical completion.

    Baseline event IDs are compared one-for-one.  An additive tape is admitted
    only when every baseline event realizes and discards exactly the same units,
    every required additive event completes without discard, and total discard
    does not increase for any item.
    """
    base_events = _copy_event_sequence(baseline_events, "baseline_events")
    new_events = _copy_event_sequence(additive_events, "additive_events")
    required_ids = _required_event_ids(required_complete)
    baseline = simulate_capacity(capacity=capacity, initial_shed=initial_shed,
                                 initial_carried=initial_carried,
                                 events=base_events)
    candidate = simulate_capacity(capacity=capacity, initial_shed=initial_shed,
                                  initial_carried=initial_carried,
                                  events=[*base_events, *new_events])
    base_by_id = {r["id"]: r for r in baseline["receipts"]}
    cand_by_id = {r["id"]: r for r in candidate["receipts"]}
    additive_ids = set(cand_by_id).difference(base_by_id)
    invalid_required = [event_id for event_id in required_ids
                        if event_id not in additive_ids]
    if invalid_required:
        raise ValueError(
            "required_complete IDs must identify additive events: "
            + ", ".join(invalid_required)
        )
    regressions = []
    for event_id, old in base_by_id.items():
        new = cand_by_id[event_id]
        for field in ("realized", "discarded"):
            if new[field] != old[field]:
                regressions.append({"id": event_id, "field": field,
                                    "baseline": old[field], "candidate": new[field]})
    incomplete = []
    for event_id in required_ids:
        receipt = cand_by_id.get(event_id)
        if receipt is None:
            incomplete.append({"id": event_id, "reason": "missing"})
        elif receipt["realized"] != receipt["requested"] or receipt["discarded"]:
            incomplete.append({"id": event_id, "reason": receipt["reason"],
                               "requested": receipt["requested"],
                               "realized": receipt["realized"],
                               "discarded": receipt["discarded"]})
    base_discard = Counter(baseline["summary"]["discarded"])
    cand_discard = Counter(candidate["summary"]["discarded"])
    increased_discard = {
        item: cand_discard[item] - base_discard[item]
        for item in sorted(set(base_discard) | set(cand_discard))
        if cand_discard[item] > base_discard[item]
    }
    admitted = not regressions and not incomplete and not increased_discard
    reason = ("admitted" if admitted else
              "baseline-regression" if regressions else
              "required-event-incomplete" if incomplete else
              "increased-discard")
    return {
        "schema": "titan.w08.additive-admission.v1",
        "admitted": admitted,
        "reason": reason,
        "baseline_regressions": regressions,
        "required_incomplete": incomplete,
        "increased_discard": increased_discard,
        "baseline": baseline,
        "candidate": candidate,
    }
