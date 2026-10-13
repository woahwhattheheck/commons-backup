# SPDX-License-Identifier: Apache-2.0
"""Staged runtime view of the merged submitted-V3.1 B9/H3c adapter.

The historical wrapper calls B9 and then H3c around one parent result.  Current
V5 has newer capacity and market finalizers that need those two submitted
semantics at different boundaries:

* H3c changes unit work, so it must run before capacity projection.
* B9's terminal fertilizer sale partition is a market-order transform, so it
  belongs after the final market-order stage.

That split does not change the submitted activation theorem.  B9 can change an
action only at steps 716, 717, or 718.  H3c can change an action only when
``step % 24 == 23``.  Those domains are disjoint.  This module exposes the two
stages on one stateful object while keeping ``outer_wrappers_current`` as the
single donor/authentication authority.
"""
from __future__ import annotations

from typing import Any

import outer_wrappers_current as current


B9_ACTIVE_STEPS = frozenset(current._B9.COLLECT_STEPS) | frozenset(
    (current._B9.TERMINAL_STEP,)
)
H3C_HOUR = 23
H3C_TURNS_PER_DAY = current._H3C.STANDARD_CONFIG["turnsPerDay"]


def submitted_activation_domains_disjoint() -> bool:
    """Prove the exact submitted B9/H3c mutation domains cannot overlap."""
    return all(step % H3C_TURNS_PER_DAY != H3C_HOUR for step in B9_ACTIVE_STEPS)


if not submitted_activation_domains_disjoint():
    raise RuntimeError("submitted B9/H3c activation domains unexpectedly overlap")


class B9H3CStagedRuntime(current.B9H3CCurrentABI):
    """One stateful adapter exposed at two current-runtime boundaries.

    ``pre_capacity`` is H3c-only and never advances B9 episode state.
    ``post_market`` is B9-only and retains the exact B9 state machine inherited
    from :class:`outer_wrappers_current.B9H3CCurrentABI`.

    Runtime callers should invoke both methods once per completed callback on
    the same object, with any capacity/market finalizers between them.  The
    helper ``transform_staged`` executes them back-to-back and exists only as a
    parity/evidence surface; production composition may place other current-V5
    finalizers between the two stages.
    """

    def pre_capacity(self, observation: Any, configuration: Any, selected: Any):
        before = selected
        action = selected
        if self.goose_rescue:
            action = current._H3C.apply_goose_eod_cap_rescue(
                action, observation, configuration, enabled=True
            )
        return action, {
            "stage": "goose_rescue_pre_capacity",
            "enabled": self.goose_rescue,
            "changed": action != before,
            "reason": (
                "goose_eod_cap_rescue"
                if action != before
                else ("identity" if self.goose_rescue else "disabled")
            ),
        }

    def post_market(self, observation: Any, configuration: Any, selected: Any):
        action, report = self._b9(observation, configuration, selected)
        return action, {
            "stage": "terminal_fertilizer_post_market",
            **report,
        }

    def transform_staged(self, observation: Any, configuration: Any, selected: Any):
        """Execute staged surfaces back-to-back for parity/source contracts."""
        action, h3c_report = self.pre_capacity(observation, configuration, selected)
        action, b9_report = self.post_market(observation, configuration, action)
        return action, {
            "order": (
                "goose_rescue_pre_capacity",
                "terminal_fertilizer_post_market",
            ),
            "h3c": h3c_report,
            "b9": b9_report,
            "changed": action != selected,
            "submitted_domains_disjoint": True,
        }
