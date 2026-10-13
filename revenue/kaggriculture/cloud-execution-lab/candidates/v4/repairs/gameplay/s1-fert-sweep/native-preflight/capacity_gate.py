# SPDX-License-Identifier: Apache-2.0
"""S1 admission gate consuming the EXISTING native shared-stock certificate.

The caller supplies SpatialTempo._idle_stock_bound bound to its native object.
No controller, feature flag, market order, source patch, or production activation
is installed here. Source authentication is performed by the integration runner.
A stock certificate bounds all current-day arrivals, including the fertilizer to
be collected; adding the planned fertilizer again would double-count it.
"""
from __future__ import annotations
from collections.abc import Callable
from typing import Any


def certify(lane: Any, observation: Any, tape: Any, configuration: Any,
            stock_bound: Callable[..., Any]) -> dict[str, Any]:
    """Return a fail-closed, non-mutating admission certificate.

    The certificate remains conservative: no future sales are credited, and the
    donor's twelve-unit headroom is retained. It does not establish profit,
    actor ownership, actual final-return custody, or actual acquisition fill.
    """
    denied = {'allowed': False, 'reason': 'unsupported', 'stock_upper': None}
    if not lane.standard_configuration(configuration):
        return denied
    parsed = lane._farm(observation)
    if parsed is None:
        return denied
    step, _, _, private, _ = parsed
    day, hour = divmod(step, lane.TURNS_PER_DAY)
    if day not in lane.DAYS or not lane.MIN_HOUR <= hour < lane.TURNS_PER_DAY - 1:
        return dict(denied, reason='outside_window')
    end = (day + 1) * lane.TURNS_PER_DAY
    if not isinstance(tape, list) or len(tape) < end:
        return dict(denied, reason='missing_day')
    try:
        certificate = stock_bound(observation, tape, end)
    except Exception:
        return dict(denied, reason='bound_unavailable')
    if (not isinstance(certificate, tuple) or len(certificate) != 3
            or type(certificate[0]) is not int or certificate[0] < 0):
        return dict(denied, reason='bound_unavailable')
    stock = certificate[0]
    if stock < lane._inventory_total(private):
        return dict(denied, reason='bound_below_observed_stock')
    limit = lane.SHED_CAPACITY - lane.HEADROOM_RESERVE
    return {'allowed': stock <= limit,
            'reason': 'capacity' if stock > limit else 'certified',
            'stock_upper': stock, 'capacity_limit': limit,
            'future_sale_credit': 0}


def consider(lane: Any, original_consider: Callable[..., Any], observation: Any,
             action: Any, state: Any, tape: Any, configuration: Any,
             stock_bound: Callable[..., Any]) -> Any:
    """Compose before donor mutation; a veto retains the original action/state."""
    certificate = certify(lane, observation, tape, configuration, stock_bound)
    if not certificate['allowed']:
        return action
    return original_consider(observation, action, state, tape, configuration)
