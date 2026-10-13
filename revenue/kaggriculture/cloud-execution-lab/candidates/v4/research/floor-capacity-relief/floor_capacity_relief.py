"""ASTRA-FLOORDRAIN: source-bound shed-overflow floor-liquidation research.

Research-only. This module models one narrow official-engine seam:

* EOD inventory-to-shed transfer is capacity bounded and excess actor cargo is
  discarded in deterministic inventory/item order.
* A successful SELL quoted at the $1 price floor removes one shed unit and pays
  $1 but does not increase market inventory.

The planner below is deliberately fail-closed: it proposes only floor-price
SELLs, never product-policy sales above the floor, and only when each marginal
slot preserves incoming cargo whose declared retention value plus realized sale
cash strictly exceeds the declared shadow value of the drained shed unit.

It does not mutate the runtime, canonical key set, controller, evaluator,
archive, or production policy. CARRYBANK retains actor-inventory hoisting;
HARVESTCLOCK/SELLWINDOW retain sale-window semantics and wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha1
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import argparse
import json

ENGINE_BLOB_SHA = "3c202c7ee921da239356789e266b694635103fc4"
PRICE_FLOOR = 1
CLAIM = "ASTRA-FLOORDRAIN"


@dataclass(frozen=True)
class DropProjection:
    shed_before: dict[str, int]
    shed_after: dict[str, int]
    retained_from_inventories: dict[str, int]
    discarded_from_inventories: dict[str, int]
    retained_sequence: tuple[str, ...]
    discarded_sequence: tuple[str, ...]
    capacity: int

    @property
    def discarded_units(self) -> int:
        return len(self.discarded_sequence)


@dataclass(frozen=True)
class DrainPlan:
    orders: tuple[tuple[str, str, int], ...]
    drained_units: dict[str, int]
    preserved_sequence: tuple[str, ...]
    baseline_discarded_sequence: tuple[str, ...]
    projected_discarded_sequence: tuple[str, ...]
    floor_cash: int
    market_inventory_delta: int
    declared_value_gain: float
    reason: str
    engine_blob_sha: str = ENGINE_BLOB_SHA
    claim: str = CLAIM


def _clean_counts(values: Mapping[str, int], *, label: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item, raw in values.items():
        n = int(raw)
        if n < 0:
            raise ValueError(f"{label}[{item!r}] must be >= 0")
        if n:
            out[str(item)] = n
    return out


def project_eod_drop(
    shed: Mapping[str, int],
    inventories: Sequence[Mapping[str, int]],
    capacity: int,
) -> DropProjection:
    """Pure projection of the official EOD shed drop/discard ordering.

    Python mapping iteration order is intentionally preserved: the engine walks
    actor inventories in list order and each inventory's item insertion order.
    Excess units are discarded once the shed is full.
    """
    capacity = int(capacity)
    if capacity < 0:
        raise ValueError("capacity must be >= 0")

    shed0 = _clean_counts(shed, label="shed")
    if sum(shed0.values()) > capacity:
        raise ValueError("shed already exceeds capacity")

    after = dict(shed0)
    retained: dict[str, int] = {}
    discarded: dict[str, int] = {}
    retained_seq: list[str] = []
    discarded_seq: list[str] = []

    for idx, inv_raw in enumerate(inventories):
        inv = _clean_counts(inv_raw, label=f"inventories[{idx}]")
        for item, n in inv.items():
            room = max(0, capacity - sum(after.values()))
            take = min(n, room)
            if take:
                after[item] = after.get(item, 0) + take
                retained[item] = retained.get(item, 0) + take
                retained_seq.extend([item] * take)
            lost = n - take
            if lost:
                discarded[item] = discarded.get(item, 0) + lost
                discarded_seq.extend([item] * lost)

    return DropProjection(
        shed_before=shed0,
        shed_after=after,
        retained_from_inventories=retained,
        discarded_from_inventories=discarded,
        retained_sequence=tuple(retained_seq),
        discarded_sequence=tuple(discarded_seq),
        capacity=capacity,
    )


def _expanded_floor_candidates(
    shed: Mapping[str, int],
    floor_quotes: Mapping[str, int | float],
    shadow_values: Mapping[str, int | float],
    protected_min: Mapping[str, int],
    available_market_rows: int,
) -> list[tuple[float, str]]:
    if available_market_rows < 0:
        raise ValueError("available_market_rows must be >= 0")
    protected = _clean_counts(protected_min, label="protected_min")
    candidates: list[tuple[float, str]] = []
    eligible_items: list[tuple[float, str, int]] = []

    for item, n in _clean_counts(shed, label="shed").items():
        quote = float(floor_quotes.get(item, float("inf")))
        if quote != PRICE_FLOOR:
            continue
        keep = protected.get(item, 0)
        sellable = max(0, n - keep)
        if sellable <= 0:
            continue
        shadow = float(shadow_values.get(item, float("inf")))
        eligible_items.append((shadow, item, sellable))

    # One SELL row can drain many units of one item. Respect the remaining row
    # budget by admitting only that many distinct items, lowest shadow first.
    for shadow, item, sellable in sorted(eligible_items)[:available_market_rows]:
        candidates.extend((shadow, item) for _ in range(sellable))
    return sorted(candidates)


def plan_floor_capacity_relief(
    *,
    shed: Mapping[str, int],
    inventories: Sequence[Mapping[str, int]],
    capacity: int,
    floor_quotes: Mapping[str, int | float],
    shed_shadow_values: Mapping[str, int | float],
    incoming_retention_values: Mapping[str, int | float],
    protected_min: Mapping[str, int] | None = None,
    available_market_rows: int = 10,
) -> DrainPlan:
    """Return a fail-closed floor-only capacity relief plan.

    A marginal drain of shed item S to preserve incoming item I is admitted iff
        retention_value(I) + $1 floor cash - shadow_value(S) > 0.

    Unknown values default to +inf for shed cargo (never drain) and 0 for
    incoming cargo (never justify a positive-cost drain).
    """
    protected_min = protected_min or {}
    baseline = project_eod_drop(shed, inventories, capacity)
    if baseline.discarded_units == 0:
        return DrainPlan(
            orders=(), drained_units={}, preserved_sequence=(),
            baseline_discarded_sequence=(), projected_discarded_sequence=(),
            floor_cash=0, market_inventory_delta=0, declared_value_gain=0.0,
            reason="no_projected_overflow",
        )

    candidates = _expanded_floor_candidates(
        shed, floor_quotes, shed_shadow_values, protected_min,
        int(available_market_rows),
    )
    if not candidates:
        return DrainPlan(
            orders=(), drained_units={}, preserved_sequence=(),
            baseline_discarded_sequence=baseline.discarded_sequence,
            projected_discarded_sequence=baseline.discarded_sequence,
            floor_cash=0, market_inventory_delta=0, declared_value_gain=0.0,
            reason="no_unprotected_floor_cargo",
        )

    # Freed slots preserve a *prefix* of the baseline discarded sequence. It is
    # impossible to preserve the second discarded unit without also making room
    # for the first. Evaluate every feasible prefix and choose the strictly best
    # positive cumulative declared-value gain.
    cumulative = 0.0
    best_gain = 0.0
    best_k = 0
    paired = list(zip(baseline.discarded_sequence, candidates))
    for k, (incoming_item, (shadow, _shed_item)) in enumerate(paired, start=1):
        incoming_value = float(incoming_retention_values.get(incoming_item, 0.0))
        cumulative += incoming_value + PRICE_FLOOR - shadow
        if cumulative > best_gain:
            best_gain = cumulative
            best_k = k

    drained: dict[str, int] = {}
    for _incoming_item, (_shadow, shed_item) in paired[:best_k]:
        drained[shed_item] = drained.get(shed_item, 0) + 1
    preserved = list(baseline.discarded_sequence[:best_k])
    gain = best_gain

    if not drained:
        return DrainPlan(
            orders=(), drained_units={}, preserved_sequence=(),
            baseline_discarded_sequence=baseline.discarded_sequence,
            projected_discarded_sequence=baseline.discarded_sequence,
            floor_cash=0, market_inventory_delta=0, declared_value_gain=0.0,
            reason="nonpositive_declared_value",
        )

    relieved_shed = dict(_clean_counts(shed, label="shed"))
    for item, n in drained.items():
        relieved_shed[item] -= n
        if relieved_shed[item] == 0:
            del relieved_shed[item]
    projected = project_eod_drop(relieved_shed, inventories, capacity)

    orders = tuple(("SELL", item, n) for item, n in sorted(drained.items()))
    # Official engine invariant for successful $1 SELL: the market inventory is
    # not incremented. This lane only admits quote == PRICE_FLOOR.
    market_delta = 0
    return DrainPlan(
        orders=orders,
        drained_units=drained,
        preserved_sequence=tuple(preserved),
        baseline_discarded_sequence=baseline.discarded_sequence,
        projected_discarded_sequence=projected.discarded_sequence,
        floor_cash=sum(drained.values()) * PRICE_FLOOR,
        market_inventory_delta=market_delta,
        declared_value_gain=gain,
        reason="positive_floor_capacity_relief",
    )


def git_blob_sha(data: bytes) -> str:
    return sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def verify_engine_blob(path: str | Path) -> bool:
    return git_blob_sha(Path(path).read_bytes()) == ENGINE_BLOB_SHA


def scenario_pack() -> dict:
    base = dict(
        shed={"MILK": 100},
        inventories=[{"MELON": 2}],
        capacity=100,
        floor_quotes={"MILK": 1},
        shed_shadow_values={"MILK": 4},
        incoming_retention_values={"MELON": 250},
        protected_min={"MILK": 98},
        available_market_rows=1,
    )
    positive = plan_floor_capacity_relief(**base)
    no_overflow = plan_floor_capacity_relief(**{**base, "shed": {"MILK": 98}})
    above_floor = plan_floor_capacity_relief(**{**base, "floor_quotes": {"MILK": 2}})
    low_value = plan_floor_capacity_relief(**{
        **base,
        "shed_shadow_values": {"MILK": 4},
        "incoming_retention_values": {"MELON": 2},
    })
    return {
        "claim": CLAIM,
        "engine_blob_sha": ENGINE_BLOB_SHA,
        "status": "research_only_default_off",
        "engine_invariants_used": [
            "EOD actor inventory drops into shed in deterministic order up to shedCapacity; excess is discarded",
            "successful SELL at quote $1 pays $1 and does not increment market inventory",
            "SELL consumes shed cargo before EOD inventory drop",
        ],
        "positive_witness": asdict(positive),
        "negative_controls": {
            "no_overflow": asdict(no_overflow),
            "above_floor": asdict(above_floor),
            "nonpositive_declared_value": asdict(low_value),
        },
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", help="optional official kaggriculture.py path to authenticate")
    args = parser.parse_args(list(argv) if argv is not None else None)
    pack = scenario_pack()
    if args.engine:
        pack["engine_blob_verified"] = verify_engine_blob(args.engine)
        if not pack["engine_blob_verified"]:
            print(json.dumps(pack, indent=2, sort_keys=True))
            return 2
    print(json.dumps(pack, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
