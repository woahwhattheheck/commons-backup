# SPDX-License-Identifier: Apache-2.0
"""Caller-tape earlier-day frontier for the Gemini/Antigravity STARVE_SKIP seam.

The canonical FASTING helper deliberately admits FEED suppression only at hour
23, where it is source-certain that no later same-day CARE can be authored.  A
current-native census found that surface cold.  This research-only successor
asks a narrower question: if a *complete supplied remainder of the same day*
contains no later FEED or CARE at the animal, can the same source theorem be
evaluated earlier in the day?

This module never predicts a future action and never authenticates a trace.  It
shape-validates an explicit caller-supplied sequence of later observation/action
pairs through hour 23.  The existing FASTING helper remains the mechanical
eligibility authority: a synthetic hour-23 view of the same current state is used
only to reuse its animal, pending-CARE, escape, physical-WHEAT and malformed-state
guards.  A local semantic-FEED occupancy check additionally rejects a current
same-site extended FEED that the older exact-row FASTING helper could miss.

The output proves only "no blocker in this supplied tape."  It is not current-
native reachability evidence until an external replay/receipt owner binds the
current state, suffix bytes and interpreter/source identity.  Research/
counterfactual only; no runtime/default/feature key or activation claim.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import uncared_eod_feed_skip as fasting

SCHEMA = "titan.v4.starve-suffix-no-care/v1"
BLOCKED_OPS = {"FEED", "CARE"}


def _step(observation: Any) -> int | None:
    if not isinstance(observation, dict):
        return None
    value = observation.get("step")
    return value if type(value) is int and 0 <= value <= 718 else None


def _player(observation: Any) -> int | None:
    if not isinstance(observation, dict):
        return None
    value = observation.get("player")
    return value if type(value) is int and value in (0, 1) else None


def _positions_rows(action: Any, observation: Any):
    """Return (position,row) pairs for the acting player's units, fail closed."""
    player = _player(observation)
    if player is None or not isinstance(action, dict):
        return None
    farms = observation.get("farms")
    if not isinstance(farms, list) or len(farms) != 2 or not isinstance(farms[player], dict):
        return None
    farm = farms[player]
    hands = farm.get("hands")
    hand_rows = action.get("hands")
    if not isinstance(hands, list) or not isinstance(hand_rows, list) or len(hands) != len(hand_rows):
        return None
    positions = [farm.get("farmer"), *hands]
    rows = [action.get("farmer"), *hand_rows]
    out = []
    for position, row in zip(positions, rows):
        pos = fasting._position(position)
        if pos is None or not isinstance(row, list) or not row or type(row[0]) is not str:
            return None
        out.append((pos, row))
    return out


def _one_current_semantic_feed(action: Any, observation: Any, site: tuple[int, int]) -> bool:
    """Require exactly one engine-semantic FEED at the candidate site now.

    Official unit dispatch uses ``row[0]``.  This local guard prevents an older
    exact-row FASTING helper from treating ``['FEED','extra']`` as inert while a
    second exact FEED at the same site is selected for suppression.
    """
    pairs = _positions_rows(action, observation)
    if pairs is None:
        return False
    feeds = [row for position, row in pairs if position == site and row[0] == "FEED"]
    return len(feeds) == 1 and feeds[0] == ["FEED"]


def _remaining_day_certificate(
    *,
    current_step: int,
    player: int,
    site: tuple[int, int],
    suffix: Any,
) -> dict | None:
    """Shape-validate a gapless supplied action suffix through this day's EOD."""
    eod_step = (current_step // 24) * 24 + 23
    if not isinstance(suffix, list) or len(suffix) != eod_step - current_step:
        return None
    blocked_rows = []
    for expected_step, record in enumerate(suffix, start=current_step + 1):
        if not isinstance(record, dict) or set(record) != {"observation", "action"}:
            return None
        observation = record["observation"]
        action = record["action"]
        if _step(observation) != expected_step or _player(observation) != player:
            return None
        if expected_step // 24 != current_step // 24:
            return None
        pairs = _positions_rows(action, observation)
        if pairs is None:
            return None
        for position, row in pairs:
            if position == site and row[0] in BLOCKED_OPS:
                blocked_rows.append({"step": expected_step, "op": row[0]})
    if blocked_rows:
        return None
    return {
        "suffix_start_step": current_step + 1,
        "suffix_end_step": eod_step,
        "suffix_rows": len(suffix),
        "same_site_future_feed_rows": 0,
        "same_site_future_care_rows": 0,
        "provenance": "CALLER_SUPPLIED_UNVERIFIED_TAPE",
        "authenticated_trace_claim": False,
    }


def plan_trace_no_care_feed_skip(
    current_action: Any,
    current_observation: Any,
    configuration: Any,
    remaining_day_suffix: Any,
) -> list[dict]:
    """Return earlier-day candidates conditional on a complete supplied suffix.

    Hour 23 intentionally returns no candidates: the existing FASTING helper owns
    that surface directly.  For earlier hours, we reuse FASTING's current
    mechanical guards by changing only the *step label* of a deep-copied current
    observation to this day's hour 23.  No state field used by those guards is
    changed, and the day number is preserved.
    """
    current_step = _step(current_observation)
    player = _player(current_observation)
    if current_step is None or player is None or current_step % 24 == 23:
        return []
    synthetic_step = (current_step // 24) * 24 + 23
    # FASTING rejects step 719, so the final partial frontier remains closed.
    if synthetic_step > 718:
        return []
    synthetic_observation = deepcopy(current_observation)
    synthetic_observation["step"] = synthetic_step
    mechanical = fasting.plan_uncared_eod_feed_skip(
        current_action, synthetic_observation, configuration
    )
    out = []
    for candidate in mechanical:
        site_value = candidate.get("site")
        if (not isinstance(site_value, list) or len(site_value) != 2
                or any(type(v) is not int for v in site_value)):
            continue
        site = (site_value[0], site_value[1])
        if not _one_current_semantic_feed(current_action, current_observation, site):
            continue
        suffix_cert = _remaining_day_certificate(
            current_step=current_step,
            player=player,
            site=site,
            suffix=remaining_day_suffix,
        )
        if suffix_cert is None:
            continue
        accepted = dict(candidate)
        accepted.update({
            "schema": SCHEMA,
            "current_step": current_step,
            "current_hour": current_step % 24,
            "synthetic_fast_gate_step": synthetic_step,
            "remaining_day_certificate": suffix_cert,
            "fixed_tape_only": True,
            "caller_supplied_tape_only": True,
            "authenticated_trace_claim": False,
            "current_native_reachability_claim": False,
            "runtime_prediction": False,
            "policy_claim": False,
            "activation_claim": False,
        })
        out.append(accepted)
    return out


def build_single_counterfactual(
    current_action: Any,
    current_observation: Any,
    configuration: Any,
    remaining_day_suffix: Any,
    *,
    candidate_index: int = 0,
    enabled: bool = False,
):
    """Rewrite one conditional current FEED to PASS for external replay only."""
    if enabled is not True:
        return current_action
    if type(candidate_index) is not int or candidate_index < 0:
        return current_action
    candidates = plan_trace_no_care_feed_skip(
        current_action,
        current_observation,
        configuration,
        remaining_day_suffix,
    )
    if candidate_index >= len(candidates):
        return current_action
    selected = candidates[candidate_index]
    actor = selected.get("actor")
    result = deepcopy(current_action)
    if actor == 0:
        if result.get("farmer") != ["FEED"]:
            return current_action
        result["farmer"] = ["PASS"]
        return result
    if type(actor) is int and actor > 0:
        hands = result.get("hands")
        if (isinstance(hands, list) and actor - 1 < len(hands)
                and hands[actor - 1] == ["FEED"]):
            hands[actor - 1] = ["PASS"]
            return result
    return current_action
