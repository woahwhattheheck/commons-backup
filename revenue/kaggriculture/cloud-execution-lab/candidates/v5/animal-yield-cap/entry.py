# SPDX-License-Identifier: Apache-2.0
"""Thin V5 treatment entry for canonical V4 ANIMAL-HEADROOM.

The mechanism remains owned by the byte-pinned V4 helper copied beside this
entry by build.py.  This file only composes that helper after the canonical V5
parent has produced its action card.  Control runs use the unmodified parent
package; this module is treatment-only and has no default activation path.
"""
from __future__ import annotations

from copy import deepcopy

import animal_headroom_harvest as headroom
import baseline_main as baseline

_LAST_REPORT = None


def agent(observation, configuration=None):
    """Return canonical V5 action with the exact ANIMAL-HEADROOM transform."""
    global _LAST_REPORT
    cfg = dict(configuration or {})
    # Reuse the parent's public identity binder so the helper sees exactly the
    # same player/clock identity that the canonical runtime consumes.
    canonical = baseline._canonical_entrypoint_observation(observation, cfg)
    returned = baseline.agent(canonical, cfg)
    plan = headroom.plan_animal_headroom_harvest(returned, canonical, cfg)
    _LAST_REPORT = deepcopy(plan)
    # The common no-engagement path must preserve both parent action identity
    # and latency: do not ask the canonical helper to repeat the proof.
    if not plan.get("eligible"):
        return returned
    return headroom.apply_animal_headroom_harvest(
        returned, canonical, cfg, enabled=True
    )


def last_report():
    """Expose engagement evidence without leaking mutable helper state."""
    return deepcopy(_LAST_REPORT)
