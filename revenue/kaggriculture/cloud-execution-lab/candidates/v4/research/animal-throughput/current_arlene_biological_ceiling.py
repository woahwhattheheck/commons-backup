#!/usr/bin/env python3
"""Tighten current Arlene's authored FERT ceiling with animal biology.

Research-only and policy-inert. The companion current_arlene_census.py proves the
current route bank and scheduled COLLECT_FERTILIZER rows. This module intersects
that worker-slot ceiling with the official engine's animal-EOD generation ceiling.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import current_arlene_census as base

EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
EXECUTED_DECISION_STEPS = 719
TURNS_PER_DAY = 24
ANIMALS = base.ANIMALS
HERE = Path(__file__).resolve()
V4_ROOT = HERE.parents[2]
ENGINE_PATH = V4_ROOT.parent.parent / "reference" / "engine" / "kaggriculture.py"


class BiologicalCeilingError(RuntimeError):
    pass


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def verify_engine_source(path: Path = ENGINE_PATH) -> dict[str, Any]:
    actual = git_blob_sha(path)
    if actual != EXPECTED_ENGINE_BLOB:
        raise BiologicalCeilingError(
            f"official engine drift: expected {EXPECTED_ENGINE_BLOB}, got {actual}"
        )
    source = path.read_text(encoding="utf-8")
    markers = (
        '"fertilizer_available": False',
        'if tile["consecutive_unfed"] >= 2:',
        'tile["fertilizer_available"] = True',
        'if (step + 1) % turns_per_day == 0:',
        '_end_of_day(state, env, day)',
        '_process_market(state, env)',
    )
    missing = [marker for marker in markers if marker not in source]
    if missing:
        raise BiologicalCeilingError(
            f"official animal/EOD semantics drifted: missing {missing!r}"
        )
    # Animal PLACE executes during the unit phase; BUY_ANIMAL arrives later in the
    # same turn's market phase. A same-step purchase therefore cannot fund PLACE.
    unit_marker = '_apply_unit_action(obs0.farms[i], s.observation.private, 0, _allowed(farmer_action),'
    market_marker = '_process_market(state, env)'
    unit_at = source.find(unit_marker)
    market_at = source.find(market_marker, unit_at + 1)
    if unit_at < 0 or market_at < 0 or unit_at >= market_at:
        raise BiologicalCeilingError("unit-before-market interpreter ordering drifted")
    return {
        "engine_blob": actual,
        "executed_decision_steps": EXECUTED_DECISION_STEPS,
        "turns_per_day": TURNS_PER_DAY,
    }


def _eod_steps(horizon: int, turns_per_day: int) -> list[int]:
    if horizon < 0:
        raise ValueError("horizon must be nonnegative")
    if turns_per_day <= 0:
        raise ValueError("turns_per_day must be positive")
    return list(range(turns_per_day - 1, horizon, turns_per_day))


def optimistic_biological_ceiling(
    route: Iterable[Mapping[str, Any]],
    *,
    max_orders: int = base.EXPECTED_MAX_ORDERS,
    horizon: int = EXECUTED_DECISION_STEPS,
    turns_per_day: int = TURNS_PER_DAY,
) -> dict[str, Any]:
    """Return a strict optimistic FERT bound for one authored route.

    Assumptions intentionally favor the route: every executable BUY_ANIMAL succeeds,
    every matchable later PLACE succeeds, and every placed animal survives forever.
    The source-pinned engine starts a new animal with fertilizer unavailable and only
    surviving EOD refresh makes one unit available. Each purchase unit is matched to
    at most one strictly-later PLACE row of the same species because market processing
    follows unit actions within a turn.
    """
    if max_orders <= 0:
        raise ValueError("max_orders must be positive")
    route_rows = list(route)
    limit = min(horizon, len(route_rows))
    eods = _eod_steps(limit, turns_per_day)

    available: Counter[str] = Counter()
    bought: Counter[str] = Counter()
    matched: Counter[str] = Counter()
    unmatched_places: Counter[str] = Counter()
    placement_steps: list[tuple[int, str]] = []
    collect_slots = 0

    for step, action in enumerate(route_rows[:limit]):
        if not isinstance(action, Mapping):
            raise BiologicalCeilingError(f"step {step} is not an action mapping")

        # Official interpreter executes all unit actions before the market phase.
        for row in base._worker_rows(action):
            op = str(row[0])
            if op == "COLLECT_FERTILIZER":
                collect_slots += 1
            if op != "PLACE" or len(row) < 2 or str(row[1]) not in ANIMALS:
                continue
            animal = str(row[1])
            if available[animal] > 0:
                available[animal] -= 1
                matched[animal] += 1
                placement_steps.append((step, animal))
            else:
                unmatched_places[animal] += 1

        for row in base._market_rows(action, max_orders):
            if str(row[0]) != "BUY_ANIMAL" or len(row) < 2 or str(row[1]) not in ANIMALS:
                continue
            animal = str(row[1])
            quantity = base._quantity(row)
            available[animal] += quantity
            bought[animal] += quantity

    refreshes_by_species: Counter[str] = Counter()
    refreshes_by_placement: list[dict[str, int | str]] = []
    for step, animal in placement_steps:
        # PLACE is in the unit phase, so a placement on an EOD step is present when
        # _daily_refresh_animals executes later in that same interpreter call.
        refreshes = sum(eod >= step for eod in eods)
        refreshes_by_species[animal] += refreshes
        refreshes_by_placement.append(
            {"step": step, "animal": animal, "optimistic_eod_refreshes": refreshes}
        )

    biological = sum(refreshes_by_species.values())
    joint = min(collect_slots, biological)
    return {
        "execution_horizon_steps": limit,
        "eod_steps": eods,
        "animal_buy_units": {animal: bought[animal] for animal in ANIMALS},
        "optimistic_matched_placements": {animal: matched[animal] for animal in ANIMALS},
        "optimistic_unmatched_place_rows": {
            animal: unmatched_places[animal] for animal in ANIMALS
        },
        "optimistic_unused_bought_animals": {
            animal: available[animal] for animal in ANIMALS
        },
        "optimistic_animal_eod_refreshes_by_species": {
            animal: refreshes_by_species[animal] for animal in ANIMALS
        },
        "optimistic_animal_eod_refreshes": biological,
        "scheduled_collect_slots": collect_slots,
        "fertilizer_units_optimistic_joint_upper_bound": joint,
        "biological_refresh_headroom_above_joint_bound": biological - joint,
        "scheduled_collect_headroom_above_joint_bound": collect_slots - joint,
        "placement_refresh_detail": refreshes_by_placement,
    }


def build_report(
    routes: Mapping[str, list[dict[str, Any]]],
    *,
    max_orders: int,
    source_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not routes:
        raise BiologicalCeilingError("route bank is empty")
    rows = []
    for route_id in sorted(routes):
        row = optimistic_biological_ceiling(routes[route_id], max_orders=max_orders)
        row["route_id"] = route_id
        rows.append(row)
    biological = [row["optimistic_animal_eod_refreshes"] for row in rows]
    collect = [row["scheduled_collect_slots"] for row in rows]
    joint = [row["fertilizer_units_optimistic_joint_upper_bound"] for row in rows]
    return {
        "schema": "titan-v4-herdscale-biological-fertilizer-ceiling-v1",
        "policy_inert": True,
        "decision_authority": False,
        "surface": "current_frozen_arlene_plus_official_engine_biology",
        "source_receipt": dict(source_receipt or {}),
        "truth_boundary": (
            "This is an optimistic authored-route upper bound, not realized production or EV. "
            "It assumes every executable animal purchase and matchable later placement succeeds "
            "and that every placed animal survives forever. Real escapes/no-ops can only lower it."
        ),
        "summary": {
            "routes": len(rows),
            "min_biological_eod_refresh_ceiling": min(biological),
            "max_biological_eod_refresh_ceiling": max(biological),
            "min_scheduled_collect_ceiling": min(collect),
            "max_scheduled_collect_ceiling": max(collect),
            "min_joint_fertilizer_ceiling": min(joint),
            "max_joint_fertilizer_ceiling": max(joint),
        },
        "routes": rows,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    engine_receipt = verify_engine_source()
    routes, max_orders, arlene_receipt = base.load_current_routes()
    receipt = {**arlene_receipt, **engine_receipt}
    result = build_report(routes, max_orders=max_orders, source_receipt=receipt)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
