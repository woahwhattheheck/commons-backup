# SPDX-License-Identifier: Apache-2.0
"""R04 lane L3: no-late-sale-advance (port of the peer B10 lane).

Peer mechanism (attribution): ASTRA and GPT-5.6 SOL, commons repo branch
``riot/v3-peer`` (commit 900fe85b9). Their S20-R01 ablation on the canonical
v3 optimizer found that disabling sale advancement at absolute step >= 648
measured +328.60 own and +289.90 margin, 48/48 positive. Their port capped the
optimizer's "now" sale at max(reference_now_qty, minimum_now).

R04-route analog: at absolute step >= NO_LATE_SALE_ADVANCE_STEP (default 648),
the E184 Sale Window layer must NOT pull future tape-planned sales forward
into today's SELL rows. The tape's own late SELL spray rows (e.g. SELL CARROT
1000 zero-fill) are published tape behavior, not advancement, and are NOT
suppressed.

Why the call-site gate: the seam is the E184 ``agent()`` reservation call
site in r04_full_router.py, exactly analogous to r04_sale_fertilizer gating
SALE_EXCLUDED inside E184. Undoing reservations post-hoc in ``v3_agent()``
would corrupt the per-due-step debt bookkeeping (sale_window_debts), so the
reservation call site is the correct seam: when the predicate below is true,
``reserve_sales()`` never runs and no debt is recorded. Debts recorded before
the threshold remain valid and ``subtract_advanced_sales()`` still settles
them at their due steps. With the flag off the condition short-circuits and
behavior is byte-identical to the pre-lane route.

Python standard library only.
"""

from __future__ import annotations

# Default suppression threshold: absolute step, matching the peer lane.
DEFAULT_THRESHOLD = 648

# Telemetry: how many steps were actually suppressed, and the last one.
# Updated by suppressed() on a hit; cleared by reset().
REPORT = {"suppressed_steps": 0, "last": None}


def reset():
    """Clear the suppression telemetry."""
    REPORT["suppressed_steps"] = 0
    REPORT["last"] = None


def suppressed(step, enabled, threshold=DEFAULT_THRESHOLD):
    """Return True when the E184 reservation at ``step`` must be skipped.

    Pure decision logic (plus telemetry recording): the flag off short-circuits
    to False for every step; with the flag on, steps at or above ``threshold``
    suppress the reservation. ``install()`` validates the threshold is
    non-negative, mirroring the sale-horizon validation.
    """
    step = int(step)
    hit = bool(enabled) and step >= int(threshold)
    if hit:
        REPORT["suppressed_steps"] += 1
        REPORT["last"] = step
    return hit
