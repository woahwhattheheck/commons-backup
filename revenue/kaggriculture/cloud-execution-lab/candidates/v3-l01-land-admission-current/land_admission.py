# SPDX-License-Identifier: Apache-2.0
"""Minimal L01 land-admission mechanism for a current TITAN package.

The historical L01 arm mutated only precomputed route data.  This module keeps
that exact intervention surface: after ``TitanAgent._initialize`` has built its
route table, append one ``BUY_LAND`` market order at steps 74 and 98 wherever
the market row has capacity and does not already contain a land purchase.

No observation, seed, opponent, seat, score, or environment variable is read.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

BUY_LAND = "BUY_LAND"
LAND_STEPS = (74, 98)
MAX_ORDERS = 10


def _has_buy_land(market: Sequence[Any] | None) -> bool:
    return any(
        isinstance(order, (list, tuple))
        and bool(order)
        and order[0] == BUY_LAND
        for order in (market or ())
    )


def patch_routes(
    routes: Mapping[Any, Sequence[MutableMapping[str, Any]]],
    *,
    steps: Sequence[int] = LAND_STEPS,
    max_orders: int = MAX_ORDERS,
) -> dict[str, Any]:
    """Apply the deterministic route patch and return an auditable receipt.

    ``routes`` is mutated in place because the runtime consumes this table.
    Shared route-row objects are safe: once a row receives ``BUY_LAND``, a
    second reference observes it and is skipped.
    """
    if max_orders <= 0:
        raise ValueError("max_orders must be positive")

    requested_steps = tuple(int(step) for step in steps)
    receipt: dict[str, Any] = {
        "schema": "titan-v3-land-admission-install-v1",
        "steps": list(requested_steps),
        "max_orders": int(max_orders),
        "routes_seen": 0,
        "rows_seen": 0,
        "activations": 0,
        "existing": 0,
        "full": 0,
        "out_of_range": 0,
        "sites": [],
    }

    for route_name, route in routes.items():
        receipt["routes_seen"] += 1
        if not route:
            receipt["out_of_range"] += len(requested_steps)
            continue
        for step in requested_steps:
            if step < 0 or step >= len(route):
                receipt["out_of_range"] += 1
                continue
            row = route[step]
            if not isinstance(row, MutableMapping):
                raise TypeError(
                    f"route {route_name!r} step {step} is not a mutable mapping"
                )
            receipt["rows_seen"] += 1
            market = row.setdefault("market", [])
            if not isinstance(market, list):
                raise TypeError(
                    f"route {route_name!r} step {step} market is not a list"
                )
            if _has_buy_land(market):
                receipt["existing"] += 1
                continue
            if len(market) >= max_orders:
                receipt["full"] += 1
                continue
            market.append([BUY_LAND])
            receipt["activations"] += 1
            receipt["sites"].append(
                {
                    "route": str(route_name),
                    "step": step,
                    "market_index": len(market) - 1,
                }
            )
    return receipt


def install(agent: Any) -> dict[str, Any]:
    """Install the route patch on an initialized agent."""
    controller = getattr(agent, "controller", None)
    routes = getattr(controller, "R", None) if controller is not None else None
    if not isinstance(routes, Mapping) or not routes:
        return {
            "schema": "titan-v3-land-admission-install-v1",
            "installed": False,
            "reason": "no_controller_routes",
            "activations": 0,
            "sites": [],
        }
    receipt = patch_routes(routes)
    receipt["installed"] = True
    return receipt


def wrap(agent: Any) -> Any:
    """Wrap one agent instance and patch every controller initialization.

    ``TitanAgent`` deliberately reconstructs its controller after a deadline
    cancellation. Installation therefore cannot be a one-shot per-agent flag:
    every completed ``_initialize`` must re-apply the idempotent route patch to
    the current controller route bank.
    """
    if getattr(agent, "_land_admission_wrapped", False):
        return agent

    original_initialize = agent._initialize
    state: dict[str, Any] = {
        "initializations": 0,
        "receipt": None,
    }

    def _initialize() -> None:
        original_initialize()
        state["initializations"] += 1
        state["receipt"] = install(agent)

    agent._initialize = _initialize
    agent._land_admission_wrapped = True
    agent._land_admission_state = state
    return agent
