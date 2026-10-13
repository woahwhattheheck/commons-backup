"""Equal-horizon full-interpreter controls for adjacent raw BUY phasing.

This consumes the existing lockstep-scale full-interpreter harness from an exact
Git-blob snapshot.  It compares one official callback against one official
callback: there is no synthetic next-callback/wait baseline and no opponent
prediction.  The three constructed cases are research controls only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import types
from pathlib import Path
from typing import Any

CONTRACT_GIT_BLOB = "45df2f3eb2dc53720f2bdcaa795f04dddd88aa17"
HARNESS_GIT_BLOB = "eedbb09261c0bc3a11d33a34e0d50b81139ddb98"
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _module_snapshot(path: Path, expected: str, name: str):
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != expected:
        raise ValueError(f"source pin mismatch for {path}: {actual} != {expected}")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(data, str(path), "exec"), module.__dict__, module.__dict__)
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module.__dict__


def action(rows: list) -> dict:
    return {"farmer": ["PASS"], "hands": [], "market": rows}


def case_specs() -> list[dict[str, Any]]:
    buy = ["BUY_PRODUCT", "WHEAT", 10]
    sell = ["SELL", "WHEAT", 10]
    return [
        {
            "name": "delay-buy-behind-rival-sell",
            "own_stock": {"WHEAT": 0},
            "rival_stock": {"WHEAT": 10},
            "inventory": {"WHEAT": 10000},
            "before_rows": [buy, []],
            "after_rows": [[], buy],
            "rival_rows": [sell, []],
            "expected_direction": "delay_one_slot",
            "expected_relation": "delta_own_positive",
        },
        {
            "name": "advance-buy-to-rival-buy-phase",
            "own_stock": {"WHEAT": 0},
            "rival_stock": {"WHEAT": 0},
            "inventory": {"WHEAT": 10000},
            "before_rows": [[], buy],
            "after_rows": [buy, []],
            "rival_rows": [["BUY_PRODUCT", "WHEAT", 10], []],
            "expected_direction": "advance_one_slot",
            "expected_relation": "delta_own_positive",
        },
        {
            "name": "no-rival-row-phase-control",
            "own_stock": {"WHEAT": 0},
            "rival_stock": {"WHEAT": 0},
            "inventory": {"WHEAT": 10000},
            "before_rows": [buy, []],
            "after_rows": [[], buy],
            "rival_rows": [[], []],
            "expected_direction": "delay_one_slot",
            "expected_relation": "delta_own_zero",
        },
    ]


def validate_specs(contract_ns: dict[str, Any]) -> list[dict[str, Any]]:
    certify = contract_ns.get("certify_adjacent_buy_phase")
    if not callable(certify):
        raise ValueError("authenticated contract has no certifier")
    out = []
    for spec in case_specs():
        cert = certify(action(spec["before_rows"]), action(spec["after_rows"]), max_orders=10)
        if not cert.admitted or cert.direction != spec["expected_direction"]:
            raise ValueError(f"constructed case does not satisfy raw-phase contract: {spec['name']}")
        out.append({
            "name": spec["name"],
            "direction": cert.direction,
            "item": cert.item,
            "quantity": cert.quantity,
            "source_slot": cert.source_slot,
            "target_slot": cert.target_slot,
        })
    return out


def build_report(runtime: Path, package_dir: Path | None = None) -> dict[str, Any]:
    package_dir = (package_dir or Path(__file__).resolve().parent).resolve()
    contract_ns = _module_snapshot(package_dir / "raw_phase_contract.py", CONTRACT_GIT_BLOB,
                                   "titan_raw_phase_contract_snapshot")
    harness_ns = _module_snapshot(package_dir / "row_intervention_controls.py", HARNESS_GIT_BLOB,
                                  "titan_row_intervention_snapshot")
    validate_specs(contract_ns)
    pins = harness_ns.get("PINS")
    if type(pins) is not dict or pins.get("checks/reference/engine/kaggriculture.py") != ENGINE_GIT_BLOB:
        raise ValueError("full-interpreter harness engine pin drift")
    load_official = harness_ns.get("load_official")
    fixture = harness_ns.get("fixture")
    compare_pair = harness_ns.get("compare_pair")
    if not all(callable(fn) for fn in (load_official, fixture, compare_pair)):
        raise ValueError("authenticated harness API incomplete")
    engine, Struct, hashes = load_official(Path(runtime))

    rows: list[dict[str, Any]] = []
    for spec in case_specs():
        case = fixture(
            spec["name"],
            spec["own_stock"],
            spec["rival_stock"],
            spec["inventory"],
            [spec["before_rows"]],
            [spec["after_rows"]],
            [spec["rival_rows"]],
        )
        for seat in (0, 1):
            row = compare_pair(engine, Struct, case, seat)
            relation = (
                row["delta_own"] > 0 if spec["expected_relation"] == "delta_own_positive"
                else row["delta_own"] == 0
            )
            rows.append({
                **row,
                "expected_relation": spec["expected_relation"],
                "relation_holds": relation,
            })

    all_equal_horizon = all(row["interpreter_calls"] == 4 for row in rows)
    # compare_pair runs two arms; each one-callback arm initializes once and then
    # executes exactly one tested callback => 2 interpreter calls per arm.
    return {
        "schema": "titan.v4.lockstep-raw-phase-engine-controls.v1",
        "policy_authorized": False,
        "opponent_prediction": False,
        "contract_git_blob": CONTRACT_GIT_BLOB,
        "harness_git_blob": HARNESS_GIT_BLOB,
        "engine_git_blob": ENGINE_GIT_BLOB,
        "engine_hashes": hashes,
        "equal_horizon_interpreter_calls": all_equal_horizon,
        "all_relations_hold": all(row["relation_holds"] for row in rows),
        "all_final_assets_equal": all(row["final_assets_equal"] for row in rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.runtime)
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
