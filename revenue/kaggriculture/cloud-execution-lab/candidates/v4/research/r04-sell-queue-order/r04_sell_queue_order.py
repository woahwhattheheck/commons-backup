#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound R04 SELL queue-index exposure census.

Research only.  Kaggriculture processes market order *indices* sequentially. At
one index both players quote their current unit against the same pre-commit
inventory, commit both units, then continue that order until exhausted before
the engine advances to the next queue index.  Consequently, two players selling
the same product at different queue indices are not simultaneous for that
product: the earlier-index sale can mutate market inventory before the later
seller is quoted.  This tool finds those authored structural exposures in the
canonical R04 effective routes.

The census grants no economic or rewrite authority.  Shed availability, actual
market inventory, price-floor/rounding, opponent selection and all preceding
state still require current-native replay.  It only identifies source-real rows
where SELL-slot order can matter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import types
from pathlib import Path
from typing import Any

EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
EXPECTED_ENGINE_SPEC_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
EXPECTED_TAPES_BLOB = "a43289b9cc5e34a2481fddf652762a7d92f427ef"
EXPECTED_ROUTER_BLOB = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"

ROUTE_STEP = 144
FINAL_PLAN_STEP = 648
LAST_STEP = 718
TAPE_COUNT = 13
TAPE_STEPS = LAST_STEP + 1
MAX_ORDERS = 10
PRODUCTS = frozenset(
    ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
)

HERE = Path(__file__).resolve()
V4_ROOT = HERE.parents[2]
TAPES_PATH = V4_ROOT / "donor" / "overlay" / "r01_tapes.py"
ROUTER_PATH = V4_ROOT / "donor" / "overlay" / "r04_full_router.py"
ENGINE_PATH = V4_ROOT.parent.parent / "reference" / "engine" / "kaggriculture.py"
ENGINE_SPEC_PATH = V4_ROOT.parent.parent / "reference" / "engine" / "kaggriculture.json"

ENGINE_MARKERS = (
    'def _process_market(state, env):',
    'max_orders = max(1, int(get(env.configuration, "maxMarketOrdersPerTurn", 10)))',
    'queues.append(q[:max_orders])',
    'for i in range(max_len):',
    '# Both players see the same pre-commit inventory for this unit.',
    'quoted[player_id] = ("SELL", item, market_price(item, market["inventory"][item], market.get("params")), ostate)',
    'ok = _commit_unit(op, item, price, farms[player_id], privates[player_id], market, shed_capacity)',
    'if price > 1:',
    'market["inventory"][item] += 1',
    '_refresh_prices(market)',
)
ROUTER_MARKERS = (
    "ROUTE_STEP = 144",
    "FINAL_PLAN_STEP = 648",
    "LAST_STEP = 718",
    "tape = self.tapes[state.plan]",
    "action = copy.deepcopy(tape[step])",
)


class SellQueueCensusError(RuntimeError):
    pass


class VerifiedSources:
    __slots__ = ("source_blobs", "max_orders", "tapes_snapshot")

    def __init__(self, *, source_blobs: dict[str, str], max_orders: int, tapes_snapshot: bytes):
        self.source_blobs = dict(source_blobs)
        self.max_orders = max_orders
        self.tapes_snapshot = tapes_snapshot


def _read(path: Path) -> bytes:
    return path.read_bytes()


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _decode(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SellQueueCensusError(f"{label} is not UTF-8") from exc


def _require_markers(text: str, markers: tuple[str, ...], label: str) -> None:
    missing = [m for m in markers if m not in text]
    if missing:
        raise SellQueueCensusError(f"{label} semantics drifted; missing {missing!r}")


def _max_orders(spec_snapshot: bytes) -> int:
    try:
        doc = json.loads(_decode(spec_snapshot, "engine spec"))
        entry = doc["configuration"]["maxMarketOrdersPerTurn"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SellQueueCensusError("maxMarketOrdersPerTurn contract unavailable") from exc
    if not isinstance(entry, dict) or entry.get("type") != "integer":
        raise SellQueueCensusError("maxMarketOrdersPerTurn type drift")
    value = entry.get("default")
    if type(value) is not int or value != MAX_ORDERS:
        raise SellQueueCensusError(
            f"maxMarketOrdersPerTurn default drift: expected {MAX_ORDERS}, got {value!r}"
        )
    return value


def verify_sources(
    *,
    engine_path: Path = ENGINE_PATH,
    engine_spec_path: Path = ENGINE_SPEC_PATH,
    tapes_path: Path = TAPES_PATH,
    router_path: Path = ROUTER_PATH,
) -> VerifiedSources:
    snapshots = {
        "engine_blob": _read(engine_path),
        "engine_spec_blob": _read(engine_spec_path),
        "r01_tapes_blob": _read(tapes_path),
        "r04_full_router_blob": _read(router_path),
    }
    actual = {name: _git_blob(data) for name, data in snapshots.items()}
    expected = {
        "engine_blob": EXPECTED_ENGINE_BLOB,
        "engine_spec_blob": EXPECTED_ENGINE_SPEC_BLOB,
        "r01_tapes_blob": EXPECTED_TAPES_BLOB,
        "r04_full_router_blob": EXPECTED_ROUTER_BLOB,
    }
    for name, want in expected.items():
        if actual[name] != want:
            raise SellQueueCensusError(f"{name} drift: expected {want}, got {actual[name]}")
    _require_markers(_decode(snapshots["engine_blob"], "engine"), ENGINE_MARKERS, "engine")
    _require_markers(_decode(snapshots["r04_full_router_blob"], "router"), ROUTER_MARKERS, "router")
    return VerifiedSources(
        source_blobs=actual,
        max_orders=_max_orders(snapshots["engine_spec_blob"]),
        tapes_snapshot=snapshots["r01_tapes_blob"],
    )


def _load_module_snapshot(source: bytes, source_path: Path):
    module = types.ModuleType("_titan_v4_sell_queue_tapes")
    module.__file__ = str(source_path)
    code = compile(source, str(source_path), "exec")
    exec(code, module.__dict__)
    return module


def load_tapes(*, snapshot: bytes, source_path: Path = TAPES_PATH) -> list[list[dict[str, Any]]]:
    tapes = _load_module_snapshot(snapshot, source_path).load_tapes()
    if len(tapes) != TAPE_COUNT or any(len(t) != TAPE_STEPS for t in tapes):
        raise SellQueueCensusError("canonical tape bank shape drift")
    return tapes


def effective_route(tapes: list[list[dict[str, Any]]], plan: int) -> list[dict[str, Any]]:
    if not 0 <= plan < TAPE_COUNT:
        raise SellQueueCensusError(f"plan out of range: {plan}")
    return tapes[0][:ROUTE_STEP] + tapes[plan][ROUTE_STEP:FINAL_PLAN_STEP] + tapes[2][FINAL_PLAN_STEP:]


def sell_slots(action: Any, *, max_orders: int = MAX_ORDERS) -> list[dict[str, Any]]:
    if type(max_orders) is not int or max_orders <= 0:
        raise SellQueueCensusError("max_orders must be a positive plain integer")
    if not isinstance(action, dict):
        return []
    market = action.get("market")
    if not isinstance(market, list):
        return []
    found = []
    for index, raw in enumerate(market[:max_orders]):
        if not isinstance(raw, list) or len(raw) < 3 or raw[0] != "SELL":
            continue
        item = raw[1]
        if item not in PRODUCTS:
            continue
        try:
            quantity = int(raw[2])
        except (TypeError, ValueError, OverflowError):
            continue
        if quantity <= 0:
            continue
        found.append({"index": index, "item": item, "quantity": quantity})
    return found


def classify_pair(action_a: Any, action_b: Any, *, max_orders: int = MAX_ORDERS) -> dict[str, Any]:
    a = sell_slots(action_a, max_orders=max_orders)
    b = sell_slots(action_b, max_orders=max_orders)
    by_a: dict[str, list[int]] = {}
    by_b: dict[str, list[int]] = {}
    for row in a:
        by_a.setdefault(row["item"], []).append(row["index"])
    for row in b:
        by_b.setdefault(row["item"], []).append(row["index"])
    mismatches = []
    for item in sorted(set(by_a) & set(by_b)):
        for a_index in by_a[item]:
            for b_index in by_b[item]:
                if a_index == b_index:
                    continue
                mismatches.append(
                    {
                        "item": item,
                        "a_index": a_index,
                        "b_index": b_index,
                        "earlier": "a" if a_index < b_index else "b",
                        "a_sell_slot_count": len(a),
                        "b_sell_slot_count": len(b),
                        "a_sell_slot_permutation_available": len(a) >= 2,
                        "b_sell_slot_permutation_available": len(b) >= 2,
                    }
                )
    return {
        "a_sell_slots": a,
        "b_sell_slots": b,
        "a_reorderable": len(a) >= 2,
        "b_reorderable": len(b) >= 2,
        "same_item_index_mismatches": mismatches,
    }


def build_report(tapes: list[list[dict[str, Any]]], sources: VerifiedSources) -> dict[str, Any]:
    routes = [effective_route(tapes, plan) for plan in range(TAPE_COUNT)]
    authored = []
    for plan, route in enumerate(routes):
        for step, action in enumerate(route):
            slots = sell_slots(action, max_orders=sources.max_orders)
            if len(slots) >= 2:
                authored.append({"plan": plan, "step": step, "sell_slots": slots})

    exposures = []
    for plan_a, route_a in enumerate(routes):
        for plan_b, route_b in enumerate(routes):
            for step, (action_a, action_b) in enumerate(zip(route_a, route_b)):
                pair = classify_pair(action_a, action_b, max_orders=sources.max_orders)
                if not pair["same_item_index_mismatches"]:
                    continue
                exposures.append(
                    {
                        "plan_a": plan_a,
                        "plan_b": plan_b,
                        "step": step,
                        "a_sell_slots": pair["a_sell_slots"],
                        "b_sell_slots": pair["b_sell_slots"],
                        "same_item_index_mismatches": pair["same_item_index_mismatches"],
                    }
                )

    return {
        "schema": "titan.v4.r04-sell-queue-order.v1",
        "status": "SOURCE_BOUND_RESEARCH_ONLY",
        "sources": sources.source_blobs,
        "max_market_orders_per_turn": sources.max_orders,
        "theorem": {
            "source_fact": (
                "market queue indices execute sequentially; within one index both players "
                "quote each unit against the same pre-commit inventory, then commit"
            ),
            "structural_exposure": (
                "the same product authored at different SELL queue indices across players "
                "can be quoted after different prior market mutations"
            ),
            "rewrite_authority": "NONE; current-native replay is required",
        },
        "authored_reorderable_steps": authored,
        "cross_route_index_exposures": exposures,
        "totals": {
            "authored_reorderable_steps": len(authored),
            "cross_route_index_exposures": len(exposures),
            "exposure_mismatches": sum(len(row["same_item_index_mismatches"]) for row in exposures),
        },
        "not_claimed": [
            "shed inventory sufficiency",
            "strict price improvement at the realized market inventory",
            "opponent queue prediction",
            "economic uplift",
            "safe queue rewrite",
            "runtime activation or default promotion",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    sources = verify_sources()
    tapes = load_tapes(snapshot=sources.tapes_snapshot)
    report = build_report(tapes, sources)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
