#!/usr/bin/env python3
"""Original-engine correspondence tests; fixtures are fixed actions, not policies."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import recorded_inputs as subject

ENGINE_DIR = None
COUNTS = {"engine_calls": 0, "fixture_records": 0}


class RecordedInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluator = subject.load(subject.ROOT / "cloud-eval/evaluate.py", "fixture_eval")
        cls.tracer = subject.load(subject.ROOT / "cloud-widefield-lab/trace_apex_loss.py", "fixture_trace")
        cls.loader = subject.ROOT / "20260907-offline-agent/evaluate.py"
        engine, cls.hashes = cls.evaluator.get_engine(ENGINE_DIR, cls.loader)
        def interpreted(state, env):
            COUNTS["engine_calls"] += 1
            return engine.interpreter(state, env)
        cls.engine = SimpleNamespace(specification=engine.specification, interpreter=interpreted)
        cls.fixtures = {}
        for candidate_seat in (0, 1):
            class FixedActions:
                def __init__(self, spec, *_):
                    self.candidate = spec == "fixed-candidate"
                    self.index = 0
                    self.ready = {"kind": "ready"}
                def act(self, observation, configuration, timeout):
                    market = []
                    if self.index == 0:
                        market = [["BUY_SEED", "CARROT", 2 if self.candidate else 1]]
                    elif self.index == 1 and self.candidate:
                        market = [["HIRE"]]
                    self.index += 1
                    return {"kind": "action", "action": {"farmer": ["PASS"], "hands": [], "market": market},
                            "call_seconds": 0.0, "call_cpu_seconds": 0.0}
                def close(self):
                    pass
                def report(self):
                    return {"synthetic_fixed_actions": True, "calls": self.index}
            facade = SimpleNamespace(**vars(cls.evaluator))
            facade.Actor = FixedActions
            facade.fingerprint = lambda value: {"fixture": value}
            fixture = cls.tracer.play(facade, cls.engine, ENGINE_DIR, cls.loader,
                                     "fixed-candidate", "fixed-opponent", 0, candidate_seat)
            cls.fixtures[candidate_seat] = fixture
            COUNTS["fixture_records"] += 1
        cls.original_actor = cls.evaluator.Actor

    def recover(self, game=None):
        return subject.recover_inputs(game or self.fixtures[0], self.evaluator,
                                      self.tracer, self.engine, ENGINE_DIR, self.loader)

    def changed(self, transform):
        game = copy.deepcopy(self.fixtures[0])
        transform(game)
        with self.assertRaises((ValueError, TypeError)):
            self.recover(game)

    def test_both_seats_complete_digest_and_bank_correspondence(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                inputs, receipt = self.recover(self.fixtures[seat])
                self.assertEqual(len(inputs), 719)
                self.assertEqual(receipt["source_trace_sha256"], receipt["reconstructed_trace_sha256"])
                self.assertTrue(all(row["seat"] == seat for row in inputs))
                self.assertEqual(receipt["policy_calls"], 0)
                self.assertFalse(receipt["candidate_internal_state_reconstructed"])

    def test_input_boundary_and_private_state_are_complete(self):
        inputs, _ = self.recover()
        self.assertEqual(inputs[683]["observation"]["step"], 683)
        self.assertEqual(inputs[683]["observation"]["remainingOverageTime"], 0)
        self.assertIsNone(inputs[0]["configuration"].get("seed"))
        self.assertIn("private", inputs[683]["observation"])
        self.assertIn("tiles", inputs[683]["observation"]["farms"][0])
        self.assertNotEqual(inputs[0]["observation"], inputs[1]["observation"])
        self.assertEqual(inputs[1]["expected_action"]["market"], [["HIRE"]])

    def test_no_real_actor_or_shared_evaluator_mutation(self):
        with mock.patch.object(self.evaluator, "Actor", side_effect=AssertionError("policy execution")) as actor:
            self.recover()
            actor.assert_not_called()
        self.assertIs(self.evaluator.Actor, self.original_actor)

    def test_source_record_unchanged(self):
        original = subject.canonical(self.fixtures[0])
        inputs, _ = self.recover()
        inputs[0]["expected_action"]["market"].append(["HIRE"])
        self.assertEqual(subject.canonical(self.fixtures[0]), original)

    def test_stream_hash_reproducible(self):
        inputs, report = self.recover()
        payload = b"".join(subject.canonical(row) + b"\n" for row in inputs)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), report["input_jsonl_sha256"])

    def test_missing_joint_action(self):
        self.changed(lambda game: game["actions_and_timing"][2]["actions"].pop())

    def test_step_gap(self):
        self.changed(lambda game: game["actions_and_timing"][4].update(step=5))

    def test_invalid_seat(self):
        self.changed(lambda game: game.update(candidate_seat=True))

    def test_missing_seed(self):
        self.changed(lambda game: game.pop("seed"))

    def test_incomplete_record(self):
        self.changed(lambda game: game.update(status="failed"))

    def test_nan_bank(self):
        self.changed(lambda game: game["actions_and_timing"][0]["bank"].__setitem__(0, float("nan")))

    def test_changed_action_detected(self):
        self.changed(lambda game: game["actions_and_timing"][0]["actions"][0]["market"][0].__setitem__(2, 9))

    def test_changed_bank_detected(self):
        self.changed(lambda game: game["actions_and_timing"][1]["bank"].__setitem__(0, -1.0))

    def test_changed_terminal_score_detected(self):
        self.changed(lambda game: game["scores"].__setitem__(0, -1.0))

    def test_changed_trace_digest_detected(self):
        self.changed(lambda game: game.update(trace_sha256="0" * 64))

    def test_truncated_complete_record_detected(self):
        def truncate(game):
            game["actions_and_timing"] = game["actions_and_timing"][:-1]
            game["steps_completed"] -= 1
        self.changed(truncate)

    def test_cli_gzip_and_source_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            record = root / "record.json"
            record.write_text(json.dumps({"schema": subject.SCHEMA,
                                          "engine_ref": self.evaluator.ENGINE_REF,
                                          "engine_sha256": self.hashes,
                                          "games": [self.fixtures[0]]}))
            output, receipt = root / "inputs.jsonl.gz", root / "receipt.json"
            with mock.patch("builtins.print"):
                code = subject.main(["--record", str(record), "--engine-dir", str(ENGINE_DIR),
                                     "--expected-trace", self.fixtures[0]["trace_sha256"],
                                     "--output", str(output), "--receipt", str(receipt)])
            self.assertEqual(code, 0)
            payload = gzip.decompress(output.read_bytes())
            report = json.loads(receipt.read_text())
            self.assertEqual(len(payload.splitlines()), 719)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), report["input_jsonl_sha256"])
            self.assertEqual(hashlib.sha256(record.read_bytes()).hexdigest(), report["source_record_sha256"])

    def test_failed_cli_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            record, output, receipt = root / "record.json", root / "out.jsonl", root / "receipt.json"
            output.write_bytes(b"previous input")
            receipt.write_bytes(b"previous receipt")
            record.write_text(json.dumps({"schema": subject.SCHEMA, "games": [self.fixtures[0]]}))
            with self.assertRaises(ValueError):
                subject.main(["--record", str(record), "--engine-dir", str(ENGINE_DIR),
                              "--expected-trace", "f" * 64, "--output", str(output), "--receipt", str(receipt)])
            self.assertEqual(output.read_bytes(), b"previous input")
            self.assertEqual(receipt.read_bytes(), b"previous receipt")

    def document(self):
        return {"schema": subject.SCHEMA, "engine_ref": self.evaluator.ENGINE_REF,
                "engine_sha256": copy.deepcopy(self.hashes),
                "games": [copy.deepcopy(self.fixtures[0])]}

    def recover_document(self, document=None, **kwargs):
        return subject.recover_record(self.document() if document is None else document,
                                      self.evaluator, self.tracer, self.engine,
                                      ENGINE_DIR, self.loader, self.hashes, **kwargs)

    def test_record_schema_engine_and_custom_configuration(self):
        cases = [("schema", None), ("engine_ref", "wrong"), ("engine_sha256", {}),
                 ("configuration_overrides", {"startingMoney": 1}),
                 ("configuration", {"startingMoney": 1})]
        for key, value in cases:
            with self.subTest(key=key):
                document = self.document(); document[key] = value
                with self.assertRaises(ValueError):
                    self.recover_document(document)

    def test_record_view_preserves_original_and_actor_rng_identity(self):
        document = self.document()
        before = subject.canonical(document)
        inputs, receipt = self.recover_document(document, seat=1)
        self.assertEqual(subject.canonical(document), before)
        self.assertEqual(inputs[1]["observation"]["player"], 1)
        self.assertEqual(inputs[0]["expected_action"], document["games"][0]["actions_and_timing"][0]["actions"][1])
        self.assertEqual(receipt["original_candidate_seat"], 0)
        self.assertFalse(receipt["view_is_original_candidate"])
        self.assertEqual(receipt["candidate_actor_rng_seed"], 20260908)
        self.assertEqual(receipt["candidate_pythonhashseed"], 20260908)

    def test_record_invalid_original_seat_not_masked_by_view(self):
        document = self.document()
        document["games"][0]["candidate_seat"] = True
        with self.assertRaises(ValueError):
            self.recover_document(document, seat=1)
        for kw in ({"seat": True}, {"game_index": True}, {"expected_trace": "0" * 64}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.recover_document(**kw)

    def test_atomic_replace_failure_preserves_target(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "output"
            target.write_bytes(b"old")
            with mock.patch.object(subject.os, "replace", side_effect=OSError("fixture")):
                with self.assertRaises(OSError):
                    subject.atomic_write(target, b"new")
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(list(target.parent.iterdir()), [target])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    ENGINE_DIR = args.engine_dir
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecordedInputTests))
    report = {"schema": "titan.recorded-inputs-tests.v1", "tests_run": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), **COUNTS,
              "scope": "Two synthetic fixed-action original-engine fixtures; no policy calls, new evaluation games or historical WIDEFIELD source execution.",
              "adapter_sha256": hashlib.sha256(Path(subject.__file__).read_bytes()).hexdigest(),
              "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "engine_sha256": RecordedInputTests.hashes,
              "tracer_blob": "8194b53a3f9df6a81998a7c56a703c056d17238f",
              "evaluator_blob": "6bcde5b7dc1abc33eb3cd7ec42833affc2d28b53"}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
