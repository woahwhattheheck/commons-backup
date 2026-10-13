"""Bounded public-evidence rival-response scenarios for TITAN E09.

This module is an additive experiment seam.  It does not infer a rival's hidden
inventory or implementation and it does not mutate the canonical seller.

A market intervention made on step ``t`` cannot cause the rival's already
simultaneous market row on step ``t`` to change.  The earliest causal response
represented here is therefore step ``t + 1``.  Quantities are explicit stress
inputs supplied by the caller; exposed production only gates whether a
temporary product-switch hypothesis is admissible and is never treated as
known carried or shed stock.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ResponseBranch:
    """One bounded public-evidence response hypothesis."""

    name: str
    product: str
    plan: tuple[tuple[int, int], ...]
    reacts_to_intervention: bool
    evidence: str


@dataclass(frozen=True)
class ResponseChoice:
    """Decision-level consequence of scoring common candidates by branch."""

    baseline_candidate: str
    chosen_candidate: str
    response_sensitive: bool
    changed: bool
    worst_value: float
    mean_value: float
    branch_winners: tuple[tuple[str, str], ...]
    reason: str


def _canonical_product(value: object) -> str:
    product = str(value).strip().upper()
    if not product:
        raise ValueError("product must be non-empty")
    return product


def _canonical_plan(
    plan: Sequence[object],
    *,
    cap: int,
) -> tuple[tuple[int, int], ...]:
    """Preserve a caller-supplied dated plan; do not shift its steps."""

    rows: list[tuple[int, int]] = []
    seen: set[int] = set()
    for raw in plan:
        if not isinstance(raw, (tuple, list)) or len(raw) != 2:
            raise ValueError("plan rows must be (step, quantity)")
        step = int(raw[0])
        quantity = int(raw[1])
        if step < 0:
            raise ValueError("plan steps must be non-negative")
        if quantity < 0 or quantity > cap:
            raise ValueError("stress quantity exceeds the bounded scenario cap")
        if step in seen:
            raise ValueError("plan steps must be unique")
        seen.add(step)
        rows.append((step, quantity))
    return tuple(rows)


def build_response_branches(
    *,
    current_step: int,
    horizon_end: int,
    intervention_product: str,
    stress_quantity: int,
    next_absorption_step: int | None = None,
    switch_products: Sequence[str] = (),
    exposed_products: Sequence[str] = (),
    max_stress_quantity: int = 100,
    fixed_rival_plan: Sequence[object] = (),
) -> tuple[ResponseBranch, ...]:
    """Build a bounded family of causal *future* rival-response hypotheses.

    ``stress_quantity`` is a caller-selected scenario quantity, not an estimate
    of private rival stock.  ``exposed_products`` can come from public crop or
    animal production evidence; it merely admits a switch branch.  It does not
    certify that the rival has a saleable unit.

    ``fixed_rival_plan`` is the no-response control: the caller-supplied dated
    rival plan, preserved verbatim, including any current-turn row.  An omitted
    or empty plan is the explicit zero-sale control; ``MarketPath.score`` maps
    ``()`` to zero rival units for the whole horizon, so callers that already
    have a concrete pre-intervention path must pass that path here.  Same-item
    branches can be passed directly to the current ``MarketPath.score`` rival
    plan input.  Cross-product switch branches require a multi-product/history
    adapter and must not be silently projected into the single-product scorer.
    """

    now = int(current_step)
    end = int(horizon_end)
    quantity = int(stress_quantity)
    cap = int(max_stress_quantity)
    if now < 0 or end < now:
        raise ValueError("invalid response horizon")
    if quantity < 0 or cap < 0 or quantity > cap:
        raise ValueError("stress quantity exceeds the bounded scenario cap")

    item = _canonical_product(intervention_product)
    control = _canonical_plan(fixed_rival_plan, cap=cap)
    branches = [
        ResponseBranch(
            "fixed_path",
            item,
            control,
            False,
            "control: caller-supplied rival plan is independent of this intervention",
        )
    ]
    if quantity == 0 or now >= end:
        return tuple(branches)

    first_reaction = now + 1
    branches.append(
        ResponseBranch(
            "next_turn_compete",
            item,
            ((first_reaction, quantity),),
            True,
            "earliest causal response; never the simultaneous current turn",
        )
    )

    if next_absorption_step is not None:
        absorption = int(next_absorption_step)
        # Waiting *through* an observed absorption means the response can be
        # scheduled only after that event.  If it lies outside this horizon the
        # branch is inapplicable rather than clipped backward.
        delayed = absorption + 1
        if absorption > now and delayed <= end:
            branches.append(
                ResponseBranch(
                    "post_absorption_delay",
                    item,
                    ((delayed, quantity),),
                    True,
                    "response waits until after the supplied public absorption event",
                )
            )

    exposed = {_canonical_product(p) for p in exposed_products}
    seen: set[str] = set()
    for raw in switch_products:
        product = _canonical_product(raw)
        if product == item or product in seen or product not in exposed:
            continue
        seen.add(product)
        branches.append(
            ResponseBranch(
                f"next_turn_switch_{product.lower()}",
                product,
                ((first_reaction, quantity),),
                True,
                "temporary switch admitted only by explicit public production support",
            )
        )
    return tuple(branches)


def same_item_rival_plan(branch: ResponseBranch, product: str) -> tuple[tuple[int, int], ...] | None:
    """Return a plan suitable for one-product ``MarketPath.score``, if valid."""

    wanted = _canonical_product(product)
    if _canonical_product(branch.product) != wanted:
        return None
    return tuple((int(step), int(quantity)) for step, quantity in branch.plan)


def choose_response_robust_candidate(
    values: Mapping[str, Mapping[str, float]],
    *,
    baseline_branch: str = "fixed_path",
) -> ResponseChoice:
    """Choose a candidate only from comparable, finite branch values.

    Values should be complete downstream economic outcomes (for example paired
    rollout utility or terminal cash), not forecast confidence.  Every candidate
    must cover exactly the same response branches.

    If every branch has the same winner as the fixed-path control, E09 is an
    explicit no-op.  Otherwise the robust candidate maximizes worst branch
    value, then mean branch value, then fixed-path value, with lexical candidate
    identity only as a deterministic final tie-break.
    """

    if not values:
        raise ValueError("at least one candidate is required")
    candidate_names = tuple(sorted(str(name) for name in values))
    if len(candidate_names) != len(values):
        raise ValueError("candidate names must be unique after string normalization")

    first = values[candidate_names[0]]
    branches = tuple(sorted(str(name) for name in first))
    if not branches or baseline_branch not in branches:
        raise ValueError("a common baseline branch is required")

    normalized: dict[str, dict[str, float]] = {}
    expected = set(branches)
    for candidate in candidate_names:
        row = values[candidate]
        if set(map(str, row)) != expected:
            raise ValueError("all candidates must cover exactly the same branches")
        converted: dict[str, float] = {}
        for branch in branches:
            score = float(row[branch])
            if not math.isfinite(score):
                raise ValueError("candidate values must be finite")
            converted[branch] = score
        normalized[candidate] = converted

    def winner(branch: str) -> str:
        # Lexically smaller candidate wins exact ties so the result is stable.
        return min(candidate_names, key=lambda c: (-normalized[c][branch], c))

    baseline_candidate = winner(baseline_branch)
    branch_winners = tuple((branch, winner(branch)) for branch in branches)
    response_sensitive = any(
        branch != baseline_branch and branch_winner != baseline_candidate
        for branch, branch_winner in branch_winners
    )
    if not response_sensitive:
        scores = tuple(normalized[baseline_candidate][branch] for branch in branches)
        return ResponseChoice(
            baseline_candidate,
            baseline_candidate,
            False,
            False,
            min(scores),
            sum(scores) / len(scores),
            branch_winners,
            "all response branches preserve the fixed-path winner",
        )

    def rank(candidate: str) -> tuple[float, float, float, str]:
        scores = tuple(normalized[candidate][branch] for branch in branches)
        # Negated lexical content cannot be expressed numerically; choose from
        # the numeric maxima first, then min lexical identity below.
        return (
            min(scores),
            sum(scores) / len(scores),
            normalized[candidate][baseline_branch],
            candidate,
        )

    numeric = {
        candidate: rank(candidate)[:3]
        for candidate in candidate_names
    }
    best_numeric = max(numeric.values())
    chosen = min(candidate for candidate in candidate_names if numeric[candidate] == best_numeric)
    chosen_scores = tuple(normalized[chosen][branch] for branch in branches)
    changed = chosen != baseline_candidate
    return ResponseChoice(
        baseline_candidate,
        chosen,
        True,
        changed,
        min(chosen_scores),
        sum(chosen_scores) / len(chosen_scores),
        branch_winners,
        (
            "response branches change the robust candidate"
            if changed
            else "response branches matter, but fixed-path winner remains robust"
        ),
    )
