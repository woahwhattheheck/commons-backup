# SPDX-License-Identifier: Apache-2.0
"""Retry-safe public surface for the V3.1 fertilizer-hand current-ABI adapter.

The base adapter deliberately caches a same-step candidate decision so repeated
agent calls are deterministic. A refreshed same-step parent view is stronger
authority, though: prices, money, shed stock, selected market rows, remaining
route PLANT intent, or HIRE intent can all invalidate or change the original
admission decision.

This public surface therefore treats the cached HIRE as a convenience only. On
every same-step retry it reruns the *full* admission gate against fresh inputs.
Only a freshly admissible plan may be returned. Any retry that cannot reach and
pass that gate permanently retires the cached HIRE so a later same-step call
cannot resurrect stale economics.

New consumers should import ``FertHandCurrentABI`` from this module.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from fert_hand_current import (
    FertHandCurrentABI as _BaseFertHandCurrentABI,
    _future_hire,
    _identity,
)


class FertHandCurrentABI(_BaseFertHandCurrentABI):
    """Base adapter plus fail-closed full same-step admission revalidation."""

    @staticmethod
    def _retire_cached_hire(state: Any) -> None:
        """Permanently retire a candidate HIRE after refreshed authority fails."""
        state.pending = None
        state.hire_step = None
        state.hire_buy = 0
        state.want = 0
        state.tried = True

    @staticmethod
    def _fresh_retry_state(state: Any) -> Any:
        """Clone durable state while removing only the cached admission plan."""
        fresh = deepcopy(state)
        fresh.pending = None
        fresh.hire_step = None
        fresh.hire_buy = 0
        fresh.want = 0
        fresh.tried = False
        return fresh

    @staticmethod
    def _adopt_revalidated_plan(state: Any, fresh: Any) -> None:
        state.pending = fresh.pending
        state.hire_step = fresh.hire_step
        state.hire_buy = fresh.hire_buy
        state.want = fresh.want
        state.tried = fresh.tried

    def _cached_retry_state(self, observation: Any) -> Any | None:
        """Find a cached candidate HIRE using only exact public player/step IDs."""
        if not isinstance(observation, Mapping):
            return None
        player = observation.get("player")
        step = observation.get("step")
        if type(player) is not int or player not in (0, 1) or type(step) is not int:
            return None
        state = self._states.get(player)
        if state is None or state.hire_step != step:
            return None
        return state

    def transform_selected(
        self,
        observation: Any,
        configuration: Mapping[str, Any] | None,
        selected: Any,
        *,
        future_actions: Any = None,
    ):
        """Never let an early-return retry path preserve a stale cached HIRE."""
        retry_state = self._cached_retry_state(observation)
        result, report = super().transform_selected(
            observation,
            configuration,
            selected,
            future_actions=future_actions,
        )
        if retry_state is None:
            return result, report

        # A cached retry is authoritative only when our _consider_hire override
        # reached and passed the complete fresh admission gate. Every base
        # early-return path (malformed input/config, incomplete route tail,
        # cardinality drift, etc.) must retire the cached plan as well.
        if not (
            isinstance(report, Mapping)
            and report.get("changed") is True
            and report.get("reason") == "reapply_hire_plan"
            and report.get("revalidated_full_admission") is True
        ):
            self._retire_cached_hire(retry_state)
        return result, report

    def _consider_hire(
        self,
        observation: Mapping[str, Any],
        selected: Mapping[str, Any],
        state: Any,
        rest: list[Mapping[str, Any]],
    ):
        parsed = observation.get("step") if isinstance(observation, Mapping) else None
        retry = type(parsed) is int and state.hire_step == parsed
        if not retry:
            return super()._consider_hire(observation, selected, state, rest)

        # Preserve specific collision diagnostics, but do not stop here: HIRE
        # collision is only one way fresh retry authority can invalidate the
        # cached economics.
        market = selected.get("market")
        if not isinstance(market, list):
            self._retire_cached_hire(state)
            return _identity(selected, "malformed_market_retry")
        if any(order and not isinstance(order, list) for order in market):
            self._retire_cached_hire(state)
            return _identity(selected, "malformed_market_retry")
        if any(
            isinstance(order, list) and order and order[0] == "HIRE"
            for order in market
        ):
            self._retire_cached_hire(state)
            return _identity(selected, "parent_hire_collision_retry")
        if _future_hire(rest):
            self._retire_cached_hire(state)
            return _identity(selected, "future_parent_hire_retry")

        # Re-run the base admission theorem from a clone with only the cached
        # candidate plan cleared. This rechecks current money/hires, prices,
        # target + future-PLANT opportunity, fertilizer stock/reservations,
        # market capacity, and all existing shape/economic gates.
        fresh_state = self._fresh_retry_state(state)
        fresh_result, fresh_report = super()._consider_hire(
            observation,
            selected,
            fresh_state,
            rest,
        )
        if not (
            isinstance(fresh_report, Mapping)
            and fresh_report.get("changed") is True
            and fresh_report.get("reason") == "admit_fertilizer_hand"
        ):
            self._retire_cached_hire(state)
            return _identity(
                selected,
                "retry_admission_lost",
                fresh_reason=(
                    fresh_report.get("reason")
                    if isinstance(fresh_report, Mapping)
                    else "malformed_fresh_report"
                ),
            )

        self._adopt_revalidated_plan(state, fresh_state)
        report = dict(fresh_report)
        report["reason"] = "reapply_hire_plan"
        report["revalidated_full_admission"] = True
        return fresh_result, report
