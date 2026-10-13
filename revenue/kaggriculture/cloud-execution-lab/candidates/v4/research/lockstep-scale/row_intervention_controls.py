"""Full-interpreter, paired microtrajectory controls for lockstep row interventions.

Research support for the existing lockstep-scale family, NOT a gameplay policy,
observer, episode evaluator, or economic promotion gate. Constructed, capacity-
valid stocks are injected into an official initialized world. A positive result
is not evidence that a live opponent will take the assumed future actions.

python row_intervention_controls.py --runtime EXPANDED_RUNTIME --output report.json
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

PINS = {
    "checks/reference/evaluator/loader.py": "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5",
    "checks/reference/engine/kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "checks/reference/engine/kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "checks/reference/engine/utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}
SCHEMA = "titan-v4-row-intervention-controls-v1"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def integer(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an exact integer in [{low}, {high}]")
    return value


def load_official(runtime: Path):
    """Authenticate every dependency BEFORE importing the existing real loader.

    Its cache is complete, so get_engine cannot enter its download branch.
    The loader compiles the actual upstream seed helper and imports the complete,
    unchanged interpreter. Restore its temporary package entries afterward.
    """
    runtime = Path(runtime).resolve()
    for relative, expected in PINS.items():
        file = runtime / relative
        if not file.is_file():
            raise ValueError(f"Missing pinned dependency: {relative}")
        actual = git_blob(file.read_bytes())
        if actual != expected:
            raise ValueError(f"Pin mismatch for {relative}: {actual} != {expected}")
    path = runtime / "checks/reference/evaluator/loader.py"
    spec = importlib.util.spec_from_file_location("estuary_row_official_loader", path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load the pinned official loader")
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    names = ("kaggle_environments", "kaggle_environments.utils")
    previous = {name: sys.modules.get(name) for name in names}
    try:
        engine, hashes = loader.get_engine(runtime / "checks/reference/engine")
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return engine, loader.Struct, hashes


def action(rows: list) -> dict:
    return {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(rows)}


def fixture(name: str, own_stock: dict, rival_stock: dict, inventory: dict,
            before: list[list], after: list[list], rival: list[list], **overrides) -> dict:
    result = {
        "name": name, "seed": 20260911, "start_step": 101,
        "own_stock": own_stock, "rival_stock": rival_stock,
        "inventory": inventory, "money": [100000, 100000], "shops": [],
        "max_orders": 10,
        "before": [action(rows) for rows in before],
        "after": [action(rows) for rows in after],
        "rival": [action(rows) for rows in rival],
    }
    result.update(overrides)
    return copy.deepcopy(result)


def validate_case(case: dict, engine) -> None:
    if not isinstance(case, dict) or not isinstance(case.get("name"), str):
        raise ValueError("A named case dictionary is required")
    integer(case["seed"], "seed", 0, 2**63 - 1)
    step = integer(case["start_step"], "start_step", 0, 717)
    integer(case["max_orders"], "max_orders", 1, 100)
    for key in ("own_stock", "rival_stock"):
        if not isinstance(case[key], dict) or set(case[key]) - set(engine.PRODUCTS):
            raise ValueError(f"{key} contains unknown products")
        for q in case[key].values():
            integer(q, "stock", 0, 100)
        if sum(case[key].values()) > 100:
            raise ValueError("Constructed stock exceeds standard shed capacity")
    if not isinstance(case["inventory"], dict) or set(case["inventory"]) - set(engine.PRODUCTS):
        raise ValueError("Unknown inventory product")
    for value in case["inventory"].values():
        integer(value, "inventory", -10**6, 10**6)
    if not isinstance(case["money"], list) or len(case["money"]) != 2:
        raise ValueError("Two role-ordered money amounts are required")
    for value in case["money"]:
        integer(value, "money", 0, 10**9)
    if not isinstance(case["shops"], list) or any(x not in engine.SHOPS for x in case["shops"]):
        raise ValueError("Unknown town shop")
    n = len(case["before"])
    integer(n, "trajectory length", 1, 73)
    if step + n > 719 or any(not isinstance(case[k], list) or len(case[k]) != n
                            for k in ("before", "after", "rival")):
        raise ValueError("Trajectories must have equal lengths within the official horizon")
    # Raw market rows, including empty slots/dead tails, are deliberately retained.
    for key in ("before", "after", "rival"):
        for selected in case[key]:
            if not isinstance(selected, dict) or not isinstance(selected.get("market"), list):
                raise ValueError("Each action must carry its original market list")
    digest(case)  # Reject non-JSON/nonfinite fixtures before interpreter execution.


def snapshot(state, seat: int) -> dict:
    farms = copy.deepcopy(state[0].observation.farms)
    order = (seat, 1 - seat)
    cash = [farms[i].pop("money") for i in order]
    for value in cash:
        integer(value, "realized cash", 0, 10**12)
    # Role-normalize all asset state, not just shed quantities.
    assets = {
        "farms": [farms[i] for i in order],
        "private": [copy.deepcopy(state[i].observation.private) for i in order],
        "market": copy.deepcopy(state[0].observation.market),
        "town": copy.deepcopy(state[0].observation.town),
        "day": state[0].observation.day, "hour": state[0].observation.hour,
        "status": [state[i].status for i in order],
    }
    return {"cash": cash, "assets": assets, "assets_sha256": digest(assets)}


def run_world(engine, Struct, case: dict, seat: int, variant: str) -> dict:
    """Run one initialized, detached full-interpreter microtrajectory."""
    integer(seat, "seat", 0, 1)
    if variant not in ("before", "after"):
        raise ValueError("variant must be before or after")
    validate_case(case, engine)
    original = copy.deepcopy(case)
    cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                  for k, v in engine.specification["configuration"].items()})
    cfg.update(seed=case["seed"], maxMarketOrdersPerTurn=case["max_orders"])
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status="ACTIVE", reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    for i, s in enumerate(state):
        s.observation.farms[i]["money"] = case["money"][0 if i == seat else 1]
        stock = case["own_stock"] if i == seat else case["rival_stock"]
        s.observation.private["shed"] = {p: stock.get(p, 0) for p in s.observation.private["shed"]}
    state[0].observation.market["inventory"].update(case["inventory"])
    engine._refresh_prices(state[0].observation.market)
    state[0].observation.town["unlocked_shops"] = list(case["shops"])
    trace = []
    for offset, (ours, theirs) in enumerate(zip(case[variant], case["rival"])):
        for i, s in enumerate(state):
            s.observation.step = case["start_step"] + offset
            s.action = copy.deepcopy(ours if i == seat else theirs)
        engine.interpreter(state, env)
        trace.append({"step": case["start_step"] + offset,
                      "actions": [copy.deepcopy(ours), copy.deepcopy(theirs)],
                      "state": snapshot(state, seat)})
    if case != original:
        raise RuntimeError("The fixture was mutated during detached execution")
    return {"final": trace[-1]["state"], "trace_sha256": digest(trace),
            "interpreter_calls": 1 + len(trace)}


def compare_pair(engine, Struct, case: dict, seat: int) -> dict:
    before = run_world(engine, Struct, case, seat, "before")
    after = run_world(engine, Struct, case, seat, "after")
    do = after["final"]["cash"][0] - before["final"]["cash"][0]
    dr = after["final"]["cash"][1] - before["final"]["cash"][1]
    return {
        "name": case["name"], "seat": seat, "fixture_sha256": digest(case),
        "before_cash": before["final"]["cash"], "after_cash": after["final"]["cash"],
        "delta_own": do, "delta_rival": dr, "delta_margin": do - dr,
        "final_assets_equal": before["final"]["assets"] == after["final"]["assets"],
        "before_assets_sha256": before["final"]["assets_sha256"],
        "after_assets_sha256": after["final"]["assets_sha256"],
        "before_trace_sha256": before["trace_sha256"],
        "after_trace_sha256": after["trace_sha256"],
        "interpreter_calls": before["interpreter_calls"] + after["interpreter_calls"],
    }


def collateral(item="MILK", qty=50, inventory=9899, rival_wheat_slot=1) -> dict:
    if item == "WHEAT":
        raise ValueError("The collateral item must differ from WHEAT")
    integer(qty, "qty", 1, 50)
    integer(rival_wheat_slot, "rival_wheat_slot", 1, 9)
    sell_w, sell_x = ["SELL", "WHEAT", qty], ["SELL", item, qty]
    rival = [sell_x] + [[] for _ in range(rival_wheat_slot - 1)] + [sell_w]
    return fixture(f"collateral-{item}-{qty}-{inventory}-slot{rival_wheat_slot}",
                   {"WHEAT": qty, item: qty}, {"WHEAT": qty, item: qty},
                   {"WHEAT": inventory, item: inventory},
                   [[sell_x], [sell_w]], [[sell_w, sell_x], []], [rival, []])


def named_cases() -> list[dict]:
    w = ["SELL", "WHEAT", 50]
    m = ["SELL", "MILK", 50]
    return [
        collateral(),
        fixture("buyer-reversal", {"WHEAT": 50}, {}, {"WHEAT": 9899},
                [[], [w]], [[w], []], [[["BUY_PRODUCT", "WHEAT", 50]], []]),
        fixture("pure-wheat-dump", {"WHEAT": 50}, {"WHEAT": 50}, {"WHEAT": 9899},
                [[], [w]], [[w], []], [[w], []]),
        fixture("vacant-row0-join", {"WHEAT": 50, "MILK": 50},
                {"WHEAT": 50, "MILK": 50}, {"WHEAT": 9899, "MILK": 9899},
                [[[], m], [w]], [[w, m], []], [[m, w], []]),
        fixture("multi-join-truncates-incumbent-hire", {"WHEAT": 1, "MILK": 1},
                {"WHEAT": 1, "MILK": 1}, {"WHEAT": 9899, "MILK": 9899},
                [[["BUY_SEED", "WHEAT", 1]] * 8 + [["HIRE"]],
                 [["SELL", "WHEAT", 1], ["SELL", "MILK", 1]]],
                [[["SELL", "MILK", 1], ["SELL", "WHEAT", 1]] +
                 [["BUY_SEED", "WHEAT", 1]] * 8, []],
                [[["SELL", "MILK", 1], ["SELL", "WHEAT", 1]], []]),
    ]


def native_horizon(item="MILK", delay=72, shop_copies=4) -> dict:
    """Construct a pure native-product timing intervention over real town ticks.

    Day12 admits up to four unlocked shop instances under standard cadence.
    Whole-episode reachability is still not asserted for the injected world.
    The rival REALLY sells the same product at our join step; there are no
    incumbent own rows, buys, funding dependencies, or extra arrivals.
    """
    product_shop = {"MILK": "SMOOTHIE_SHOP", "CARROT": "PET_CAFE",
                    "STRAWBERRY": "SMOOTHIE_SHOP", "TOMATO": "PIZZA_SHOP",
                    "WOOL": "YARN_STORE"}
    if item not in product_shop:
        raise ValueError("Unsupported native horizon control product")
    integer(delay, "delay", 1, 72)
    integer(shop_copies, "shop_copies", 0, 4)
    before, after, rival = ([[] for _ in range(delay + 1)] for _ in range(3))
    sell = ["SELL", item, 10]
    before[-1] = [sell]
    after[0] = [sell]
    rival[0] = [sell]
    return fixture(f"native-horizon-{item}-{delay}-shops{shop_copies}",
                   {item: 10}, {item: 10}, {item: 9899}, before, after, rival,
                   start_step=301, money=[3000, 3000],
                   shops=[product_shop[item]] * shop_copies)


def validate_pair(row: dict) -> None:
    """Report integrity only; this does NOT declare a positive row ship-ready."""
    integer(row["seat"], "seat", 0, 1)
    for key in ("before_cash", "after_cash"):
        if type(row[key]) is not list or len(row[key]) != 2:
            raise ValueError("Cash must be a two-role vector")
        for value in row[key]:
            integer(value, "cash", 0, 10**12)
    do = row["after_cash"][0] - row["before_cash"][0]
    dr = row["after_cash"][1] - row["before_cash"][1]
    for key, expected in (("delta_own", do), ("delta_rival", dr), ("delta_margin", do - dr)):
        if type(row[key]) is not int or row[key] != expected:
            raise ValueError(f"Incorrect {key}")
    for key in ("fixture_sha256", "before_assets_sha256", "after_assets_sha256",
                "before_trace_sha256", "after_trace_sha256"):
        value = row[key]
        if (type(value) is not str or len(value) != 64 or
                any(c not in "0123456789abcdef" for c in value)):
            raise ValueError(f"Invalid {key}")
    if type(row["final_assets_equal"]) is not bool:
        raise ValueError("Asset equality must be a boolean")
    if row["final_assets_equal"] != (row["before_assets_sha256"] == row["after_assets_sha256"]):
        raise ValueError("Asset equality and state digests disagree")
    integer(row["interpreter_calls"], "interpreter_calls", 4, 148)


def report(engine, Struct) -> dict:
    named = [{"fixture": case,
              "pairs": [compare_pair(engine, Struct, case, seat) for seat in (0, 1)]}
             for case in named_cases()]
    matrix = []
    for item in engine.PRODUCTS:
        if item == "WHEAT":
            continue
        for qty in (1, 10, 25, 50):
            for inv in (9700, 9899, 10000, 10100):
                for slot in (1, 2):
                    case = collateral(item, qty, inv, slot)
                    matrix.extend(compare_pair(engine, Struct, case, s) for s in (0, 1))
    horizon = []
    for item in ("MILK", "CARROT", "STRAWBERRY", "TOMATO", "WOOL"):
        for delay in (1, 24, 48, 72):
            for copies in (0, 1, 4):
                case = native_horizon(item, delay, copies)
                horizon.extend(compare_pair(engine, Struct, case, s) for s in (0, 1))
    controls = []
    for case in named_cases() + [native_horizon()]:
        identity = copy.deepcopy(case)
        identity["after"] = copy.deepcopy(identity["before"])
        controls.extend(compare_pair(engine, Struct, identity, s) for s in (0, 1))
    for row in [p for n in named for p in n["pairs"]] + matrix + horizon + controls:
        validate_pair(row)
    if any(p["delta_margin"] or p["before_trace_sha256"] != p["after_trace_sha256"]
           for p in controls):
        raise RuntimeError("Same-action negative control is not identical")
    return {
        "schema": SCHEMA, "dependency_blobs": PINS,
        "source_blob": git_blob(Path(__file__).read_bytes()),
        "scope": "constructed full-interpreter microtrajectories; no field frequency, whole-game EV, native wiring or promotion claim",
        "fixture_policy": "100-unit sheds; standard game defaults except explicit max_orders; role-swapped paired worlds; PASS units; no external arrivals",
        "named_cases": named, "matrix": matrix, "identity_controls": controls,
        "horizon_primary_fixture": native_horizon(), "horizon": horizon,
        "horizon_summary": {"pairs": len(horizon),
            "negative_margin": sum(r["delta_margin"] < 0 for r in horizon),
            "zero_margin": sum(r["delta_margin"] == 0 for r in horizon),
            "positive_margin": sum(r["delta_margin"] > 0 for r in horizon),
            "all_final_assets_equal": all(r["final_assets_equal"] for r in horizon)},
        "matrix_summary": {"pairs": len(matrix),
            "negative_margin": sum(r["delta_margin"] < 0 for r in matrix),
            "zero_margin": sum(r["delta_margin"] == 0 for r in matrix),
            "positive_margin": sum(r["delta_margin"] > 0 for r in matrix),
            "all_final_assets_equal": all(r["final_assets_equal"] for r in matrix)},
        "interpreter_calls": sum(p["interpreter_calls"] for p in
            [p for n in named for p in n["pairs"]] + matrix + horizon + controls),
        "disposition": "mechanism controls only; keep feature OFF pending native composition and matched field gates",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    engine, Struct, _ = load_official(args.runtime)
    result = report(engine, Struct)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"matrix": result["matrix_summary"], "horizon": result["horizon_summary"],
                      "interpreter_calls": result["interpreter_calls"],
                      "report_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
