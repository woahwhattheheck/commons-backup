#!/usr/bin/env python3
"""Source-bound animal-throughput census for TITAN V4's fixed route tapes.

This tool is deliberately policy-inert. It proves what the current tape router can
schedule; it does not mutate actions or enable a new controller.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

TURNS_PER_DAY = 24
ROUTE_STEP = 144
FINAL_PLAN_STEP = 648
LAST_STEP = 718
TAPE_COUNT = 13
TAPE_STEPS = LAST_STEP + 1

# These two blobs define the route data + splice semantics observed when this census
# was authored. Fail closed if either changes: a stale census is worse than no census.
EXPECTED_TAPES_BLOB = "a43289b9cc5e34a2481fddf652762a7d92f427ef"
EXPECTED_ROUTER_BLOB = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"

UNIT_OPS_OF_INTEREST = (
    "BUILD_COOP",
    "BUILD_PASTURE",
    "PLACE",
    "FEED",
    "CARE",
    "COLLECT_FERTILIZER",
    "HARVEST",
    "DROP",
    "PICKUP",
)
MARKET_OPS_OF_INTEREST = (
    "BUY_ANIMAL",
    "BUY_PRODUCT",
    "BUY_SEED",
    "SELL",
    "HIRE",
    "BUY_LAND",
)
ANIMAL_NAMES = frozenset({"GOOSE", "COW", "SHEEP"})

HERE = Path(__file__).resolve()
V4_ROOT = HERE.parents[2]
TAPES_PATH = V4_ROOT / "donor" / "overlay" / "r01_tapes.py"
ROUTER_PATH = V4_ROOT / "donor" / "overlay" / "r04_full_router.py"
ENGINE_PATH = V4_ROOT.parent.parent / "reference" / "engine" / "kaggriculture.py"


class CensusError(RuntimeError):
    pass


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def verify_sources(
    tapes_path: Path = TAPES_PATH,
    router_path: Path = ROUTER_PATH,
    engine_path: Path = ENGINE_PATH,
) -> dict[str, str]:
    actual_tapes = git_blob_sha(tapes_path)
    actual_router = git_blob_sha(router_path)
    if actual_tapes != EXPECTED_TAPES_BLOB:
        raise CensusError(
            f"r01_tapes.py drift: expected {EXPECTED_TAPES_BLOB}, got {actual_tapes}"
        )
    if actual_router != EXPECTED_ROUTER_BLOB:
        raise CensusError(
            f"r04_full_router.py drift: expected {EXPECTED_ROUTER_BLOB}, got {actual_router}"
        )

    router = router_path.read_text(encoding="utf-8")
    required_router_markers = (
        "if step == ROUTE_STEP:",
        "state.plan = SHOP_PLANS.get(tuple(shops[:2]), 0)",
        "if step == FINAL_PLAN_STEP:",
        "state.plan = 2",
        "tape = self.tapes[state.plan]",
        "action = copy.deepcopy(tape[step])",
    )
    missing_router = [m for m in required_router_markers if m not in router]
    if missing_router:
        raise CensusError(f"router splice semantics drifted: missing {missing_router!r}")

    engine = engine_path.read_text(encoding="utf-8")
    required_engine_markers = (
        'if op == "COLLECT_FERTILIZER":',
        'if not tile["fertilizer_available"]:',
        'tile["fertilizer_available"] = False',
        '_inv_add(inv, "FERTILIZER", 1)',
        'tile["fertilizer_available"] = True',
    )
    missing_engine = [m for m in required_engine_markers if m not in engine]
    if missing_engine:
        raise CensusError(f"fertilizer mechanics drifted: missing {missing_engine!r}")

    return {
        "r01_tapes_blob": actual_tapes,
        "r04_full_router_blob": actual_router,
        "engine_blob": git_blob_sha(engine_path),
    }


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("_herdscale_r01_tapes", path)
    if spec is None or spec.loader is None:
        raise CensusError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_tapes(path: Path = TAPES_PATH) -> list[list[dict[str, Any]]]:
    tapes = _load_module(path).load_tapes()
    if len(tapes) != TAPE_COUNT or any(len(t) != TAPE_STEPS for t in tapes):
        raise CensusError(
            f"expected {TAPE_COUNT}x{TAPE_STEPS} tapes, got "
            f"{len(tapes)} tapes / {[len(t) for t in tapes[:3]]}"
        )
    return tapes


def effective_route(tapes: list[list[dict[str, Any]]], plan: int) -> list[dict[str, Any]]:
    """Reconstruct the exact base-route splice used by r04_full_router.Policy.act."""
    if not 0 <= plan < len(tapes):
        raise CensusError(f"plan {plan} outside 0..{len(tapes)-1}")
    if any(len(t) != TAPE_STEPS for t in tapes):
        raise CensusError("all tapes must have 719 steps")
    route = (
        tapes[0][:ROUTE_STEP]
        + tapes[plan][ROUTE_STEP:FINAL_PLAN_STEP]
        + tapes[2][FINAL_PLAN_STEP:]
    )
    if len(route) != TAPE_STEPS:
        raise AssertionError("route splice length drift")
    return route


def _worker_rows(action: dict[str, Any]) -> list[list[Any]]:
    rows: list[Any] = [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]
    return [row if isinstance(row, list) and row else ["PASS"] for row in rows]


def _market_rows(action: dict[str, Any]) -> list[list[Any]]:
    rows = action.get("market") or []
    return [row for row in rows if isinstance(row, list) and row]


def _quantity(row: list[Any], default: int = 1) -> int:
    if len(row) < 3:
        return default
    try:
        return max(0, int(row[2]))
    except (TypeError, ValueError):
        return default


def census_route(route: list[dict[str, Any]], plan: int) -> dict[str, Any]:
    unit_ops: Counter[str] = Counter()
    unit_targets: Counter[str] = Counter()
    market_ops: Counter[str] = Counter()
    market_targets: Counter[str] = Counter()
    market_units: Counter[str] = Counter()
    per_day: dict[int, Counter[str]] = defaultdict(Counter)
    collect_steps: list[dict[str, int]] = []

    for step, action in enumerate(route):
        day = step // TURNS_PER_DAY

        for actor, row in enumerate(_worker_rows(action)):
            op = str(row[0])
            unit_ops[op] += 1
            per_day[day][op] += 1
            if len(row) > 1:
                unit_targets[f"{op}:{row[1]}"] += 1
            if op == "COLLECT_FERTILIZER":
                collect_steps.append({"step": step, "day": day, "actor": actor})

        for row in _market_rows(action):
            op = str(row[0])
            market_ops[op] += 1
            target = str(row[1]) if len(row) > 1 else ""
            if target:
                market_targets[f"{op}:{target}"] += 1
                market_units[f"{op}:{target}"] += _quantity(row)

    collect_slots = unit_ops["COLLECT_FERTILIZER"]
    animal_buys = {
        animal: market_units[f"BUY_ANIMAL:{animal}"] for animal in sorted(ANIMAL_NAMES)
    }
    animal_places = {
        animal: unit_targets[f"PLACE:{animal}"] for animal in sorted(ANIMAL_NAMES)
    }

    days_with_collect = sorted({entry["day"] for entry in collect_steps})
    daily_collect = {
        str(day): per_day[day]["COLLECT_FERTILIZER"]
        for day in range((TAPE_STEPS + TURNS_PER_DAY - 1) // TURNS_PER_DAY)
        if per_day[day]["COLLECT_FERTILIZER"]
    }

    return {
        "plan": plan,
        "route_splice": {
            "opening_plan": 0,
            "opening_steps": [0, ROUTE_STEP - 1],
            "midgame_plan": plan,
            "midgame_steps": [ROUTE_STEP, FINAL_PLAN_STEP - 1],
            "endgame_plan": 2,
            "endgame_steps": [FINAL_PLAN_STEP, LAST_STEP],
        },
        "collection_action_slots": collect_slots,
        # Official engine semantics: a successful COLLECT clears one boolean flag and
        # adds exactly one FERT. Failed/no-op rows can only reduce realized output.
        "fertilizer_units_upper_bound_from_scheduled_collects": collect_slots,
        "collect_days": days_with_collect,
        "daily_collect_slots": daily_collect,
        "animal_buy_units": animal_buys,
        "animal_place_rows": animal_places,
        "unit_ops": {op: unit_ops[op] for op in UNIT_OPS_OF_INTEREST},
        "market_orders": {op: market_ops[op] for op in MARKET_OPS_OF_INTEREST},
        "market_targets": dict(sorted(market_targets.items())),
    }


def build_census(
    tapes: list[list[dict[str, Any]]],
    source_receipt: dict[str, str] | None = None,
) -> dict[str, Any]:
    routes = [census_route(effective_route(tapes, plan), plan) for plan in range(TAPE_COUNT)]
    ceilings = [r["fertilizer_units_upper_bound_from_scheduled_collects"] for r in routes]
    return {
        "schema": "titan-v4-herdscale-throughput-census-v1",
        "policy_inert": True,
        "source_receipt": source_receipt or {},
        "mechanics_proof": {
            "collect_success_consumes_one_boolean_flag": True,
            "collect_success_adds_exactly_one_fertilizer": True,
            "animal_eod_regenerates_fertilizer_flag": True,
            "consequence": (
                "For the fixed base route, scheduled COLLECT_FERTILIZER worker rows are "
                "an upper bound on fertilizer units collectible by that route. Invalid, "
                "duplicate, or mistimed rows can only lower realized collection."
            ),
        },
        "router_proof": {
            "opening": "plan 0, steps 0..143",
            "midgame": "selected plan, steps 144..647",
            "endgame": "plan 2, steps 648..718",
        },
        "summary": {
            "routes": TAPE_COUNT,
            "min_scheduled_collect_ceiling": min(ceilings),
            "max_scheduled_collect_ceiling": max(ceilings),
            "mean_scheduled_collect_ceiling": sum(ceilings) / len(ceilings),
        },
        "routes": routes,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--skip-source-pins",
        action="store_true",
        help="development only: do not authenticate canonical source blobs",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    receipt = {} if args.skip_source_pins else verify_sources()
    result = build_census(load_tapes(), receipt)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
