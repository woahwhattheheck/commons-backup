"""Independent queue contract and full official-interpreter acceptance.

python check_join_queue_contract.py --reference CHECKS_REFERENCE --receipt out.json
Add -O to Python for the optimized run. --unit-only is for fault-injection runs.
The four oracle inputs must already exist and match their pins: no downloads.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

PINS = {
    "evaluator/loader.py": "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5",
    "engine/kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "engine/kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "engine/utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}
STATS = {"interpreter_calls": 0, "actual_transitions": 0, "matrix_pairs": 0, "matrix_negative": 0,
         "matrix_positive": 0, "matrix_zero": 0, "slot_preserving_pairs": 0}
REPORT = {}


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_oracle(reference):
    root = Path(reference)
    for relative, expected in PINS.items():
        data = (root / relative).read_bytes()
        if git_blob(data) != expected:
            raise ValueError("oracle source drift: " + relative)
    loader = load_file("crosscurrent_official_loader", root / "evaluator/loader.py")
    engine, _ = loader.get_engine(root / "engine")
    return engine, loader.Struct


def act(rows):
    return {"farmer": ["PASS"], "hands": [], "market": rows}


def check(before, after, **kw):
    return CONTRACT.certify_join_queue(before, after, item=kw.pop("item", "WHEAT"),
                                        quantity=kw.pop("quantity", 10), **kw)


class QueueTests(unittest.TestCase):
    def test_empty_and_absent_market(self):
        for old in (act([]), {"farmer": ["PASS"], "hands": []}):
            with self.subTest(old=old):
                self.assertTrue(check(old, act([["SELL", "WHEAT", 10]])).slot_safe)

    def test_literal_noops_replace_without_moving_tail(self):
        for noop in (None, [], ["PASS"]):
            old = act([noop, ["SELL", "MILK", 5], [], ["BUY_SEED", "TOMATO", 2]])
            new = copy.deepcopy(old); new["market"][0] = ["SELL", "WHEAT", 10]
            self.assertTrue(check(old, new).slot_safe)

    def test_occupied_row_zero_rejected_below_cap(self):
        for row in (["SELL", "MILK", 50], ["HIRE"], ["BUY_PRODUCT", "FERTILIZER", 1]):
            old = act([row]); new = act([["SELL", "WHEAT", 10], row])
            self.assertFalse(check(old, new).slot_safe)

    def test_unknown_and_conditionally_dead_are_not_literal_noops(self):
        for row in (["UNKNOWN"], ["SELL", "MILK", 0], ["SELL", "MILK"], ["PASS", "extra"], "PASS", {}):
            old = act([row]); new = act([["SELL", "WHEAT", 10]])
            self.assertFalse(check(old, new).slot_safe)

    def test_raw_tail_compaction_and_deletion_rejected(self):
        old = act([[], [], ["SELL", "MILK", 4], None])
        for rows in ([["SELL", "WHEAT", 10], ["SELL", "MILK", 4]],
                     [["SELL", "WHEAT", 10], [], ["SELL", "MILK", 4]]):
            self.assertFalse(check(old, act(rows)).slot_safe)

    def test_tail_reorder_rejected(self):
        old = act([[], ["SELL", "MILK", 4], ["HIRE"]])
        self.assertFalse(check(old, act([["SELL", "WHEAT", 10], ["HIRE"], ["SELL", "MILK", 4]])).slot_safe)

    def test_dead_suffix_must_also_be_identical(self):
        old = act([[], ["HIRE"], ["BUY_LAND"]]); new = copy.deepcopy(old)
        new["market"][0] = ["SELL", "WHEAT", 10]
        self.assertTrue(check(old, new, max_orders=1).slot_safe)
        new["market"][2] = ["PASS"]
        self.assertFalse(check(old, new, max_orders=1).slot_safe)

    def test_full_and_overfull_queues_keep_their_positions(self):
        for length in (10, 11, 20):
            old = act([[]] + [["HIRE"]] * (length - 1)); new = copy.deepcopy(old)
            new["market"][0] = ["SELL", "WHEAT", 10]
            self.assertTrue(check(old, new).slot_safe)
            new["market"] = new["market"][:9]
            self.assertFalse(check(old, new).slot_safe)

    def test_extra_row_added_to_empty_rejected(self):
        self.assertFalse(check(act([]), act([["SELL", "WHEAT", 10], ["HIRE"]])).slot_safe)

    def test_nonmarket_changes_rejected(self):
        old = act([])
        for key, value in (("farmer", ["HARVEST"]), ("hands", [["PASS"]]), ("extra", 1)):
            new = act([["SELL", "WHEAT", 10]]); new[key] = value
            self.assertFalse(check(old, new).slot_safe)

    def test_scalar_types_are_not_equal(self):
        old = act([]); old["metadata"] = {"n": 1}
        for value in (True, 1.0):
            new = act([["SELL", "WHEAT", 10]]); new["metadata"] = {"n": value}
            self.assertFalse(check(old, new).slot_safe)

    def test_exact_join_shape(self):
        for row in (["SELL", "WHEAT", "10"], ["SELL", "WHEAT", 10.0],
                    ["SELL", "WHEAT", 10, "extra"], ["SELL", "MILK", 10], ["PASS"]):
            self.assertFalse(check(act([]), act([row])).slot_safe)

    def test_quantity_validation(self):
        for q in (0, -1, 1001, True, 10.0, "10", None, float("inf")):
            self.assertFalse(check(act([]), act([["SELL", "WHEAT", 10]]), quantity=q).slot_safe)

    def test_product_validation(self):
        for item in ("COW", "wheat", None, [], 3):
            self.assertFalse(check(act([]), act([["SELL", "WHEAT", 10]]), item=item).slot_safe)

    def test_cap_normalization_matches_engine(self):
        old = act([[], ["HIRE"], ["BUY_LAND"]]); new = copy.deepcopy(old)
        new["market"][0] = ["SELL", "WHEAT", 10]
        for raw, effective, hazards in ((0, 1, ()), (-3, 1, ()), ("2", 2, (1,)), (3.9, 3, (1, 2))):
            c = check(old, new, max_orders=raw)
            self.assertTrue(c.slot_safe); self.assertEqual(c.effective_cap, effective)
            self.assertEqual(c.resource_sensitive_slots, hazards)

    def test_invalid_cap_fails_closed(self):
        for cap in (None, float("nan"), float("inf"), "nonsense", []):
            self.assertFalse(check(act([]), act([["SELL", "WHEAT", 10]]), max_orders=cap).slot_safe)

    def test_invalid_action_market_and_missing_join(self):
        for old, new in (([], act([])), (act([]), None), (act(None), act([])),
                         (act([]), act("x")), (act([]), {}), (act([]), act([]))):
            self.assertFalse(check(old, new).slot_safe)

    def test_non_json_inputs_fail_closed(self):
        cyclic = []; cyclic.append(cyclic)
        for value in (float("nan"), float("inf"), (1, 2), {1: "bad"}, cyclic):
            old = act([]); old["meta"] = value
            new = act([["SELL", "WHEAT", 10]]); new["meta"] = value
            self.assertFalse(check(old, new).slot_safe)

    def test_no_mutation_and_repeated_calls_identical(self):
        old = act([[], ["SELL", "MILK", 3]]); new = copy.deepcopy(old)
        new["market"][0] = ["SELL", "WHEAT", 10]
        snapshots = copy.deepcopy((old, new))
        self.assertEqual(check(old, new), check(old, new))
        self.assertEqual((old, new), snapshots)

    def test_certificates_bind_exact_actions(self):
        old = act([]); new = act([["SELL", "WHEAT", 10]])
        c = check(old, new)
        expected = json.dumps(new, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        self.assertEqual(c.after_sha256, hashlib.sha256(expected).hexdigest())
        new["market"][0][2] = 11
        self.assertFalse(check(old, new).slot_safe)
        self.assertNotEqual(c.after_sha256, check(old, new, quantity=11).after_sha256)

    def test_resource_and_same_product_hazards(self):
        tail = [["HIRE"], ["BUY_LAND"], ["BUY_SEED", "TOMATO", 1],
                ["BUY_ANIMAL", "COW", 1], ["BUY_PRODUCT", "WHEAT", 1], ["SELL", "WHEAT", 1]]
        old = act([[]] + tail); new = act([["SELL", "WHEAT", 10]] + tail)
        c = check(old, new)
        self.assertTrue(c.slot_safe)
        self.assertEqual(c.resource_sensitive_slots, (1, 2, 3, 4, 5))
        self.assertEqual(c.same_product_slots, (5, 6))

    def test_hazards_beyond_cap_do_not_execute(self):
        old = act([[], ["BUY_PRODUCT", "WHEAT", 1]])
        new = act([["SELL", "WHEAT", 10], ["BUY_PRODUCT", "WHEAT", 1]])
        c = check(old, new, max_orders=1)
        self.assertEqual(c.resource_sensitive_slots, ())
        self.assertEqual(c.same_product_slots, ())


def execute(seat, own_turns, rival_turns, *, item="WHEAT", other="MILK", qty=10,
            own_other=50, rival_other=50, cash=0, cap=10):
    if type(seat) is not int or seat not in (0, 1) or item == other:
        raise ValueError("invalid fixture seat/product pair")
    if len(own_turns) != len(rival_turns) or len(own_turns) not in (1, 2):
        raise ValueError("fixture requires matched one- or two-step schedules")
    cfg = STRUCT({k: v.get("default") if isinstance(v, dict) else v
                  for k, v in ENGINE.specification["configuration"].items()})
    cfg.seed = 20260911; cfg.maxMarketOrdersPerTurn = cap
    env = STRUCT(configuration=cfg, done=False, info={})
    states = [STRUCT(observation=STRUCT(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
    ENGINE.interpreter(states, env); STATS["interpreter_calls"] += 1
    market = states[0].observation.market
    market["params"] = None
    market["inventory"][item] = ENGINE.MARKET_PARAMS[item]["I0"] - 101
    market["inventory"][other] = ENGINE.MARKET_PARAMS[other]["I0"] - 101
    ENGINE._refresh_prices(market)
    states[0].observation.town["unlocked_shops"] = []
    for i, state in enumerate(states):
        state.observation.farms[i]["money"] = cash
        state.observation.private["shed"] = {item: qty if i == seat else 50,
                                               other: own_other if i == seat else rival_other}
        if sum(state.observation.private["shed"].values()) > 100:
            raise ValueError("fixture violates shed capacity")
    for offset, (ours, rivals) in enumerate(zip(own_turns, rival_turns)):
        for i, state in enumerate(states):
            state.observation.step = 101 + offset
            state.action = act(copy.deepcopy(ours if i == seat else rivals))
        ENGINE.interpreter(states, env); STATS["interpreter_calls"] += 1
        STATS["actual_transitions"] += 1
    return {"cash": [f["money"] for f in states[0].observation.farms],
            "private": [copy.deepcopy(s.observation.private) for s in states],
            "inventory": copy.deepcopy(market["inventory"]),
            "status": [s.status for s in states]}


def paired(seat, item="WHEAT", other="MILK", qty=10, preserve_slot=False):
    old = [["SELL", other, 50]]
    if preserve_slot:
        old.insert(0, ["PASS"])
    new = [["SELL", item, qty], ["SELL", other, 50]]
    rivals = [[["SELL", item, 50], ["SELL", other, 50]], []]
    base = execute(seat, [old, [["SELL", item, qty]]], rivals, item=item, other=other, qty=qty)
    candidate = execute(seat, [new, []], rivals, item=item, other=other, qty=qty)
    delta = [candidate["cash"][i] - base["cash"][i] for i in range(2)]
    return base, candidate, {"own": delta[seat], "rival": delta[1-seat],
                             "margin": delta[seat] - delta[1-seat]}, check(act(old), act(new), item=item, quantity=qty)


class EngineTests(unittest.TestCase):
    def test_cross_product_negative_witness_both_seats(self):
        witnesses = []
        for seat in (0, 1):
            base, candidate, delta, cert = paired(seat)
            self.assertEqual([base["cash"][seat], base["cash"][1-seat]], [12103, 11816])
            self.assertEqual([candidate["cash"][seat], candidate["cash"][1-seat]], [11320, 12633])
            self.assertEqual(delta, {"own": -783, "rival": 817, "margin": -1600})
            self.assertEqual(base["private"], candidate["private"])
            self.assertEqual(base["inventory"], candidate["inventory"])
            self.assertEqual(candidate["status"], ["ACTIVE", "ACTIVE"])
            self.assertFalse(cert.slot_safe)
            witnesses.append({"seat": seat, "base_cash": base["cash"], "candidate_cash": candidate["cash"],
                              "delta": delta, "final_private_and_inventory_equal": True,
                              "certificate": asdict(cert)})
        REPORT["cross_product_witness"] = witnesses

    def test_cross_product_full_interpreter_matrix(self):
        rows = []
        for item in ENGINE.PRODUCTS:
            for other in ENGINE.PRODUCTS:
                if item == other:
                    continue
                for qty in (1, 10, 50):
                    for seat in (0, 1):
                        with self.subTest(item=item, other=other, qty=qty, seat=seat):
                            b, c, d, cert = paired(seat, item, other, qty)
                            self.assertEqual(b["private"], c["private"])
                            self.assertEqual(b["inventory"], c["inventory"])
                            self.assertFalse(cert.slot_safe)
                            STATS["matrix_pairs"] += 1
                            sign = "negative" if d["margin"] < 0 else "positive" if d["margin"] > 0 else "zero"
                            STATS["matrix_" + sign] += 1
                            rows.append([item, other, qty, seat, d["own"], d["rival"], d["margin"]])
        REPORT["matrix_sha256"] = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
        REPORT["matrix_columns"] = ["item", "other", "qty", "seat", "delta_own", "delta_rival", "delta_margin"]
        REPORT["matrix_rows"] = rows

    def test_slot_preserving_positive_controls(self):
        for other in (p for p in ENGINE.PRODUCTS if p != "WHEAT"):
            for seat in (0, 1):
                b, c, d, cert = paired(seat, other=other, preserve_slot=True)
                self.assertTrue(cert.slot_safe)
                self.assertEqual(b["private"], c["private"])
                self.assertEqual(b["inventory"], c["inventory"])
                self.assertEqual(d, {"own": 27, "rival": -26, "margin": 53})
                STATS["slot_preserving_pairs"] += 1

    def test_slot_safe_is_not_resource_neutral(self):
        witnesses = []
        old = [["PASS"], ["BUY_PRODUCT", "FERTILIZER", 5]]
        new = [["SELL", "WHEAT", 10], ["BUY_PRODUCT", "FERTILIZER", 5]]
        cert = check(act(old), act(new))
        self.assertTrue(cert.slot_safe); self.assertEqual(cert.resource_sensitive_slots, (1,))
        for seat in (0, 1):
            kw = {"own_other": 90, "rival_other": 0, "cash": 100000}
            base = execute(seat, [old, [["SELL", "WHEAT", 10]]], [[], []], **kw)
            candidate = execute(seat, [new, []], [[], []], **kw)
            self.assertEqual(base["private"][seat]["shed"].get("FERTILIZER", 0), 0)
            self.assertEqual(candidate["private"][seat]["shed"].get("FERTILIZER", 0), 5)
            self.assertNotEqual(base["private"], candidate["private"])
            witnesses.append({"seat": seat, "base_own_shed": base["private"][seat]["shed"],
                              "candidate_own_shed": candidate["private"][seat]["shed"],
                              "base_cash": base["cash"], "candidate_cash": candidate["cash"]})
        REPORT["resource_sensitive_witness"] = witnesses

    def test_oracle_rejects_each_changed_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in PINS:
                target = root / relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((REFERENCE / relative).read_bytes())
            for relative in PINS:
                target = root / relative; original = target.read_bytes()
                target.write_bytes(original + b"\n")
                with self.assertRaises(ValueError):
                    load_oracle(root)
                target.write_bytes(original)

    def test_missing_oracle_rejected_before_loader_can_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in PINS:
                if relative == "engine/utils.py":
                    continue
                target = root / relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((REFERENCE / relative).read_bytes())
            with self.assertRaises(FileNotFoundError):
                load_oracle(root)

    def test_fixture_rejects_truncated_schedules(self):
        with self.assertRaises(ValueError):
            execute(0, [[], []], [[]])
        with self.assertRaises(ValueError):
            execute(True, [[]], [[]])

    def test_engine_cap_controls_keep_buy_dead(self):
        old = [["PASS"], ["BUY_PRODUCT", "FERTILIZER", 5]]
        new = [["SELL", "WHEAT", 10], ["BUY_PRODUCT", "FERTILIZER", 5]]
        for cap in (0, -2, 1, "1"):
            for seat in (0, 1):
                c = check(act(old), act(new), max_orders=cap)
                self.assertTrue(c.slot_safe); self.assertEqual(c.resource_sensitive_slots, ())
                result = execute(seat, [new], [[]], cap=cap, cash=100000)
                self.assertEqual(result["private"][seat]["shed"].get("FERTILIZER", 0), 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--contract", type=Path, default=Path(__file__).with_name("join_queue_contract.py"))
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--unit-only", action="store_true")
    args = parser.parse_args()
    global CONTRACT, ENGINE, STRUCT, REFERENCE
    CONTRACT = load_file("crosscurrent_contract", args.contract)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QueueTests)
    if not args.unit_only:
        if args.reference is None:
            parser.error("--reference is required unless --unit-only")
        REFERENCE = args.reference
        ENGINE, STRUCT = load_oracle(args.reference)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(EngineTests))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    receipt = {"schema": "titan-v4-crosscurrent-queue-v1", "tests": result.testsRun,
               "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
               "optimized": not __debug__, "unit_only": args.unit_only,
               "contract_blob": git_blob(args.contract.read_bytes()),
               "checker_blob": git_blob(Path(__file__).read_bytes()), "oracle_pins": PINS,
               "scope": "constructed capacity-valid two-step full-interpreter worlds, NOT trajectory reachability, full games or economics promotion",
               **STATS, **REPORT}
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k not in REPORT and k != "oracle_pins"}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)


if __name__ == "__main__":
    main()
