"""Executable exact-engine MW2 contracts. Set TITAN_ENGINE_DIR to the pinned bundle."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import seat_market_probe as probe


class SeatMarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get("TITAN_ENGINE_DIR")
        if not configured:
            raise RuntimeError("TITAN_ENGINE_DIR must point to the exact engine/spec/utils bundle")
        cls.directory = Path(configured).resolve()
        cls.engine, cls.sources = probe.load_engine(cls.directory)

    def scenario(self, rows_a, rows_b, *, item="WHEAT", quantity=50, inventory=10000):
        state, env = probe.initialize(self.engine)
        for s in state:
            s.observation.private["shed"][item] = quantity
        state[0].observation.market["inventory"][item] = inventory
        self.engine._refresh_prices(state[0].observation.market)
        state[0].action["market"] = rows_a
        state[1].action["market"] = rows_b
        return state, env

    def test_exact_pins(self):
        self.assertEqual({k: v["git_blob"] for k, v in self.sources.items()}, probe.PINS)
        self.assertEqual(self.sources["kaggriculture.py"]["bytes"], 40356)

    def test_initial_player_before_first_action(self):
        state, _ = probe.initialize(self.engine)
        self.assertEqual([s.observation.player for s in state], [0, 1])
        self.assertEqual([s.observation.step for s in state], [0, 0])
        # initialize() supplied a buy action before calling interpreter; it is not run.
        self.assertEqual([s.observation.private["seeds"]["WHEAT"] for s in state], [0, 0])
        self.assertEqual([f["money"] for f in state[0].observation.farms], [3000, 3000])

    def test_initial_seat_ids_do_not_depend_on_seed(self):
        for seed in (0, 1, 17, 231, 999999):
            with self.subTest(seed=seed):
                state, env = probe.initialize(self.engine, seed)
                self.assertEqual([s.observation.player for s in state], [0, 1])
                self.assertIsNone(env.configuration.seed)
                self.assertEqual(env.info["seed"], seed)

    def test_private_stores_and_actions_not_shared_in_observation(self):
        state, _ = probe.initialize(self.engine)
        state[1].observation.private["shed"]["WOOL"] = 17
        state[1].action["market"] = [["SELL", "WOOL", 17]]
        self.assertEqual(state[0].observation.private["shed"]["WOOL"], 0)
        self.assertIsNot(state[0].observation.private, state[1].observation.private)
        self.assertFalse(hasattr(state[0].observation, "action"))
        self.assertFalse(hasattr(state[0].observation, "seed"))
        self.assertNotIn("private", state[0].observation.farms[1])
        self.assertFalse(self.engine.specification["observation"]["private"]["shared"])

    def test_swap_preserves_public_aliases_and_seat_ids(self):
        state, _ = probe.initialize(self.engine)
        state[0].observation.farms[0]["money"] = 11
        state[1].observation.private["shed"]["WHEAT"] = 4
        other = probe.swapped(state)
        self.assertIs(other[0].observation.farms, other[1].observation.farms)
        self.assertIs(other[0].observation.market, other[1].observation.market)
        self.assertEqual([s.observation.player for s in other], [0, 1])
        self.assertEqual(other[0].observation.private["shed"]["WHEAT"], 4)
        self.assertEqual(other[0].observation.farms[1]["money"], 11)
        self.assertEqual(probe.snapshot(probe.swapped(other)), probe.snapshot(state))

    def test_same_slot_equal_sellers_have_equal_cash(self):
        self.assertEqual(probe.timing_control(self.engine), [4036, 4036])
        self.assertEqual(probe.timing_control(self.engine, reverse=True), [4036, 4036])

    def test_raw_slot_not_physical_seat_controls_timing_witness(self):
        self.assertEqual(probe.timing_control(self.engine, trailing=True), [7655, 314])
        self.assertEqual(probe.timing_control(self.engine, trailing=True, reverse=True), [7655, 314])

    def test_floor_sales_are_cash_positive_inventory_invisible(self):
        state, env = self.scenario([["SELL", "WOOL", 3]], [["SELL", "WOOL", 2]],
                                   item="WOOL", quantity=3, inventory=110000)
        result = probe.market_pair(self.engine, state, env)
        self.assertEqual(result["market"]["inventory"]["WOOL"], 110000)
        self.assertEqual([f["money"] for f in result["farms"]], [3003, 3002])

    def test_opposite_buy_sell_same_slot(self):
        state, env = self.scenario([["SELL", "WHEAT", 2]], [["BUY_PRODUCT", "WHEAT", 2]])
        result = probe.market_pair(self.engine, state, env)
        self.assertEqual(result["market"]["inventory"]["WHEAT"], 10000)
        self.assertEqual([p["shed"]["WHEAT"] for p in result["private"]], [48, 52])

    def test_cash_failure_is_own_state_not_seat_priority(self):
        state, env = self.scenario([["BUY_PRODUCT", "WHEAT", 10]], [["BUY_PRODUCT", "WHEAT", 10]], quantity=0)
        state[0].observation.farms[0]["money"] = 0
        result = probe.market_pair(self.engine, state, env)
        self.assertEqual(result["private"][0]["shed"]["WHEAT"], 0)
        self.assertEqual(result["private"][1]["shed"]["WHEAT"], 10)

    def test_capacity_failure_is_own_state(self):
        state, env = self.scenario([["BUY_PRODUCT", "WHEAT", 2]], [["BUY_PRODUCT", "WHEAT", 2]], quantity=0)
        state[0].observation.private["shed"]["WOOL"] = 100
        result = probe.market_pair(self.engine, state, env)
        self.assertEqual(result["private"][0]["shed"]["WHEAT"], 0)
        self.assertEqual(result["private"][1]["shed"]["WHEAT"], 2)

    def test_atomic_land_hire_and_seed_animal_rows(self):
        rows = [["BUY_LAND"], ["HIRE"], ["BUY_SEED", "WHEAT", 2], ["BUY_ANIMAL", "GOOSE", 1]]
        state, env = self.scenario(rows, list(reversed(rows)), quantity=0)
        result = probe.market_pair(self.engine, state, env)
        for farm, private in zip(result["farms"], result["private"]):
            self.assertEqual(len(farm["hands"]), 1)
            self.assertEqual(len(farm["unlocked_quadrants"]), 2)
            self.assertEqual(private["seeds"]["WHEAT"], 2)
            self.assertEqual(private["shed"]["GOOSE"], 1)

    def test_cap_counts_raw_inert_rows_before_parsing(self):
        for cap in (10, 1, 2, 0, -1):
            with self.subTest(cap=cap):
                count = max(1, cap)
                state, env = self.scenario([[]] * count + [["SELL", "WHEAT", 1]], [["SELL", "WHEAT", 1]])
                env.configuration.maxMarketOrdersPerTurn = cap
                result = probe.market_pair(self.engine, state, env)
                self.assertEqual(result["private"][0]["shed"]["WHEAT"], 50)
                self.assertEqual(result["private"][1]["shed"]["WHEAT"], 49)

    def test_market_pair_does_not_mutate_caller_inputs(self):
        state, env = self.scenario([["SELL", "WHEAT", 1]], [["BUY_PRODUCT", "WHEAT", 1]])
        old_state, old_env = copy.deepcopy(state), copy.deepcopy(env)
        probe.market_pair(self.engine, state, env)
        self.assertEqual(state, old_state)
        self.assertEqual(env, old_env)

    def test_probe_detects_deliberately_sequential_quote_mutant(self):
        state, env = self.scenario([["SELL", "WOOL", 50]], [["SELL", "WOOL", 50]], item="WOOL")
        real_commit = self.engine._commit_unit

        def wrong_commit(op, item, price, farm, private, market, shed_capacity=100):
            if op == "SELL":
                price = self.engine.market_price(item, market["inventory"][item], market.get("params"))
            return real_commit(op, item, price, farm, private, market, shed_capacity)

        with patch.object(self.engine, "_commit_unit", wrong_commit):
            with self.assertRaisesRegex(probe.ProbeError, "player-swap"):
                probe.market_pair(self.engine, state, env)

    def test_seed_zero_disproves_full_episode_symmetry(self):
        witness = probe.eod_control(self.engine, seed=0)
        self.assertTrue(witness["identical_initial_farms"])
        self.assertEqual(witness["weed_tiles_by_seat"], [[], [[0, 3]]])
        self.assertTrue(witness["different_farm_outcomes"])

    def test_randomized_market_player_swap(self):
        rng = random.Random(12655)
        for index in range(256):
            with self.subTest(index=index):
                state, env = probe.synthetic_case(self.engine, rng, index)
                probe.market_pair(self.engine, state, env)

    def test_report_is_deterministic_and_self_hashed(self):
        a = probe.run_probe(self.engine, self.sources, 8)
        b = probe.run_probe(self.engine, self.sources, 8)
        self.assertEqual(a, b)
        digest = a.pop("receipt_sha256")
        self.assertEqual(digest, hashlib.sha256(probe.canonical(a)).hexdigest())

    def test_invalid_case_count_fails_closed(self):
        for value in (0, -1, 100001, True, "10", 2.5):
            with self.subTest(value=value), self.assertRaises(probe.ProbeError):
                probe.run_probe(self.engine, self.sources, value)

    def test_source_byte_drift_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in probe.PINS:
                (root / name).write_bytes((self.directory / name).read_bytes())
            for name in probe.PINS:
                original = (root / name).read_bytes()
                (root / name).write_bytes(original + b"\n")
                with self.subTest(name=name), self.assertRaisesRegex(probe.ProbeError, "pin mismatch"):
                    probe.load_engine(root)
                (root / name).write_bytes(original)

    def test_loader_does_not_pollute_global_modules(self):
        names = ("kaggle_environments", "kaggle_environments.utils")
        before = {name: sys.modules.get(name) for name in names}
        probe.load_engine(self.directory)
        self.assertEqual(before, {name: sys.modules.get(name) for name in names})

    def test_cli_rejects_bad_data_without_overwriting_output(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "receipt.json"
            target.write_text("keep\n")
            result = subprocess.run([sys.executable, str(Path(probe.__file__)), "--engine-dir", str(self.directory),
                                     "--cases", "0", "--output", str(target)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(target.read_text(), "keep\n")

    def test_cli_never_overwrites_pinned_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in probe.PINS:
                (root / name).write_bytes((self.directory / name).read_bytes())
            target = root / "kaggriculture.json"
            before = target.read_bytes()
            result = subprocess.run([sys.executable, str(Path(probe.__file__)), "--engine-dir", str(root),
                                     "--cases", "1", "--output", str(target)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(target.read_bytes(), before)

    def test_cli_emits_identical_file_and_stdout(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "receipt.json"
            result = subprocess.run([sys.executable, str(Path(probe.__file__)), "--engine-dir", str(self.directory),
                                     "--cases", "8", "--output", str(target)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, target.read_bytes())
            self.assertEqual(json.loads(result.stdout)["market_player_swap"]["mismatches"], 0)
            self.assertFalse(list(Path(temp).glob(".seat-receipt-*")))


if __name__ == "__main__":
    unittest.main()
