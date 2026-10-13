#!/usr/bin/env python3
"""Source-bound census of the current frozen Arlene animal-throughput route bank.

Research-only. This module authenticates current Arlene, decodes its route bank through
the source's own lazy ``routes()`` API, and reports authored animal/service capacity.
It never mutates actions, runtime configuration, defaults, archives, or policy.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

EXPECTED_ARLENE_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
EXPECTED_TURNS = 720
EXPECTED_MAX_ORDERS = 10
ANIMALS = ("GOOSE", "COW", "SHEEP")
ANIMAL_PRODUCTS = ("EGG", "MILK", "WOOL")
UNIT_OPS = (
    "BUILD_COOP",
    "BUILD_PASTURE",
    "PLACE",
    "FEED",
    "CARE",
    "HARVEST",
    "COLLECT_FERTILIZER",
    "DROP",
    "PICKUP",
)
MARKET_OPS = ("BUY_ANIMAL", "BUY_PRODUCT", "BUY_SEED", "SELL", "HIRE", "BUY_LAND")

HERE = Path(__file__).resolve()
V4_ROOT = HERE.parents[2]
ARLENE_PATH = (
    V4_ROOT.parent.parent / "reference" / "next-panel" / "vendor" / "arlene.py"
)


class CurrentArleneCensusError(RuntimeError):
    pass


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def verify_arlene_source(path: Path = ARLENE_PATH) -> dict[str, Any]:
    actual = git_blob_sha(path)
    if actual != EXPECTED_ARLENE_BLOB:
        raise CurrentArleneCensusError(
            f"arlene.py drift: expected {EXPECTED_ARLENE_BLOB}, got {actual}"
        )
    source = path.read_text(encoding="utf-8")
    markers = (
        "TURNS = 720",
        "MAX_ORDERS = 10",
        "_ROUTES = None",
        "def routes():",
        'p = json.loads(zlib.decompress(base64.b64decode(_BLOB)).decode())',
        'out = {p["main"]: p["full"]}',
        'out[t["h"]] = out[t["parent"]][:t["at"]] + t["suffix"]',
    )
    missing = [marker for marker in markers if marker not in source]
    if missing:
        raise CurrentArleneCensusError(
            f"Arlene route-decoder semantics drifted: missing {missing!r}"
        )
    return {"arlene_blob": actual}


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("_herdscale_current_arlene", path)
    if spec is None or spec.loader is None:
        raise CurrentArleneCensusError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_current_routes(
    path: Path = ARLENE_PATH,
    *,
    authenticate: bool = True,
) -> tuple[dict[str, list[dict[str, Any]]], int, dict[str, Any]]:
    receipt = verify_arlene_source(path) if authenticate else {}
    module = _load_module(path)
    turns = getattr(module, "TURNS", None)
    max_orders = getattr(module, "MAX_ORDERS", None)
    route_loader = getattr(module, "routes", None)
    if turns != EXPECTED_TURNS:
        raise CurrentArleneCensusError(
            f"expected Arlene TURNS={EXPECTED_TURNS}, got {turns!r}"
        )
    if max_orders != EXPECTED_MAX_ORDERS:
        raise CurrentArleneCensusError(
            f"expected Arlene MAX_ORDERS={EXPECTED_MAX_ORDERS}, got {max_orders!r}"
        )
    if not callable(route_loader):
        raise CurrentArleneCensusError("Arlene routes() decoder missing")
    raw = route_loader()
    if not isinstance(raw, Mapping) or not raw:
        raise CurrentArleneCensusError("Arlene routes() must return a non-empty mapping")

    routes: dict[str, list[dict[str, Any]]] = {}
    for route_id, route in raw.items():
        if not isinstance(route_id, str) or not route_id:
            raise CurrentArleneCensusError(f"invalid route id {route_id!r}")
        if not isinstance(route, list) or len(route) != EXPECTED_TURNS:
            size = len(route) if isinstance(route, list) else type(route).__name__
            raise CurrentArleneCensusError(
                f"route {route_id!r} must contain {EXPECTED_TURNS} actions, got {size}"
            )
        if any(not isinstance(action, dict) for action in route):
            raise CurrentArleneCensusError(f"route {route_id!r} contains non-dict action")
        routes[route_id] = route

    declared_ids = {
        str(getattr(module, name))
        for name in ("MAIN", "YARN", "YARN_CARROT", "MILK_GLUT")
        if isinstance(getattr(module, name, None), str)
    }
    missing_ids = sorted(declared_ids - set(routes))
    if missing_ids:
        raise CurrentArleneCensusError(
            f"declared Arlene route ids absent from decoded bank: {missing_ids!r}"
        )
    receipt.update(
        {
            "turns": turns,
            "max_orders": max_orders,
            "route_ids": sorted(routes),
            "declared_route_ids": sorted(declared_ids),
        }
    )
    return routes, max_orders, receipt


def _worker_rows(action: Mapping[str, Any]) -> list[list[Any]]:
    raw: list[Any] = [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]
    return [row if isinstance(row, list) and row else ["PASS"] for row in raw]


def _market_rows(action: Mapping[str, Any], max_orders: int) -> list[list[Any]]:
    raw = action.get("market") or []
    if not isinstance(raw, list):
        return []
    return [row for row in raw[:max_orders] if isinstance(row, list) and row]


def _quantity(row: list[Any], default: int = 1) -> int:
    if len(row) < 3:
        return default
    try:
        return max(0, int(row[2]))
    except (TypeError, ValueError):
        return 0


def _span(spans: dict[str, list[int]], key: str, step: int) -> None:
    pair = spans.setdefault(key, [step, step])
    pair[0] = min(pair[0], step)
    pair[1] = max(pair[1], step)


def census_current_route(
    route: Iterable[Mapping[str, Any]],
    route_id: str,
    *,
    max_orders: int = EXPECTED_MAX_ORDERS,
) -> dict[str, Any]:
    if max_orders <= 0:
        raise ValueError("max_orders must be positive")

    unit_ops: Counter[str] = Counter()
    unit_targets: Counter[str] = Counter()
    market_ops: Counter[str] = Counter()
    market_units: Counter[str] = Counter()
    product_sell_units: Counter[str] = Counter()
    spans: dict[str, list[int]] = {}
    steps = 0
    actor_rows = 0

    for step, action in enumerate(route):
        if not isinstance(action, Mapping):
            raise CurrentArleneCensusError(
                f"route {route_id!r} step {step} is not an action mapping"
            )
        steps = step + 1
        for row in _worker_rows(action):
            actor_rows += 1
            op = str(row[0])
            unit_ops[op] += 1
            if op in UNIT_OPS:
                _span(spans, f"unit:{op}", step)
            if len(row) > 1:
                unit_targets[f"{op}:{row[1]}"] += 1

        for row in _market_rows(action, max_orders):
            op = str(row[0])
            market_ops[op] += 1
            target = str(row[1]) if len(row) > 1 else ""
            if target:
                market_units[f"{op}:{target}"] += _quantity(row)
                if op in MARKET_OPS:
                    _span(spans, f"market:{op}:{target}", step)
            if op == "SELL" and target in ANIMAL_PRODUCTS:
                product_sell_units[target] += _quantity(row)

    animal_buys = {
        animal: market_units[f"BUY_ANIMAL:{animal}"] for animal in ANIMALS
    }
    animal_places = {
        animal: unit_targets[f"PLACE:{animal}"] for animal in ANIMALS
    }
    total_animals = sum(animal_buys.values())
    collect_slots = unit_ops["COLLECT_FERTILIZER"]
    harvest_rows = unit_ops["HARVEST"]

    def per_animal(value: int) -> float | None:
        return round(value / total_animals, 6) if total_animals else None

    return {
        "route_id": route_id,
        "steps": steps,
        "actor_rows": actor_rows,
        "collection_action_slots": collect_slots,
        "fertilizer_units_upper_bound_from_scheduled_collects": collect_slots,
        "animal_buy_units": animal_buys,
        "animal_place_rows": animal_places,
        "animal_product_sell_units": {
            product: product_sell_units[product] for product in ANIMAL_PRODUCTS
        },
        "unit_ops": {op: unit_ops[op] for op in UNIT_OPS},
        "market_orders": {op: market_ops[op] for op in MARKET_OPS},
        "service_ratios_per_animal_bought": {
            "place_rows": per_animal(sum(animal_places.values())),
            "feed_rows": per_animal(unit_ops["FEED"]),
            "care_rows": per_animal(unit_ops["CARE"]),
            "harvest_rows": per_animal(harvest_rows),
            "collect_fertilizer_rows": per_animal(collect_slots),
        },
        "spans": dict(sorted(spans.items())),
    }


def build_current_census(
    routes: Mapping[str, list[dict[str, Any]]],
    *,
    max_orders: int,
    source_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not routes:
        raise CurrentArleneCensusError("route bank is empty")
    rows = [
        census_current_route(routes[route_id], route_id, max_orders=max_orders)
        for route_id in sorted(routes)
    ]
    collect = [row["collection_action_slots"] for row in rows]
    buys = [sum(row["animal_buy_units"].values()) for row in rows]
    service_keys = ("FEED", "CARE", "HARVEST", "COLLECT_FERTILIZER")
    service_ranges = {
        key: {
            "min": min(row["unit_ops"][key] for row in rows),
            "max": max(row["unit_ops"][key] for row in rows),
        }
        for key in service_keys
    }
    return {
        "schema": "titan-v4-herdscale-current-arlene-census-v1",
        "policy_inert": True,
        "decision_authority": False,
        "surface": "current_frozen_arlene_route_bank",
        "source_receipt": source_receipt or {},
        "truth_boundary": (
            "This is authored current-route structure, not realized execution or EV. "
            "Repairs, no-ops, movement, private inventory, and final-return transforms can "
            "reduce or alter realized actions."
        ),
        "fertilizer_bound": (
            "Official engine semantics make each successful COLLECT_FERTILIZER consume one "
            "animal availability flag and add exactly one FERT; scheduled COLLECT rows are "
            "therefore an upper bound, never a realized-output claim."
        ),
        "summary": {
            "routes": len(rows),
            "min_scheduled_collect_ceiling": min(collect),
            "max_scheduled_collect_ceiling": max(collect),
            "mean_scheduled_collect_ceiling": sum(collect) / len(collect),
            "min_animal_buy_units": min(buys),
            "max_animal_buy_units": max(buys),
            "service_row_ranges": service_ranges,
        },
        "routes": rows,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    routes, max_orders, receipt = load_current_routes()
    result = build_current_census(
        routes, max_orders=max_orders, source_receipt=receipt
    )
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
