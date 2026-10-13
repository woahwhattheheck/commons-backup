# SPDX-License-Identifier: Apache-2.0
"""Inventory engine-inactive represented market rows in the exact private runtime."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE / "candidate.py"


def load_candidate():
    name = "_sol_pro_sell_custody_census_candidate"
    spec = importlib.util.spec_from_file_location(name, CANDIDATE)
    if spec is None or spec.loader is None:
        raise ImportError("candidate spec unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run() -> dict[str, Any]:
    candidate = load_candidate()
    config = json.loads(
        (candidate._ARENA_ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8")
    )
    instance = candidate._candidate_new_instance(candidate._ARENA_ROOT, config)
    instance._initialize()
    consumer = instance.consumer
    controller = consumer.controller
    limit = max(1, int(config.get("maxMarketOrdersPerTurn", 10)))

    actions_over_limit = 0
    suffix_rows = 0
    suffix_nonempty = 0
    suffix_sell_rows = 0
    suffix_sell_units = 0
    suffix_sell_items: dict[str, int] = {}
    witnesses: list[dict[str, Any]] = []

    bank = controller.R
    if isinstance(bank, dict):
        route_items = list(bank.items())
    else:
        route_items = list(enumerate(bank))

    for route_key, route in route_items:
        if not isinstance(route, list):
            raise RuntimeError(f"route {route_key!r} is not a list")
        for step, action in enumerate(route):
            if not isinstance(action, dict):
                raise RuntimeError(f"route {route_key!r} step {step} is not a mapping")
            market = action.get("market", [])
            if not isinstance(market, list):
                raise RuntimeError(f"route {route_key!r} step {step} market is not a list")
            if len(market) <= limit:
                continue
            actions_over_limit += 1
            suffix = market[limit:]
            suffix_rows += len(suffix)
            local_sales = []
            for offset, row in enumerate(suffix, start=limit):
                if row:
                    suffix_nonempty += 1
                if (
                    isinstance(row, list)
                    and len(row) > 2
                    and row[0] == "SELL"
                    and type(row[2]) is int
                    and row[2] > 0
                ):
                    item = str(row[1])
                    units = int(row[2])
                    suffix_sell_rows += 1
                    suffix_sell_units += units
                    suffix_sell_items[item] = suffix_sell_items.get(item, 0) + units
                    local_sales.append({"index": offset, "item": item, "units": units})
            if local_sales and len(witnesses) < 24:
                witnesses.append(
                    {
                        "route": route_key,
                        "step": step,
                        "represented_rows": len(market),
                        "limit": limit,
                        "suffix_sales": local_sales,
                    }
                )

    receipt = candidate.install_receipt()
    result = {
        "schema_version": 1,
        "operation": "TITAN-V3-EXECUTABLE-SELL-CUSTODY-20260910-01",
        "consumer_type": type(consumer).__name__,
        "patch_factor": (receipt or {}).get("factor"),
        "private_runtime": (receipt or {}).get("private_runtime"),
        "max_market_orders_per_turn": limit,
        "routes": len(bank),
        "actions_over_limit": actions_over_limit,
        "suffix_rows": suffix_rows,
        "suffix_nonempty_rows": suffix_nonempty,
        "suffix_sell_rows": suffix_sell_rows,
        "suffix_sell_units": suffix_sell_units,
        "suffix_sell_items": dict(sorted(suffix_sell_items.items())),
        "witnesses": witnesses,
        "decision": "STATIC_SIGNAL" if suffix_sell_rows else "NO_STATIC_SUFFIX_SELL_SIGNAL",
        "evidence_boundary": (
            "Static represented-route census only; action activation and score require "
            "matched official-engine games."
        ),
    }
    if result["consumer_type"] != "ExecutableSellCustodyFrozenSelected":
        raise RuntimeError(f"unexpected consumer type: {result['consumer_type']}")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    result = run()
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
