"""Exact box-plus-total-variation adversarial mixture optimizer."""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Mapping, Sequence

from mixture_common import MixFamily, _quantity, _require

def _worst_case_mixture(
    effects: Mapping[str, Fraction],
    families: Sequence[MixFamily],
    radius: Fraction,
) -> dict[str, Any]:
    """Solve the exact box-constrained total-variation linear minimum.

    Starting at the nominal distribution, total variation permits moving at
    most ``radius`` units of probability mass.  For a linear objective the
    optimum moves mass greedily from the highest-effect available donor to the
    lowest-effect available receiver, respecting each family's box bounds.
    """

    weights: dict[str, Fraction] = {family.name: family.nominal for family in families}
    donor_capacity: dict[str, Fraction] = {family.name: family.nominal - family.lower for family in families}
    receiver_capacity: dict[str, Fraction] = {family.name: family.upper - family.nominal for family in families}
    remaining = radius
    transfers: list[dict[str, Any]] = []

    donors = sorted(families, key=lambda family: (effects[family.name], family.name), reverse=True)
    receivers = sorted(families, key=lambda family: (effects[family.name], family.name))
    donor_index = 0
    receiver_index = 0
    while remaining > 0 and donor_index < len(donors) and receiver_index < len(receivers):
        donor = donors[donor_index]
        receiver = receivers[receiver_index]
        if donor_capacity[donor.name] <= 0:
            donor_index += 1
            continue
        if receiver_capacity[receiver.name] <= 0:
            receiver_index += 1
            continue
        if effects[donor.name] <= effects[receiver.name]:
            break
        moved = min(remaining, donor_capacity[donor.name], receiver_capacity[receiver.name])
        _require(moved > 0, "INTERNAL", "mixture optimizer made no progress")
        weights[donor.name] -= moved
        weights[receiver.name] += moved
        donor_capacity[donor.name] -= moved
        receiver_capacity[receiver.name] -= moved
        remaining -= moved
        transfers.append(
            {
                "from": donor.name,
                "to": receiver.name,
                "mass": _quantity(moved),
                "objective_change": _quantity(moved * (effects[receiver.name] - effects[donor.name])),
            }
        )

    _require(sum(weights.values(), Fraction(0)) == 1, "INTERNAL", "optimized weights do not sum to one")
    for family in families:
        _require(family.lower <= weights[family.name] <= family.upper, "INTERNAL", "optimized weight violates bound", family=family.name)
    moved_mass = radius - remaining
    _require(sum(abs(weights[family.name] - family.nominal) for family in families) / 2 == moved_mass, "INTERNAL", "total-variation witness is inconsistent")
    value = sum(weights[family.name] * effects[family.name] for family in families)
    nominal_value = sum(family.nominal * effects[family.name] for family in families)
    return {
        "nominal_value": _quantity(nominal_value),
        "worst_case_value": _quantity(value),
        "radius": _quantity(radius),
        "mass_moved": _quantity(moved_mass),
        "unused_radius": _quantity(remaining),
        "witness_weights": {family.name: _quantity(weights[family.name]) for family in families},
        "transfers": transfers,
    }
