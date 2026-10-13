import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
FIXTURE = PKG / "fixtures" / "requote.synthetic.json"
SPEC = importlib.util.spec_from_file_location("redline_chronology", PKG / "compile_redline.py")
redline = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(redline)


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class RedlineSourceChronologyTests(unittest.TestCase):
    def test_counter_observed_before_claimed_baseline_holds(self):
        raw = fixture()
        raw["baseline"]["observed_at"] = "2026-09-17T02:00:00Z"
        raw["counter"]["observed_at"] = "2026-09-17T01:00:00Z"
        raw["as_of"] = "2026-09-17T03:00:00Z"
        result, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "HOLD_CONTRADICTION")
        self.assertIn(
            "COUNTER_OBSERVED_BEFORE_BASELINE",
            {hold["code"] for hold in result["holds"]},
        )

    def test_as_of_before_retained_sources_holds(self):
        raw = fixture()
        raw["baseline"]["observed_at"] = "2026-09-17T02:00:00Z"
        raw["counter"]["observed_at"] = "2026-09-17T03:00:00Z"
        raw["as_of"] = "2026-09-17T01:00:00Z"
        result, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "HOLD_CONTRADICTION")
        codes = {hold["code"] for hold in result["holds"]}
        self.assertIn("AS_OF_BEFORE_BASELINE_OBSERVATION", codes)
        self.assertIn("AS_OF_BEFORE_COUNTER_OBSERVATION", codes)

    def test_timezone_representations_compare_by_instant(self):
        raw = fixture()
        raw["counter"] = copy.deepcopy(raw["baseline"])
        raw["counter"]["document_id"] = "COUNTER-TZ"
        raw["counter"]["generation"] = "counter-tz-v1"
        raw["counter"]["baseline_generation"] = raw["baseline"]["generation"]
        raw["baseline"]["observed_at"] = "2026-09-17T02:00:00+01:00"
        raw["counter"]["observed_at"] = "2026-09-17T01:30:00Z"
        raw["as_of"] = "2026-09-17T01:30:00Z"
        result, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "ACCEPTABLE_AS_WRITTEN")
        chronology_codes = {
            "COUNTER_OBSERVED_BEFORE_BASELINE",
            "AS_OF_BEFORE_BASELINE_OBSERVATION",
            "AS_OF_BEFORE_COUNTER_OBSERVATION",
        }
        self.assertFalse(chronology_codes & {hold["code"] for hold in result["holds"]})

    def test_equal_observation_and_as_of_boundary_is_allowed(self):
        raw = fixture()
        raw["counter"] = copy.deepcopy(raw["baseline"])
        raw["counter"]["document_id"] = "COUNTER-EQUAL-TIME"
        raw["counter"]["generation"] = "counter-equal-v1"
        raw["counter"]["baseline_generation"] = raw["baseline"]["generation"]
        raw["baseline"]["observed_at"] = "2026-09-17T02:00:00Z"
        raw["counter"]["observed_at"] = "2026-09-17T02:00:00Z"
        raw["as_of"] = "2026-09-17T02:00:00Z"
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "ACCEPTABLE_AS_WRITTEN")


if __name__ == "__main__":
    unittest.main()
