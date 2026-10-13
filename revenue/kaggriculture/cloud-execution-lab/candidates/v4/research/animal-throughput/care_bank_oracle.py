#!/usr/bin/env python3
"""Source-bound CARE-bank semantics and authored-cadence census for TITAN V4.

Research-only.  The official engine keeps CARE as a delayed animal-production
bonus: an EOD production event consumes the *previous* pending CARE bank before
that day's CARE can add a new unit for a later cycle.  This module models that
state transition exactly, exposes clipping/erasure accounting, and reports only
conservative structural pressure from the current frozen Arlene route bank.

It never rewrites an action, changes runtime/default/config/archive state, or
claims current-native economic value.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
EXPECTED_ARLENE_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
TURNS_PER_DAY = 24
ANIMAL_SPECS = {
    "GOOSE": {"structure": "COOP", "first_yield_day": 4, "interval": 1, "max_held": 4},
    "COW": {"structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6},
    "SHEEP": {"structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6},
}

HERE = Path(__file__).resolve()
V4_ROOT = HERE.parents[2]
ENGINE_PATH = V4_ROOT.parent.parent / "reference" / "engine" / "kaggriculture.py"
CURRENT_ARLENE_CENSUS = HERE.with_name("current_arlene_census.py")


class CareBankError(RuntimeError):
    pass


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def verify_engine_source(path: Path = ENGINE_PATH) -> dict[str, Any]:
    """Authenticate the exact engine and the animal-refresh markers we model."""
    actual = git_blob_sha(path)
    if actual != EXPECTED_ENGINE_BLOB:
        raise CareBankError(
            f"engine drift: expected {EXPECTED_ENGINE_BLOB}, got {actual}"
        )
    source = path.read_text(encoding="utf-8")
    markers = (
        "def _daily_refresh_animals(farm, day):",
        'if tile["consecutive_unfed"] >= 2:',
        'days_since_first = next_day - tile["placed_day"] - a["first_yield_day"]',
        'bonus = tile.pop("pending_care_bonus", 0) if tile["fed_today"] else 0',
        'tile["yield_units"] = min(a["max_held"], tile["yield_units"] + base + bonus)',
        'tile["pending_care_bonus"] = 0',
        'if tile["cared_today"] and tile["fed_today"]:',
        'tile["pending_care_bonus"] = tile.get("pending_care_bonus", 0) + 1',
    )
    missing = [marker for marker in markers if marker not in source]
    if missing:
        raise CareBankError(f"engine CARE semantics markers drifted: {missing!r}")
    return {"engine_blob": actual, "modeled_function": "_daily_refresh_animals"}


def _int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CareBankError(f"{name} must be an integer >= {minimum}, got {value!r}")
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise CareBankError(f"{name} must be bool, got {value!r}")
    return value


def is_production_eod(animal: str, placed_day: int, day: int) -> bool:
    if animal not in ANIMAL_SPECS:
        raise CareBankError(f"unknown animal {animal!r}")
    placed_day = _int(placed_day, "placed_day")
    day = _int(day, "day")
    if placed_day > day:
        raise CareBankError("placed_day cannot be after current day")
    spec = ANIMAL_SPECS[animal]
    next_day = day + 1
    days_since_first = next_day - placed_day - spec["first_yield_day"]
    return days_since_first >= 0 and days_since_first % spec["interval"] == 0


def _validated_state(state: Mapping[str, Any], day: int) -> dict[str, Any]:
    if not isinstance(state, Mapping):
        raise CareBankError("animal state must be a mapping")
    animal = state.get("animal")
    if animal not in ANIMAL_SPECS:
        raise CareBankError(f"unknown animal {animal!r}")
    day = _int(day, "day")
    placed_day = _int(state.get("placed_day"), "placed_day")
    if placed_day > day:
        raise CareBankError("placed_day cannot be after current day")
    max_held = ANIMAL_SPECS[animal]["max_held"]
    yield_units = _int(state.get("yield_units"), "yield_units")
    if yield_units > max_held:
        raise CareBankError(
            f"yield_units exceeds {animal} max_held {max_held}: {yield_units}"
        )
    consecutive_unfed = _int(state.get("consecutive_unfed"), "consecutive_unfed")
    if consecutive_unfed > 1:
        raise CareBankError(
            f"live animal consecutive_unfed cannot exceed 1, got {consecutive_unfed}"
        )
    return {
        "animal": animal,
        "placed_day": placed_day,
        "yield_units": yield_units,
        "consecutive_unfed": consecutive_unfed,
        "fed_today": _bool(state.get("fed_today"), "fed_today"),
        "cared_today": _bool(state.get("cared_today"), "cared_today"),
        "pending_care_bonus": _int(state.get("pending_care_bonus", 0), "pending_care_bonus"),
    }


def refresh_animal_day(state: Mapping[str, Any], day: int) -> dict[str, Any]:
    """Mirror one animal's exact `_daily_refresh_animals` EOD transition.

    The return makes the CARE-specific accounting explicit while retaining a
    normalized `next_state` for chaining.  Escape occurs before production,
    exactly as in the engine.
    """
    s = _validated_state(state, day)
    spec = ANIMAL_SPECS[s["animal"]]
    before_bank = s["pending_care_bonus"]
    before_yield = s["yield_units"]
    consecutive = 0 if s["fed_today"] else s["consecutive_unfed"] + 1

    if consecutive >= 2:
        return {
            "animal": s["animal"],
            "day": day,
            "production_eod": False,
            "escaped": True,
            "escape_structure": spec["structure"],
            "yield_before": before_yield,
            "yield_after": None,
            "base_units": 0,
            "bank_before": before_bank,
            "bank_consumed_for_yield": 0,
            "bank_erased_unfed_production": 0,
            "bank_destroyed_on_escape": before_bank,
            "bank_added_after_production": 0,
            "bank_after": None,
            "raw_production_units": 0,
            "realized_production_units": 0,
            "clipped_total_units": 0,
            "clipped_care_bonus_units": 0,
            "consecutive_unfed_before": s["consecutive_unfed"],
            "consecutive_unfed_after": consecutive,
            "next_state": {"kind": spec["structure"]},
        }

    production = is_production_eod(s["animal"], s["placed_day"], day)
    bank_consumed = 0
    bank_erased = 0
    raw_units = 0
    realized_units = 0
    clipped_total = 0
    clipped_care = 0
    yield_after = before_yield
    bank_mid = before_bank

    if production:
        base = 1
        if s["fed_today"]:
            bonus = before_bank
            bank_consumed = before_bank
        else:
            bonus = 0
            bank_erased = before_bank
        raw_units = base + bonus
        headroom = max(0, spec["max_held"] - before_yield)
        realized_units = min(raw_units, headroom)
        clipped_total = raw_units - realized_units
        base_realized = min(base, headroom)
        care_realized = max(0, realized_units - base_realized)
        clipped_care = max(0, bonus - care_realized)
        yield_after = min(spec["max_held"], before_yield + raw_units)
        bank_mid = 0
    else:
        base = 0

    bank_added = 1 if s["cared_today"] and s["fed_today"] else 0
    bank_after = bank_mid + bank_added
    next_state = {
        "animal": s["animal"],
        "placed_day": s["placed_day"],
        "yield_units": yield_after,
        "consecutive_unfed": consecutive,
        "fed_today": False,
        "cared_today": False,
        "fertilizer_available": True,
        "pending_care_bonus": bank_after,
    }
    return {
        "animal": s["animal"],
        "day": day,
        "production_eod": production,
        "escaped": False,
        "yield_before": before_yield,
        "yield_after": yield_after,
        "base_units": base,
        "bank_before": before_bank,
        "bank_consumed_for_yield": bank_consumed,
        "bank_erased_unfed_production": bank_erased,
        "bank_destroyed_on_escape": 0,
        "bank_added_after_production": bank_added,
        "bank_after": bank_after,
        "raw_production_units": raw_units,
        "realized_production_units": realized_units,
        "clipped_total_units": clipped_total,
        "clipped_care_bonus_units": clipped_care,
        "consecutive_unfed_before": s["consecutive_unfed"],
        "consecutive_unfed_after": consecutive,
        "next_state": next_state,
    }


def care_today_marginal(state: Mapping[str, Any], day: int) -> dict[str, Any]:
    """Compare the same final pre-EOD state with today's CARE bit OFF vs ON."""
    base = dict(state)
    base["cared_today"] = False
    cared = dict(state)
    cared["cared_today"] = True
    off = refresh_animal_day(base, day)
    on = refresh_animal_day(cared, day)

    if off["escaped"]:
        classification = "ESCAPES_BEFORE_CARE_BANKING"
    elif not _bool(state.get("fed_today"), "fed_today"):
        classification = "NO_FEED_NO_NEW_CARE_BANK"
    else:
        classification = "BANKS_ONE_FOR_FUTURE_PRODUCTION"

    return {
        "classification": classification,
        "same_day_yield_delta": (
            None if off["yield_after"] is None else on["yield_after"] - off["yield_after"]
        ),
        "bank_after_delta": (
            None if off["bank_after"] is None else on["bank_after"] - off["bank_after"]
        ),
        "off": off,
        "on": on,
    }


def first_yield_care_bound(animal: str) -> dict[str, Any]:
    """Best-case bound for daily FEED+CARE before an animal's first production.

    Before first yield there is nothing to harvest, so cap clipping at the first
    production is source-certain under the stated daily-feed/care premise.
    Today's CARE on the production EOD is not part of the consumed bank; it is
    banked only after production for a later cycle.
    """
    if animal not in ANIMAL_SPECS:
        raise CareBankError(f"unknown animal {animal!r}")
    spec = ANIMAL_SPECS[animal]
    care_bank_entering_first_yield = max(0, spec["first_yield_day"] - 1)
    useful_bank_capacity = max(0, spec["max_held"] - 1)
    guaranteed_clipped = max(0, care_bank_entering_first_yield - useful_bank_capacity)
    return {
        "animal": animal,
        "first_yield_day": spec["first_yield_day"],
        "interval": spec["interval"],
        "max_held": spec["max_held"],
        "daily_feed_care_bank_entering_first_yield": care_bank_entering_first_yield,
        "max_useful_care_bank_at_empty_first_yield": useful_bank_capacity,
        "guaranteed_clipped_care_units_if_daily_feed_care_and_no_prior_harvest": guaranteed_clipped,
        "production_day_care_consumed_same_day": False,
    }


def _worker_rows(action: Mapping[str, Any]) -> list[list[Any]]:
    raw: list[Any] = [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]
    return [row if isinstance(row, list) and row else ["PASS"] for row in raw]


def census_authored_care_pressure(
    route: Iterable[Mapping[str, Any]],
    route_id: str,
    *,
    turns_per_day: int = TURNS_PER_DAY,
) -> dict[str, Any]:
    """Report route-level CARE pressure without pretending rows target one animal.

    `PLACE COW` windows are *authored pressure windows only*.  They do not claim
    placement succeeds, that later CARE/FEED rows target that cow, or that any
    CARE bonus clips in live execution.
    """
    turns_per_day = _int(turns_per_day, "turns_per_day", minimum=1)
    care_steps: list[int] = []
    feed_steps: list[int] = []
    cow_place_steps: list[int] = []
    per_day: dict[int, Counter[str]] = {}
    steps = 0

    for step, action in enumerate(route):
        if not isinstance(action, Mapping):
            raise CareBankError(f"route {route_id!r} step {step} is not a mapping")
        steps = step + 1
        day_counts = per_day.setdefault(step // turns_per_day, Counter())
        for row in _worker_rows(action):
            op = str(row[0])
            if op == "CARE":
                care_steps.append(step)
                day_counts["CARE"] += 1
            elif op == "FEED":
                feed_steps.append(step)
                day_counts["FEED"] += 1
            if op == "PLACE" and len(row) > 1 and row[1] == "COW":
                cow_place_steps.append(step)
                day_counts["PLACE_COW"] += 1

    care_by_day = Counter(step // turns_per_day for step in care_steps)
    feed_by_day = Counter(step // turns_per_day for step in feed_steps)
    cow_windows = []
    pre_days = ANIMAL_SPECS["COW"]["first_yield_day"] - 1
    for place_step in cow_place_steps:
        place_day = place_step // turns_per_day
        window_days = range(place_day, place_day + pre_days)
        care_rows = sum(care_by_day[d] for d in window_days)
        feed_rows = sum(feed_by_day[d] for d in window_days)
        cow_windows.append(
            {
                "place_step": place_step,
                "place_day": place_day,
                "pre_first_yield_days": [place_day, place_day + pre_days - 1],
                "all_animal_care_rows_in_window": care_rows,
                "all_animal_feed_rows_in_window": feed_rows,
                "target_specific": False,
                "realized_placement": False,
            }
        )

    active_days = sorted(set(care_by_day) | set(feed_by_day))
    return {
        "route_id": route_id,
        "steps": steps,
        "care_rows": len(care_steps),
        "feed_rows": len(feed_steps),
        "care_days": len(care_by_day),
        "feed_days": len(feed_by_day),
        "max_care_rows_one_day": max(care_by_day.values(), default=0),
        "max_feed_rows_one_day": max(feed_by_day.values(), default=0),
        "daily": [
            {
                "day": day,
                "care_rows": care_by_day[day],
                "feed_rows": feed_by_day[day],
                "paired_feed_care_rows_upper_bound": min(care_by_day[day], feed_by_day[day]),
            }
            for day in active_days
        ],
        "authored_cow_place_windows": cow_windows,
        "truth_boundary": (
            "Counts are authored route pressure only. CARE/FEED target identity, movement, "
            "placement success, feed success, harvest headroom and final-return transforms "
            "are not inferred."
        ),
    }


def _load_current_routes() -> tuple[Mapping[str, list[dict[str, Any]]], int, dict[str, Any]]:
    if not CURRENT_ARLENE_CENSUS.exists():
        raise CareBankError(f"missing sibling current Arlene census: {CURRENT_ARLENE_CENSUS}")
    spec = importlib.util.spec_from_file_location("_caresat_current_arlene", CURRENT_ARLENE_CENSUS)
    if spec is None or spec.loader is None:
        raise CareBankError("cannot load current_arlene_census.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    routes, max_orders, receipt = module.load_current_routes()
    if receipt.get("arlene_blob") != EXPECTED_ARLENE_BLOB:
        raise CareBankError(
            f"unexpected Arlene receipt {receipt.get('arlene_blob')!r}"
        )
    return routes, max_orders, receipt


def build_current_report() -> dict[str, Any]:
    engine_receipt = verify_engine_source()
    routes, _max_orders, arlene_receipt = _load_current_routes()
    rows = [
        census_authored_care_pressure(routes[route_id], route_id)
        for route_id in sorted(routes)
    ]
    return {
        "schema": "titan-v4-caresat-v1",
        "policy_inert": True,
        "decision_authority": False,
        "engine_receipt": engine_receipt,
        "arlene_receipt": arlene_receipt,
        "first_yield_bounds": {
            animal: first_yield_care_bound(animal) for animal in sorted(ANIMAL_SPECS)
        },
        "summary": {
            "routes": len(rows),
            "min_care_rows": min(row["care_rows"] for row in rows),
            "max_care_rows": max(row["care_rows"] for row in rows),
            "min_feed_rows": min(row["feed_rows"] for row in rows),
            "max_feed_rows": max(row["feed_rows"] for row in rows),
            "cow_daily_feed_care_guaranteed_first_yield_clipped_units": first_yield_care_bound("COW")[
                "guaranteed_clipped_care_units_if_daily_feed_care_and_no_prior_harvest"
            ],
        },
        "routes": rows,
        "truth_boundary": (
            "The engine theorem and explicit-state transition are source-bound. Current-route "
            "CARE cadence is structural pressure only; this report does not prove target-specific "
            "redundancy, realized clipping, action rewrite safety, or economic value."
        ),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--state-json",
        help="instead of current-route report, evaluate one explicit animal state JSON",
    )
    parser.add_argument("--day", type=int, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.state_json is not None:
        if args.day is None:
            raise CareBankError("--day is required with --state-json")
        try:
            state = json.loads(args.state_json)
        except json.JSONDecodeError as exc:
            raise CareBankError(f"invalid --state-json: {exc}") from exc
        result = {
            "schema": "titan-v4-caresat-explicit-state-v1",
            "engine_receipt": verify_engine_source(),
            "transition": refresh_animal_day(state, args.day),
            "care_today_marginal": care_today_marginal(state, args.day),
        }
    else:
        result = build_current_report()

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
