# SPDX-License-Identifier: Apache-2.0
"""P07: bind represented route lanes to the hands that physically exist.

The parent route can request several HIRE orders in one market queue even when only a
prefix executes.  On the following observation, the route may nevertheless emit one
command per *requested* hand.  The engine ignores commands beyond the physical hand
count, which means the implicit "first lanes win" assignment can discard a stronger
represented lane.

This module does not create actors, retry HIRE, change money, or edit market/farmer
orders.  It activates only after observing a one-step HIRE underfill and only when the
route proves the requested new actors are an exact suffix.  Existing actors retain
identity.  The completed new actors are assigned to the strongest represented suffix
lanes using a deterministic, route-only lexicographic score.  Any ambiguity fails
closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

PASS_TYPES = frozenset(("", "PASS", "NONE", "NOOP"))
PRODUCTIVE_TYPES = frozenset(
    (
        "HARVEST",
        "PLANT",
        "WATER",
        "FERTILIZE",
        "COLLECT_FERTILIZER",
        "FEED",
        "CARE",
        "MILK",
        "SHEAR",
        "DIG",
        "PICKUP",
        "DROP",
        "PLACE",
        "BUILD",
    )
)
LOGISTICS_TYPES = frozenset(("PICKUP", "DROP", "PLACE", "BUILD"))


@dataclass(frozen=True)
class _PendingHire:
    step: int
    day: int
    route_token: tuple[type, Any]
    baseline_hands: int
    requested_hands: int


@dataclass(frozen=True)
class _ActiveBinding:
    day: int
    route_token: tuple[type, Any]
    mapping: tuple[int, ...]
    expected_physical_hands: int
    expected_logical_hands: int
    start_step: int
    end_step: int
    lane_scores: tuple[tuple[int, int, int, int, int], ...]
    requested_hands: int
    completed_hands: int


def _strict_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    if isinstance(value, str) and value.strip() not in (str(parsed), f"+{parsed}"):
        return None
    return parsed


def _route_token(route_id: Any) -> tuple[type, Any] | None:
    if isinstance(route_id, bool) or not isinstance(route_id, (str, int)):
        return None
    return (type(route_id), route_id)


def _command_type(command: Any) -> str | None:
    if not isinstance(command, (list, tuple)) or not command:
        return None
    head = command[0]
    if not isinstance(head, str):
        return None
    return head.strip().upper()


def _max_market_orders(configuration: Mapping[str, Any]) -> int | None:
    raw = configuration.get("maxMarketOrdersPerTurn", 10)
    value = _strict_int(raw)
    if value is None:
        return None
    return max(1, value)


def _executable_hires(action: Mapping[str, Any], configuration: Mapping[str, Any]) -> int | None:
    queue = action.get("market")
    if not isinstance(queue, list):
        return None
    limit = _max_market_orders(configuration)
    if limit is None:
        return None
    hires = 0
    for order in queue[:limit]:
        if order in (None, []):
            continue
        kind = _command_type(order)
        if kind is None:
            return None
        if kind == "HIRE":
            hires += 1
    return hires


def _hands_value(value: Any) -> int | None:
    if isinstance(value, (list, tuple)):
        return len(value)
    parsed = _strict_int(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def _physical_hand_count(observation: Mapping[str, Any]) -> int | None:
    farm = observation.get("farm")
    if isinstance(farm, Mapping) and "hands" in farm:
        return _hands_value(farm.get("hands"))

    farms = observation.get("farms")
    player = _strict_int(observation.get("player"))
    if player is None:
        return None
    own: Any = None
    if isinstance(farms, (list, tuple)) and 0 <= player < len(farms):
        own = farms[player]
    elif isinstance(farms, Mapping):
        own = farms.get(player, farms.get(str(player)))
    if isinstance(own, Mapping) and "hands" in own:
        return _hands_value(own.get("hands"))
    return None


def _action_shape(action: Any) -> tuple[list[Any], list[Any], Any] | None:
    if not isinstance(action, Mapping):
        return None
    hands = action.get("hands")
    market = action.get("market")
    if not isinstance(hands, list) or not isinstance(market, list) or "farmer" not in action:
        return None
    return hands, market, action.get("farmer")


def _lane_score(commands: Sequence[Any]) -> tuple[int, int, int, int, int] | None:
    productive = 0
    logistics = 0
    nonpass = 0
    first_productive = len(commands) + 1
    first_nonpass = len(commands) + 1
    for offset, command in enumerate(commands):
        kind = _command_type(command)
        if kind is None:
            return None
        if kind in PASS_TYPES:
            continue
        nonpass += 1
        if first_nonpass > len(commands):
            first_nonpass = offset
        if kind in PRODUCTIVE_TYPES:
            productive += 1
            if first_productive > len(commands):
                first_productive = offset
        if kind in LOGISTICS_TYPES:
            logistics += 1
    # More productive/non-PASS work is better; earlier work wins equal totals.
    return (productive, logistics, nonpass, -first_productive, -first_nonpass)


def _certified_lane_scores(
    route: Sequence[Any],
    *,
    start_step: int,
    day: int,
    logical_hands: int,
    configuration: Mapping[str, Any],
    horizon: int,
) -> tuple[tuple[tuple[int, int, int, int, int], ...], int] | None:
    if not isinstance(route, (list, tuple)) or not (0 <= start_step < len(route)):
        return None
    if horizon < 1:
        return None

    per_lane: list[list[Any]] = [[] for _ in range(logical_hands)]
    end_step = start_step
    for absolute in range(start_step, min(len(route), start_step + horizon)):
        row = route[absolute]
        if not isinstance(row, Mapping):
            break
        hands = row.get("hands")
        if not isinstance(hands, list) or len(hands) != logical_hands:
            break
        if any(_command_type(command) is None for command in hands):
            return None
        for lane, command in enumerate(hands):
            per_lane[lane].append(command)
        end_step = absolute + 1
        future_hires = _executable_hires(row, configuration)
        if future_hires is None:
            return None
        # Unit actions on this row execute before the next HIRE.  Include it, but
        # do not certify the changed actor cardinality that follows.
        if future_hires:
            break

    if end_step == start_step:
        return None
    scores = tuple(_lane_score(commands) for commands in per_lane)
    if any(score is None for score in scores):
        return None
    return tuple(score for score in scores if score is not None), end_step


class JointActorAssignment:
    """Stateful one-step receipt join for physical hand assignment.

    A single instance belongs to one agent instance.  It deliberately has no
    persistence protocol: reconstruction, retries, route switches, malformed
    observations and cardinality drift all lose the certificate and return the
    unchanged action.
    """

    def __init__(self, *, enabled: bool = False, horizon: int = 96):
        self.enabled = bool(enabled)
        self.horizon = int(horizon)
        if self.horizon < 1:
            raise ValueError("horizon must be positive")
        self.reset()

    def reset(self) -> None:
        self._last_step: int | None = None
        self._last_day: int | None = None
        self._last_route: tuple[type, Any] | None = None
        self._last_hands: int | None = None
        self._pending: _PendingHire | None = None
        self._active: _ActiveBinding | None = None
        self._blocked: tuple[tuple[type, Any], int] | None = None

    def _block(self, token: tuple[type, Any], day: int) -> None:
        self._pending = None
        self._active = None
        self._blocked = (token, day)

    def _remember(self, step: int, day: int, token: tuple[type, Any], hands: int) -> None:
        self._last_step = step
        self._last_day = day
        self._last_route = token
        self._last_hands = hands

    def _report(self, *, reason: str, step: int | None = None, changed: bool = False, **extra: Any) -> dict[str, Any]:
        report: dict[str, Any] = {
            "enabled": self.enabled,
            "changed": bool(changed),
            "reason": reason,
        }
        if step is not None:
            report["step"] = step
        report.update(extra)
        return report

    def _activate(
        self,
        *,
        pending: _PendingHire,
        completed: int,
        step: int,
        selected_hands: list[Any],
        route: Sequence[Any],
        configuration: Mapping[str, Any],
    ) -> _ActiveBinding | None:
        logical = pending.baseline_hands + pending.requested_hands
        if len(selected_hands) != logical:
            return None
        physical = pending.baseline_hands + completed
        if completed < 0 or completed >= pending.requested_hands:
            return None
        scored = _certified_lane_scores(
            route,
            start_step=step,
            day=pending.day,
            logical_hands=logical,
            configuration=configuration,
            horizon=self.horizon,
        )
        if scored is None:
            return None
        lane_scores, end_step = scored
        candidates = range(pending.baseline_hands, logical)
        ranked = sorted(candidates, key=lambda lane: (lane_scores[lane], -lane), reverse=True)
        chosen = tuple(sorted(ranked[:completed]))
        mapping = tuple(range(pending.baseline_hands)) + chosen
        if len(mapping) != physical or any(index >= logical for index in mapping):
            return None
        return _ActiveBinding(
            day=pending.day,
            route_token=pending.route_token,
            mapping=mapping,
            expected_physical_hands=physical,
            expected_logical_hands=logical,
            start_step=step,
            end_step=end_step,
            lane_scores=lane_scores,
            requested_hands=pending.requested_hands,
            completed_hands=completed,
        )

    def apply(
        self,
        observation: Mapping[str, Any],
        configuration: Mapping[str, Any],
        selected: Mapping[str, Any],
        *,
        route: Sequence[Any],
        route_id: Any,
    ) -> tuple[Mapping[str, Any], dict[str, Any]]:
        """Return ``(action, receipt)``; ``action is selected`` on every decline."""
        if not self.enabled:
            return selected, self._report(reason="flag_off")
        if not isinstance(observation, Mapping) or not isinstance(configuration, Mapping):
            self.reset()
            return selected, self._report(reason="malformed_call")
        shape = _action_shape(selected)
        step = _strict_int(observation.get("step"))
        day = _strict_int(observation.get("day"))
        token = _route_token(route_id)
        physical = _physical_hand_count(observation)
        if shape is None or step is None or step < 0 or day is None or day < 0 or token is None or physical is None:
            self.reset()
            return selected, self._report(reason="malformed_observation_or_action", step=step)
        selected_hands, _, _ = shape

        transition_reason: str | None = None
        if self._last_step is not None:
            if step == 0 and step <= self._last_step:
                self.reset()
                transition_reason = "episode_reset"
            elif day != self._last_day:
                self._pending = None
                self._active = None
                self._blocked = None
                transition_reason = "day_reset"
            elif token != self._last_route:
                self._block(token, day)
                transition_reason = "route_switch"
            elif step <= self._last_step:
                self._block(token, day)
                transition_reason = "repeated_or_reordered_step"
            elif step != self._last_step + 1:
                self._block(token, day)
                transition_reason = "step_gap"

        if self._blocked == (token, day):
            self._remember(step, day, token, physical)
            return selected, self._report(reason=transition_reason or "blocked_interval", step=step)

        activation: _ActiveBinding | None = None
        observed: dict[str, Any] = {}
        if self._pending is not None:
            pending = self._pending
            self._pending = None
            if pending.route_token != token or pending.day != day or pending.step + 1 != step:
                self._block(token, day)
                self._remember(step, day, token, physical)
                return selected, self._report(reason="pending_receipt_discontinuity", step=step)
            completed = physical - pending.baseline_hands
            observed = {
                "requested_hands": pending.requested_hands,
                "completed_hands": completed,
                "baseline_hands": pending.baseline_hands,
            }
            if completed < 0 or completed > pending.requested_hands:
                self._block(token, day)
                self._remember(step, day, token, physical)
                return selected, self._report(reason="unexpected_actor_delta", step=step, **observed)
            if completed < pending.requested_hands:
                activation = self._activate(
                    pending=pending,
                    completed=completed,
                    step=step,
                    selected_hands=selected_hands,
                    route=route,
                    configuration=configuration,
                )
                if activation is None:
                    self._block(token, day)
                    self._remember(step, day, token, physical)
                    return selected, self._report(reason="ambiguous_underfill", step=step, **observed)
                self._active = activation
            else:
                transition_reason = "all_hires_completed"

        active = self._active
        output: Mapping[str, Any] = selected
        changed = False
        report_reason = transition_reason or "no_observed_underfill"
        stop_after_current = False
        if active is not None:
            valid = (
                active.route_token == token
                and active.day == day
                and active.start_step <= step < active.end_step
                and physical == active.expected_physical_hands
                and len(selected_hands) == active.expected_logical_hands
                and all(0 <= index < len(selected_hands) for index in active.mapping)
            )
            if not valid:
                self._block(token, day)
                self._remember(step, day, token, physical)
                return selected, self._report(reason="binding_drift", step=step)
            remapped = [selected_hands[index] for index in active.mapping]
            output_dict = dict(selected)
            output_dict["hands"] = remapped
            output = output_dict
            changed = remapped != selected_hands
            report_reason = "underfill_binding_active"
            hires_now = _executable_hires(selected, configuration)
            if hires_now is None:
                self._block(token, day)
                self._remember(step, day, token, physical)
                return selected, self._report(reason="malformed_market_prefix", step=step)
            stop_after_current = bool(hires_now)
            observed.update(
                mapping=list(active.mapping),
                logical_hands=active.expected_logical_hands,
                physical_hands=active.expected_physical_hands,
                interval=[active.start_step, active.end_step],
                lane_scores=[list(score) for score in active.lane_scores],
            )

        if self._active is None:
            hires = _executable_hires(selected, configuration)
            if hires is None:
                self._block(token, day)
                self._remember(step, day, token, physical)
                return selected, self._report(reason="malformed_market_prefix", step=step)
            if hires:
                # Before a HIRE executes, represented and physical actors must be
                # identical.  Otherwise this is a late join or inherited mismatch.
                if len(selected_hands) != physical:
                    self._block(token, day)
                    self._remember(step, day, token, physical)
                    return selected, self._report(reason="uncertified_hire_baseline", step=step)
                self._pending = _PendingHire(
                    step=step,
                    day=day,
                    route_token=token,
                    baseline_hands=physical,
                    requested_hands=hires,
                )
                report_reason = "hire_receipt_pending"
                observed.update(requested_hands=hires, baseline_hands=physical)

        if active is not None and step + 1 >= active.end_step:
            self._block(token, day)
            stop_after_current = False
            report_reason = "binding_interval_end"
        elif stop_after_current:
            self._block(token, day)
            report_reason = "binding_future_hire_boundary"

        self._remember(step, day, token, physical)
        return output, self._report(reason=report_reason, step=step, changed=changed, **observed)
