"""Actual pinned-controller tests; use original artifacts, never replacement policies."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import observe

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("T07_COK_SOURCE", HERE / "sources/cok-v10/main.py"))
PACK = Path(os.environ.get("T07_PACK", HERE.parent / "cloud-pack"))
ENGINE = Path(os.environ.get("TITAN_ENGINE", HERE / "engine"))
EVAL = Path(os.environ.get("TITAN_EVALUATOR", HERE.parent / "cloud-eval/evaluate.py"))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def fixture(step=72, seat=0, shops=("BAKERY",), qualifies=True):
    """Deliberate public gate fixture, not an observed game or hidden panel."""
    farm = {"money": 1000, "tiles": [[{"kind": "EMPTY"} for _ in range(8)] for _ in range(8)],
            "farmer": [3, 3], "hands": [], "shedCapacity": 100}
    farms = [copy.deepcopy(farm), copy.deepcopy(farm)]
    farms[seat]["money"] = 999 if qualifies else 1000
    rival_tiles = farms[1-seat]["tiles"]
    values = ["COW"] + ["SHEEP"] * 4 + ["WHEAT"] * 5 + ["MELON"] * 4
    for index, kind in enumerate(values):
        key = "animal" if kind in ("COW", "SHEEP") else "crop"
        rival_tiles[index // 8][index % 8] = {"kind": "PASTURE" if key == "animal" else "FIELD", key: kind}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": seat,
            "farms": farms, "town": {"unlocked_shops": list(shops)},
            "market": {}, "private": {"shed": {}, "inventories": [{}]},
            "remainingOverageTime": 0}


class ObserverTests(unittest.TestCase):
    def observer(self):
        return observe.CokObserver(SOURCE, PACK)

    def test_source_identity(self):
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), observe.SOURCE_SHA256)
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "changed.py"
            changed.write_bytes(SOURCE.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                observe.CokObserver(changed, PACK)

    def test_actual_gate_both_seats(self):
        for seat in (0, 1):
            policy = self.observer()
            action = policy.act(fixture(seat=seat))
            record = policy.last_record
            self.assertIs(record["gate_after"], True)
            self.assertTrue(record["gate_evaluated_this_call"])
            self.assertEqual(record["route"], "v5/low")
            self.assertEqual(record["public_features"]["own_money"], 999)
            self.assertEqual(record["public_features"]["rival_money"], 1000)
            self.assertEqual(set(action), {"farmer", "hands", "market"})

    def test_not_gate_time(self):
        for step in (71, 73, 168):
            policy = self.observer()
            policy.act(fixture(step=step))
            self.assertTrue(policy.last_record["predicate_matches_now"])
            self.assertIsNone(policy.last_record["gate_after"])
            self.assertFalse(policy.last_record["gate_evaluated_this_call"])
            self.assertNotEqual(policy.last_record["route"], "v5/low")

    def test_money_and_malformed_features(self):
        for value in (None, True, float("nan"), float("inf"), "bad", 1000, 1001):
            obs = fixture()
            obs["farms"][0]["money"] = value
            policy = self.observer()
            policy.act(obs)
            self.assertIs(policy.last_record["gate_after"], False)
            json.dumps(policy.last_record, allow_nan=False)
        obs = fixture()
        del obs["farms"][0]["money"]
        policy = self.observer(); policy.act(obs)
        self.assertIsNone(policy.last_record["public_features"]["own_money"])
        self.assertFalse(policy.last_record["gate_after"])

    def test_counts_and_shops(self):
        cases = []
        for kind in ("COW", "SHEEP", "WHEAT", "MELON"):
            obs = fixture()
            for row in obs["farms"][1]["tiles"]:
                for tile in row:
                    if tile.get("animal") == kind or tile.get("crop") == kind:
                        tile.clear()
                        break
                else:
                    continue
                break
            cases.append(obs)
        for shops in ([], ["YARN_STORE"], "BAKERY", [1]):
            obs = fixture(); obs["town"]["unlocked_shops"] = shops; cases.append(obs)
        for obs in cases:
            policy = self.observer(); policy.act(obs)
            self.assertFalse(policy.last_record["gate_after"])
        obs = fixture(); obs["farms"][1]["tiles"][3][0] = {"crop": "MELON"}
        policy = self.observer(); policy.act(obs)
        self.assertTrue(policy.last_record["gate_after"])

    def test_closed_gate_cannot_reopen_same_step(self):
        policy = self.observer()
        policy.act(fixture(qualifies=False))
        policy.act(fixture(qualifies=True))
        self.assertTrue(policy.last_record["predicate_matches_now"])
        self.assertFalse(policy.last_record["gate_after"])
        self.assertFalse(policy.last_record["cached_retry"])

    def test_open_gate_can_close_same_step(self):
        policy = self.observer()
        policy.act(fixture())
        policy.act(fixture(qualifies=False))
        self.assertTrue(policy.last_record["gate_before"])
        self.assertFalse(policy.last_record["gate_after"])
        self.assertTrue(policy.last_record["gate_changed"])
        policy.act(fixture())
        self.assertFalse(policy.last_record["gate_after"])

    def test_retry_preserves_action_and_no_second_evaluation(self):
        policy = self.observer()
        obs = fixture(); first = policy.act(obs)
        original = copy.deepcopy(first)
        first["market"].append(["SELL", "WHEAT", 999])
        second = policy.act(obs)
        self.assertEqual(second, original)
        self.assertTrue(policy.last_record["cached_retry"])
        self.assertFalse(policy.last_record["gate_evaluated_this_call"])
        self.assertFalse(policy.last_record["gate_changed"])

    def test_sticky_expert_at_168(self):
        policy = self.observer()
        policy.act(fixture())
        policy.act(fixture(167, shops=("BAKERY", "YARN_STORE")))
        self.assertIsNone(policy.last_record["expert_after"])
        policy.act(fixture(168, shops=("BAKERY", "YARN_STORE")))
        self.assertEqual(policy.last_record["expert_after"], "high")
        self.assertEqual(policy.last_record["route"], "v5/high")
        policy.act(fixture(169, shops=("ICE_CREAM_SHOP", "YARN_STORE")))
        self.assertEqual(policy.last_record["expert_after"], "high")
        self.assertEqual(policy.last_record["route"], "v5/high")

    def test_dominated_shop_route_is_low(self):
        policy = self.observer(); policy.act(fixture())
        policy.act(fixture(168, shops=("ICE_CREAM_SHOP", "YARN_STORE")))
        self.assertEqual(policy.last_record["expert_after"], "low")
        self.assertEqual(policy.last_record["route"], "v5/low")

    def test_step_reset_and_new_actor(self):
        policy = self.observer(); policy.act(fixture())
        policy.act(fixture(168, shops=("BAKERY", "YARN_STORE")))
        policy.act(fixture(0))
        self.assertTrue(policy.last_record["reset_observed"])
        self.assertIsNone(policy.last_record["gate_after"])
        self.assertIsNone(policy.last_record["expert_after"])
        policy.act(fixture(72))
        policy.act(fixture(71))
        self.assertTrue(policy.last_record["reset_observed"])
        self.assertIsNone(policy.last_record["gate_after"])
        other = self.observer(); other.act(fixture(73))
        self.assertIsNone(other.last_record["gate_after"])

    def test_no_private_data_and_detached_state(self):
        obs = fixture()
        obs["private"]["secret_marker"] = "DO_NOT_EXPORT_PRIVATE"
        saved = copy.deepcopy(obs)
        policy = self.observer(); policy.act(obs)
        record = policy.last_record
        self.assertNotIn("DO_NOT_EXPORT_PRIVATE", json.dumps(record))
        record["route_state"]["v5_gate"] = False
        policy.act(fixture(168, shops=("BAKERY", "YARN_STORE")))
        self.assertTrue(policy.last_record["gate_after"])
        self.assertEqual(obs, saved)

    def test_missing_shared_step_is_not_fabricated(self):
        obs = fixture(); del obs["step"]
        policy = self.observer(); policy.act(obs)
        self.assertFalse(policy.last_record["step_present"])
        self.assertIsNone(policy.last_record["observed_step"])
        self.assertEqual(policy.last_record["controller_step"], 0)
        self.assertIsNone(policy.last_record["gate_after"])

    def test_official_action_equivalence_for_both_seats(self):
        # A full chronological *synthetic observation* sequence, not a game.
        for seat in (0, 1):
            baseline = observe.load_official(PACK).make_agent(SOURCE)
            policy = self.observer()
            for step in range(719):
                obs = fixture(step, seat, ("BAKERY", "YARN_STORE") if step >= 168 else ("BAKERY",))
                expected = baseline(copy.deepcopy(obs), {})
                self.assertEqual(policy.act(obs), expected, (seat, step))
                self.assertIsNone(policy.last_record["telemetry_error"])
            self.assertEqual(policy.calls, 719)

    def test_jsonl_report_and_expected_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = observe.load_official(PACK).make_agent(SOURCE)
            inputs = []
            for step in (71, 72, 72, 168, 169):
                obs = fixture(step, shops=("BAKERY", "YARN_STORE") if step >= 168 else ("BAKERY",))
                inputs.append({"match_id": "synthetic", "observation": obs,
                               "expected_action": baseline(copy.deepcopy(obs), {})})
            (root / "input.jsonl").write_text("".join(json.dumps(r) + "\n" for r in inputs))
            report = observe.run_jsonl(SOURCE, PACK, root/"input.jsonl", root/"output.jsonl", root/"summary.json")
            actor = report["actors"][0]
            self.assertEqual(actor["expected_action_mismatches"], 0)
            self.assertEqual(actor["gate_evaluations"], 1)
            self.assertEqual(actor["cached_retries"], 1)
            self.assertFalse(actor["has_every_step_0_through_718"])
            self.assertEqual(actor["expert_transitions"], [{"step": 168, "before": None, "after": "high"}])
            bad = inputs[0]; bad["expected_action"] = {"wrong": 1}
            (root / "input.jsonl").write_text(json.dumps(bad) + "\n")
            proc = subprocess.run([sys.executable, str(HERE/"observe.py"), "--source", str(SOURCE),
                "--pack", str(PACK), "--input", str(root/"input.jsonl"), "--output", str(root/"out2.jsonl"),
                "--summary", str(root/"sum2.json")], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            with self.assertRaises(ValueError):
                observe.run_jsonl(SOURCE, PACK, root/"input.jsonl", root/"input.jsonl", root/"summary.json")

    def test_engine_generated_observation_and_real_transition(self):
        evaluator = load(EVAL, "cok_observer_eval")
        engine, hashes = evaluator.get_engine(ENGINE)
        cfg = evaluator.Struct({k: v.get("default") if isinstance(v, dict) else v
                               for k, v in engine.specification["configuration"].items()})
        cfg.seed = 0  # Initialization fixture only; no scored game or held panel.
        env = evaluator.Struct(configuration=cfg, done=False, info={})
        state = [evaluator.Struct(observation=evaluator.Struct(), action={}, status="ACTIVE", reward=0)
                 for _ in (0, 1)]
        engine.interpreter(state, env)
        self.assertIsNone(cfg.seed)
        for seat in (0, 1):
            state[seat].observation.step = 0
            observer = self.observer()
            baseline = observe.load_official(PACK).make_agent(SOURCE)
            action = observer.act(state[seat].observation, cfg)
            self.assertEqual(action, baseline(copy.deepcopy(state[seat].observation), copy.deepcopy(cfg)))
            self.assertEqual(observer.last_record["seat"], seat)
            state[seat].action = action
        engine.interpreter(state, env)
        self.assertTrue(all(s.status == "ACTIVE" for s in state))
        self.assertEqual(len(hashes), 3)


if __name__ == "__main__":
    unittest.main()
