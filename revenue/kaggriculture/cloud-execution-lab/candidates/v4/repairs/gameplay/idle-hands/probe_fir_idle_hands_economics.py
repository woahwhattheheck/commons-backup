# SPDX-License-Identifier: Apache-2.0
"""Bind KESTREL's engine witnesses to FIR's exact idle-hands source donor.

This is a focused counterexample test, not a field panel or promotion gate.
Extract b85fc33b48d5ec253ff19031c742da2366e7bbee for the original engine probe.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


def pinned_import(name, path, sha):
    data = path.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if actual != sha:
        raise ValueError(f"{name} pin mismatch: {actual} != {sha}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--helper", type=Path, required=True)
    ap.add_argument("--probe", type=Path, required=True)
    ap.add_argument("--engine-dir", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()
    helper_pin = "dc1f66cddbfcb08b08b226ff5a988ec428e9f016"
    probe_pin = "574512bfa17c66a64a5b507fbcaa0b55ea7d4129"
    h = pinned_import("fir_idle_hands", args.helper, helper_pin)
    p = pinned_import("kestrel_engine_probe", args.probe, probe_pin)
    p.ENGINE, engine_hashes = p.load_engine(args.engine_dir)
    receipt = {"helper_blob": helper_pin, "probe_blob": probe_pin,
               "engine_files": engine_hashes, "candidate_helper_executed": True,
               "v4_field_panel": False, "cash_counterexamples": [], "identity_guards": []}

    class CandidateProbe(unittest.TestCase):
        def test_all_off_exact_identity(self):
            action = {"farmer": ["PASS"], "hands": [], "market": []}
            self.assertIs(h.apply_all(action, object(), object()), action)

        def test_existing_zero_benefit_and_terminal_guards(self):
            for name, step, tile, cargo, switches in (
                ("age4_watered", 117, p.wheat(held=4, watered=True), {"FERTILIZER": 1}, {"wheat_fert": True}),
                ("yield5_cap", 115, p.wheat(held=5), {"FERTILIZER": 1}, {"wheat_fert": True}),
                ("last_refresh_care", 695, p.animal(fed=True), {}, {"care_all": True}),
                ("terminal_feed", 718, p.animal(debt=1), {"WHEAT": 1}, {"feed_all": True}),
            ):
                with self.subTest(name=name):
                    state, env = p.fixture(step, tile, cargo)
                    action = state[0].action
                    snapshot = deepcopy((action, state[0].observation))
                    self.assertIs(h.apply_all(action, state[0].observation, env.configuration, **switches), action)
                    self.assertEqual((action, state[0].observation), snapshot)
                    receipt["identity_guards"].append(name)

        def test_actual_candidate_fert_still_loses_cash_both_seats(self):
            for seat in (0, 1):
                with self.subTest(seat=seat):
                    parent, pe = p.fixture(115, p.wheat(held=3), {"FERTILIZER": 1}, seat=seat)
                    child, ce = deepcopy((parent, pe))
                    action = child[seat].action
                    snapshot = deepcopy((action, child[seat].observation))
                    candidate = h.apply_all(action, child[seat].observation, ce.configuration, wheat_fert=True)
                    self.assertEqual(candidate["farmer"], ["FERTILIZE"])
                    self.assertEqual((action, child[seat].observation), snapshot)
                    self.assertEqual(candidate["hands"], action["hands"])
                    self.assertEqual(candidate["market"], action["market"])
                    p.tick(parent, pe, 115, seat=seat)
                    p.tick(child, ce, 115, candidate["farmer"][0], seat=seat)
                    for state, env in ((parent, pe), (child, ce)):
                        for step, command in ((116, "WATER"), (117, "HARVEST"), (118, "PASS"), (119, "PASS")):
                            p.tick(state, env, step, command, seat=seat)
                        p.tick(state, env, 120, seat=seat, market=[["SELL", "FERTILIZER", 1], ["SELL", "WHEAT", 6]])
                    parent_cash = parent[0].observation.farms[seat]["money"]
                    child_cash = child[0].observation.farms[seat]["money"]
                    self.assertEqual((parent_cash, child_cash), (3197, 3121))
                    receipt["cash_counterexamples"].append({"seat": seat, "activation": "FERTILIZE",
                        "parent_cash": parent_cash, "candidate_cash": child_cash,
                        "delta_cash": child_cash - parent_cash})

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CandidateProbe))
    receipt.update(tests=result.testsRun, status="PASS" if result.wasSuccessful() else "FAIL",
                   errors=len(result.errors), failures=len(result.failures))
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
