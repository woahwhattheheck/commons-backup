# SPDX-License-Identifier: Apache-2.0
"""Exact-slot and retry guard around the additive P02 live overlay."""
from __future__ import annotations

from copy import deepcopy

from land_unlock_runtime import LandUnlockOverlay as _BaseLandUnlockOverlay
from land_unlock_runtime_support import _land_slots, _step


class LandUnlockOverlay(_BaseLandUnlockOverlay):
    """Fail closed when the selected action no longer matches the certificate."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._strict_memo = None

    def reset(self):
        super().reset()
        self._strict_memo = None

    def _remember(self, now, action, result, report):
        self._strict_memo = {
            "step": int(now),
            "input": deepcopy(action),
            "output": deepcopy(result),
            "report": deepcopy(report),
        }
        return result, report

    def _decline(self, now, action, reason, **details):
        self.pending = None
        self.last_step = int(now)
        self._record(now, reason, **details)
        report = {
            "changed": False,
            "reason": reason,
            "mode": self.mode,
            "step": int(now),
            "pending": None,
            **deepcopy(details),
        }
        return self._remember(now, action, action, report)

    def apply(self, agent, observation, configuration, action):
        cfg = dict(configuration or {})
        now = _step(observation, cfg)
        limit = int(cfg.get("maxMarketOrdersPerTurn", 10))

        memo = self._strict_memo
        if memo is not None and int(memo["step"]) == now:
            if action == memo["input"]:
                return deepcopy(memo["output"]), deepcopy(memo["report"])
            pending = self.pending
            if (pending is not None
                    and pending.get("phase") == "defer_scheduled"
                    and now == int(pending["original_step"])):
                slots = _land_slots(action, limit)
                expected = int(pending["original_slot"])
                if slots != [expected]:
                    return self._decline(
                        now, action, "deferral_declined",
                        decline_reason="slot_mismatch",
                        slots=slots, expected_slot=expected)
            return self._decline(now, action, "same_step_action_changed")
        if memo is not None and (now == 0 or now < int(memo["step"])):
            self._strict_memo = None

        pending = self.pending
        if (pending is not None and pending.get("phase") == "confirmed"
                and now == int(pending["original_step"])):
            slots = _land_slots(action, limit)
            expected = int(pending["original_slot"])
            if slots != [expected]:
                return self._decline(
                    now, action, "suppression_declined",
                    decline_reason="slot_mismatch",
                    slots=slots, expected_slot=expected)

        before_pending = deepcopy(self.pending)
        before_events = deepcopy(self.events)
        result, report = super().apply(agent, observation, cfg, action)

        # Base P02 can suppress or defer a unique BUY_LAND without proving that
        # its selected slot is the exact represented route slot.
        if report.get("reason") == "original_suppressed":
            expected = int(before_pending["original_slot"])
            actual = int(report["slot"])
            if actual != expected:
                self.pending = None
                self.events = before_events
                self.last_step = now
                return self._decline(
                    now, action, "suppression_declined",
                    decline_reason="slot_mismatch",
                    slot=actual, expected_slot=expected)

        if report.get("reason") == "original_deferred":
            expected = int(self.pending["original_slot"])
            actual = int(report["slot"])
            if actual != expected:
                self.pending = before_pending
                self.events = before_events
                self.last_step = now
                return self._decline(
                    now, action, "deferral_declined",
                    decline_reason="slot_mismatch",
                    slot=actual, expected_slot=expected)

        return self._remember(now, action, result, report)
