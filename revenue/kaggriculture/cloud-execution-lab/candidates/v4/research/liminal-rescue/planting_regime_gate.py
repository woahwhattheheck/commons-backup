"""Conservative research-only gate for optional *new* crop commitments.

This module deliberately does not integrate itself into TITAN. It is a small,
deterministic decision kernel recovered from the useful signal in the historical
SEED-HOARD experiment: some market draws made *not starting* a new crop program
better than blindly committing capital.

The kernel is fail-open. It may reject a new optional commitment only when the
caller provides an explicitly verified conservative value floor and that floor
is below the incremental hurdle. Existing commitments and required obligations
are never blocked here.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class PlantingProposal:
    crop: str
    incremental_cost: Optional[float]
    conservative_units: Optional[float]
    harvest_price_floor: Optional[float]
    collateral_value_floor: Optional[float] = 0.0
    risk_buffer: Optional[float] = 0.0
    verified_floor: bool = False
    existing_commitment: bool = False
    required_for_obligation: bool = False


@dataclass(frozen=True)
class GateDecision:
    admit: bool
    reason: str
    value_floor: Optional[float]
    hurdle: Optional[float]
    margin_floor: Optional[float]


def _valid_nonnegative(value: Optional[float]) -> bool:
    return value is not None and isfinite(value) and value >= 0.0


def evaluate_planting(proposal: PlantingProposal) -> GateDecision:
    """Evaluate one optional new planting proposal.

    Safety contract:
    * never block existing commitments or required obligations;
    * never block on an unverified/missing/non-finite economic floor;
    * never implement a crop-wide/global ban;
    * reject only a *new optional* commitment whose verified lower-bound value
      is strictly below incremental cost plus the explicit risk buffer.
    """

    if proposal.existing_commitment:
        return GateDecision(True, "existing_commitment", None, None, None)

    if proposal.required_for_obligation:
        return GateDecision(True, "required_for_obligation", None, None, None)

    if not proposal.verified_floor:
        return GateDecision(True, "unverified_floor_fail_open", None, None, None)

    numbers = (
        proposal.incremental_cost,
        proposal.conservative_units,
        proposal.harvest_price_floor,
        proposal.collateral_value_floor,
        proposal.risk_buffer,
    )
    if not all(_valid_nonnegative(v) for v in numbers):
        return GateDecision(True, "invalid_or_missing_floor_fail_open", None, None, None)

    assert proposal.incremental_cost is not None
    assert proposal.conservative_units is not None
    assert proposal.harvest_price_floor is not None
    assert proposal.collateral_value_floor is not None
    assert proposal.risk_buffer is not None

    value_floor = (
        proposal.conservative_units * proposal.harvest_price_floor
        + proposal.collateral_value_floor
    )
    hurdle = proposal.incremental_cost + proposal.risk_buffer
    margin_floor = value_floor - hurdle

    if margin_floor < 0.0:
        return GateDecision(
            False,
            "verified_negative_incremental_floor",
            value_floor,
            hurdle,
            margin_floor,
        )

    return GateDecision(
        True,
        "verified_nonnegative_incremental_floor",
        value_floor,
        hurdle,
        margin_floor,
    )
