# SPDX-License-Identifier: Apache-2.0
"""Offline, unseeded official-market reproductions for order-slot ablations.

This module is evaluation-only. The agent runtime is the patched lab overlay.
No opponent observation or fixture data is passed to the production transform.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
ENGINE_HASHES = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
}
SOURCE_PATH = "revenue/kaggriculture/cloud-widefield-lab/apex_sheep_overlay.py"
ORIGINAL_BLOB = "04b6a493d974ccb25ce1a340185feac63a86ca97"


def load_file(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No Python loader for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_engine(directory: Path, loader: Path) -> tuple[Any, Any]:
    # The reused loader can prepare a cache. This reproduction never does:
    # every byte is present and hash-checked before invoking it.
    for name, expected in ENGINE_HASHES.items():
        actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Pinned engine mismatch: {name}")
    old = load_file(loader, "ordered_ablation_existing_loader")
    if old.ENGINE_REF != ENGINE_REF:
        raise ValueError("The engine loader has a different upstream source pin")
    engine, _ = old.get_engine(directory)
    return engine, old.Struct


def run_market(
    engine: Any, struct: Any, own_orders: list, rival_orders: list,
    *, own_seat: int = 0, product: str = "WOOL", quantity: int = 8,
    inventory_offset: int = 0, cash: int = 1000, max_orders: int = 10,
) -> dict[str, Any]:
    """Execute the actual market phase from a manufactured complete market state."""
    if own_seat not in (0, 1):
        raise ValueError("The fixture seat must be 0 or 1")
    farms = [engine._new_farm(10, cash), engine._new_farm(10, cash)]
    market = engine._new_market()
    market["inventory"][product] += inventory_offset
    engine._refresh_prices(market)
    privates = [engine._new_private(), engine._new_private()]
    for private in privates:
        private["shed"][product] = quantity
    queues = [None, None]
    queues[own_seat], queues[1 - own_seat] = own_orders, rival_orders
    state = [struct(observation=struct(farms=farms, market=market, private=privates[i]),
                    action={"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(queues[i])})
             for i in range(2)]
    env = struct(configuration=struct(boardSize=10, maxMarketOrdersPerTurn=max_orders,
                                       farmHandCostMult=1, shedCapacity=100))
    engine._process_market(state, env)
    return {
        "cash_own_rival": [int(farms[own_seat]["money"]), int(farms[1-own_seat]["money"])],
        "margin": int(farms[own_seat]["money"] - farms[1-own_seat]["money"]),
        "shed_own_rival": [privates[own_seat]["shed"], privates[1-own_seat]["shed"]],
        "seeds_own_rival": [privates[own_seat]["seeds"], privates[1-own_seat]["seeds"]],
        "market": market,
        "hires_own_rival": [farms[own_seat]["hires_today"], farms[1-own_seat]["hires_today"]],
    }


def apply_overlay(overlay: Any, action: dict, name: str = "agent_no_goose") -> dict:
    """Bind a selected action as the component-test input; restore prior parent."""
    calls = []
    previous = overlay._BASE
    def selected_action(obs: dict, cfg: Any = None) -> dict:
        calls.append((obs, cfg))
        return action
    try:
        overlay._BASE = selected_action
        result = getattr(overlay, name)({}, {})
        if len(calls) != 1:
            raise AssertionError(f"Parent called {len(calls)} times, expected one")
        return result
    finally:
        overlay._BASE = previous


def reproduce(root: Path, engine_dir: Path, loader: Path) -> dict:
    engine, struct = load_engine(engine_dir, loader)
    overlay = load_file(root / SOURCE_PATH, "ordered_ablation_overlay")
    action = {"farmer": ["PASS"], "hands": [],
              "market": [["BUY_ANIMAL", "GOOSE", 1], ["SELL", "WOOL", 8]]}
    fixed = apply_overlay(overlay, action)
    legacy = apply_overlay(overlay, action, "agent_no_goose_compacted_legacy")
    records = []
    for seat in (0, 1):
        variants = {}
        for label, candidate in (("original", action), ("slot_preserved", fixed), ("legacy_compacted", legacy)):
            variants[label] = run_market(engine, struct, candidate["market"], [["SELL", "WOOL", 8]], own_seat=seat)
        records.append({"own_seat": seat, "results": variants,
                        "compaction_only_margin_delta": variants["legacy_compacted"]["margin"] - variants["slot_preserved"]["margin"]})
    # A second boundary shows why the queue length itself is semantic.
    capped_action = {"farmer": ["PASS"], "hands": [],
                     "market": [["BUY_ANIMAL", "GOOSE", 1], *([[]] * 9), ["BUY_SEED", "TOMATO", 1]]}
    boundary = {}
    for label, name in (("slot_preserved", "agent_no_goose"), ("legacy_compacted", "agent_no_goose_compacted_legacy")):
        candidate = apply_overlay(overlay, capped_action, name)
        boundary[label] = run_market(engine, struct, candidate["market"], [])
    return {
        "kind": "manufactured_official_engine_regression_not_full_game",
        "game_seeds_consumed": [], "hosted_episodes_replayed": [],
        "upstream_engine_commit": ENGINE_REF, "engine_sha256": ENGINE_HASHES,
        "original_overlay_git_blob": ORIGINAL_BLOB,
        "patched_overlay_sha256": hashlib.sha256((root / SOURCE_PATH).read_bytes()).hexdigest(),
        "paired_seat_witnesses": records,
        "order_limit_boundary": boundary,
        "interpretation": "The 56 margin delta is a fixture witness, not a correction to PR10009's historical full-game scores.",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--engine-dir", type=Path)
    parser.add_argument("--loader", type=Path)
    parser.add_argument("--output", type=Path, default=Path("ordered-ablation-evidence.json"))
    args = parser.parse_args()
    engine = args.engine_dir or args.root / "test_support/engine"
    loader = args.loader or args.root / "test_support/existing_loader.py"
    if not loader.exists():
        loader = args.root / "revenue/kaggriculture/20260907-offline-agent/evaluate.py"
    evidence = reproduce(args.root, engine, loader)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "seat_margin_deltas": [r["compaction_only_margin_delta"] for r in evidence["paired_seat_witnesses"]]}))


if __name__ == "__main__":
    main()
