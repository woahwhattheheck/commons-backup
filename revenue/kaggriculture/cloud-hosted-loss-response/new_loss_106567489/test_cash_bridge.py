"""Arithmetic controls and actual pinned-interpreter fixtures; no scored games."""
import copy
from fractions import Fraction
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import cash_bridge as cb


def simple_trace(events, observed=(10, 0), status="RECONCILED"):
    return {"configuration": {"turnsPerDay": 24}, "engine_ref": cb.ENGINE_REF,
        "episode_id": 123, "opening": [{"cash": 100}, {"cash": 100}],
        "terminal": [{"cash": 100+observed[0]}, {"cash": 100+observed[1]}],
        "transitions": [{"frame": 1, "action_step": 0,
            "observed_cash_delta": list(observed), "audit": {"status": status, "events": events}}]}


def sale(seat, cash, item="WHEAT"):
    return {"kind": "trade", "op": "SELL", "item": item,
            "seat": seat, "cash_delta": cash, "success": True}


class ArithmeticTests(unittest.TestCase):
    def test_symmetric_price_volume_identity(self):
        r = cb.price_volume([2, 4], [Fraction(10), Fraction(28)], 0)
        self.assertEqual(r["volume_component"], -12)
        self.assertEqual(r["realized_price_component"], -6)
        self.assertEqual(r["own_minus_rival_proceeds"], -18)

    def test_exact_fractional_identity(self):
        r = cb.price_volume([3, 2], [Fraction(10), Fraction(9)], 0)
        self.assertEqual(r["volume_component"], Fraction(47, 12))
        self.assertEqual(r["realized_price_component"], Fraction(-35, 12))
        self.assertEqual(cb.jsonable(r)["volume_component"], {"numerator": 47, "denominator": 12})

    def test_one_sided_revenue_is_not_fabricated_price(self):
        r = cb.price_volume([0, 3], [Fraction(0), Fraction(10)], 1)
        self.assertEqual(r["undecomposed_proceeds"], 10)
        self.assertEqual(r["average_price_by_seat"], [None, Fraction(10, 3)])
        self.assertIsNone(r["volume_component"])
        self.assertIsNone(r["realized_price_component"])

    def test_price_quantity_inconsistency_rejected(self):
        with self.assertRaises(ValueError):
            cb.price_volume([0, 1], [Fraction(5), Fraction(5)], 0)

    def test_finite_numeric_inputs(self):
        for bad in (True, "1", float("nan"), float("inf")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cb.number(bad)

    def test_mismatch_events_never_become_attributed_sales(self):
        trace = simple_trace([sale(0, 10)], status="MISMATCH")
        r = cb.build_bridge(trace, 0)
        self.assertFalse(r["all_cash_attributed"])
        self.assertEqual(r["unverified_cash_delta_by_seat"], [10, 0])
        self.assertEqual(r["sales_by_product"], {})
        self.assertIsNone(r["largest_favorable_changes"][0]["cash_by_cause"])

    def test_unavailable_stays_unassigned(self):
        r = cb.build_bridge(simple_trace([], observed=(-9, 6), status="UNAVAILABLE"), 1)
        self.assertEqual(r["terminal_margin"], 15)
        self.assertEqual(r["unverified_cash_delta_by_seat"], [-9, 6])

    def test_residual_is_not_zeroed(self):
        r = cb.build_bridge(simple_trace([sale(0, 7)]), 0)
        self.assertEqual(r["reconciled_cash_residual_by_seat"], [3, 0])
        self.assertTrue(r["arithmetic_bridge_exact"])
        self.assertFalse(r["all_cash_attributed"])

    def test_offsetting_residuals_still_incomplete(self):
        trace = simple_trace([sale(0, 7)])
        trace["transitions"].append({"frame": 2, "action_step": 1,
            "observed_cash_delta": [0, 0], "audit": {"status": "RECONCILED", "events": [sale(0, 3)]}})
        r = cb.build_bridge(trace, 0)
        self.assertEqual(r["reconciled_cash_residual_by_seat"], [0, 0])
        self.assertFalse(r["all_cash_attributed"])

    def test_terminal_or_frame_cash_mismatch_rejected(self):
        for key in ("terminal", "frame"):
            trace = simple_trace([sale(0, 10)])
            if key == "terminal":
                trace["terminal"][0]["cash"] += 1
            else:
                trace["transitions"][0]["farms_after"] = [{"cash": 111}, {"cash": 100}]
            with self.subTest(key=key), self.assertRaises(ValueError):
                cb.build_bridge(trace, 0)

    def test_reported_residual_must_match(self):
        trace = simple_trace([sale(0, 7)])
        trace["transitions"][0]["cash_residual"] = [0, 0]
        with self.assertRaises(ValueError):
            cb.build_bridge(trace, 0)

    def test_seat_flip_and_input_immutability(self):
        trace = simple_trace([sale(0, 10)])
        original = copy.deepcopy(trace)
        self.assertEqual(cb.build_bridge(trace, 0)["terminal_margin"], 10)
        self.assertEqual(cb.build_bridge(trace, 1)["terminal_margin"], -10)
        self.assertEqual(trace, original)

    def test_bad_seat_and_frame_order(self):
        for s in (True, 2, -1, "0"):
            with self.subTest(s=s), self.assertRaises(ValueError):
                cb.build_bridge(simple_trace([]), s)
        trace = simple_trace([sale(0, 10)])
        trace["transitions"][0]["frame"] = 2
        with self.assertRaises(ValueError):
            cb.build_bridge(trace, 0)

    def test_failed_trade_has_no_quantity(self):
        event = sale(0, 0)
        event["success"] = False
        r = cb.build_bridge(simple_trace([event], observed=(0, 0)), 0)
        self.assertEqual(r["sales_by_product"], {})
        self.assertTrue(r["all_cash_attributed"])


class OfficialEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Required dependency: no skipped real-engine test reported as a pass.
        cls.engine_dir = Path(os.environ["KAG_ENGINE_DIR"])
        cls.rowan = cb.load_trace_module()
        cls.ev = cls.rowan.evaluator()
        cls.engine, cls.hashes = cls.ev.get_engine(cls.engine_dir)

    def replay(self, batches, *, initial_step=0, cash=(3000, 3000), stocks=None):
        ev, engine = self.ev, self.engine
        cfg = ev.Struct({k: v.get("default") if isinstance(v, dict) else v
                         for k, v in engine.specification["configuration"].items()})
        # A deterministic manufactured-state initializer, not a tournament seed.
        cfg.seed = 7
        env = ev.Struct(configuration=cfg, done=False, info={})
        states = [ev.Struct(observation=ev.Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
        engine.interpreter(states, env)
        env.info["EpisodeId"] = 123
        for s in (0, 1):
            states[0].observation.farms[s]["money"] = cash[s]
            states[s].observation.private["shed"] = copy.deepcopy((stocks or ({"WHEAT": 20}, {"WHEAT": 20}))[s])
            states[s].observation.step = initial_step
            states[s].observation.day = initial_step // cfg.turnsPerDay
            states[s].observation.hour = initial_step % cfg.turnsPerDay
        frames = [copy.deepcopy(states)]
        for i, actions in enumerate(batches):
            step = initial_step+i
            for s in (0, 1):
                states[s].observation.step = step
                states[s].action = copy.deepcopy(actions[s])
            engine.interpreter(states, env)
            for s in (0, 1):
                states[s].observation.step = step+1
                # Framework-reported reward for the retained observation.
                states[s].reward = float(states[0].observation.farms[s]["money"])
            frames.append(copy.deepcopy(states))
        return {"configuration": dict(cfg), "info": dict(env.info), "steps": frames}

    def analyze(self, replay):
        return self.rowan.analyze(replay, self.engine, self.ev)

    def test_actual_different_volumes_complete_bridge(self):
        replay = self.replay([[{"market": [["SELL", "WHEAT", 2]]}, {"market": [["SELL", "WHEAT", 4]]}]])
        trace = self.analyze(replay)
        self.assertEqual(trace["transition_statuses"], {"RECONCILED": 1})
        r = cb.build_bridge(trace, 1)
        self.assertTrue(r["all_cash_attributed"])
        self.assertEqual(r["sales_by_product"]["WHEAT"]["units_by_seat"], [2, 4])
        self.assertEqual(r["attributed_cash_delta_by_seat"], trace["transitions"][0]["observed_cash_delta"])

    def test_actual_timing_changes_realized_prices(self):
        replay = self.replay([
            [{"market": [["SELL", "WHEAT", 10]]}, {}],
            [{}, {"market": [["SELL", "WHEAT", 10]]}]])
        r = cb.build_bridge(self.analyze(replay), 1)
        sale_info = r["sales_by_product"]["WHEAT"]
        self.assertEqual(sale_info["volume_component"], 0)
        self.assertNotEqual(sale_info["average_price_by_seat"][0], sale_info["average_price_by_seat"][1])
        self.assertEqual(sale_info["realized_price_component"], r["terminal_margin"])

    def test_actual_capital_and_ordered_sale_funding(self):
        replay = self.replay([[{"market": [["SELL", "WHEAT", 3], ["BUY_SEED", "TOMATO", 1], ["HIRE"]]}, {}]], cash=(0, 0))
        trace = self.analyze(replay)
        r = cb.build_bridge(trace, 0)
        self.assertTrue(r["all_cash_attributed"])
        causes = {c["cause"]: c for c in r["cash_by_cause"]}
        self.assertIn("trade:BUY_SEED:TOMATO", causes)
        self.assertIn("trade:SELL:WHEAT", causes)
        self.assertIn("hire", causes)
        self.assertEqual(r["terminal_margin"], trace["terminal"][0]["cash"])

    def test_actual_insufficient_sale_funding_retained(self):
        replay = self.replay([[{"market": [["SELL", "WHEAT", 2], ["BUY_SEED", "TOMATO", 1], ["HIRE"]]}, {}]], cash=(0, 0))
        r = cb.build_bridge(self.analyze(replay), 0)
        causes = {c["cause"]: c for c in r["cash_by_cause"]}
        self.assertTrue(r["all_cash_attributed"])
        self.assertEqual(causes["trade:SELL:WHEAT"]["cash_delta_by_seat"], [49, 0])
        self.assertNotIn("trade:BUY_SEED:TOMATO", causes)
        self.assertEqual(causes["hire"]["cash_delta_by_seat"], [-1, 0])

    def test_actual_boundary_and_missing_shared_step(self):
        replay = self.replay([[{}, {}], [{"market": [["SELL", "WHEAT", 1]]}, {}]], initial_step=23)
        for frame in replay["steps"]:
            frame[1]["observation"].pop("step", None)
        trace = self.analyze(replay)
        self.assertEqual(trace["transition_statuses"], {"RECONCILED": 2})
        r = cb.build_bridge(trace, 0)
        self.assertEqual([d["day"] for d in r["daily"]], [0, 1])
        self.assertTrue(r["all_cash_attributed"])

    def test_cli_preserves_string_embedded_episode(self):
        self.check_external_episode_binding("123")

    def test_cli_keeps_missing_embedded_episode_explicit(self):
        self.check_external_episode_binding(None)

    def check_external_episode_binding(self, embedded):
        replay = self.replay([[{}, {}]])
        if embedded is None:
            replay["info"].pop("EpisodeId")
        else:
            replay["info"]["EpisodeId"] = embedded
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "replay.raw"
            raw.write_text(json.dumps(replay))
            cmd = [sys.executable, str(Path(cb.__file__)), str(raw),
                "--engine-dir", str(self.engine_dir), "--episode-id", "123",
                "--player-index", "0", "--our-submission-id", "111",
                "--rival-submission-id", "222", "--expected-cash", "3000,3000",
                "--provider-source", "synthetic fixture record", "--output", str(root / "result")]
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, done.stderr)
            bridge = json.loads((root / "result/cash-bridge.json").read_text())
            self.assertEqual(bridge["requested_episode_id"], 123)
            self.assertEqual(bridge["episode_id"], embedded)
            binding = bridge["source"]["provider_binding"]
            self.assertEqual(binding["requested_episode_id"], 123)
            self.assertEqual(binding["embedded_episode_id"], embedded)
            self.assertEqual(binding["source"], "synthetic fixture record")
            trace = json.loads(gzip.decompress((root / "result/trace.json.gz").read_bytes()))
            self.assertEqual(trace["episode_id"], embedded)
            self.assertTrue(bridge["all_cash_attributed"])

    def test_cli_writes_bound_hashes_and_exact_frames(self):
        replay = self.replay([[{}, {"market": [["SELL", "WHEAT", 3]]}]])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "123.raw"
            raw.write_text(json.dumps(replay))
            cash = [replay["steps"][-1][0]["observation"]["farms"][s]["money"] for s in (0, 1)]
            cmd = [sys.executable, str(Path(cb.__file__)), str(raw), "--engine-dir", str(self.engine_dir),
                "--episode-id", "123", "--player-index", "0", "--our-submission-id", "111",
                "--rival-submission-id", "222", "--expected-cash", ",".join(map(str, cash)),
                "--provider-source", "synthetic fixture identity, not an actual provider result",
                "--output", str(root / "result")]
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, done.stderr)
            result = root / "result"
            manifest = json.loads((result / "MANIFEST.json").read_text())
            for name, entry in manifest["files"].items():
                b = (result / name).read_bytes()
                self.assertEqual(hashlib.sha256(b).hexdigest(), entry["sha256"])
            witness = json.loads(gzip.decompress((result / "observed-witnesses.json.gz").read_bytes()))
            self.assertEqual(witness["cases"][0]["before"], replay["steps"][0])
            self.assertEqual(witness["cases"][0]["after"], replay["steps"][1])
            again = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(again.returncode, 0)
            self.assertIn("FileExistsError", again.stderr)
            # An episode mismatch cannot leave a result directory.
            cmd[cmd.index("--episode-id")+1] = "999"
            cmd[-1] = str(root / "bad-result")
            bad = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse((root / "bad-result").exists())


if __name__ == "__main__":
    unittest.main()
