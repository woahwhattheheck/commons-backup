# SPDX-License-Identifier: Apache-2.0
"""Recovery-safe live adapter for the P02 land-unlock timing certificate."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from land_unlock_runtime_support import (
    LandUnlockOverlaySupport,
    _land_slots,
    _market_limit,
    _remove_unique_land,
    _step,
    _unlocked_count,
)


class LandUnlockOverlay(LandUnlockOverlaySupport):
    """Apply one P02-certified timing move with observation-bound receipts."""

    def apply(self, agent, observation, configuration, action):
        """Return ``(action, report)`` without invoking or replacing a producer."""
        cfg = dict(configuration or {})
        now = _step(observation, cfg)
        limit = _market_limit(cfg)
        route_id, route = self._route(agent)
        report = {"changed": False, "reason": "no_change", "mode": self.mode,
                  "step": now, "pending": deepcopy(self.pending)}

        # A repeated callback at step zero is still the same engine step.  A
        # true new match is observable here as either first use or a backward
        # step transition; resetting on every ``now == 0`` would erase the
        # pending receipt before the same-step replay path below can use it.
        if self.last_step is None or now < self.last_step:
            had_state = self.pending is not None or self.last_step is not None
            self.pending = None
            self.events = []
            if had_state:
                self._record(now, "match_reset")
        same_step = self.last_step == now
        self.last_step = now

        if route_id is None:
            self.pending = None
            report["reason"] = "no_route"
            return action, report

        if self.pending is not None and self.pending["route_id"] != route_id:
            self._record(now, "route_changed", previous=self.pending["route_id"], current=route_id)
            self.pending = None
            report["reason"] = "route_changed"
            report["pending"] = None
            return action, report

        # A repeated call for the same engine step must reproduce the exact move.
        if same_step:
            repeated = self._repeat_pending_action(action, now, limit)
            if repeated is not None:
                result, reason, slot = repeated
                report.update(changed=True, reason=reason, slot=slot,
                              pending=deepcopy(self.pending))
                return result, report

        unlocked = _unlocked_count(observation)
        pending = self.pending
        if pending is not None and pending["phase"] == "await_fill" and now > pending["emitted_step"]:
            delta = unlocked - int(pending["baseline_unlocked"])
            if delta == 1:
                self._record(now, "fill_confirmed", move=pending["move"],
                             emitted_step=pending["emitted_step"],
                             original_step=pending["original_step"])
                if pending["move"] == "advance":
                    pending["phase"] = "confirmed"
                    pending["confirmed_step"] = now
                else:
                    self.pending = None
                    report.update(reason="deferred_fill_confirmed", pending=None)
                    return action, report
            else:
                self._record(now, "fill_not_confirmed", move=pending["move"],
                             delta=delta, emitted_step=pending["emitted_step"])
                self.pending = None
                report.update(reason="fill_not_confirmed", pending=None)
                return action, report

        pending = self.pending
        if pending is not None and pending["phase"] == "confirmed":
            original = int(pending["original_step"])
            if now < original:
                report.update(reason="await_original_suppression", pending=deepcopy(pending))
                return action, report
            if now == original:
                result, slots = _remove_unique_land(action, limit)
                if (result is not None and unlocked == int(pending["baseline_unlocked"]) + 1):
                    self._record(now, "original_suppressed", slot=slots[0],
                                 emitted_step=pending["emitted_step"])
                    self.pending = None
                    report.update(changed=True, reason="original_suppressed", slot=slots[0],
                                  pending=None)
                    return result, report
                self._record(now, "suppression_declined", slots=slots, unlocked=unlocked)
            self.pending = None
            report.update(reason="suppression_declined", pending=None)
            return action, report

        pending = self.pending
        if pending is not None and pending["phase"] == "defer_scheduled":
            target = int(pending["target_step"])
            if now < target:
                report.update(reason="await_deferred_step", pending=deepcopy(pending))
                return action, report
            if now > target:
                self._record(now, "deferred_step_missed", target_step=target)
                self.pending = None
                report.update(reason="deferred_step_missed", pending=None)
                return action, report
            if getattr(agent, "diagnostics", {}).get("status") != "completed":
                self._record(now, "deferred_step_unavailable", status=getattr(agent, "diagnostics", {}).get("status"))
                self.pending = None
                report.update(reason="deferred_step_unavailable", pending=None)
                return action, report
            if unlocked != int(pending["baseline_unlocked"]):
                self._record(now, "deferred_state_changed", unlocked=unlocked)
                self.pending = None
                report.update(reason="deferred_state_changed", pending=None)
                return action, report
            candidate, slot, certificate_report = self._certify_insertion(
                observation, cfg, route, action, now,
                pending["original_step"], pending["original_slot"])
            if candidate is None:
                self._record(now, "deferred_recertification_failed",
                             certificate_reason=certificate_report.get("reason"))
                self.pending = None
                report.update(reason="deferred_recertification_failed",
                              certificate=certificate_report, pending=None)
                return action, report
            pending.update(phase="await_fill", move="defer", emitted_step=now,
                           emitted_slot=slot)
            self._record(now, "deferred_inserted", slot=slot,
                         original_step=pending["original_step"])
            report.update(changed=True, reason="deferred_inserted", slot=slot,
                          certificate=certificate_report, pending=deepcopy(pending))
            return candidate, report

        guard = self._base_guard(agent)
        if guard is not None:
            report["reason"] = guard
            return action, report
        if getattr(agent, "diagnostics", {}).get("status") != "completed":
            report["reason"] = "producer_not_completed"
            return action, report
        # The P02 helper can see four days, but no timing move can exceed max_shift.
        # Avoid invoking it on the hundreds of turns with no nearby purchase.
        nearby = False
        for step in range(now, min(len(route), now + self.max_shift + 1)):
            row = route[step]
            if isinstance(row, Mapping) and _land_slots(row, limit):
                nearby = True
                break
        if not nearby:
            report["reason"] = "no_nearby_land_purchase"
            return action, report

        certificate, certificate_report = self._analyze(
            observation, cfg, route, action, now)
        report["certificate"] = certificate_report
        if certificate is None:
            report["reason"] = certificate_report.get("reason", "not_certified")
            return action, report
        if self._crosses_decision(now, certificate):
            report["reason"] = "route_decision_barrier"
            return action, report
        original = int(certificate.original_step)
        target = int(certificate.recommended_step)
        if target == original:
            report["reason"] = "already_at_certified_step"
            return action, report
        if target < original:
            if target != now:
                report["reason"] = "await_advance_step"
                return action, report
            candidate, slot, recertification = self._certify_insertion(
                observation, cfg, route, action, now, original,
                int(certificate.original_slot))
            if candidate is None:
                report.update(reason="advance_recertification_failed",
                              recertification=recertification)
                return action, report
            self.pending = {
                "phase": "await_fill", "move": "advance", "route_id": route_id,
                "baseline_unlocked": unlocked, "original_step": original,
                "original_slot": int(certificate.original_slot),
                "target_step": target, "emitted_step": now, "emitted_slot": slot,
                "quadrant": certificate.quadrant, "land_cost": int(certificate.land_cost),
            }
            self._record(now, "advance_inserted", slot=slot, original_step=original,
                         quadrant=certificate.quadrant)
            report.update(changed=True, reason="advance_inserted", slot=slot,
                          recertification=recertification,
                          pending=deepcopy(self.pending))
            return candidate, report

        if self.mode != "both":
            report["reason"] = "deferral_disabled"
            return action, report
        if original != now:
            report["reason"] = "await_original_for_deferral"
            return action, report
        result, slots = _remove_unique_land(action, limit)
        if result is None:
            report.update(reason="represented_land_not_unique_in_selected", slots=slots)
            return action, report
        self.pending = {
            "phase": "defer_scheduled", "move": "defer", "route_id": route_id,
            "baseline_unlocked": unlocked, "original_step": original,
            "original_slot": int(certificate.original_slot), "target_step": target,
            "quadrant": certificate.quadrant, "land_cost": int(certificate.land_cost),
        }
        self._record(now, "original_deferred", selected_slot=slots[0], target_step=target,
                     quadrant=certificate.quadrant)
        report.update(changed=True, reason="original_deferred", slot=slots[0],
                      pending=deepcopy(self.pending))
        return result, report
