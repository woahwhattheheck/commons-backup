#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only census of authored WHEAT purchases in the current Arlene route bank.

This is routing evidence for TOWNPROCURE. It does not choose, move, add, suppress,
or execute market orders. A zero-row result is meaningful: the town-timing oracle
has no authored BUY_PRODUCT WHEAT commitment to retime in the current route bank.

Source custody is snapshot-bound: the exact Arlene bytes authenticated here are the
same bytes compiled and executed to obtain ``routes()``. The pathname is never
reopened after authentication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import types
from collections import Counter
from pathlib import Path

EXPECTED_VENDOR_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
SCHEMA = "titan.v4.market-baseline.current-wheat-buy-census.v2"


def _lab_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _read_snapshot(path: Path) -> bytes:
    """Read one immutable source snapshot; callers must not reopen *path*."""
    return path.read_bytes()


def _git_blob_bytes(data: bytes) -> str:
    if not isinstance(data, bytes):
        raise TypeError("Git blob input must be bytes")
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def _load_vendor_snapshot(source: bytes, source_path: Path):
    """Compile/execute only the already-authenticated vendor bytes."""
    if not isinstance(source, bytes):
        raise TypeError("vendor snapshot must be bytes")
    module = types.ModuleType("titan_v4_current_arlene")
    module.__file__ = str(source_path)
    module.__package__ = None
    code = compile(source, str(source_path), "exec")
    exec(code, module.__dict__)
    return module


def census(*, expected_vendor_blob: str = EXPECTED_VENDOR_BLOB) -> dict:
    lab = _lab_root()
    vendor = lab / "reference" / "next-panel" / "vendor" / "arlene.py"
    vendor_snapshot = _read_snapshot(vendor)
    blob = _git_blob_bytes(vendor_snapshot)
    if blob != expected_vendor_blob:
        raise RuntimeError(
            f"vendor source drift: expected {expected_vendor_blob}, got {blob}"
        )

    module = _load_vendor_snapshot(vendor_snapshot, vendor)
    routes = module.routes()
    if not isinstance(routes, dict) or not routes:
        raise RuntimeError("vendor routes() returned no route bank")

    rows = []
    all_buy_products = Counter()
    route_lengths = {}
    for route_hash in sorted(routes):
        route = routes[route_hash]
        if not isinstance(route, list):
            raise RuntimeError(f"route {route_hash!r} is not a list")
        route_lengths[route_hash] = len(route)
        for step, callback in enumerate(route):
            if not isinstance(callback, dict):
                raise RuntimeError(
                    f"route {route_hash!r} callback {step} is not an object"
                )
            market = callback.get("market") or []
            if not isinstance(market, list):
                raise RuntimeError(
                    f"route {route_hash!r} callback {step} market is not a list"
                )
            for row_index, raw in enumerate(market):
                if not isinstance(raw, list) or not raw:
                    continue
                if raw[0] != "BUY_PRODUCT":
                    continue
                item = raw[1] if len(raw) > 1 else None
                quantity = raw[2] if len(raw) > 2 else None
                all_buy_products[str(item)] += 1
                if item != "WHEAT":
                    continue
                if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                    raise RuntimeError(
                        f"invalid authored WHEAT quantity at {route_hash}:{step}:{row_index}: {quantity!r}"
                    )
                rows.append(
                    {
                        "route": route_hash,
                        "step": step,
                        "row_index": row_index,
                        "quantity": quantity,
                        "day": step // 24,
                        "hour": step % 24,
                        "on_shop_town_interval_default": step % 4 == 0,
                        "on_center_town_interval_default": step % 24 == 0,
                    }
                )

    steps = sorted({row["step"] for row in rows})
    quantities = sorted({row["quantity"] for row in rows})
    result = {
        "schema": SCHEMA,
        "decision": "AUTHORED_WHEAT_BUYS_PRESENT" if rows else "NO_AUTHORED_WHEAT_BUYS",
        "vendor_git_blob": blob,
        "vendor_sha256": hashlib.sha256(vendor_snapshot).hexdigest(),
        "route_count": len(routes),
        "route_lengths": route_lengths,
        "buy_product_rows_by_item": dict(sorted(all_buy_products.items())),
        "wheat_buy_row_count": len(rows),
        "routes_with_wheat_buys": sorted({row["route"] for row in rows}),
        "wheat_buy_steps": steps,
        "wheat_buy_quantities": quantities,
        "wheat_buy_rows": rows,
        "limits": [
            "read-only authored-route census; no runtime mutation",
            "vendor semantics execute from the authenticated byte snapshot, never a reopened path",
            "does not infer unlocked-shop demand, cash, shed headroom, feed duty or rival flow",
            "does not authorize speculative BUY_PRODUCT WHEAT",
            "a downstream retimer must preserve item and quantity and suppress the exact later authored row",
        ],
    }
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    result["result_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args(argv)
    result = census()
    print(json.dumps(result, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
