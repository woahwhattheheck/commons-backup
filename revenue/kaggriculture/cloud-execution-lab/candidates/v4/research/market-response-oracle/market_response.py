# SPDX-License-Identifier: Apache-2.0
"""Coupled market-counterfactual oracle; research only, no runtime installation.

For a fixed own lot and two schedules, find the worst margin difference under
one shared rival stream: up to B rival units, distributed across all callbacks,
with a before/paired/after market-row choice at each callback. The three choices
are realizable with a fixed own row 1 and a rival row 0, 1, or 2. This is NOT an
unrestricted opponent, a prediction of private stock, or a full-game guarantee.

Price, paired-fill, floor-admission and town-consumption semantics are consumed
from the existing scheduler module, not reimplemented here. Official-engine
checks live in test_market_response.py. Dynamic programming keeps the lowest
accumulated regret for each (rival_used, candidate_inventory, reference_inventory)
state. Future payoffs depend only on that state and the fixed schedules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Callable, Iterable

Plan = tuple[tuple[int, int], ...]
Pulse = tuple[int, int, str]
ALIGNMENTS = ("before", "paired", "after")
MAX_HORIZON = 8
MAX_LOT = 100


@dataclass(frozen=True)
class Audit:
    complete: bool
    worst_delta: float | None
    rival_stream: tuple[Pulse, ...]
    transitions: int
    max_frontier: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _int(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def normalize_plan(rows: Iterable[Iterable[int]], *, quantity: int,
                   now: int, end: int) -> Plan:
    """Reject ambiguous duplicate dates instead of silently overwriting them."""
    seen: dict[int, int] = {}
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise ValueError("every plan row must be [step, quantity]")
        step = _int(row[0], "plan step", now, end)
        count = _int(row[1], "plan quantity", 0, quantity)
        if step in seen:
            raise ValueError("duplicate plan step")
        seen[step] = count
    if sum(seen.values()) > quantity:
        raise ValueError("plan sells more than the initial lot")
    return tuple(sorted((step, count) for step, count in seen.items() if count))


def audit_plan(model: Any, *, quantity: int, reference: Plan, candidate: Plan,
               rival_budget: int, absorb: Callable[[int], int],
               terminal: bool = False, max_transitions: int = 200_000) -> Audit:
    """Exact finite-family worst case, or an explicit INCOMPLETE result.

    A work-limited partial search never returns a safety certificate. Carry is
    valued exactly as MarketPath.score does; its interpretation remains a model
    continuation, not realized game cash. Only completed results have a minimum.
    """
    quantity = _int(quantity, "quantity", 0, MAX_LOT)
    rival_budget = _int(rival_budget, "rival_budget", 0, MAX_LOT)
    now = _int(model.now, "now", 0, 10**9)
    end = _int(model.end, "end", now, now + MAX_HORIZON)
    max_transitions = _int(max_transitions, "max_transitions", 0, 10**8)
    if type(terminal) is not bool:
        raise ValueError("terminal must be bool")
    reference = normalize_plan(reference, quantity=quantity, now=now, end=end)
    candidate = normalize_plan(candidate, quantity=quantity, now=now, end=end)
    if reference == candidate:
        return Audit(True, 0.0, (), 0, 1, "identical_plans")
    base, chosen = dict(reference), dict(candidate)
    consumption = {t: _int(absorb(t), "absorption", 0, 10**6)
                   for t in range(now, end + 1)}
    initial = _int(model.inventory, "inventory", -10**9, 10**9)
    # Values contain accumulated candidate-minus-reference margin, and a witness.
    layer = {(0, initial, initial): (0.0, ())}
    transitions, max_frontier = 0, 1
    for step in range(now, end + 1):
        next_layer: dict[tuple[int, int, int], tuple[float, tuple[Pulse, ...]]] = {}
        own_c, own_b = chosen.get(step, 0), base.get(step, 0)
        for (used, inv_c, inv_b), (delta, trace) in layer.items():
            for rival in range(rival_budget - used + 1):
                orientations = ALIGNMENTS if rival and (own_c or own_b) else ("paired",)
                for alignment in orientations:
                    if transitions >= max_transitions:
                        return Audit(False, None, (), transitions, max_frontier,
                                     "transition_budget_exhausted")
                    transitions += 1
                    c_cash, c_rival, c_inv = model.joint(inv_c, own_c, rival, alignment)
                    b_cash, b_rival, b_inv = model.joint(inv_b, own_b, rival, alignment)
                    updated = delta + (c_cash - c_rival) - (b_cash - b_rival)
                    if not isfinite(updated):
                        raise ValueError("non-finite market transition")
                    key = (used + rival, c_inv - consumption[step], b_inv - consumption[step])
                    old = next_layer.get(key)
                    # Strict comparison leaves deterministic first witness on ties.
                    if old is None or updated < old[0]:
                        witness = trace + ((step, rival, alignment),) if rival else trace
                        next_layer[key] = (updated, witness)
        layer = next_layer
        max_frontier = max(max_frontier, len(layer))
    rem_c = quantity - sum(chosen.values())
    rem_b = quantity - sum(base.values())
    worst: float | None = None
    witness: tuple[Pulse, ...] = ()
    for (_, inv_c, inv_b), (delta, trace) in layer.items():
        if not terminal:
            delta += model.single(inv_c, rem_c)[0] - model.single(inv_b, rem_b)[0]
        if not isfinite(delta):
            raise ValueError("non-finite continuation value")
        if worst is None or delta < worst:
            worst, witness = float(delta), trace
    return Audit(True, worst, witness, transitions, max_frontier, "complete")


def select_robust_lot(scheduler: Any, *, enabled: bool = False,
                      audit_transition_budget: int = 200_000,
                      **kwargs: Any) -> tuple[Any, dict[str, Any]]:
    """Research adapter over the existing optimizer, not a replacement planner.

    OFF delegates once, unchanged. ON composes an additional feasibility predicate
    with the caller's physical gate. It never reverts a forced-capacity rescue to
    a physically infeasible reference. A work-limited candidate is not admitted.
    A positive result covers only the declared finite market-response family.
    """
    if type(enabled) is not bool:
        raise ValueError("enabled must be bool")
    if not enabled:
        return scheduler.optimize_lot(**kwargs)
    left = _int(audit_transition_budget, "audit_transition_budget", 0, 10**8)
    quantity, now = kwargs["quantity"], kwargs["now"]
    end = kwargs["dates"][-1]
    reference = normalize_plan(kwargs["reference"], quantity=quantity, now=now, end=end)
    physical = kwargs.get("capacity_ok")
    physically_ok = bool(physical(kwargs["reference"])) if physical else True
    min_now = kwargs.get("minimum_now", 0)
    reference_feasible = physically_ok and dict(reference).get(now, 0) >= min_now
    if not reference_feasible:
        plan, info = scheduler.optimize_lot(**kwargs)
        info = dict(info)
        info["market_response_audit"] = {"status": "skipped_infeasible_reference",
                                         "certified": False}
        return plan, info
    model = scheduler.MarketPath(kwargs["item"], kwargs["inventory"],
                                 kwargs["params"], kwargs["shops"], kwargs["config"], now, end)
    absorb = lambda t: scheduler.absorption(kwargs["item"], t, kwargs["shops"], kwargs["config"])
    terminal = end == kwargs.get("last", 718)
    audits: dict[Plan, Audit] = {}

    def gate(plan: Plan) -> bool:
        nonlocal left
        if physical and not physical(plan):
            return False
        key = normalize_plan(plan, quantity=quantity, now=now, end=end)
        if key == reference:
            return True
        if key not in audits:
            result = audit_plan(model, quantity=quantity, reference=reference,
                                candidate=key, rival_budget=kwargs["rival_quantity"],
                                absorb=absorb, terminal=terminal, max_transitions=left)
            left -= result.transitions
            audits[key] = result
        result = audits[key]
        return bool(result.complete and result.worst_delta is not None
                    and result.worst_delta > 0)

    options = dict(kwargs)
    options["capacity_ok"] = gate
    plan, info = scheduler.optimize_lot(**options)
    info = dict(info)
    key = normalize_plan(plan, quantity=quantity, now=now, end=end)
    result = audits.get(key)
    info["market_response_audit"] = {
        "status": "reference_preserved" if key == reference else "finite_family_positive",
        "certified": key == reference or bool(result and result.complete and result.worst_delta > 0),
        "worst_delta": 0.0 if key == reference else result.worst_delta,
        "family": "same rival stream; <=budget units; per-callback before/paired/after",
        "audited_plans": len(audits),
        "incomplete_plans": sum(not a.complete for a in audits.values()),
        "transitions": audit_transition_budget - left,
    }
    return plan, info
