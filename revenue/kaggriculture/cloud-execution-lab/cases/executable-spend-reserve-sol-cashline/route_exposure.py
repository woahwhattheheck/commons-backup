#!/usr/bin/env python3
"""Measure frozen-route exposure to executable-prefix spend-reserve drift.

The scanner is deliberately attribution-only.  It authenticates the exact Arlene
source, decodes its conserved route graph through the production Agent class, and
reports where spend-bearing rows sit beyond the engine's raw market-order prefix.
It never claims that structural exposure changed a game outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ARLENE_REL = Path(
    "revenue/kaggriculture/cloud-execution-lab/reference/next-panel/vendor/arlene.py"
)
EXPECTED_ARLENE_GIT_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
OUTPUT_CAP_ANCHOR = "market = (market + extra)[:MAX_ORDERS]"
SPEND_OPS = frozenset({"HIRE", "BUY_LAND", "BUY_SEED", "BUY_ANIMAL", "BUY_PRODUCT"})


class ExposureError(RuntimeError):
    """Raised when an authenticated route or scan invariant is violated."""


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bound_source(repo: Path) -> tuple[Path, bytes]:
    root = repo.resolve()
    path = (root / ARLENE_REL).resolve()
    if path != root and root not in path.parents:
        raise ExposureError(f"path escapes repository: {ARLENE_REL}")
    data = path.read_bytes()
    actual = git_blob_sha(data)
    if actual != EXPECTED_ARLENE_GIT_BLOB:
        raise ExposureError(
            f"expected Arlene Git blob {EXPECTED_ARLENE_GIT_BLOB}, observed {actual}"
        )
    text = data.decode("utf-8")
    if text.count(OUTPUT_CAP_ANCHOR) != 1:
        raise ExposureError("Arlene output-cap anchor missing or duplicated")
    return path, data


def _load(path: Path) -> ModuleType:
    name = f"titan_route_exposure_{hashlib.sha256(str(path).encode()).hexdigest()[:16]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ExposureError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _op(order: Any) -> str | None:
    if not isinstance(order, list) or not order or not isinstance(order[0], str):
        return None
    return order[0]


def _canonical_cell(step: int, market: list[Any]) -> str:
    return json.dumps([step, market], sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def scan(repo: Path) -> dict[str, Any]:
    path, source = _bound_source(repo)
    module = _load(path)
    controller = module.Agent()
    routes = controller.R
    if not isinstance(routes, dict) or not routes:
        raise ExposureError("Agent.R must be a nonempty mapping")

    default_cap = max(1, int(getattr(module, "MAX_ORDERS", 10)))
    caps = tuple(range(1, default_cap + 1))
    per_cap: dict[int, dict[str, Any]] = {
        cap: {
            "route_cells_over_cap": 0,
            "route_cells_with_suffix_spend": 0,
            "route_cells_with_active_sell_and_suffix_spend": 0,
            "suffix_spend_rows": 0,
            "suffix_spend_by_op": {op: 0 for op in sorted(SPEND_OPS)},
            "unique_cells_over_cap": set(),
            "unique_cells_with_suffix_spend": set(),
            "unique_cells_with_active_sell_and_suffix_spend": set(),
            "examples": [],
        }
        for cap in caps
    }
    route_lengths: dict[str, int] = {}
    total_route_cells = 0
    market_route_cells = 0
    max_market_rows = 0

    for route_name in sorted(routes, key=str):
        route = routes[route_name]
        if not isinstance(route, list) or not route:
            raise ExposureError(f"route {route_name!r} must be a nonempty list")
        route_lengths[str(route_name)] = len(route)
        for step, action in enumerate(route):
            total_route_cells += 1
            if not isinstance(action, dict):
                raise ExposureError(f"route {route_name!r} step {step}: action is not a mapping")
            market = action.get("market", [])
            if market is None:
                market = []
            if not isinstance(market, list):
                raise ExposureError(f"route {route_name!r} step {step}: market is not a list")
            if market:
                market_route_cells += 1
            max_market_rows = max(max_market_rows, len(market))
            canonical = _canonical_cell(step, market)

            for cap in caps:
                record = per_cap[cap]
                active = market[:cap]
                suffix = market[cap:]
                if suffix:
                    record["route_cells_over_cap"] += 1
                    record["unique_cells_over_cap"].add(canonical)
                suffix_spend = [row for row in suffix if _op(row) in SPEND_OPS]
                if not suffix_spend:
                    continue
                record["route_cells_with_suffix_spend"] += 1
                record["suffix_spend_rows"] += len(suffix_spend)
                record["unique_cells_with_suffix_spend"].add(canonical)
                active_sell = any(_op(row) == "SELL" for row in active)
                if active_sell:
                    record["route_cells_with_active_sell_and_suffix_spend"] += 1
                    record["unique_cells_with_active_sell_and_suffix_spend"].add(canonical)
                for row in suffix_spend:
                    record["suffix_spend_by_op"][_op(row)] += 1
                if len(record["examples"]) < 12:
                    record["examples"].append(
                        {
                            "route": str(route_name),
                            "step": step,
                            "market_rows": len(market),
                            "active_ops": [_op(row) for row in active],
                            "suffix_spend_ops": [_op(row) for row in suffix_spend],
                        }
                    )

    serialized_caps: dict[str, Any] = {}
    for cap in caps:
        raw = per_cap[cap]
        serialized_caps[str(cap)] = {
            "route_cells_over_cap": raw["route_cells_over_cap"],
            "unique_cells_over_cap": len(raw["unique_cells_over_cap"]),
            "route_cells_with_suffix_spend": raw["route_cells_with_suffix_spend"],
            "unique_cells_with_suffix_spend": len(raw["unique_cells_with_suffix_spend"]),
            "route_cells_with_active_sell_and_suffix_spend": raw[
                "route_cells_with_active_sell_and_suffix_spend"
            ],
            "unique_cells_with_active_sell_and_suffix_spend": len(
                raw["unique_cells_with_active_sell_and_suffix_spend"]
            ),
            "suffix_spend_rows": raw["suffix_spend_rows"],
            "suffix_spend_by_op": raw["suffix_spend_by_op"],
            "examples": raw["examples"],
        }

    default = serialized_caps[str(default_cap)]
    default_exposed = default["unique_cells_with_suffix_spend"] > 0
    return {
        "schema": "titan-v3-executable-spend-route-exposure/v1",
        "source": {
            "path": ARLENE_REL.as_posix(),
            "git_blob": git_blob_sha(source),
            "sha256": sha256(source),
            "bytes": len(source),
            "output_cap_anchor": OUTPUT_CAP_ANCHOR,
        },
        "routes": {
            "count": len(routes),
            "lengths": route_lengths,
            "total_cells_with_aliases": total_route_cells,
            "market_cells_with_aliases": market_route_cells,
            "max_market_rows": max_market_rows,
        },
        "engine_prefix_model": "raw_list_prefix_max_1_configured_cap",
        "arlene_output_cap": default_cap,
        "caps": serialized_caps,
        "default_cap_status": "EXPOSED" if default_exposed else "DORMANT_AT_DEFAULT_CAP",
        "default_cap_future_route_exposure_only": default_exposed,
        "scoreboard_causality_claim": False,
        "notes": [
            "route_cells_with_aliases counts each named route independently",
            "unique_cells deduplicates conserved shared prefixes by step and market payload",
            "current Agent output is source-bound to MAX_ORDERS; future reserve reads raw route rows",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(scan(args.repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
