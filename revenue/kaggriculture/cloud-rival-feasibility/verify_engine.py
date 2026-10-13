# SPDX-License-Identifier: MIT
"""Focused stage correspondence; no game panels, initialization, or policy tests."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import types

from linear_bounds import Limits, verify_certificate
from rival_feasibility import Interval, RivalLedger, check_extension

ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"


def load_engine(root):
    source = Path(root) / "kaggriculture.py"
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if digest != ENGINE_SHA256 or blob != ENGINE_GIT_BLOB:
        raise ValueError("Supply the documented exact official engine file")
    # Stage calls below do not initialize an episode or call seed resolution.
    # The import-only helper raises if accidentally reached; no game behavior is
    # implemented by it. Official module bytes and stage bodies are unchanged.
    def unused_seed_helper(*args, **kwargs):
        raise AssertionError("Episode initialization is outside this stage check")
    helper = types.ModuleType("kaggle_environments.utils")
    helper.resolve_episode_seed = unused_seed_helper
    previous = sys.modules.get("kaggle_environments.utils")
    sys.modules["kaggle_environments.utils"] = helper
    try:
        spec = importlib.util.spec_from_file_location("rill_official_engine", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            del sys.modules["kaggle_environments.utils"]
        else:
            sys.modules["kaggle_environments.utils"] = previous
    return module


def run(root):
    engine = load_engine(root)
    cases = []
    durations = []
    negative_certificates = 0
    limits = Limits(seconds=1.0)
    for product in ("WHEAT", "EGG", "STRAWBERRY"):
        for inventory in (9950, 10000, 100000000):
            for swap in (False, True):
                market = engine._new_market()
                market["inventory"][product] = inventory
                farms = [engine._new_farm(10, 1000) for _ in range(2)]
                privates = [engine._new_private() for _ in range(2)]
                for private in privates:
                    private["shed"][product] = 5
                    if product != "WHEAT":
                        private["shed"]["WHEAT"] = 3
                orders = [[["SELL", product, 3], ["BUY_PRODUCT", "WHEAT", 2]],
                          [["SELL", product, 2], ["BUY_PRODUCT", "WHEAT", 1]]]
                if swap:
                    orders.reverse()
                state = [types.SimpleNamespace(
                    observation=types.SimpleNamespace(market=market, farms=farms, private=privates[seat]),
                    action={"market": orders[seat]}) for seat in range(2)]
                env = types.SimpleNamespace(configuration={"shedCapacity": 100, "boardSize": 10})
                logs = [[], []]
                commit = engine._commit_unit
                def record(op, item, price, farm, private, market, shed_capacity=100):
                    before = farm["money"]
                    ok = commit(op, item, price, farm, private, market, shed_capacity)
                    if ok:
                        seat = next(i for i, other in enumerate(farms) if other is farm)
                        logs[seat].append((op, item, int(abs(farm["money"] - before))))
                    return ok
                engine._commit_unit = record
                try:
                    engine._process_market(state, env)
                finally:
                    engine._commit_unit = commit
                for seat in (0, 1):
                    events = []
                    for op, item, cash in logs[seat]:
                        kind = "sale" if op == "SELL" else "buy"
                        if events and (events[-1]["kind"], events[-1]["product"]) == (kind, item):
                            events[-1]["quantity"] += 1
                            events[-1]["cash"] += cash
                        else:
                            events.append(dict(kind=kind, step=0, product=item, quantity=1, cash=cash))
                    events.append(dict(kind="cash_checkpoint", step=1, cash=int(farms[seat]["money"])))
                    # Runtime input is unknown rival stock plus PUBLIC initial/final
                    # money; private truth was used only by the offline engine.
                    base = RivalLedger(sorted(set((product, "WHEAT"))), 100,
                                       as_of_step=1, cash=Interval(1000, 1000))
                    start = time.perf_counter()
                    result = check_extension(base, events, complete=True)
                    durations.append((time.perf_counter() - start) * 1000)
                    if result.result.status != "possible":
                        raise AssertionError((product, inventory, seat, result))
                    changed = copy.deepcopy(events)
                    changed[0]["cash"] += 1
                    negative = check_extension(base, changed, complete=True, limits=limits)
                    rebuilt = base.fork()
                    for event in changed:
                        rebuilt.event(**event)
                    if negative.keep or not verify_certificate(rebuilt.constraints, negative.result.certificate):
                        raise AssertionError("Altered receipt must contradict exact public cash")
                    negative_certificates += 1
                    # The same cash discrepancy is compatible with an unobserved
                    # nonmarket expense; it must not be pruned when costs unknown.
                    widened = copy.deepcopy(changed)
                    widened.insert(-1, dict(kind="expense", step=0, cash=Interval()))
                    if check_extension(base, widened, complete=True, limits=limits).result.status != "possible":
                        raise AssertionError("Unknown expense was incorrectly set to zero")
                    cases.append({"product": product, "initial_market_inventory": inventory,
                                  "seat": seat, "swapped_orders": swap, "events": events,
                                  "public_final_cash": int(farms[seat]["money"]),
                                  "decision": result.as_dict(), "changed_receipt_rejected": True,
                                  "unknown_expense_retained": True})
    return {"scope": "18 official market stages / 36 per-seat paths; not full games",
            "engine_sha256": ENGINE_SHA256, "engine_git_blob": ENGINE_GIT_BLOB,
            "engine_commit": "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c",
            "accepted_actual_paths": len(cases), "certified_negative_controls": negative_certificates,
            "unknown_expense_cases_retained": len(cases), "max_warm_call_ms": max(durations),
            "timing_includes_base_validation": True, "full_games": 0, "cases": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = run(args.engine_root)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
