# SPDX-License-Identifier: MIT
"""Conservative joint inventory/cash constraints for caller-priced rival paths.

No opponent-private observations, parent controller, pricing model, scenario
probabilities, or game dependencies. Facts and complete event paths come from
the caller. Missing continuation, inconsistent facts, or exhausted budgets retain
candidates. All quantities describe actual fills, not requested order amounts.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Iterable, Mapping
from time import monotonic

from linear_bounds import Constraint, Limits, Result, rational, solve


@dataclass(frozen=True)
class Interval:
    lower: int | str | Fraction = 0
    upper: int | str | Fraction | None = None

    def __post_init__(self):
        low = rational(self.lower)
        high = None if self.upper is None else rational(self.upper)
        if high is not None and high < low:
            raise ValueError("Reversed interval")
        object.__setattr__(self, "lower", low)
        object.__setattr__(self, "upper", high)


def _add(target, source, scale=1):
    result = dict(target)
    for key, value in source.items():
        result[key] = result.get(key, Fraction(0)) + scale * value
    return {k: v for k, v in result.items() if v}


class RivalLedger:
    """Linear relaxation of a supplied ordered stock and cash history.

    Each modeled product has separate shed and carry. Total modeled shed has a
    single capacity limit. Unmodeled products can only reduce true free capacity,
    so omitting them is a relaxation, not a false infeasibility result. Carry has
    no shed-capacity restriction. An interval deposit is ONE variable subtracted
    from carry and added to shed, preserving cross-product/time correlations.
    """
    def __init__(self, products: Iterable[str], capacity: int, *, as_of_step: int,
                 shed: Mapping[str, Interval] | None = None,
                 carry: Mapping[str, Interval] | None = None,
                 cash: Interval = Interval()):
        self.products = tuple(dict.fromkeys(products))
        if not self.products or capacity < 0:
            raise ValueError("Supply products and nonnegative capacity")
        self.capacity = rational(capacity)
        self.as_of_step = int(as_of_step)
        self.constraints: list[Constraint] = []
        self._serial = 0
        self._step = -1
        self.shed = {p: self._quantity((shed or {}).get(p, Interval(0, capacity)), f"shed:{p}")
                     for p in self.products}
        self.carry = {p: self._quantity((carry or {}).get(p, Interval()), f"carry:{p}")
                      for p in self.products}
        self.cash = self._quantity(cash, "cash")
        self._checkpoint("initial")

    def _constraint(self, a, bound, label):
        self._serial += 1
        self.constraints.append(Constraint.make(a, bound, f"{self._serial}:{label}"))

    def _quantity(self, value, label):
        if not isinstance(value, Interval):
            value = Interval(value, value)
        name = f"v{self._serial}:{label}"
        if value.lower < 0:
            raise ValueError("Inventory, receipts and expense amounts must be nonnegative")
        self._constraint({name: -1}, -value.lower, f"{label}:lower")
        if value.upper is not None:
            self._constraint({name: 1}, value.upper, f"{label}:upper")
        return {name: Fraction(1)}

    def _checkpoint(self, label):
        total = {}
        for product in self.products:
            self._constraint({k: -v for k, v in self.shed[product].items()}, 0, f"{label}:shed:{product}")
            self._constraint({k: -v for k, v in self.carry[product].items()}, 0, f"{label}:carry:{product}")
            total = _add(total, self.shed[product])
        self._constraint(total, self.capacity, f"{label}:shared_shed")
        self._constraint({k: -v for k, v in self.cash.items()}, 0, f"{label}:cash")

    def event(self, kind: str, *, step: int, product: str | None = None,
              quantity: int | Fraction | Interval = 0,
              cash: int | Fraction | Interval | None = None):
        """Append in exact execution order; equal-step events are NOT netted.

        sale/buy: quantity is the realized fill and cash the exact ordered
        receipt/cost, or a conservative interval.  None means [0, infinity).
        deposit/pickup: accepted transfer; harvest/consume/discard affect carry.
        cash_checkpoint: the actual historical public cash at or before as_of_step.
        income/expense: unallocated nonmarket cash effects, including costs that
        prevent net public cash from being misread as gross receipts.
        """
        kinds = {"sale", "buy", "deposit", "pickup", "harvest", "consume", "income", "expense", "discard", "cash_checkpoint"}
        if kind not in kinds or step < self._step:
            raise ValueError("Use known events in chronological execution order")
        if kind == "cash_checkpoint":
            if isinstance(cash, Interval) or cash is None:
                raise ValueError("Public cash checkpoint must be exact")
            return self.observe_cash(cash, step=step)
        if kind not in {"income", "expense"} and product not in self.shed:
            raise ValueError("Event product is not modeled")
        self._step = step
        label = f"{step}:{kind}:{product or 'cash'}"
        if kind in {"income", "expense"}:
            delta = self._quantity(Interval() if cash is None else cash, label)
            self.cash = _add(self.cash, delta, 1 if kind == "income" else -1)
        else:
            delta = self._quantity(quantity, label)
            if kind in {"sale", "pickup"}:
                self.shed[product] = _add(self.shed[product], delta, -1)
            if kind in {"buy", "deposit"}:
                self.shed[product] = _add(self.shed[product], delta)
            if kind in {"harvest", "pickup"}:
                self.carry[product] = _add(self.carry[product], delta)
            if kind in {"consume", "deposit", "discard"}:
                self.carry[product] = _add(self.carry[product], delta, -1)
            if kind in {"sale", "buy"}:
                money = self._quantity(Interval() if cash is None else cash, f"{label}:money")
                self.cash = _add(self.cash, money, 1 if kind == "sale" else -1)
        self._checkpoint(label)
        return self

    def observe_cash(self, value: int, *, step: int):
        """Bind ONLY an actually observed historical checkpoint, never future cash."""
        if step > self.as_of_step or step < self._step:
            raise ValueError("Cash checkpoint must be causal and after supplied events")
        self._step = step
        self._constraint(self.cash, value, f"observed:{step}:cash:upper")
        self._constraint({k: -v for k, v in self.cash.items()}, -rational(value),
                         f"observed:{step}:cash:lower")
        return self

    def fork(self):
        return deepcopy(self)

    def check(self, limits: Limits = Limits()):
        return solve(self.constraints, limits)


@dataclass(frozen=True)
class Decision:
    keep: bool
    result: Result

    def as_dict(self):
        return {"keep": self.keep, **self.result.as_dict()}


def _candidate(base, events, complete, limits, deadline):
    if not complete:
        return Decision(True, Result("unknown", "incomplete_continuation"))
    candidate = base.fork()
    try:
        for event in events:
            if monotonic() >= deadline:
                return Decision(True, Result("unknown", "budget"))
            candidate.event(**event)
        result = candidate.check(replace(limits, seconds=max(0, deadline - monotonic())))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return Decision(True, Result("unknown", "malformed_candidate"))
    return Decision(result.status != "infeasible", result)


def check_extension(base: RivalLedger, events, *, complete: bool = False,
                    limits: Limits = Limits()) -> Decision:
    """Reject only a complete extension of consistent caller-supplied evidence.

    `complete` means every potentially relevant stock/cash change is represented
    exactly or by a conservative interval. It is not a claim of perfect knowledge.
    Without that property a missing future deposit must not cause rejection.
    The time budget is shared by base checking and the candidate, not per stage.
    """
    deadline = monotonic() + limits.seconds
    evidence = base.check(limits)
    if evidence.status != "possible":
        return Decision(True, Result("unknown", "base_" + evidence.status))
    return _candidate(base, events, complete, limits, deadline)


def check_column(base: RivalLedger, plan_events, *, complete: bool = False,
                 limits: Limits = Limits()):
    """Remove a table column only if ALL supplied own-plan paths contradict facts.

    Receipts may depend on our plan. Keep a column with mixed applicability and
    flag it rather than silently substituting a rival response in one cell. A
    single time budget covers base checking and every supplied plan in this call.
    """
    deadline = monotonic() + limits.seconds
    evidence = base.check(limits)
    decisions = []
    for events in plan_events:
        if evidence.status != "possible":
            decision = Decision(True, Result("unknown", "base_" + evidence.status))
        else:
            decision = _candidate(base, events, complete, limits, deadline)
        decisions.append(decision)
    return {"keep": not decisions or any(d.keep for d in decisions),
            "conditional": bool(decisions) and any(not d.keep for d in decisions) and any(d.keep for d in decisions),
            "plans": [d.as_dict() for d in decisions]}


def t12_sale_events(product: str, stream, *, receipts=None):
    """Adapt an existing T12 (label, ((step, qty), ...), alignment) unchanged.

    The caller's receipt callback sees the entire stream/alignment and event index;
    it must use the exact ordered scorer for the relevant own plan. None leaves
    cash unconstrained. This does not invent missing production or transfer events.
    """
    label, timeline, alignment = stream
    if alignment not in {"before", "paired", "after"}:
        raise ValueError("Unknown relative order alignment")
    return [{"kind": "sale", "step": step, "product": product, "quantity": quantity,
             "cash": None if receipts is None else receipts(stream, index)}
            for index, (step, quantity) in enumerate(timeline)]
