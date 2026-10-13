# SPDX-License-Identifier: Apache-2.0
"""Copy-on-write early-land overlay for the current TITAN route bank.

The only policy change is to append one ``BUY_LAND`` order at steps 74 and 98
when the selected route row has room and does not already contain that order.
The source route bank and every untouched route/row/order object remain intact,
so controls created in the same interpreter cannot inherit candidate mutations.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Any, Mapping, MutableMapping, Sequence

LAND_STEPS: tuple[int, int] = (74, 98)
DEFAULT_MAX_ORDERS = 10
REVISION = "current-land-74-98-cow-v1"


@dataclass(frozen=True)
class PatchReport:
    revision: str
    route_keys: int
    distinct_routes: int
    changed_routes: int
    insertions: int
    inserted_by_step: dict[str, int]
    skipped_duplicate: int
    skipped_full: int
    skipped_short_route: int
    source_fingerprint: str
    candidate_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def route_fingerprint(routes: Mapping[Any, Sequence[Mapping[str, Any]]]) -> str:
    """Fingerprint route values without depending on insertion order of keys."""
    ordered = [(str(key), routes[key]) for key in sorted(routes, key=lambda x: str(x))]
    return hashlib.sha256(_canonical(ordered)).hexdigest()


def _contains_land(market: Sequence[Any]) -> bool:
    return any(
        isinstance(order, (list, tuple)) and bool(order) and order[0] == "BUY_LAND"
        for order in market
    )


def patch_routes(
    routes: Mapping[Any, Sequence[Mapping[str, Any]]],
    *,
    max_orders: int = DEFAULT_MAX_ORDERS,
    land_steps: Sequence[int] = LAND_STEPS,
) -> tuple[dict[Any, Sequence[Mapping[str, Any]]], PatchReport]:
    """Return a copy-on-write route bank and an exact mutation receipt.

    The input mapping and nested objects are never mutated. Aliased route lists
    remain aliased in the returned mapping. A route is copied only when at least
    one insertion is admitted; only changed rows and their market lists are
    copied inside that route.
    """
    if not isinstance(routes, Mapping):
        raise TypeError("routes must be a mapping")
    if isinstance(max_orders, bool) or not isinstance(max_orders, int) or max_orders <= 0:
        raise ValueError("max_orders must be a positive integer")

    steps: tuple[int, ...] = tuple(int(step) for step in land_steps)
    if not steps or any(step < 0 for step in steps) or len(set(steps)) != len(steps):
        raise ValueError("land_steps must contain unique non-negative integers")

    source_fingerprint = route_fingerprint(routes)
    patched: dict[Any, Sequence[Mapping[str, Any]]] = dict(routes)
    route_cache: dict[int, Sequence[Mapping[str, Any]]] = {}
    counters: Counter[str] = Counter()
    distinct_routes: set[int] = set()

    for key, original_route in routes.items():
        if not isinstance(original_route, Sequence) or isinstance(original_route, (str, bytes)):
            raise TypeError(f"route {key!r} must be a sequence")
        route_id = id(original_route)
        distinct_routes.add(route_id)
        if route_id in route_cache:
            patched[key] = route_cache[route_id]
            continue

        candidate_route: list[Mapping[str, Any]] | None = None
        for step in steps:
            if step >= len(original_route):
                counters["skipped_short_route"] += 1
                continue
            source_row = original_route[step]
            if not isinstance(source_row, Mapping):
                raise TypeError(f"route {key!r} step {step} must be a mapping")
            market = source_row.get("market") or []
            if not isinstance(market, Sequence) or isinstance(market, (str, bytes)):
                raise TypeError(f"route {key!r} step {step} market must be a sequence")
            if _contains_land(market):
                counters["skipped_duplicate"] += 1
                continue
            if len(market) >= max_orders:
                counters["skipped_full"] += 1
                continue

            if candidate_route is None:
                candidate_route = list(original_route)
            row = dict(source_row)
            row["market"] = list(market) + [["BUY_LAND"]]
            candidate_route[step] = row
            counters["insertions"] += 1
            counters[f"step:{step}"] += 1

        result_route: Sequence[Mapping[str, Any]] = (
            original_route if candidate_route is None else candidate_route
        )
        if candidate_route is not None:
            counters["changed_routes"] += 1
        route_cache[route_id] = result_route
        patched[key] = result_route

    report = PatchReport(
        revision=REVISION,
        route_keys=len(routes),
        distinct_routes=len(distinct_routes),
        changed_routes=counters["changed_routes"],
        insertions=counters["insertions"],
        inserted_by_step={str(step): counters[f"step:{step}"] for step in steps},
        skipped_duplicate=counters["skipped_duplicate"],
        skipped_full=counters["skipped_full"],
        skipped_short_route=counters["skipped_short_route"],
        source_fingerprint=source_fingerprint,
        candidate_fingerprint=route_fingerprint(patched),
    )
    return patched, report


def install(agent: Any, *, max_orders: int = DEFAULT_MAX_ORDERS) -> PatchReport:
    """Install once per initialized controller, including deadline reinitialization.

    TITAN intentionally replaces ``agent.controller`` after an episode deadline.
    Idempotence therefore belongs to the controller object, not to the long-lived
    agent wrapper. Keeping that distinction prevents the overlay from silently
    disappearing in later episodes while still avoiding duplicate insertions.

    The mapping object itself is retained deliberately. Current TITAN installs
    SpatialTempo first, and that wrapper captures controller.R as its pristine
    route source. Replacing the mapping would let its per-action rebuild restore
    the unpatched bank before the producer reads steps 74 and 98.
    """
    controller = getattr(agent, "controller", None)
    routes = getattr(controller, "R", None)
    if controller is None or routes is None:
        raise RuntimeError("initialized TITAN controller with route bank required")
    if not isinstance(routes, MutableMapping):
        raise TypeError("controller.R must be a mutable mapping for in-place COW install")

    existing = getattr(agent, "_land_7498_report", None)
    installed_controller = getattr(agent, "_land_7498_controller", None)
    if isinstance(existing, PatchReport) and installed_controller is controller:
        return existing

    patched, report = patch_routes(routes, max_orders=max_orders)
    routes.clear()
    routes.update(patched)
    controller.R = routes
    agent._land_7498_controller = controller
    agent._land_7498_report = report
    diagnostics = getattr(agent, "diagnostics", None)
    if isinstance(diagnostics, MutableMapping):
        diagnostics["land_74_98"] = report.to_dict()
    return report


def wrap(agent: Any, *, max_orders: int = DEFAULT_MAX_ORDERS) -> Any:
    """Patch immediately after TITAN's lazy initialization, before production."""
    if getattr(agent, "_land_7498_wrapped", False):
        return agent
    original_initialize = agent._initialize

    def initialize() -> None:
        original_initialize()
        install(agent, max_orders=max_orders)

    agent._initialize = initialize
    agent._land_7498_wrapped = True
    return agent
