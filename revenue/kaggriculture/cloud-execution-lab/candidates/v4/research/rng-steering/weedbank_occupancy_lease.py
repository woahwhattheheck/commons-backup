# SPDX-License-Identifier: Apache-2.0
"""Source-bound accounting for the Gemini/Antigravity WEEDBANK idea.

This is a research oracle, not a policy. It keeps two source-real baseline
occupancy policies separate instead of mixing their labor and RNG semantics:

* ``leave_first_weed_until_horizon``: once a weed spawns, leave it resident
  through the horizon and optionally clean it afterwards. RNG draws stop at
  the first weed, so the draw count is truncated geometric and there is at
  most one eventual weed-cleanup action.
* ``clear_each_weed_before_next_eod``: DIG every spawned weed before the next
  EOD (with a terminal-horizon weed cleaned afterwards). The tile is empty at
  every EOD, so it consumes one weed RNG draw per EOD and can reweed repeatedly.

A structure lease suppresses those baseline weed draws while present, but the
oracle assigns no positive value to moving the shared RNG cursor. It emits no
runtime admission bit and gives hidden-seed targeting no authority.
"""
from __future__ import annotations

import hashlib
import math

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
STANDARD_WEED_CHANCE = 0.005
STANDARD_EODS = 30

BASELINE_LEAVE_FIRST_WEED = "leave_first_weed_until_horizon"
BASELINE_CLEAR_AND_RENEW = "clear_each_weed_before_next_eod"
BASELINE_POLICIES = frozenset((BASELINE_LEAVE_FIRST_WEED, BASELINE_CLEAR_AND_RENEW))


class WeedbankContractError(ValueError):
    """Input or source evidence is outside the bounded theorem."""


def git_blob_sha1(data: bytes) -> str:
    if not isinstance(data, bytes):
        raise WeedbankContractError("engine data must be bytes")
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def verify_engine_bytes(data: bytes) -> bool:
    """Fail closed unless bytes are the exact pinned official engine."""
    if git_blob_sha1(data) != ENGINE_GIT_BLOB:
        raise WeedbankContractError("official engine Git blob drift")
    text = data.decode("utf-8")
    anchors = (
        'if op == "DIG":',
        "Removes plants, weeds, empty coop/pasture. Does NOT remove a placed animal.",
        'if op == "BUILD_COOP":',
        'farm["tiles"][fy][fx] = {"kind": "COOP"}',
        'if farm["tiles"][y][x] is None and rng.random() < weed_chance:',
    )
    missing = [anchor for anchor in anchors if anchor not in text]
    if missing:
        raise WeedbankContractError("pinned engine is missing WEEDBANK source anchors")
    return True


def _plain_nonnegative_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WeedbankContractError(f"{name} must be a nonnegative plain int")
    return value


def _probability(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeedbankContractError("weed_chance must be a finite number in [0,1]")
    value = float(value)
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise WeedbankContractError("weed_chance must be a finite number in [0,1]")
    return value


def _baseline_policy(value) -> str:
    if not isinstance(value, str) or value not in BASELINE_POLICIES:
        raise WeedbankContractError(
            "baseline_policy must be an explicit supported occupancy policy"
        )
    return value


def weed_spawn_probability(eods: int, weed_chance: float = STANDARD_WEED_CHANCE) -> float:
    """Probability of at least one weed event across ``eods`` eligible EODs."""
    eods = _plain_nonnegative_int(eods, "eods")
    p = _probability(weed_chance)
    return 1.0 - (1.0 - p) ** eods


def expected_baseline_weed_events(
    eods: int,
    weed_chance: float,
    baseline_policy: str,
) -> float:
    """Expected weed events caused by the explicit baseline occupancy policy."""
    eods = _plain_nonnegative_int(eods, "eods")
    p = _probability(weed_chance)
    policy = _baseline_policy(baseline_policy)
    if policy == BASELINE_LEAVE_FIRST_WEED:
        return weed_spawn_probability(eods, p)
    return float(eods) * p


def expected_empty_tile_rng_draws(
    eods: int,
    weed_chance: float,
    baseline_policy: str,
) -> float:
    """Expected weed RNG draws under the explicit baseline occupancy policy."""
    eods = _plain_nonnegative_int(eods, "eods")
    p = _probability(weed_chance)
    policy = _baseline_policy(baseline_policy)
    if policy == BASELINE_CLEAR_AND_RENEW:
        # The policy restores the tile to None before every subsequent EOD.
        return float(eods)
    if eods == 0:
        return 0.0
    if p == 0.0:
        return float(eods)
    # Leave-first policy: a first weed ends later eligibility through horizon.
    return weed_spawn_probability(eods, p) / p


def occupancy_lease_receipt(
    eods: int,
    weed_chance: float = STANDARD_WEED_CHANCE,
    *,
    baseline_policy: str,
    restore_with_dig: bool = True,
) -> dict:
    """Return policy-separated labor/RNG accounting for one structure lease.

    The baseline policy is mandatory because weed cleanup changes future RNG
    eligibility. ``direct_action_delta`` is expected baseline weed-cleanup
    actions minus lease BUILD/restore actions; its sign is evidence for that
    named baseline only, never a global WEEDBANK verdict.
    """
    if not isinstance(restore_with_dig, bool):
        raise WeedbankContractError("restore_with_dig must be bool")
    eods = _plain_nonnegative_int(eods, "eods")
    p = _probability(weed_chance)
    policy = _baseline_policy(baseline_policy)

    weed_probability = weed_spawn_probability(eods, p)
    weed_events = expected_baseline_weed_events(eods, p, policy)
    baseline_rng_draws = expected_empty_tile_rng_draws(eods, p, policy)
    build_actions = 1
    restore_actions = 1 if restore_with_dig else 0
    lease_actions = build_actions + restore_actions
    direct_action_delta = weed_events - lease_actions
    if direct_action_delta > 0.0:
        labor_verdict = "LEASE_DIRECT_LABOR_ADVANTAGE_UNDER_NAMED_BASELINE"
    elif direct_action_delta < 0.0:
        labor_verdict = "BASELINE_DIRECT_LABOR_ADVANTAGE_UNDER_NAMED_BASELINE"
    else:
        labor_verdict = "DIRECT_LABOR_TIE_UNDER_NAMED_BASELINE"

    return {
        "schema": "titan-v4/weedbank-occupancy-lease/v2",
        "source_engine_git_blob": ENGINE_GIT_BLOB,
        "baseline_policy": policy,
        "eods": eods,
        "weed_chance": p,
        "weed_spawn_probability": weed_probability,
        "expected_baseline_weed_events": weed_events,
        "expected_baseline_weed_cleanup_actions": weed_events,
        "expected_baseline_rng_draws": baseline_rng_draws,
        "expected_rng_draws_suppressed": baseline_rng_draws,
        "build_actions": build_actions,
        "restore_actions": restore_actions,
        "lease_actions": lease_actions,
        "direct_action_delta": direct_action_delta,
        "direct_weed_labor_advantage": direct_action_delta > 0.0,
        "direct_labor_verdict": labor_verdict,
        "global_direct_labor_sign_authority": False,
        "rng_decision_authority": False,
        "hidden_seed_targeting_authority": False,
        "runtime_policy_authority": False,
    }
