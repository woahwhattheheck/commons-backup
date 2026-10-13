# SPDX-License-Identifier: Apache-2.0
"""Offline conformance against the existing, unchanged Arlene controller.

No games or source downloads. Reports scheduled-prefix compatibility only.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from commitment_window import inspect_commitment, program_boundary

ARLENE_SHA256 = "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4"
MAIN = "7015cc00acfa4922"
SHEEP = "dc76e4003029ac51"


def check(file: Path) -> dict:
    data = file.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != ARLENE_SHA256:
        raise ValueError("Arlene source differs from the recorded consumed revision")
    spec = importlib.util.spec_from_file_location("commitment_actual_arlene", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    controller = module.Agent()
    original_routes = deepcopy(controller.R)
    original_cur = controller.cur
    pairs, comparisons = [], 0
    start = time.perf_counter()
    for current in controller.R:
        controller.cur = current  # evaluator setup; the callable never changes it
        for target in controller.R:
            boundary = program_boundary(controller.R[current], controller.R[target])
            accepted = []
            for now in range(boundary.decision_stop):
                expected = controller._switch_ok(target, now)
                observed = not boundary.same_object and boundary.prefix_matches(now)
                assert expected == observed, (current, target, now)
                comparisons += 1
                if expected:
                    accepted.append(now)
            pairs.append({"current": current, "target": target,
                          "first_difference": boundary.first_difference,
                          "actual_first_matching_checkpoint": accepted[0] if accepted else None,
                          "actual_last_matching_checkpoint": accepted[-1] if accepted else None,
                          "actual_matching_checkpoint_count": len(accepted),
                          "first_farmer_difference": boundary.first_farmer_difference,
                          "first_hands_difference": boundary.first_hands_difference,
                          "first_market_difference": boundary.first_market_difference,
                          "current_program_sha256": boundary.current_sha256,
                          "target_program_sha256": boundary.target_sha256})
    controller.cur = MAIN
    primary = inspect_commitment(controller, SHEEP, 226)
    assert primary["first_difference"] == 226
    assert primary["first_market_slot"] == 2
    assert primary["first_hands_difference"] == 252
    assert primary["first_farmer_difference"] == 360
    assert primary["controller_accepts_now"] and not primary["can_wait_one_structurally"]
    later = [inspect_commitment(controller, SHEEP, t) for t in (227, 240, 252, 360)]
    assert all(not item["controller_accepts_now"] for item in later)
    assert controller.cur == MAIN and controller.R == original_routes
    controller.cur = original_cur
    cost_changes = []
    for step in (226, 241):
        aa = controller.R[MAIN][step]["market"]
        bb = controller.R[SHEEP][step]["market"]
        for slot, (a, b) in enumerate(zip(aa, bb)):
            if a != b:
                cost_changes.append({"step": step, "slot": slot,
                                     "current_order": a, "target_order": b})
    return {"status": "PASS", "scope": "actual_controller_scheduled_prefix_conformance",
            "source_sha256": digest,
            "source_git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
            "source_artifact": 10030763484,
            "source_pin": "3708a125158b6e39ffaf61b6e9e54b632eb2760e",
            "comparison_count": comparisons, "mismatches": 0,
            "pairs": pairs, "main_to_sheep_at_226": primary,
            "later_checkpoints": [{"now": item["now"],
                                   "controller_accepts_now": item["controller_accepts_now"],
                                   "predicate_agrees": item["predicate_agrees"]} for item in later],
            "first_two_capital_queue_changes": cost_changes,
            "routes_unchanged": True, "parent_action_calls": 0,
            "games": 0, "new_seeds": [], "elapsed_seconds": time.perf_counter() - start}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arlene-file", type=Path,
                        default=Path(__file__).resolve().parent.parent /
                        "cloud-titan-composition/vendor/sell/reference/next-panel/vendor/arlene.py")
    parser.add_argument("--output", type=Path, default=Path("commitment-results.json"))
    args = parser.parse_args()
    report = check(args.arlene_file)
    report["consumer_sha256"] = {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("commitment_window.py", "check_commitment_window.py", "test_commitment_window.py")}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "comparisons": report["comparison_count"],
                      "mismatches": report["mismatches"],
                      "latest_main_sheep_choice": report["main_to_sheep_at_226"]["last_equal_prefix_checkpoint"],
                      "elapsed_seconds": report["elapsed_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
