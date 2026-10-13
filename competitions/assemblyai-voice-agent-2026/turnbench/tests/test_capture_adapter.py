import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import capture_adapter as ca
import turnbench as tb
from api.evaluate import evaluate_payload


class CaptureAdapterTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "fixtures" / "raw-capture.jsonl").read_bytes()
        self.scenario = tb.loads_strict((ROOT / "fixtures" / "scenario.json").read_bytes())

    def test_raw_capture_normalizes_and_passes(self):
        trace = ca.normalize_jsonl(self.raw, "barge-in-ticket-01", "SYNTHETIC")
        receipt = tb.evaluate(self.scenario, trace)
        self.assertEqual("PASS", receipt["decision"])

    def test_secrets_and_audio_are_not_retained(self):
        trace = ca.normalize_jsonl(self.raw, "barge-in-ticket-01", "SYNTHETIC")
        encoded = tb.canonical_bytes(trace)
        self.assertNotIn(b"sess_SECRET", encoded)
        self.assertNotIn(b"resume_SECRET", encoded)
        self.assertNotIn(b"BASE64_AUDIO_SECRET", encoded)
        self.assertNotIn(b"INC-123", encoded)

    def test_live_capture_label_stays_unverified(self):
        trace = ca.normalize_jsonl(self.raw, "barge-in-ticket-01", "LIVE_CAPTURE_UNVERIFIED")
        receipt = tb.evaluate(self.scenario, trace)
        self.assertEqual("LIVE_CAPTURE_UNVERIFIED", receipt["provider_origin_status"])
        self.assertFalse(receipt["live_provider_performance_proven"])

    def test_capture_time_regression_rejected(self):
        lines = self.raw.decode().splitlines()
        row = json.loads(lines[1])
        row["at_ms"] = 1
        lines[1] = json.dumps(row)
        with self.assertRaisesRegex(ValueError, "time regressed"):
            ca.normalize_jsonl(("\n".join(lines) + "\n").encode(), "barge-in-ticket-01", "SYNTHETIC")

    def test_missing_resolved_turn_detection_rejected(self):
        lines = self.raw.decode().splitlines()
        row = json.loads(lines[0])
        del row["event"]["config"]["input"]["turn_detection"]
        lines[0] = json.dumps(row)
        with self.assertRaisesRegex(ValueError, "turn_detection"):
            ca.normalize_jsonl(("\n".join(lines) + "\n").encode(), "barge-in-ticket-01", "SYNTHETIC")

    def test_unknown_capture_events_are_dropped(self):
        extra = b'{"at_ms":2050,"direction":"client","event":{"type":"input.audio","audio":"NOPE"}}\n'
        trace = ca.normalize_jsonl(self.raw + extra, "barge-in-ticket-01", "SYNTHETIC")
        encoded = tb.canonical_bytes(trace)
        self.assertNotIn(b"NOPE", encoded)
        self.assertNotIn(b"input.audio", encoded)

    def test_api_payload_matches_core(self):
        trace = ca.normalize_jsonl(self.raw, "barge-in-ticket-01", "SYNTHETIC")
        self.assertEqual(tb.evaluate(self.scenario, trace), evaluate_payload({"scenario": self.scenario, "trace": trace}))

    def test_api_unknown_key_rejected(self):
        trace = ca.normalize_jsonl(self.raw, "barge-in-ticket-01", "SYNTHETIC")
        with self.assertRaisesRegex(ValueError, "unknown keys"):
            evaluate_payload({"scenario": self.scenario, "trace": trace, "secret": "x"})


if __name__ == "__main__":
    unittest.main()
