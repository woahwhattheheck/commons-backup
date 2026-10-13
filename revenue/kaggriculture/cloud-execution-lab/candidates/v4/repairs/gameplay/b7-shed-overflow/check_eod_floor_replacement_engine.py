#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Official-engine differential for B7 $1 EOD same-product replacement."""
from __future__ import annotations

import builtins
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import types

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_CONFIG_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
HELPER_BLOB = "7ed47fd01e01158d175234824509af25b2ce1725"
HERE = Path(__file__).resolve().parent
LAB = HERE.parents[4]
ENGINE = LAB / "reference" / "engine" / "kaggriculture.py"
ENGINE_CONFIG = LAB / "reference" / "engine" / "kaggriculture.json"
HELPER = HERE / "eod_floor_replacement.py"
CFG = {"turnsPerDay": 24, "shedCapacity": 100, "maxMarketOrdersPerTurn": 10}


class CheckError(RuntimeError):
    pass


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def capture(path: Path, expected: str, label: str) -> bytes:
    """Read an authority exactly once and authenticate those captured bytes."""
    data = path.read_bytes()
    observed = git_blob_bytes(data)
    if observed != expected:
        raise CheckError(f"{label} drift: {observed}")
    return data


def load_captured(
    name: str,
    path: Path,
    data: bytes,
    *,
    config_path: Path | None = None,
    config_bytes: bytes | None = None,
):
    """Compile/exec captured source bytes; never reopen the verified source path.

    kaggriculture.py reads its adjacent JSON specification at import time. For
    that module only, bind the exact captured JSON bytes to that path through a
    module-local builtins mapping so executed engine authority is
    (engine.py bytes, kaggriculture.json bytes), both captured once.
    """
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    module.__dict__["__name__"] = name

    builtin_map = dict(vars(builtins))
    if config_path is not None:
        if config_bytes is None:
            raise CheckError("captured config bytes required")
        target = str(config_path.resolve())
        real_open = builtins.open

        def pinned_open(file, *args, **kwargs):
            try:
                resolved = str(Path(file).resolve())
            except (TypeError, ValueError, OSError):
                resolved = None
            if resolved == target:
                mode = args[0] if args else kwargs.get("mode", "r")
                if not isinstance(mode, str) or any(flag in mode for flag in ("w", "a", "x", "+")):
                    raise CheckError("engine config authority is read-only")
                if "b" in mode:
                    return io.BytesIO(config_bytes)
                encoding = kwargs.get("encoding") or "utf-8"
                return io.StringIO(config_bytes.decode(encoding))
            return real_open(file, *args, **kwargs)

        builtin_map["open"] = pinned_open

    module.__dict__["__builtins__"] = builtin_map
    code = compile(data, str(path), "exec")
    exec(code, module.__dict__)
    return module


def capture_sources():
    engine_bytes = capture(ENGINE, ENGINE_BLOB, "engine")
    config_bytes = capture(ENGINE_CONFIG, ENGINE_CONFIG_BLOB, "engine config")
    helper_bytes = capture(HELPER, HELPER_BLOB, "helper")
    return {
        "engine_bytes": engine_bytes,
        "config_bytes": config_bytes,
        "helper_bytes": helper_bytes,
        "pins": {
            "engine": git_blob_bytes(engine_bytes),
            "engine_config": git_blob_bytes(config_bytes),
            "helper": git_blob_bytes(helper_bytes),
        },
    }


def capture_once_regression(engine_bytes: bytes, config_bytes: bytes, helper_bytes: bytes) -> bool:
    """Prove pathname replacement after capture cannot change executed bytes."""
    with tempfile.TemporaryDirectory(prefix="b7-capture-once-") as raw:
        root = Path(raw)
        engine_path = root / "kaggriculture.py"
        config_path = root / "kaggriculture.json"
        helper_path = root / "eod_floor_replacement.py"
        engine_path.write_bytes(engine_bytes)
        config_path.write_bytes(config_bytes)
        helper_path.write_bytes(helper_bytes)

        captured_engine = engine_path.read_bytes()
        captured_config = config_path.read_bytes()
        captured_helper = helper_path.read_bytes()

        engine_path.write_text("raise RuntimeError('reopened engine path')\n")
        config_path.write_text("{not-json")
        helper_path.write_text("raise RuntimeError('reopened helper path')\n")

        engine = load_captured(
            "_b7_capture_engine",
            engine_path,
            captured_engine,
            config_path=config_path,
            config_bytes=captured_config,
        )
        helper = load_captured("_b7_capture_helper", helper_path, captured_helper)
        if engine.PRICE_FLOOR != 1 or not callable(helper.analyze):
            raise CheckError("capture-once regression loaded unexpected authority")
    return True


def floor_stock(engine, item: str) -> int:
    p = engine.MARKET_PARAMS[item]
    start = int(p["I0"])
    if engine.market_price(item, start, None) == 1:
        return start
    delta = max(1, int(p["T"]))
    for _ in range(64):
        stock = start + delta
        if engine.market_price(item, stock, None) == 1:
            return stock
        delta *= 2
    raise CheckError(f"no exact floor stock found for {item} within 64 doublings")


def base_state(engine, helper, item: str, room: int, overflow: int):
    farm = engine._new_farm(10, 100)
    private = engine._new_private()
    private["shed"][item] = 20
    private["shed"]["WHEAT"] = 80
    private["inventories"] = [{item: room + overflow}]
    market = engine._new_market()
    market["inventory"][item] = floor_stock(engine, item)
    engine._refresh_prices(market)
    obs = {
        "step": 23,
        "player": 0,
        "farms": [copy.deepcopy(farm)],
        "private": copy.deepcopy(private),
        "market": copy.deepcopy(market),
    }
    rows = [] if room == 0 else [["SELL", "WHEAT", room]]
    action = {"farmer": ["PASS"], "hands": [], "market": rows}
    decision = helper.analyze(obs, action, CFG, market_price_fn=engine.market_price)
    if not decision.get("admit"):
        raise CheckError(f"helper rejected {item=} {room=} {overflow=}: {decision}")
    if decision["proposal"] != ["SELL", item, overflow]:
        raise CheckError(f"proposal mismatch: {decision}")
    return farm, private, market, action, decision


def execute_sell_row(engine, farm, private, market, row):
    if not isinstance(row, list) or len(row) != 3 or row[0] != "SELL":
        raise CheckError(f"bad checker row {row}")
    item, requested = row[1], row[2]
    remaining = requested
    while remaining > 0:
        quote = engine.market_price(item, market["inventory"][item], market.get("params"))
        if not engine._commit_unit("SELL", item, quote, farm, private, market, 100):
            break
        remaining -= 1
    engine._refresh_prices(market)
    return requested - remaining


def run_cell(engine, helper, item: str, room: int, overflow: int):
    farm, private, market, action, decision = base_state(engine, helper, item, room, overflow)
    baseline_farm = copy.deepcopy(farm)
    baseline_private = copy.deepcopy(private)
    baseline_market = copy.deepcopy(market)
    candidate_farm = copy.deepcopy(farm)
    candidate_private = copy.deepcopy(private)
    candidate_market = copy.deepcopy(market)

    for row in action["market"]:
        sold0 = execute_sell_row(engine, baseline_farm, baseline_private, baseline_market, row)
        sold1 = execute_sell_row(engine, candidate_farm, candidate_private, candidate_market, row)
        if sold0 != row[2] or sold1 != row[2]:
            raise CheckError("prefix SELL did not execute exactly")

    proposal = decision["proposal"]
    before_public_x = candidate_market["inventory"][item]
    sold_replacement = execute_sell_row(engine, candidate_farm, candidate_private, candidate_market, proposal)
    if sold_replacement != overflow:
        raise CheckError("replacement SELL did not execute exactly")
    if candidate_market["inventory"][item] != before_public_x:
        raise CheckError("floor SELL changed public X inventory")
    if candidate_market != baseline_market:
        raise CheckError("public market post-prefix/post-replacement mismatch")

    engine._drop_inventories_to_shed(baseline_private, 100)
    engine._drop_inventories_to_shed(candidate_private, 100)
    if candidate_private["shed"] != baseline_private["shed"]:
        raise CheckError("final shed mismatch")
    if candidate_private["inventories"] != baseline_private["inventories"]:
        raise CheckError("final inventory mismatch")
    gain = candidate_farm["money"] - baseline_farm["money"]
    if gain != overflow:
        raise CheckError(f"cash gain mismatch: {gain} != {overflow}")
    return gain


def run_rival_floor_stability(engine, helper):
    checked = 0
    for item in sorted(helper.NONBUYABLE_PRODUCTS):
        market = engine._new_market()
        market["inventory"][item] = floor_stock(engine, item)
        engine._refresh_prices(market)
        before = copy.deepcopy(market)
        rival_farm = engine._new_farm(10, 100)
        rival_private = engine._new_private()
        rival_private["shed"][item] = 3
        quote = engine.market_price(item, market["inventory"][item], market.get("params"))
        if quote != 1:
            raise CheckError(f"non-floor rival setup {item}: {quote}")
        if not engine._commit_unit("SELL", item, quote, rival_farm, rival_private, market, 100):
            raise CheckError(f"rival SELL failed {item}")
        engine._refresh_prices(market)
        if market != before:
            raise CheckError(f"rival floor SELL changed public market for {item}")
        checked += 1
    return checked


def run():
    captured = capture_sources()
    engine = load_captured(
        "_b7_floor_engine",
        ENGINE,
        captured["engine_bytes"],
        config_path=ENGINE_CONFIG,
        config_bytes=captured["config_bytes"],
    )
    helper = load_captured("_b7_floor_helper", HELPER, captured["helper_bytes"])
    if not capture_once_regression(
        captured["engine_bytes"], captured["config_bytes"], captured["helper_bytes"]
    ):
        raise CheckError("capture-once regression failed")

    expected_nonbuyable = set(engine.PRODUCTS) - {"WHEAT", "FERTILIZER"}
    if set(helper.NONBUYABLE_PRODUCTS) != expected_nonbuyable:
        raise CheckError("non-buyable product domain drift")

    cells = 0
    gain = 0
    by_item = {}
    for item in sorted(helper.NONBUYABLE_PRODUCTS):
        item_cells = 0
        for room in (0, 1, 2, 3):
            for overflow in (1, 2, 3, 4):
                gain += run_cell(engine, helper, item, room, overflow)
                cells += 1
                item_cells += 1
        by_item[item] = item_cells

    rival = run_rival_floor_stability(engine, helper)
    return {
        "status": "PASS",
        "scope": "official-engine B7 floor SELL + EOD same-product replacement; default-OFF/unwired",
        "pins": captured["pins"],
        "capture_once_path_swap_regression": True,
        "cells": cells,
        "cash_gain_sum": gain,
        "cells_by_item": by_item,
        "rival_floor_sell_stability_items": rival,
        "nonbuyable_products": sorted(helper.NONBUYABLE_PRODUCTS),
    }


def main() -> int:
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
