#!/usr/bin/env python3
"""Source-bound outer bounds for EGG market elasticity in canonical Kaggriculture.

This is research only.  It deliberately computes *loose* physical outer bounds:
if even impossible best-case EGG production cannot reach the price floor, then a
real strategy cannot do so either.  Likewise, all shop unlocks are pessimistically
assumed to consume EGG when bounding maximum scarcity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
SPEC_GIT_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"

PRICE_FLOOR = 1
EGG_BASE = 50
EGG_I0 = 10_000
EGG_T = 332
EGG_ABOVE_TARGET = 0.20
HINGE_GAIN = 8.0
EGG_BELOW_TARGET = 0.40
EGG_MAX_HELD = 4

# Exact standard configuration / source constants pinned by the blobs above.
AGENTS = 2
BOARD_SIZE = 10
EPISODE_STEPS = 720
TURNS_PER_DAY = 24
SHOP_UNLOCK_INTERVAL_DAYS = 3
SHOP_SELL_INTERVAL_STEPS = 4
CENTER_SELL_INTERVAL_STEPS = 24
MAX_SHOP_INSTANCES = 8


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _shape(func: str, x: float, T: float | None = None) -> float:
    x = max(0.0, x)
    if func == "log":
        return math.log1p(x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    raise ValueError(f"unsupported shape {func!r}")


def egg_price(inventory: int) -> int:
    if type(inventory) is not int or inventory < 0:
        raise ValueError("inventory must be a non-negative exact int")
    if inventory < EGG_I0:
        amp = EGG_BELOW_TARGET * EGG_BASE / _shape("hinge", EGG_T, EGG_T)
        raw = EGG_BASE + amp * _shape("hinge", EGG_I0 - inventory, EGG_T)
    else:
        amp = EGG_ABOVE_TARGET * EGG_BASE / _shape("log", EGG_T, EGG_T)
        raw = EGG_BASE - amp * _shape("log", inventory - EGG_I0, EGG_T)
    return max(PRICE_FLOOR, int(round(raw)))


def first_glut_excess_reaching_floor() -> int:
    """First integer excess over I0 where the exact pricing function returns $1."""
    lo, hi = 0, 1
    while egg_price(EGG_I0 + hi) > PRICE_FLOOR:
        hi *= 2
    while lo < hi:
        mid = (lo + hi) // 2
        if egg_price(EGG_I0 + mid) <= PRICE_FLOOR:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _processed_steps() -> range:
    # Canonical interpreter processes step EPISODE_STEPS-2, then marks DONE.
    return range(0, EPISODE_STEPS - 1)


def max_town_egg_depletion() -> dict[str, Any]:
    processed = list(_processed_steps())
    center_ticks = sum(1 for step in processed if step % CENTER_SELL_INTERVAL_STEPS == 0)
    last_step = processed[-1]

    shop_ticks: list[dict[str, int]] = []
    total_shop = 0
    for instance in range(1, MAX_SHOP_INSTANCES + 1):
        unlock_day = instance * SHOP_UNLOCK_INTERVAL_DAYS
        first_active_step = unlock_day * TURNS_PER_DAY
        if first_active_step > last_step:
            ticks = 0
        else:
            first_tick = first_active_step
            remainder = first_tick % SHOP_SELL_INTERVAL_STEPS
            if remainder:
                first_tick += SHOP_SELL_INTERVAL_STEPS - remainder
            ticks = 0 if first_tick > last_step else ((last_step - first_tick) // SHOP_SELL_INTERVAL_STEPS + 1)
        # BAKERY / BRUNCH_SPOT both consume one EGG per shop tick.  Assume every
        # random unlock is one of those to form a safe maximum-depletion bound.
        total_shop += ticks
        shop_ticks.append({"instance": instance, "unlock_day": unlock_day, "egg_ticks": ticks})

    return {
        "town_center_egg_ticks": center_ticks,
        "max_egg_shop_ticks": total_shop,
        "max_total_egg_depletion": center_ticks + total_shop,
        "shop_instances": shop_ticks,
    }


def standard_episode_bounds() -> dict[str, Any]:
    days = EPISODE_STEPS // TURNS_PER_DAY
    # Deliberately impossible best case: every tile on both farms is treated as
    # a goose for every EOD, and each EOD is allowed to add a full max_held=4.
    # The real engine can only do less: placement/setup/feed/care/harvest/cash
    # constraints and held clipping all reduce production.
    max_generated = AGENTS * BOARD_SIZE * BOARD_SIZE * days * EGG_MAX_HELD
    max_market_inventory = EGG_I0 + max_generated
    glut_price_lower_bound = egg_price(max_market_inventory)

    town = max_town_egg_depletion()
    min_market_inventory = max(0, EGG_I0 - town["max_total_egg_depletion"])
    scarcity_price_upper_bound = egg_price(min_market_inventory)

    return {
        "days": days,
        "max_player_generated_egg_market_increase": max_generated,
        "max_market_inventory_outer_bound": max_market_inventory,
        "glut_price_lower_bound": glut_price_lower_bound,
        "max_town_egg_depletion": town["max_total_egg_depletion"],
        "min_market_inventory_outer_bound": min_market_inventory,
        "scarcity_price_upper_bound": scarcity_price_upper_bound,
        "reachable_price_outer_interval": [glut_price_lower_bound, scarcity_price_upper_bound],
        "town_detail": town,
    }


def receipt() -> dict[str, Any]:
    floor_excess = first_glut_excess_reaching_floor()
    bounds = standard_episode_bounds()
    return {
        "schema": "titan-v4-egg-elasticity-bound/v1",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "spec_git_blob": SPEC_GIT_BLOB,
        "decision_authority": False,
        "runtime_mutation": False,
        "direct_buy_product_egg_supported": False,
        "verdict": "ASYMMETRIC_BUT_FINITE_NO_DIRECT_EGG_SHORT_SQUEEZE",
        "curve": {
            "price_floor": PRICE_FLOOR,
            "first_glut_excess_units_reaching_floor": floor_excess,
            "price_immediately_before_floor": egg_price(EGG_I0 + floor_excess - 1),
            "price_at_floor_threshold": egg_price(EGG_I0 + floor_excess),
            "price_at_plus_332": egg_price(EGG_I0 + 332),
            "price_at_plus_1000": egg_price(EGG_I0 + 1000),
            "price_at_plus_5000": egg_price(EGG_I0 + 5000),
        },
        "standard_episode": bounds,
        "interpretation": [
            "EGG glut is unusually price-resilient, but the logarithmic curve is finite and still reaches the global $1 floor.",
            "Under standard 720-step physical limits, even a deliberately impossible production upper bound cannot push EGG below the reported glut lower bound.",
            "BUY_PRODUCT cannot buy EGG in the pinned engine, so holding self-produced EGG avoids adding supply but does not remove EGG from the market; it is not a direct short squeeze.",
            "Town demand can create EGG scarcity, but even the all-EGG-shop outer bound yields the reported finite scarcity price upper bound.",
            "No optimality, margin, opener, or activation claim follows from these mechanics bounds; goose economics still require opportunity-cost and current-native field evidence.",
        ],
    }


def _find_cloud_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if parent.name == "cloud-execution-lab":
            return parent
    raise ValueError("cannot locate cloud-execution-lab ancestor")


def verify_checkout(source_file: Path | None = None) -> dict[str, str]:
    here = Path(source_file or __file__).resolve()
    cloud = _find_cloud_root(here)
    engine = cloud / "reference" / "engine" / "kaggriculture.py"
    spec = cloud / "reference" / "engine" / "kaggriculture.json"
    got_engine = git_blob_sha1(engine.read_bytes())
    got_spec = git_blob_sha1(spec.read_bytes())
    if got_engine != ENGINE_GIT_BLOB:
        raise ValueError(f"engine Git blob drift: expected {ENGINE_GIT_BLOB}, got {got_engine}")
    if got_spec != SPEC_GIT_BLOB:
        raise ValueError(f"spec Git blob drift: expected {SPEC_GIT_BLOB}, got {got_spec}")
    return {"engine_git_blob": got_engine, "spec_git_blob": got_spec}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-checkout", action="store_true")
    args = parser.parse_args()
    out = receipt()
    if args.verify_checkout:
        out["checkout"] = verify_checkout()
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
