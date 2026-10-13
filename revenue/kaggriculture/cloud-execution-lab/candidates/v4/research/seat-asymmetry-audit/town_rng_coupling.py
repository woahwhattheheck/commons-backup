#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact EOD weed-stream -> town-shop RNG coupling model for TITAN V4 research.

Official Kaggriculture seeds one random.Random per end of day, spends it on
farm-0 weed trials, then farm-1 weed trials, then on the next public shop
unlock. _spawn_weeds draws exactly once for every tile that is empty when the
scan begins. Therefore the shop draw depends on total empty tiles across both
farms, regardless of weedSpawnChance.

Research / causal-integrity oracle only: no gameplay policy or live seed exploit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import random
from pathlib import Path
from typing import Sequence

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
RNG_SEED_MULTIPLIER = 1_000_003
DEFAULT_SHOP_UNLOCK_INTERVAL = 3
DEFAULT_WEED_CHANCE = 0.005
MAX_SHOP_INSTANCES = 8
SHOP_PRODUCTS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
SHOPS = tuple(sorted(SHOP_PRODUCTS))
_DECOUPLED_DOMAIN = 0x53484F50


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def verify_engine_source(path: str | Path) -> str:
    actual = git_blob(Path(path).read_bytes())
    if actual != ENGINE_GIT_BLOB:
        raise ValueError(
            f"engine source drift: expected {ENGINE_GIT_BLOB}, got {actual}"
        )
    return actual


def _nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative exact int")
    return value


def _probability(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{label} must be within [0, 1]")
    return value


def normalize_empty_counts(values: Sequence[int]) -> tuple[int, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("empty_counts must be a non-empty list/tuple")
    return tuple(
        _nonnegative_int(value, f"empty_counts[{i}]")
        for i, value in enumerate(values)
    )


def weed_rng_draw_count(empty_counts: Sequence[int]) -> int:
    """Exact count of rng.random() calls made by all weed scans."""
    return sum(normalize_empty_counts(empty_counts))


def _unlock_due(
    *,
    day: int,
    next_shop_count: int,
    shop_unlock_interval: int,
) -> bool:
    day = _nonnegative_int(day, "day")
    next_shop_count = _nonnegative_int(next_shop_count, "next_shop_count")
    if type(shop_unlock_interval) is not int or shop_unlock_interval <= 0:
        raise ValueError("shop_unlock_interval must be a positive exact int")
    next_day = day + 1
    return (
        next_day % shop_unlock_interval == 0
        and next_shop_count < MAX_SHOP_INSTANCES
    )


def official_shop_projection(
    *,
    seed: int,
    day: int,
    empty_counts: Sequence[int],
    next_shop_count: int = 0,
    shop_unlock_interval: int = DEFAULT_SHOP_UNLOCK_INTERVAL,
) -> str | None:
    """Project the official EOD shop choice from pre-weed empty-tile counts."""
    seed = _nonnegative_int(seed, "seed")
    counts = normalize_empty_counts(empty_counts)
    if not _unlock_due(
        day=day,
        next_shop_count=next_shop_count,
        shop_unlock_interval=shop_unlock_interval,
    ):
        return None
    rng = random.Random((seed * RNG_SEED_MULTIPLIER) ^ day)
    for _ in range(weed_rng_draw_count(counts)):
        rng.random()
    return rng.choice(SHOPS)


def shop_demand_vector(shop: str) -> dict[str, int]:
    """Return one unlocked shop instance's per-shop-interval public demand."""
    if shop not in SHOP_PRODUCTS:
        raise ValueError(f"unknown shop: {shop!r}")
    products = SHOP_PRODUCTS[shop]
    multiplier = 2 if len(products) == 1 else 1
    return {item: multiplier for item in products}


def stream_snapshot(
    *,
    seed: int,
    day: int,
    empty_counts: Sequence[int],
    weed_chance: float = DEFAULT_WEED_CHANCE,
    next_shop_count: int = 0,
    shop_unlock_interval: int = DEFAULT_SHOP_UNLOCK_INTERVAL,
) -> dict:
    """Replay the official EOD RNG consumers, retaining per-seat weed booleans.

    Counts describe currently-empty tiles in scan order, not arbitrary board
    coordinates. Each count consumes exactly that many random draws; changing
    ``weed_chance`` changes placement booleans but never the cursor advance.
    """
    seed = _nonnegative_int(seed, "seed")
    day = _nonnegative_int(day, "day")
    counts = normalize_empty_counts(empty_counts)
    weed_chance = _probability(weed_chance, "weed_chance")
    rng = random.Random((seed * RNG_SEED_MULTIPLIER) ^ day)
    weed_hits: list[list[bool]] = []
    for count in counts:
        seat_hits = []
        for _ in range(count):
            seat_hits.append(rng.random() < weed_chance)
        weed_hits.append(seat_hits)
    shop = (
        rng.choice(SHOPS)
        if _unlock_due(
            day=day,
            next_shop_count=next_shop_count,
            shop_unlock_interval=shop_unlock_interval,
        )
        else None
    )
    return {
        "seed": seed,
        "day": day,
        "empty_counts": list(counts),
        "weed_hits": weed_hits,
        "rng_draws_before_shop": sum(counts),
        "shop": shop,
        "shop_demand": None if shop is None else shop_demand_vector(shop),
    }


def tail_fill_counterfactual(
    *,
    seed: int,
    day: int,
    empty_counts: Sequence[int],
    seat: int,
    weed_chance: float = DEFAULT_WEED_CHANCE,
    next_shop_count: int = 0,
    shop_unlock_interval: int = DEFAULT_SHOP_UNLOCK_INTERVAL,
) -> dict:
    """Occupy one seat's final scan-order currently-empty tile before EOD.

    This state-level intervention is deliberately weaker than a policy claim:
    it says what happens if that exact final empty tile is occupied, not that
    the live controller can reach it cheaply or infer the hidden episode seed.
    """
    if type(seat) is not int or seat < 0:
        raise ValueError("seat must be a non-negative exact int")
    counts = list(normalize_empty_counts(empty_counts))
    if seat >= len(counts):
        raise ValueError("seat is outside empty_counts")
    if counts[seat] == 0:
        raise ValueError("selected seat has no empty tile to fill")

    baseline = stream_snapshot(
        seed=seed,
        day=day,
        empty_counts=counts,
        weed_chance=weed_chance,
        next_shop_count=next_shop_count,
        shop_unlock_interval=shop_unlock_interval,
    )
    variant_counts = list(counts)
    variant_counts[seat] -= 1
    variant = stream_snapshot(
        seed=seed,
        day=day,
        empty_counts=variant_counts,
        weed_chance=weed_chance,
        next_shop_count=next_shop_count,
        shop_unlock_interval=shop_unlock_interval,
    )
    prior_preserved = all(
        baseline["weed_hits"][i] == variant["weed_hits"][i]
        for i in range(seat)
    )
    own_prefix_preserved = (
        baseline["weed_hits"][seat][:-1] == variant["weed_hits"][seat]
    )
    later_changed = [
        i
        for i in range(seat + 1, len(counts))
        if baseline["weed_hits"][i] != variant["weed_hits"][i]
    ]
    return {
        "schema": "titan.v4.town-rng-tail-fill/v1",
        "intervention": "occupy_final_scan_order_empty_tile",
        "seat": seat,
        "baseline": baseline,
        "variant": variant,
        "prior_seat_weeds_preserved": prior_preserved,
        "own_remaining_weeds_preserved": own_prefix_preserved,
        "later_seats_changed": later_changed,
        "shop_changed": baseline["shop"] != variant["shop"],
        "policy_claim": False,
        "economic_claim": False,
        "live_seed_targeting_claim": False,
    }


def decoupled_shop_control(
    *,
    seed: int,
    day: int,
    next_shop_count: int = 0,
    shop_unlock_interval: int = DEFAULT_SHOP_UNLOCK_INTERVAL,
) -> str | None:
    """Counterfactual independent shop RNG, never an official-engine claim."""
    seed = _nonnegative_int(seed, "seed")
    if not _unlock_due(
        day=day,
        next_shop_count=next_shop_count,
        shop_unlock_interval=shop_unlock_interval,
    ):
        return None
    rng = random.Random(
        ((seed * RNG_SEED_MULTIPLIER) ^ day) ^ _DECOUPLED_DOMAIN
    )
    return rng.choice(SHOPS)


def compare_pair(
    *,
    seed: int,
    day: int,
    baseline_empty_counts: Sequence[int],
    candidate_empty_counts: Sequence[int],
    next_shop_count: int = 0,
    shop_unlock_interval: int = DEFAULT_SHOP_UNLOCK_INTERVAL,
) -> dict:
    baseline = normalize_empty_counts(baseline_empty_counts)
    candidate = normalize_empty_counts(candidate_empty_counts)
    base_draws = weed_rng_draw_count(baseline)
    cand_draws = weed_rng_draw_count(candidate)
    base_shop = official_shop_projection(
        seed=seed, day=day, empty_counts=baseline,
        next_shop_count=next_shop_count,
        shop_unlock_interval=shop_unlock_interval,
    )
    cand_shop = official_shop_projection(
        seed=seed, day=day, empty_counts=candidate,
        next_shop_count=next_shop_count,
        shop_unlock_interval=shop_unlock_interval,
    )
    ctl_a = decoupled_shop_control(
        seed=seed, day=day, next_shop_count=next_shop_count,
        shop_unlock_interval=shop_unlock_interval,
    )
    ctl_b = decoupled_shop_control(
        seed=seed, day=day, next_shop_count=next_shop_count,
        shop_unlock_interval=shop_unlock_interval,
    )
    unlock_due = base_shop is not None
    diverged = bool(unlock_due and base_shop != cand_shop)
    return {
        "schema": "titan.v4.town-rng-pair/v1",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "seed": seed,
        "day": day,
        "baseline_empty_counts": list(baseline),
        "candidate_empty_counts": list(candidate),
        "baseline_weed_rng_draws": base_draws,
        "candidate_weed_rng_draws": cand_draws,
        "rng_cursor_shift": cand_draws - base_draws,
        "unlock_due": unlock_due,
        "baseline_shop": base_shop,
        "candidate_shop": cand_shop,
        "shop_diverged": diverged,
        "causal_gate": (
            "ENVIRONMENT_PATH_DIVERGED"
            if diverged else "NO_SHOP_DIVERGENCE_ON_THIS_CELL"
        ),
        "decoupled_control_baseline_shop": ctl_a,
        "decoupled_control_candidate_shop": ctl_b,
        "decoupled_control_equal": ctl_a == ctl_b,
        "weed_chance_affects_cursor": False,
        "policy_claim": False,
        "economic_claim": False,
        "live_seed_targeting_claim": False,
    }


def find_coupling_witness(
    *,
    day: int = 2,
    baseline_total_empty: int = 40,
    delta: int = 1,
    seed_limit: int = 10_000,
) -> dict:
    day = _nonnegative_int(day, "day")
    baseline_total_empty = _nonnegative_int(
        baseline_total_empty, "baseline_total_empty"
    )
    seed_limit = _nonnegative_int(seed_limit, "seed_limit")
    if type(delta) is not int or delta == 0:
        raise ValueError("delta must be a non-zero exact int")
    candidate_total = baseline_total_empty + delta
    if candidate_total < 0:
        raise ValueError("candidate total empties must be non-negative")
    for seed in range(seed_limit):
        base_shop = official_shop_projection(
            seed=seed, day=day, empty_counts=[baseline_total_empty]
        )
        cand_shop = official_shop_projection(
            seed=seed, day=day, empty_counts=[candidate_total]
        )
        if base_shop is not None and base_shop != cand_shop:
            return {
                "seed": seed,
                "day": day,
                "baseline_total_empty": baseline_total_empty,
                "candidate_total_empty": candidate_total,
                "baseline_shop": base_shop,
                "candidate_shop": cand_shop,
            }
    raise ValueError("no coupling witness found in requested seed range")


def fixed_tail_fill_panel(
    *,
    seed_start: int = 1,
    seed_count: int = 256,
    days: Sequence[int] = (2, 5, 8, 11, 14, 17, 20, 23),
    empty_counts: Sequence[int] = (25, 25),
    seat: int = 1,
    weed_chance: float = DEFAULT_WEED_CHANCE,
) -> dict:
    """Deterministic constructed census of one-draw tail-fill shop flips."""
    seed_start = _nonnegative_int(seed_start, "seed_start")
    seed_count = _nonnegative_int(seed_count, "seed_count")
    if seed_count == 0:
        raise ValueError("seed_count must be positive")
    checked_days = tuple(_nonnegative_int(day, "day") for day in days)
    if not checked_days:
        raise ValueError("days must be non-empty")
    counts = normalize_empty_counts(empty_counts)
    if type(seat) is not int or seat < 0 or seat >= len(counts):
        raise ValueError("seat is outside empty_counts")
    if counts[seat] == 0:
        raise ValueError("selected seat has no empty tile to fill")
    weed_chance = _probability(weed_chance, "weed_chance")

    cells = 0
    flips = 0
    per_day: dict[str, dict[str, int]] = {}
    transitions: Counter[tuple[str | None, str | None]] = Counter()
    first_witness = None
    later_seat_weed_changes = 0

    for day in checked_days:
        day_cells = 0
        day_flips = 0
        for seed in range(seed_start, seed_start + seed_count):
            cf = tail_fill_counterfactual(
                seed=seed,
                day=day,
                empty_counts=counts,
                seat=seat,
                weed_chance=weed_chance,
            )
            before = cf["baseline"]["shop"]
            after = cf["variant"]["shop"]
            transitions[(before, after)] += 1
            cells += 1
            day_cells += 1
            if cf["later_seats_changed"]:
                later_seat_weed_changes += 1
            if before != after:
                flips += 1
                day_flips += 1
                if first_witness is None:
                    first_witness = {
                        "seed": seed,
                        "day": day,
                        "baseline_shop": before,
                        "variant_shop": after,
                        "baseline_demand": cf["baseline"]["shop_demand"],
                        "variant_demand": cf["variant"]["shop_demand"],
                        "prior_seat_weeds_preserved":
                            cf["prior_seat_weeds_preserved"],
                        "own_remaining_weeds_preserved":
                            cf["own_remaining_weeds_preserved"],
                    }
        per_day[str(day)] = {"cells": day_cells, "shop_flips": day_flips}

    return {
        "schema": "titan.v4.town-rng-tail-fill-panel/v1",
        "seed_start": seed_start,
        "seed_count": seed_count,
        "days": list(checked_days),
        "baseline_empty_counts": list(counts),
        "intervention_seat": seat,
        "variant_empty_counts": [
            value - (1 if i == seat else 0)
            for i, value in enumerate(counts)
        ],
        "weed_chance": weed_chance,
        "cells": cells,
        "shop_flips": flips,
        "shop_unchanged": cells - flips,
        "later_seat_weed_changes": later_seat_weed_changes,
        "per_day": per_day,
        "first_shop_flip_witness": first_witness,
        "transition_counts": [
            {"baseline": before, "variant": after, "count": count}
            for (before, after), count in sorted(
                transitions.items(),
                key=lambda item: (str(item[0][0]), str(item[0][1])),
            )
        ],
        "interpretation": {
            "mechanism_frequency_only": True,
            "field_ev": "NOT_ASSESSED",
            "policy_reachability": "NOT_ASSESSED",
            "promotion_decision": "NOT_ASSESSED",
        },
    }


def run_probe() -> dict:
    equal_total = compare_pair(
        seed=1, day=2,
        baseline_empty_counts=[13, 27],
        candidate_empty_counts=[27, 13],
    )
    changed_total = compare_pair(
        seed=1, day=2,
        baseline_empty_counts=[20, 20],
        candidate_empty_counts=[20, 21],
    )
    tail_fill = tail_fill_counterfactual(
        seed=5, day=2, empty_counts=[25, 25], seat=1
    )
    panel = fixed_tail_fill_panel()
    return {
        "schema": "titan.v4.town-rng-coupling/v2",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "mechanism": (
            "shared EOD RNG is consumed by per-empty-tile weed trials for both "
            "farms before the public shop choice"
        ),
        "equal_total_seat_swap_control": equal_total,
        "changed_total_witness": changed_total,
        "tail_fill_witness": tail_fill,
        "fixed_tail_fill_panel": panel,
        "first_search_witness": find_coupling_witness(
            day=2, baseline_total_empty=40, delta=1, seed_limit=100
        ),
        "gate_rule": (
            "For paired policy/economic gates, compare town.unlocked_shops at "
            "every EOD before attributing downstream market/margin divergence "
            "to the candidate. First shop divergence means the pair has entered "
            "different public environment paths; report separately or rerun "
            "with a controlled shop schedule."
        ),
        "weed_spawn_chance_zero_removes_coupling": False,
        "source_claim": True,
        "policy_claim": False,
        "economic_claim": False,
        "live_seed_targeting_claim": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verify_engine_source(args.engine)
    text = json.dumps(run_probe(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
