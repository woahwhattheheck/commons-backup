import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import turnbench as tb


def load_fixture(name):
    return tb.loads_strict((ROOT / "fixtures" / name).read_bytes())


class TurnBenchTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_fixture("scenario.json")
        self.trace = load_fixture("trace-good.json")

    def decision(self, scenario=None, trace=None):
        return tb.evaluate(scenario or self.scenario, trace or self.trace)

    def finding(self, receipt, code):
        return next(x for x in receipt["findings"] if x["code"] == code)

    def test_good_synthetic_passes_without_live_claim(self):
        r = self.decision()
        self.assertEqual("PASS", r["decision"])
        self.assertFalse(r["live_provider_performance_proven"])

    def test_self_declared_live_capture_does_not_prove_provider_origin(self):
        t = copy.deepcopy(self.trace)
        t["evidence_class"] = "LIVE_CAPTURE_UNVERIFIED"
        r = self.decision(trace=t)
        self.assertEqual("PASS", r["decision"])
        self.assertFalse(r["live_provider_performance_proven"])
        self.assertEqual("LIVE_CAPTURE_UNVERIFIED", r["provider_origin_status"])

    def test_config_hash_mismatch_fails(self):
        t = copy.deepcopy(self.trace)
        t["events"][1]["data"]["resolved_config_sha256"] = "a" * 64
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "CONFIG_BOUND")["passed"])

    def test_session_update_config_drift_fails(self):
        t = copy.deepcopy(self.trace)
        t["events"].insert(2, {"seq": 2, "at_ms": 50, "type": "session.updated", "data": {"resolved_config_sha256": "a" * 64}})
        for e in t["events"][3:]:
            e["seq"] += 1
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "CONFIG_BOUND")["passed"])

    def test_tool_call_matches_current_provider_shape_without_reply_id(self):
        t = copy.deepcopy(self.trace)
        call = next(e for e in t["events"] if e["type"] == "tool.call")
        self.assertEqual({"call_id", "name", "arguments"}, set(call["data"]))
        tb.validate_trace(t)

    def test_turn_latency_over_budget_fails(self):
        s = copy.deepcopy(self.scenario)
        s["assertions"]["max_turn_start_latency_ms"] = 100
        r = self.decision(scenario=s)
        self.assertFalse(self.finding(r, "TURN_START_LATENCY")["passed"])

    def test_missing_reply_fails(self):
        t = copy.deepcopy(self.trace)
        t["events"] = [e for e in t["events"] if not (e["type"] == "reply.started" and e["data"].get("item_id") == "item_2")]
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "TURN_START_LATENCY")["passed"])

    def test_missing_required_interruption_fails(self):
        t = copy.deepcopy(self.trace)
        # Remove the synthetic reply that is intentionally active when the second user starts.
        # The trace stays chronological but now contains zero observed barge-ins.
        t["events"] = [
            e for e in t["events"]
            if e["data"].get("reply_id") != "reply_2" and not (e["type"] == "reply.audio" and 1000 <= e["at_ms"] <= 1300)
        ]
        r = self.decision(trace=t)
        f = self.finding(r, "BARGE_IN_CANCELLATION")
        self.assertFalse(f["passed"])
        self.assertEqual(0, f["detail"]["observed_count"])
        self.assertEqual(1, f["detail"]["required_count"])

    def test_barge_in_not_interrupted_fails(self):
        t = copy.deepcopy(self.trace)
        done = next(e for e in t["events"] if e["type"] == "reply.done" and e["data"]["reply_id"] == "reply_2")
        done["data"]["status"] = "completed"
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "BARGE_IN_CANCELLATION")["passed"])

    def test_barge_in_latency_over_budget_fails(self):
        t = copy.deepcopy(self.trace)
        done = next(e for e in t["events"] if e["type"] == "reply.done" and e["data"]["reply_id"] == "reply_2")
        done["at_ms"] = 1400
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "BARGE_IN_CANCELLATION")["passed"])

    def test_barge_in_transcript_flag_required(self):
        t = copy.deepcopy(self.trace)
        tr = next(e for e in t["events"] if e["type"] == "transcript.agent" and e["data"]["reply_id"] == "reply_2")
        tr["data"]["interrupted"] = False
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "BARGE_IN_CANCELLATION")["passed"])

    def test_tool_arguments_must_be_object(self):
        t = copy.deepcopy(self.trace)
        call = next(e for e in t["events"] if e["type"] == "tool.call")
        call["data"]["arguments"] = ["severity", "summary"]
        with self.assertRaisesRegex(ValueError, "arguments must be an object"):
            tb.validate_trace(t)

    def test_missing_required_tool_argument_fails(self):
        t = copy.deepcopy(self.trace)
        call = next(e for e in t["events"] if e["type"] == "tool.call")
        del call["data"]["arguments"]["summary"]
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "TOOL_CAUSALITY")["passed"])

    def test_tool_without_transcript_witness_fails(self):
        t = copy.deepcopy(self.trace)
        t["events"][4]["data"]["text"] = "Please open a ticket for checkout latency."
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "TOOL_CAUSALITY")["passed"])

    def test_tool_latency_over_budget_fails(self):
        s = copy.deepcopy(self.scenario)
        s["assertions"]["max_tool_call_latency_ms"] = 100
        r = self.decision(scenario=s)
        self.assertFalse(self.finding(r, "TOOL_CAUSALITY")["passed"])

    def test_forbidden_provider_error_fails(self):
        t = copy.deepcopy(self.trace)
        t["events"].insert(-1, {"seq": 19, "at_ms": 1950, "type": "session.error", "data": {"code": "server_error"}})
        t["events"][-1]["seq"] = 20
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "NO_FORBIDDEN_PROVIDER_ERROR")["passed"])

    def test_min_user_turns_fails(self):
        s = copy.deepcopy(self.scenario)
        s["assertions"]["min_user_turns"] = 3
        r = self.decision(scenario=s)
        self.assertFalse(self.finding(r, "MIN_USER_TURNS")["passed"])

    def test_clean_session_end_required(self):
        t = copy.deepcopy(self.trace)
        t["events"][-1]["data"]["clean"] = False
        r = self.decision(trace=t)
        self.assertFalse(self.finding(r, "SESSION_END")["passed"])

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            tb.loads_strict(b'{"schema":"x","schema":"y"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-finite"):
            tb.loads_strict(b'{"x":NaN}')

    def test_bool_not_integer(self):
        s = copy.deepcopy(self.scenario)
        s["assertions"]["min_user_turns"] = True
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            tb.validate_scenario(s)

    def test_sequence_regression_rejected(self):
        t = copy.deepcopy(self.trace)
        t["events"][2]["seq"] = 1
        with self.assertRaisesRegex(ValueError, "sequence"):
            tb.validate_trace(t)

    def test_time_regression_rejected(self):
        t = copy.deepcopy(self.trace)
        t["events"][3]["at_ms"] = 50
        with self.assertRaisesRegex(ValueError, "time regressed"):
            tb.validate_trace(t)

    def test_unknown_event_type_rejected(self):
        t = copy.deepcopy(self.trace)
        t["events"][3]["type"] = "magic.event"
        with self.assertRaisesRegex(ValueError, "unknown type"):
            tb.validate_trace(t)

    def test_scenario_trace_identity_mismatch_rejected(self):
        t = copy.deepcopy(self.trace)
        t["scenario_id"] = "different"
        with self.assertRaisesRegex(ValueError, "scenario_id mismatch"):
            tb.evaluate(self.scenario, t)

    def test_duplicate_required_tool_rejected(self):
        s = copy.deepcopy(self.scenario)
        s["assertions"]["required_tool_calls"].append(copy.deepcopy(s["assertions"]["required_tool_calls"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate required tool"):
            tb.validate_scenario(s)

    def test_turn_detection_order_rejected(self):
        s = copy.deepcopy(self.scenario)
        s["session_contract"]["min_silence_ms"] = 1200
        with self.assertRaisesRegex(ValueError, "less than"):
            tb.validate_scenario(s)

    def test_receipt_tamper_detected(self):
        r = self.decision()
        r["decision"] = "FAIL"
        self.assertFalse(tb.verify_receipt(self.scenario, self.trace, r))

    def test_order_stable_receipt(self):
        # Reordering object keys changes neither canonical source digest nor receipt.
        t = json.loads(json.dumps(self.trace))
        s = json.loads(json.dumps(self.scenario))
        self.assertEqual(tb.canonical_bytes(self.decision()), tb.canonical_bytes(tb.evaluate(s, t)))

    def test_cli_create_exclusive_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "receipt.json"
            cmd = [sys.executable, str(ROOT / "turnbench.py"), "evaluate", "--scenario", str(ROOT / "fixtures" / "scenario.json"), "--trace", str(ROOT / "fixtures" / "trace-good.json"), "--out", str(out)]
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(0, p.returncode, p.stderr + p.stdout)
            self.assertTrue(out.exists())
            p2 = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(64, p2.returncode)
            verify = subprocess.run([sys.executable, str(ROOT / "turnbench.py"), "verify", "--scenario", str(ROOT / "fixtures" / "scenario.json"), "--trace", str(ROOT / "fixtures" / "trace-good.json"), "--receipt", str(out)], capture_output=True, text=True)
            self.assertEqual(0, verify.returncode, verify.stderr + verify.stdout)
            self.assertIn("VALID", verify.stdout)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_cli_refuses_symlink_input(self):
        with tempfile.TemporaryDirectory() as td:
            link = Path(td) / "scenario.json"
            os.symlink(ROOT / "fixtures" / "scenario.json", link)
            out = Path(td) / "out.json"
            p = subprocess.run([sys.executable, str(ROOT / "turnbench.py"), "evaluate", "--scenario", str(link), "--trace", str(ROOT / "fixtures" / "trace-good.json"), "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(64, p.returncode)
            self.assertIn("symlink input refused", p.stdout)


if __name__ == "__main__":
    unittest.main()
