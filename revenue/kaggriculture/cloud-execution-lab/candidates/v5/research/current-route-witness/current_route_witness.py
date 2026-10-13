# SPDX-License-Identifier: Apache-2.0
"""Authenticate immutable future rows from one current committed producer receipt.

This is provenance plumbing, not a producer. It never calls ``controller.act``
or any route-selection method. Callers must supply the immutable entrypoint
receipt published with the selected action. Raw ``controller.cur`` is deliberately
not an authority: it may already contain an interrupted or later proposal.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

SCHEMA = "titan-v5-current-route-window-v3"
ROUTE_SOURCE = "entrypoint_route_receipt->controller.R[route]"
MAX_LOOKAHEAD = 72
_RECEIPT_KEYS = frozenset({"route_step", "last_step", "player", "route"})


def _plain_nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _route_id(value: Any) -> str | None:
    return value if type(value) is str and bool(value) else None


def _current_route_receipt(value: Any, observation: Any) -> dict[str, Any] | None:
    """Validate one receipt as authority for the current selected-action boundary."""
    if type(value) is not dict or set(value) != _RECEIPT_KEYS:
        return None
    route_step = value.get("route_step")
    last_step = value.get("last_step")
    player = value.get("player")
    route = _route_id(value.get("route"))
    if not _plain_nonnegative_int(route_step) or not _plain_nonnegative_int(last_step):
        return None
    if type(player) is not int or player not in (0, 1) or route is None:
        return None
    if not isinstance(observation, dict):
        return None
    step = observation.get("step")
    observed_player = observation.get("player")
    if not _plain_nonnegative_int(step):
        return None
    if type(observed_player) is not int or observed_player not in (0, 1):
        return None
    # A window may authorize transforms of the current selected action only.
    # Carried recovery receipts (route_step < last_step), stale receipts, gaps,
    # and cross-player receipts remain useful to the entrypoint but are not
    # current producer authority.
    if route_step != step or last_step != step or player != observed_player:
        return None
    return {
        "route_step": route_step,
        "last_step": last_step,
        "player": player,
        "route": route,
    }


def _worker_count(observation: Any) -> int | None:
    if not isinstance(observation, dict):
        return None
    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    if type(player) is not int or player not in (0, 1):
        return None
    if not isinstance(farms, list) or not (0 <= player < len(farms)):
        return None
    farm = farms[player]
    if not isinstance(farm, dict) or "farmer" not in farm or not isinstance(farm.get("hands"), list):
        return None
    if not isinstance(private, dict):
        return None
    inventories = private.get("inventories")
    count = 1 + len(farm["hands"])
    if not isinstance(inventories, list) or len(inventories) != count:
        return None
    return count


def _action_worker_cardinality(action: Any) -> int | None:
    if not isinstance(action, dict) or "farmer" not in action:
        return None
    hands = action.get("hands")
    market = action.get("market")
    if not isinstance(hands, list) or not isinstance(market, list):
        return None
    commands = [action["farmer"], *hands]
    if not all(
        isinstance(command, list)
        and len(command) > 0
        and isinstance(command[0], str)
        for command in commands
    ):
        return None
    return len(commands)


def _canonical_json(value: Any) -> str | None:
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        recovered = json.loads(rendered)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if recovered != value:
        return None
    return rendered


def _capture_route(
    controller: Any,
    route_id: str,
) -> tuple[str, str, list[Any], str] | None:
    """Capture one stable explicitly-authorized ``R[route_id]`` snapshot."""
    routes = getattr(controller, "R", None)
    if not isinstance(routes, dict) or route_id not in routes:
        return None
    route_ref = routes[route_id]
    if not isinstance(route_ref, (list, tuple)):
        return None

    normalized = list(route_ref)
    rendered = _canonical_json(normalized)
    if rendered is None:
        return None
    try:
        snapshot = json.loads(rendered)
    except json.JSONDecodeError:
        return None
    if not isinstance(snapshot, list):
        return None

    # Rebind only the explicitly authorized route. controller.cur is deliberately
    # ignored because it may contain an uncommitted proposal unrelated to the
    # selected action being transformed.
    if getattr(controller, "R", None) is not routes or routes.get(route_id) is not route_ref:
        return None
    rendered_after = _canonical_json(list(route_ref))
    if rendered_after != rendered:
        return None

    controller_type = f"{type(controller).__module__}.{type(controller).__qualname__}"
    route_sha256 = hashlib.sha256(rendered.encode("ascii")).hexdigest()
    return route_id, controller_type, snapshot, route_sha256


@dataclass(frozen=True)
class RouteActionWitness:
    """One detached authored row inside an immutable committed-route capture."""

    step: int
    worker_cardinality: int
    action_json: str
    action_sha256: str

    def action(self) -> dict[str, Any]:
        value = json.loads(self.action_json)
        if not isinstance(value, dict):
            raise ValueError("route action witness is not an object")
        return value

    def receipt(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "worker_cardinality": self.worker_cardinality,
            "action_sha256": self.action_sha256,
        }


@dataclass(frozen=True)
class CurrentRouteWindow:
    """Immutable bounded future window from one current committed route receipt."""

    schema: str
    route_source: str
    controller_type: str
    route_id: str
    route_step: int
    last_step: int
    player: int
    current_step: int
    current_index: int
    current_worker_cardinality: int
    route_length: int
    route_sha256: str
    lookahead: int
    rows: tuple[RouteActionWitness, ...]
    window_sha256: str

    def actions(self) -> tuple[dict[str, Any], ...]:
        return tuple(row.action() for row in self.rows)

    def b5_witness(self) -> "CurrentRouteWitness | None":
        """Derive the exact step+1/current-cardinality envelope B5/JIT accepts."""
        if not self.rows:
            return None
        row = self.rows[0]
        if row.step != self.current_step + 1:
            return None
        if row.worker_cardinality != self.current_worker_cardinality:
            return None
        return CurrentRouteWitness(
            schema=self.schema,
            route_source=self.route_source,
            controller_type=self.controller_type,
            route_id=self.route_id,
            route_step=self.route_step,
            last_step=self.last_step,
            player=self.player,
            current_step=self.current_step,
            current_index=self.current_index,
            next_step=row.step,
            worker_cardinality=self.current_worker_cardinality,
            route_length=self.route_length,
            route_sha256=self.route_sha256,
            action_json=row.action_json,
            action_sha256=row.action_sha256,
            window_sha256=self.window_sha256,
        )

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "route_source": self.route_source,
            "controller_type": self.controller_type,
            "route_id": self.route_id,
            "route_step": self.route_step,
            "last_step": self.last_step,
            "player": self.player,
            "current_step": self.current_step,
            "current_index": self.current_index,
            "current_worker_cardinality": self.current_worker_cardinality,
            "route_length": self.route_length,
            "route_sha256": self.route_sha256,
            "lookahead": self.lookahead,
            "window_sha256": self.window_sha256,
            "rows": [row.receipt() for row in self.rows],
        }


@dataclass(frozen=True)
class CurrentRouteWitness:
    """B5-compatible step+1 view derived from a CurrentRouteWindow."""

    schema: str
    route_source: str
    controller_type: str
    route_id: str
    route_step: int
    last_step: int
    player: int
    current_step: int
    current_index: int
    next_step: int
    worker_cardinality: int
    route_length: int
    route_sha256: str
    action_json: str
    action_sha256: str
    window_sha256: str

    def next_authored_action(self) -> dict[str, Any]:
        action = json.loads(self.action_json)
        if not isinstance(action, dict):
            raise ValueError("witness action payload is not an object")
        return action

    def b5_kwargs(self) -> dict[str, Any]:
        return {
            "next_authored": self.next_authored_action(),
            "next_authored_step": self.next_step,
        }

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "route_source": self.route_source,
            "controller_type": self.controller_type,
            "route_id": self.route_id,
            "route_step": self.route_step,
            "last_step": self.last_step,
            "player": self.player,
            "current_step": self.current_step,
            "current_index": self.current_index,
            "next_step": self.next_step,
            "worker_cardinality": self.worker_cardinality,
            "route_length": self.route_length,
            "route_sha256": self.route_sha256,
            "action_sha256": self.action_sha256,
            "window_sha256": self.window_sha256,
        }


def bind_current_route_window(
    controller: Any,
    observation: Any,
    *,
    completed_route_receipt: Any = None,
    lookahead: int,
) -> CurrentRouteWindow | None:
    """Capture future rows from the current committed producer receipt."""
    if type(lookahead) is not int or not 1 <= lookahead <= MAX_LOOKAHEAD:
        return None
    receipt = _current_route_receipt(completed_route_receipt, observation)
    if receipt is None:
        return None
    step = receipt["route_step"]
    count = _worker_count(observation)
    if count is None:
        return None

    captured = _capture_route(controller, receipt["route"])
    if captured is None:
        return None
    route_id, controller_type, route, route_sha256 = captured
    if step >= len(route):
        return None

    end = min(len(route), step + 1 + lookahead)
    if end <= step + 1:
        return None

    rows: list[RouteActionWitness] = []
    for authored_step in range(step + 1, end):
        authored = route[authored_step]
        cardinality = _action_worker_cardinality(authored)
        if cardinality is None:
            return None
        action_json = _canonical_json(authored)
        if action_json is None:
            return None
        rows.append(
            RouteActionWitness(
                step=authored_step,
                worker_cardinality=cardinality,
                action_json=action_json,
                action_sha256=hashlib.sha256(action_json.encode("ascii")).hexdigest(),
            )
        )

    # The digest is portable authority for both the immutable producer receipt and
    # the bounded route window. Every asserted field that changes what a consumer
    # may infer is covered, including receipt freshness/player provenance.
    window_material = json.dumps(
        {
            "schema": SCHEMA,
            "route_source": ROUTE_SOURCE,
            "controller_type": controller_type,
            "route_id": route_id,
            "route_step": receipt["route_step"],
            "last_step": receipt["last_step"],
            "player": receipt["player"],
            "current_step": step,
            "current_index": step,
            "current_worker_cardinality": count,
            "route_length": len(route),
            "route_sha256": route_sha256,
            "lookahead": lookahead,
            "rows": [row.receipt() for row in rows],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    window_sha256 = hashlib.sha256(window_material.encode("ascii")).hexdigest()

    return CurrentRouteWindow(
        schema=SCHEMA,
        route_source=ROUTE_SOURCE,
        controller_type=controller_type,
        route_id=route_id,
        route_step=receipt["route_step"],
        last_step=receipt["last_step"],
        player=receipt["player"],
        current_step=step,
        current_index=step,
        current_worker_cardinality=count,
        route_length=len(route),
        route_sha256=route_sha256,
        lookahead=lookahead,
        rows=tuple(rows),
        window_sha256=window_sha256,
    )


def bind_current_route(
    controller: Any,
    observation: Any,
    *,
    completed_route_receipt: Any = None,
) -> CurrentRouteWitness | None:
    """B5/JIT view of exact ``R[receipt.route][step+1]``."""
    window = bind_current_route_window(
        controller,
        observation,
        completed_route_receipt=completed_route_receipt,
        lookahead=1,
    )
    return None if window is None else window.b5_witness()


def bind_b5_kwargs(
    controller: Any,
    observation: Any,
    *,
    completed_route_receipt: Any = None,
) -> dict[str, Any] | None:
    """Convenience adapter for B5/JIT; no B5 import or policy dependency."""
    witness = bind_current_route(
        controller,
        observation,
        completed_route_receipt=completed_route_receipt,
    )
    return None if witness is None else witness.b5_kwargs()
