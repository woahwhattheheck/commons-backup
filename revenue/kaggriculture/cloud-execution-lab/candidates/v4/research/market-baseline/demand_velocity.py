#!/usr/bin/env python3
"""NPC demand-velocity / absorption-headroom oracle for the canonical V4 baseline.

This is a research/admission primitive, not a crop chooser or production cap.
It extends ``market_baseline`` rather than creating a second demand forecaster.
The source-exact Antigravity/Gemini per-shop ratios are useful, but by themselves
omit town-center demand, unlock horizons, replacement-shop variance and timing.

Decision authority: false. Timing authority: false. The legacy full-season
headroom leaves opponent supply unmodeled; the horizon-aligned stress primitive
can debit visible rival standing supply without claiming that supply will be sold.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics

import market_baseline as m

DEFAULT_SEEDS = tuple(range(1, 101))


def _shop_units(shop: str, item: str) -> int:
    products = m.SHOPS[shop]
    if item not in products:
        return 0
    return 2 if len(products) == 1 else 1


def per_shop_instance_velocity() -> dict[str, float]:
    """Expected units drained per shop tick by one uniformly drawn shop instance."""
    n = len(m.SHOPS)
    return {
        item: sum(_shop_units(shop, item) for shop in m.SHOPS) / n
        for item in m.PRODUCTS
    }


def _count_ticks(start_step: int, interval: int) -> int:
    return sum(1 for step in range(start_step, m.ACTION_STEPS) if step % interval == 0)


def unlock_days() -> tuple[int, ...]:
    return tuple(m.SHOP_UNLOCK_INTERVAL * i for i in range(1, m.MAX_SHOP_INSTANCES + 1))


def closed_form_expected_depletion() -> dict[str, float]:
    """Exact expectation over uniform replacement-shop draws for the default horizon.

    Weed RNG affects WHICH shop is chosen for a concrete seed, but ``random.choice``
    remains uniform over the eight sorted shop names. Each unlocked instance keeps
    consuming on every later shop tick, so its horizon depends on unlock day.
    """
    velocity = per_shop_instance_velocity()
    shop_instance_ticks = sum(
        _count_ticks(day * m.TURNS_PER_DAY, m.SHOP_SELL_INTERVAL)
        for day in unlock_days()
    )
    center_ticks = _count_ticks(0, m.CENTER_SELL_INTERVAL)
    return {
        item: velocity[item] * shop_instance_ticks
        + (center_ticks if item in m.TOWN_CENTER_PRODUCTS else 0)
        for item in m.PRODUCTS
    }


def _quantile(values: list[int], q: float) -> float:
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0,1]")
    xs = sorted(values)
    if not xs:
        raise ValueError("empty quantile")
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    if lo == hi:
        return float(xs[lo])
    return float(xs[lo] + (xs[hi] - xs[lo]) * (k - lo))


def _strict_supply(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


def _strict_step(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    if value >= m.ACTION_STEPS:
        raise ValueError(f"{label} must be inside executable callbacks 0..{m.ACTION_STEPS - 1}")
    return value


def _validate_window(start_step: int, end_step: int) -> tuple[int, int]:
    start = _strict_step(start_step, "start_step")
    end = _strict_step(end_step, "end_step")
    if end < start:
        raise ValueError("end_step must be >= start_step")
    return start, end


def _window_absorption_values(
    item: str,
    start_step: int,
    end_step: int,
    seeds: tuple[int, ...],
) -> list[int]:
    if item not in m.PRODUCTS:
        raise ValueError(f"unknown product: {item}")
    start, end = _validate_window(start_step, end_step)
    if not seeds:
        raise ValueError("seeds must be non-empty")
    runs = [m.simulate(int(seed)) for seed in seeds]
    values: list[int] = []
    for run in runs:
        before = (
            m.MARKET_I0
            if start == 0
            else run["steps"][start - 1]["inventory"][item]
        )
        after = run["steps"][end]["inventory"][item]
        values.append(before - after)
    return values


def panel_absorption_window(
    item: str,
    start_step: int,
    end_step: int,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
) -> dict:
    """Passive NPC depletion distribution for one exact inclusive callback window.

    Snapshot custody follows ``market_baseline.simulate`` exactly: each stored step
    reflects town/shop drains applied on that callback. Therefore window depletion
    is inventory immediately before ``start_step`` minus inventory after ``end_step``.
    This prevents a local rival-pressure witness from borrowing full-season NPC
    headroom that lies outside its own evidence horizon.
    """
    start, end = _validate_window(start_step, end_step)
    values = _window_absorption_values(item, start, end, seeds)
    return {
        "item": item,
        "start_step": start,
        "end_step": end,
        "inclusive_callback_count": end - start + 1,
        "seed_count": len(seeds),
        "min": min(values),
        "p10": _quantile(values, 0.10),
        "median": float(statistics.median(values)),
        "mean": statistics.fmean(values),
        "p90": _quantile(values, 0.90),
        "max": max(values),
        "p10_floor_units": int(math.floor(_quantile(values, 0.10))),
        "decision_authority": False,
        "timing_authority": False,
    }


def panel_absorption(seeds: tuple[int, ...] = DEFAULT_SEEDS) -> dict[str, dict]:
    """Final NPC depletion distribution under the existing source-exact baseline."""
    if not seeds:
        raise ValueError("seeds must be non-empty")
    runs = [m.simulate(int(seed)) for seed in seeds]
    out: dict[str, dict] = {}
    for item in m.PRODUCTS:
        values = [m.MARKET_I0 - run["steps"][-1]["inventory"][item] for run in runs]
        threshold = m.MARKET_PARAMS[item]["T"]
        out[item] = {
            "min": min(values),
            "p10": _quantile(values, 0.10),
            "median": float(statistics.median(values)),
            "mean": statistics.fmean(values),
            "p90": _quantile(values, 0.90),
            "max": max(values),
            "p10_floor_units": int(math.floor(_quantile(values, 0.10))),
            "curve": m.MARKET_PARAMS[item]["below_func"],
            "threshold_T": threshold,
            "fraction_reaching_T": sum(v >= threshold for v in values) / len(values),
        }
    return out


def conservative_headroom(
    item: str,
    added_public_supply: int,
    *,
    q: float = 0.10,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
) -> dict:
    """Compare terminal added supply with a low-quantile NPC absorption budget.

    This deliberately does *not* certify profitability or sale timing. Hidden rival
    supply can consume the same headroom, and selling early can depress price before
    later NPC demand arrives. Consumers must therefore treat this as one admission
    input, never as standalone production authority.
    """
    if item not in m.PRODUCTS:
        raise ValueError(f"unknown product: {item}")
    added = _strict_supply(added_public_supply, "added_public_supply")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0,1]")

    runs = [m.simulate(int(seed)) for seed in seeds]
    values = [m.MARKET_I0 - run["steps"][-1]["inventory"][item] for run in runs]
    budget = int(math.floor(_quantile(values, q)))
    return {
        "item": item,
        "added_public_supply": added,
        "panel_quantile": q,
        "npc_absorption_budget_units": budget,
        "disposition": (
            "PANEL_NPC_HEADROOM_NOT_EXCEEDED"
            if added <= budget
            else "PANEL_NPC_HEADROOM_EXCEEDED"
        ),
        "decision_authority": False,
        "timing_authority": False,
        "opponent_supply_accounted": False,
    }


def horizon_public_pressure_headroom(
    item: str,
    added_public_supply: int,
    visible_rival_standing_supply: int,
    *,
    start_step: int,
    end_step: int,
    public_evidence_start_step: int,
    public_evidence_end_step: int,
    q: float = 0.10,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
) -> dict:
    """Stress horizon-aligned NPC headroom with visible rival standing supply.

    ``visible_rival_standing_supply`` is intentionally a conservative public stress
    debit, not a prediction that the rival harvests or sells it. The caller must
    supply the public-evidence window separately, and this function requires that
    custody window to equal the NPC-headroom window exactly. Hidden/private rival
    inventory and newly produced future flow remain outside this primitive.
    """
    if item not in m.PRODUCTS:
        raise ValueError(f"unknown product: {item}")
    added = _strict_supply(added_public_supply, "added_public_supply")
    rival = _strict_supply(
        visible_rival_standing_supply, "visible_rival_standing_supply"
    )
    start, end = _validate_window(start_step, end_step)
    evidence_start, evidence_end = _validate_window(
        public_evidence_start_step, public_evidence_end_step
    )
    if (evidence_start, evidence_end) != (start, end):
        raise ValueError("public rival evidence window must exactly match headroom window")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0,1]")

    values = _window_absorption_values(item, start, end, seeds)
    budget = int(math.floor(_quantile(values, q)))
    residual = max(0, budget - rival)
    public_pressure = added + rival
    fits = public_pressure <= budget
    return {
        "item": item,
        "start_step": start,
        "end_step": end,
        "public_rival_evidence_start_step": evidence_start,
        "public_rival_evidence_end_step": evidence_end,
        "panel_quantile": q,
        "npc_absorption_budget_units": budget,
        "added_public_supply": added,
        "visible_rival_standing_supply_stress_units": rival,
        "public_competing_supply_stress_units": public_pressure,
        "residual_npc_headroom_after_public_rival_stress_units": residual,
        "candidate_added_supply_fits_residual": added <= residual,
        "disposition": (
            "HORIZON_PUBLIC_PRESSURE_HEADROOM_NOT_EXCEEDED"
            if fits
            else "HORIZON_PUBLIC_PRESSURE_HEADROOM_EXCEEDED"
        ),
        "decision_authority": False,
        "timing_authority": False,
        "opponent_public_standing_supply_stress_accounted": True,
        "opponent_private_supply_accounted": False,
        "rival_sale_prediction": False,
        "limitations": [
            "visible rival standing supply is public stress evidence, not a sale prediction",
            "hidden rival inventory and future production are not accounted",
            "the NPC panel is the source-exact passive baseline, not a state-conditioned shop forecast",
            "profitability and sale timing require separate current-native evidence",
        ],
    }


def report(seeds: tuple[int, ...] = DEFAULT_SEEDS) -> dict:
    return {
        "engine_blob_sha": m.ENGINE_BLOB_SHA,
        "spec_blob_sha": m.SPEC_BLOB_SHA,
        "decision_authority": False,
        "per_shop_instance_velocity": per_shop_instance_velocity(),
        "closed_form_expected_depletion": closed_form_expected_depletion(),
        "panel_seed_count": len(seeds),
        "panel_absorption": panel_absorption(seeds),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-count", type=int, default=100)
    args = parser.parse_args()
    if args.seed_count <= 0:
        raise SystemExit("--seed-count must be positive")
    seeds = tuple(range(args.seed_start, args.seed_start + args.seed_count))
    print(json.dumps(report(seeds), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
