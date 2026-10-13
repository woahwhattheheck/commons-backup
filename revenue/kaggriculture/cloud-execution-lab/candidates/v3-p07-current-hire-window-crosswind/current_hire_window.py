# SPDX-License-Identifier: Apache-2.0
"""Fail-closed P07 window proof for current-row HIRE actions.

Kaggriculture applies unit actions before market orders.  A current-row HIRE can
therefore only append actors *after* every current unit action has settled; it
cannot renumber or retroactively execute an action for an actor already present
in the observation.  This module exposes that narrow proof while retaining the
legacy cut before every future HIRE, checkpoint, and end-of-day boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

CHECKPOINTS = (226, 360, 433)
TURNS_PER_DAY = 24
LAST_ACTION_STEP = 718
DEFAULT_MAX_MARKET_ORDERS = 10
MIN_WINDOW = 3


@dataclass(frozen=True)
class WindowProof:
    """A machine-readable admission or fail-closed rejection."""

    accepted: bool
    end: int | None
    reason: str
    existing_actors: int
    current_hires: int
    executable_hire_slots: tuple[int, ...]
    inactive_hire_slots: tuple[int, ...]
    extra_current_hand_actions: int
    boundary_step: int | None
    boundary_kind: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _reject(reason: str, **fields: Any) -> WindowProof:
    base = {
        "accepted": False,
        "end": None,
        "reason": reason,
        "existing_actors": 0,
        "current_hires": 0,
        "executable_hire_slots": (),
        "inactive_hire_slots": (),
        "extra_current_hand_actions": 0,
        "boundary_step": None,
        "boundary_kind": None,
    }
    base.update(fields)
    return WindowProof(**base)


def _plain_int(value: Any) -> bool:
    return type(value) is int


def _market(row: Mapping[str, Any]) -> list[Any] | None:
    market = row.get("market", [])
    if not isinstance(market, list):
        return None
    # The official parser treats None and [] as no order.  Non-empty orders must
    # at least expose a string opcode; deeper malformed-order handling remains
    # with the official interpreter.
    for order in market:
        if order is None:
            continue
        if not isinstance(order, list):
            return None
        if order and not isinstance(order[0], str):
            return None
    return market


def _hire_slots(market: Sequence[Any]) -> tuple[int, ...]:
    return tuple(
        slot
        for slot, order in enumerate(market)
        if isinstance(order, list) and order and order[0] == "HIRE"
    )


def _existing_actor_count(observation: Mapping[str, Any]) -> int | None:
    player = observation.get("player")
    farms = observation.get("farms")
    if not _plain_int(player) or not isinstance(farms, list):
        return None
    if player < 0 or player >= len(farms):
        return None
    farm = farms[player]
    if not isinstance(farm, Mapping):
        return None
    farmer = farm.get("farmer")
    hands = farm.get("hands", [])
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    return 1 + len(hands)


def prove_window(
    observation: Mapping[str, Any],
    selected: Mapping[str, Any],
    route: Sequence[Any],
    now: int,
    *,
    max_market_orders: int = DEFAULT_MAX_MARKET_ORDERS,
) -> WindowProof:
    """Prove the actor-stable route prefix available to P07.

    The current row may contain executable HIRE orders because all current unit
    actions settle first.  A HIRE in a later row remains a hard cut.  HIRE rows
    beyond the official executable market prefix fail closed because they signal
    an authored actor-count expectation that the interpreter will not realize.
    """

    if not isinstance(observation, Mapping) or not isinstance(selected, Mapping):
        return _reject("malformed_observation_or_selected")
    if not _plain_int(now) or now < 0 or now > LAST_ACTION_STEP:
        return _reject("unsupported_step")
    if observation.get("step") != now:
        return _reject("step_binding_mismatch")
    if not _plain_int(max_market_orders) or max_market_orders < 1:
        return _reject("unsupported_market_cap")
    if not isinstance(route, Sequence) or isinstance(route, (str, bytes, bytearray)):
        return _reject("malformed_route")
    if now >= len(route):
        return _reject("route_too_short")

    existing = _existing_actor_count(observation)
    if existing is None or existing < 1:
        return _reject("malformed_actor_prefix")

    current_market = _market(selected)
    if current_market is None:
        return _reject("malformed_current_market", existing_actors=existing)
    all_current_hires = _hire_slots(current_market)
    executable = tuple(slot for slot in all_current_hires if slot < max_market_orders)
    inactive = tuple(slot for slot in all_current_hires if slot >= max_market_orders)

    hands = selected.get("hands", [])
    if not isinstance(hands, list):
        return _reject(
            "malformed_current_hands",
            existing_actors=existing,
            current_hires=len(executable),
            executable_hire_slots=executable,
            inactive_hire_slots=inactive,
        )
    extra_actions = max(0, len(hands) - (existing - 1))

    # Only the new current-HIRE path receives the additional actor-shape proof.
    # With no current HIRE, retain the predecessor's well-formed-route semantics.
    if all_current_hires:
        if inactive:
            return _reject(
                "inactive_current_hire",
                existing_actors=existing,
                current_hires=len(executable),
                executable_hire_slots=executable,
                inactive_hire_slots=inactive,
                extra_current_hand_actions=extra_actions,
            )
        if extra_actions > len(executable):
            return _reject(
                "unbound_new_actor_actions",
                existing_actors=existing,
                current_hires=len(executable),
                executable_hire_slots=executable,
                inactive_hire_slots=inactive,
                extra_current_hand_actions=extra_actions,
            )

    end = min(((now // TURNS_PER_DAY) + 1) * TURNS_PER_DAY, LAST_ACTION_STEP + 1)
    boundary_step: int | None = end
    boundary_kind: str | None = "end_of_day" if end % TURNS_PER_DAY == 0 else "episode_end"

    for checkpoint in CHECKPOINTS:
        if now < checkpoint < end:
            end = checkpoint
            boundary_step = checkpoint
            boundary_kind = "checkpoint"
            break

    # Current HIRE is deliberately excluded: unit actions settle before market.
    # Every future HIRE still terminates the proof before that row.
    for step in range(now + 1, end):
        row = route[step] if step < len(route) else None
        if row is None:
            end = step
            boundary_step = step
            boundary_kind = "missing_route_row"
            break
        if not isinstance(row, Mapping):
            return _reject(
                "malformed_future_row",
                existing_actors=existing,
                current_hires=len(executable),
                executable_hire_slots=executable,
                inactive_hire_slots=inactive,
                extra_current_hand_actions=extra_actions,
                boundary_step=step,
                boundary_kind="malformed_future_row",
            )
        future_market = _market(row)
        if future_market is None:
            return _reject(
                "malformed_future_market",
                existing_actors=existing,
                current_hires=len(executable),
                executable_hire_slots=executable,
                inactive_hire_slots=inactive,
                extra_current_hand_actions=extra_actions,
                boundary_step=step,
                boundary_kind="malformed_future_market",
            )
        if _hire_slots(future_market):
            end = step
            boundary_step = step
            boundary_kind = "future_hire"
            break

    if end - now < MIN_WINDOW:
        return _reject(
            "window_too_short",
            existing_actors=existing,
            current_hires=len(executable),
            executable_hire_slots=executable,
            inactive_hire_slots=inactive,
            extra_current_hand_actions=extra_actions,
            boundary_step=boundary_step,
            boundary_kind=boundary_kind,
        )

    reason = "current_hire_existing_actor_prefix" if executable else "legacy_no_current_hire"
    return WindowProof(
        accepted=True,
        end=end,
        reason=reason,
        existing_actors=existing,
        current_hires=len(executable),
        executable_hire_slots=executable,
        inactive_hire_slots=inactive,
        extra_current_hand_actions=extra_actions,
        boundary_step=boundary_step,
        boundary_kind=boundary_kind,
    )


def window_end(
    observation: Mapping[str, Any],
    selected: Mapping[str, Any],
    route: Sequence[Any],
    now: int,
    *,
    max_market_orders: int = DEFAULT_MAX_MARKET_ORDERS,
) -> int | None:
    """Compatibility adapter for P07's original `_window` contract."""

    return prove_window(
        observation,
        selected,
        route,
        now,
        max_market_orders=max_market_orders,
    ).end
