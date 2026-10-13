# SPDX-License-Identifier: Apache-2.0
"""Exact mirror SELL queue-index value evidence for canonical ROWSHED.

Research only.  The incumbent ROWSHED donor ranks executable SELL rows with an
endpoint price-drop heuristic.  Against a mirror/copy opponent that sells the
same product and quantity, the official per-unit lockstep interpreter gives a
sharper quantity than the endpoint proxy.

The serial early-vs-late span remains useful diagnostic evidence, but it is not
itself the value of moving a row away from a same-index mirror baseline.  At the
baseline index both actors quote each unit from the same pre-commit inventory,
then both commits are applied.  Certified queue assignment therefore uses two
asymmetric values per row:

* promote_gain = early_cash - aligned_lockstep_cash
* demote_loss  = aligned_lockstep_cash - late_cash

This module computes those values and, for a unique-product executable SELL
block, the exact permutation that maximizes the conditional mirror edge.  It
does not choose, mutate, or authorize an action.  Callers must provide the
authenticated official ``market_price`` function (the focused tests use the
source-bound V4 market baseline).
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
SCHEMA = "titan.v4.rowshed.mirror-collision-value.v2"
ASSIGNMENT_SCHEMA = "titan.v4.rowshed.mirror-assignment.v2"
# Official _process_market aborts a unit loop before iteration 100_000.
MAX_EXECUTABLE_UNITS_PER_MARKET_ORDER = 99_999
# maxMarketOrdersPerTurn defaults to 10 but custom configs may be larger.  The
# exact DP deliberately certifies only <=10 rows as a conservative research
# safety bound; larger executable prefixes remain score-only / uncertified.
MAX_ASSIGNMENT_ROWS = 10


class MirrorCollisionInputError(ValueError):
    """Evidence is malformed or cannot support a mirror-collision score."""


def _plain_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise MirrorCollisionInputError(f"{label} must be a plain nonnegative int")
    return value


def _plain_positive_int(value: Any, label: str) -> int:
    value = _plain_nonnegative_int(value, label)
    if value == 0:
        raise MirrorCollisionInputError(f"{label} must be positive")
    return value


def _item(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise MirrorCollisionInputError("item must be a nonempty string")
    return value


def _quote(price_fn: Callable[[str, int], Any], item: str, inventory: int) -> int:
    try:
        price = price_fn(item, inventory)
    except (KeyError, ValueError, TypeError, OverflowError) as error:
        raise MirrorCollisionInputError("price function rejected evidence") from error
    if type(price) is not int or price < 1:
        raise MirrorCollisionInputError("price must be a plain positive int")
    return price


def _sell_lot(
    price_fn: Callable[[str, int], Any], item: str, inventory: int, quantity: int
) -> tuple[int, int]:
    """Return (cash, ending inventory) for one serial SELL lot.

    Official ``_commit_unit`` does not add market supply for a $1 sale.  Keeping
    that detail here matters in deep-glut tails and avoids pretending every sale
    advances inventory by one.
    """
    cash = 0
    level = inventory
    for _ in range(quantity):
        price = _quote(price_fn, item, level)
        cash += price
        if price != 1:
            level += 1
    return cash, level


def _aligned_lockstep_lot(
    price_fn: Callable[[str, int], Any], item: str, inventory: int, quantity: int
) -> tuple[int, int]:
    """Return one actor's cash at the official same-index mirror baseline.

    ``_process_market`` quotes both actors' current units from the same public
    inventory before committing either.  For identical item+quantity rows, both
    receive the same quote each iteration.  A non-floor quote therefore advances
    public supply twice after the shared quote; a $1 quote advances it zero times
    because the official SELL commit suppresses supply growth at the price floor.
    """
    cash = 0
    level = inventory
    for _ in range(quantity):
        price = _quote(price_fn, item, level)
        cash += price
        if price != 1:
            level += 2
    return cash, level


def mirror_collision_score(
    *,
    item: str,
    public_inventory: int,
    fillable: int,
    price_fn: Callable[[str, int], Any],
) -> dict[str, Any]:
    """Compare early, aligned-lockstep, and late mirror SELL cash.

    This is conditional mirror-race evidence, not a rival-action prediction.  It
    assumes the rival sells the same item and executable quantity once at the
    input baseline row.  ``exact_mirror_collision_value`` is retained as the
    serial early-minus-late diagnostic span; queue assignment authority uses the
    asymmetric promote/demote values around ``aligned_lockstep_cash`` instead.
    """
    name = _item(item)
    level = _plain_nonnegative_int(public_inventory, "public_inventory")
    qty = _plain_positive_int(fillable, "fillable")
    if qty > MAX_EXECUTABLE_UNITS_PER_MARKET_ORDER:
        raise MirrorCollisionInputError("fillable exceeds official per-order unit-loop horizon")
    if not callable(price_fn):
        raise MirrorCollisionInputError("price_fn must be callable")

    early_cash, after_ours = _sell_lot(price_fn, name, level, qty)
    _rival_cash, after_rival = _sell_lot(price_fn, name, level, qty)
    late_cash, _after_both_serial = _sell_lot(price_fn, name, after_rival, qty)
    aligned_cash, after_aligned = _aligned_lockstep_lot(price_fn, name, level, qty)

    before = _quote(price_fn, name, level)
    endpoint_after = _quote(price_fn, name, level + qty)
    incumbent_endpoint_score = (before - endpoint_after) * qty
    exact_collision_value = early_cash - late_cash
    promote_gain = early_cash - aligned_cash
    demote_loss = aligned_cash - late_cash
    if min(exact_collision_value, promote_gain, demote_loss) < 0:
        raise MirrorCollisionInputError("monotone mirror collision value became negative")
    if promote_gain + demote_loss != exact_collision_value:
        raise MirrorCollisionInputError("mirror cash decomposition drift")

    return {
        "item": name,
        "public_inventory": level,
        "fillable": qty,
        "early_cash": early_cash,
        "aligned_lockstep_cash": aligned_cash,
        "late_cash": late_cash,
        "promote_gain": promote_gain,
        "demote_loss": demote_loss,
        "exact_mirror_collision_value": exact_collision_value,
        "serial_span_diagnostic_only": True,
        "incumbent_endpoint_score": incumbent_endpoint_score,
        "after_our_lot_inventory": after_ours,
        "after_aligned_pair_inventory": after_aligned,
    }


def _assignment_costs(costs: Sequence[Any], label: str = "assignment cost") -> list[int]:
    if not isinstance(costs, Sequence) or isinstance(costs, (str, bytes)):
        raise MirrorCollisionInputError(f"{label}s must be a sequence")
    if len(costs) > MAX_ASSIGNMENT_ROWS:
        raise MirrorCollisionInputError("assignment row count exceeds research safety bound")
    return [
        _plain_nonnegative_int(value, f"{label} {index}")
        for index, value in enumerate(costs)
    ]


def _assignment_sides(
    promote_gains: Sequence[Any], demote_losses: Sequence[Any] | None = None
) -> tuple[list[int], list[int]]:
    """Normalize asymmetric assignment weights.

    ``demote_losses=None`` preserves the legacy symmetric helper API for callers
    that intentionally evaluate an abstract +/- cost vector.  Canonical ROWSHED
    assignment reports always pass explicit lockstep-derived demote losses.
    """
    promote = _assignment_costs(promote_gains, "promote gain")
    if demote_losses is None:
        return promote, list(promote)
    demote = _assignment_costs(demote_losses, "demote loss")
    if len(demote) != len(promote):
        raise MirrorCollisionInputError("promote/demote assignment lengths differ")
    return promote, demote


def mirror_edge_for_permutation(
    promote_gains: Sequence[Any],
    permutation: Sequence[Any],
    demote_losses: Sequence[Any] | None = None,
) -> int:
    """Return the conditional mirror edge of one row permutation.

    For row i, moving earlier than the rival mirror baseline earns its
    lockstep-derived ``promote_gain``; moving later pays its ``demote_loss``;
    staying at the same raw index contributes zero.  When ``demote_losses`` is
    omitted, the legacy symmetric +/-cost helper behavior is preserved.
    """
    promote, demote = _assignment_sides(promote_gains, demote_losses)
    if not isinstance(permutation, Sequence) or isinstance(permutation, (str, bytes)):
        raise MirrorCollisionInputError("permutation must be a sequence")
    order = []
    for index, value in enumerate(permutation):
        if type(value) is not int:
            raise MirrorCollisionInputError(f"permutation index {index} must be a plain int")
        order.append(value)
    if sorted(order) != list(range(len(promote))):
        raise MirrorCollisionInputError("permutation must contain each row index exactly once")
    candidate_position = [0] * len(promote)
    for position, original_index in enumerate(order):
        candidate_position[original_index] = position
    total = 0
    for original_index in range(len(promote)):
        position = candidate_position[original_index]
        if position < original_index:
            total += promote[original_index]
        elif position > original_index:
            total -= demote[original_index]
    return total


def optimal_mirror_assignment(
    promote_gains: Sequence[Any], demote_losses: Sequence[Any] | None = None
) -> tuple[list[int], int]:
    """Exact O(n*2^n) assignment for the <=10-row unique-product theorem.

    Ties prefer fewer moved rows, then lexicographically smaller original-index
    permutations, so identity is retained when no positive edge exists.  Passing
    only one vector preserves the legacy symmetric helper API; canonical reports
    pass explicit asymmetric lockstep-derived promote and demote vectors.
    """
    promote, demote = _assignment_sides(promote_gains, demote_losses)
    n = len(promote)
    if n < 2:
        return list(range(n)), 0

    # mask -> (score, moved_count, original-index permutation prefix)
    states: dict[int, tuple[int, int, tuple[int, ...]]] = {0: (0, 0, ())}
    for mask in range(1 << n):
        state = states.get(mask)
        if state is None:
            continue
        score, moved, prefix = state
        position = len(prefix)
        for original_index in range(n):
            bit = 1 << original_index
            if mask & bit:
                continue
            delta = 0
            if position < original_index:
                delta = promote[original_index]
            elif position > original_index:
                delta = -demote[original_index]
            candidate = (
                score + delta,
                moved + (position != original_index),
                prefix + (original_index,),
            )
            next_mask = mask | bit
            incumbent = states.get(next_mask)
            if incumbent is None or (
                candidate[0], -candidate[1], tuple(-x for x in candidate[2])
            ) > (
                incumbent[0], -incumbent[1], tuple(-x for x in incumbent[2])
            ):
                states[next_mask] = candidate

    score, _moved, permutation = states[(1 << n) - 1]
    if score <= 0:
        return list(range(n)), 0
    return list(permutation), score


def _assignment_report(scored: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = [row["item"] for row in scored]
    report: dict[str, Any] = {
        "schema": ASSIGNMENT_SCHEMA,
        "certified": False,
        "conditional_assumption": (
            "rival submits the same unique-product SELL rows at the input baseline indices"
        ),
        "objective": (
            "+promote_gain when earlier, -demote_loss when later, 0 when same; "
            "baseline is official per-unit lockstep"
        ),
        "optimal_permutation_indices": None,
        "predicted_mirror_edge": None,
    }
    if len(scored) > MAX_ASSIGNMENT_ROWS:
        report["reason"] = "row_count_exceeds_assignment_safety_bound"
        return report
    if len(set(items)) != len(items):
        report["reason"] = "duplicate_product_rows_outside_assignment_theorem"
        return report

    serial_spans = [row["exact_mirror_collision_value"] for row in scored]
    promote = [row["promote_gain"] for row in scored]
    demote = [row["demote_loss"] for row in scored]
    permutation, edge = optimal_mirror_assignment(promote, demote)
    report.update(
        certified=True,
        reason="unique_product_exact_lockstep_assignment",
        # Compatibility diagnostic retained from v1; no longer assignment authority.
        costs=serial_spans,
        costs_semantics="serial early-minus-late diagnostic spans; not assignment weights",
        promote_gains=promote,
        demote_losses=demote,
        assignment_weight_semantics="official same-index lockstep baseline",
        optimal_permutation_indices=permutation,
        predicted_mirror_edge=edge,
    )
    return report


def analyze_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    price_fn: Callable[[str, int], Any],
) -> dict[str, Any]:
    """Score caller-authenticated executable SELL evidence under both metrics.

    Each row must contain exactly ``item``, ``public_inventory`` and ``fillable``.
    Stable score ties preserve caller order.  ``mirror_rank_indices`` remains a
    descending serial-span view for compatibility; it is explicitly NOT a queue
    optimum.  Unique-product blocks additionally receive an exact lockstep-
    baseline assignment certificate.  The report is evidence only and never
    returns an action.
    """
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise MirrorCollisionInputError("rows must be a sequence")
    if len(rows) < 2:
        raise MirrorCollisionInputError("at least two rows are required")

    scored: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise MirrorCollisionInputError("row must be a mapping")
        if set(row) != {"item", "public_inventory", "fillable"}:
            raise MirrorCollisionInputError("row key set drift")
        score = mirror_collision_score(
            item=row.get("item"),
            public_inventory=row.get("public_inventory"),
            fillable=row.get("fillable"),
            price_fn=price_fn,
        )
        score["original_index"] = index
        scored.append(score)

    incumbent_rank = [
        row["original_index"]
        for row in sorted(
            scored,
            key=lambda row: (-row["incumbent_endpoint_score"], row["original_index"]),
        )
    ]
    mirror_rank = [
        row["original_index"]
        for row in sorted(
            scored,
            key=lambda row: (-row["exact_mirror_collision_value"], row["original_index"]),
        )
    ]
    assignment = _assignment_report(scored)
    if assignment["certified"]:
        promote = assignment["promote_gains"]
        demote = assignment["demote_losses"]
        assignment["descending_score_permutation_indices"] = mirror_rank
        assignment["descending_score_predicted_edge"] = mirror_edge_for_permutation(
            promote, mirror_rank, demote
        )
        assignment["descending_score_is_optimal"] = (
            mirror_rank == assignment["optimal_permutation_indices"]
        )

    return {
        "schema": SCHEMA,
        "engine_git_blob": ENGINE_GIT_BLOB,
        "research_only": True,
        "decision_authority": False,
        "action_mutation_authority": False,
        "rival_action_prediction": False,
        "conditional_assumption": "rival sells identical item+quantity in competing queue slot",
        "scores": scored,
        "incumbent_rank_indices": incumbent_rank,
        "mirror_rank_indices": mirror_rank,
        "mirror_rank_semantics": (
            "descending serial early-minus-late evidence only; not queue-optimal assignment"
        ),
        "rank_diverges": incumbent_rank != mirror_rank,
        "mirror_assignment": assignment,
    }
