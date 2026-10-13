from copy import deepcopy
from pathlib import Path
import unittest

from research.oss_sponsor_route_map.validate import ValidationError, load_map, validate_map

HERE = Path(__file__).resolve().parent
MAP = HERE / "route_map.json"


class RouteMapValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = load_map(MAP)

    def test_checked_in_map(self):
        summary = validate_map(deepcopy(self.base))
        self.assertEqual(summary["opportunity_count"], 20)
        self.assertEqual(summary["source_count"], 19)
        self.assertNotIn("GUARANTEED", summary["reward_state_counts"])

    def mutate(self):
        return deepcopy(self.base)

    def test_too_few_rows(self):
        v = self.mutate(); v["opportunities"] = v["opportunities"][:19]
        with self.assertRaisesRegex(ValidationError, "20..30"): validate_map(v)

    def test_duplicate_opportunity(self):
        v = self.mutate(); v["opportunities"][1]["id"] = v["opportunities"][0]["id"]
        with self.assertRaisesRegex(ValidationError, "duplicate opportunity"): validate_map(v)

    def test_unknown_source(self):
        v = self.mutate(); v["opportunities"][0]["source"] = "invented"
        with self.assertRaisesRegex(ValidationError, "unknown source"): validate_map(v)

    def test_unknown_proof(self):
        v = self.mutate(); v["opportunities"][0]["proof"] = "invented"
        with self.assertRaisesRegex(ValidationError, "unknown proof"): validate_map(v)

    def test_advertised_requires_value(self):
        v = self.mutate(); v["opportunities"][0]["econ"]["advertised_value"] = None
        with self.assertRaises(ValidationError): validate_map(v)

    def test_subjective_cannot_carry_value(self):
        v = self.mutate(); v["opportunities"][0]["reward"] = "SUBJECTIVE"
        with self.assertRaisesRegex(ValidationError, "cannot assert value"): validate_map(v)

    def test_guaranteed_forbidden(self):
        v = self.mutate(); v["opportunities"][0]["reward"] = "GUARANTEED"
        with self.assertRaisesRegex(ValidationError, "may not assert GUARANTEED"): validate_map(v)

    def test_authority_profile_cannot_escalate(self):
        v = self.mutate(); v["authority_profiles"]["RESEARCH_ONLY_V1"]["external_action_authorized"] = True
        with self.assertRaisesRegex(ValidationError, "may not authorize"): validate_map(v)

    def test_wrong_fence(self):
        v = self.mutate(); v["opportunities"][0]["fence"] = "GO_NOW"
        with self.assertRaisesRegex(ValidationError, "wrong fence"): validate_map(v)

    def test_bad_source_url(self):
        v = self.mutate(); v["sources"][0]["url"] = "http://invalid.example"
        with self.assertRaisesRegex(ValidationError, "https URL"): validate_map(v)

    def test_duplicate_source_url(self):
        v = self.mutate(); v["sources"][1]["url"] = v["sources"][0]["url"]
        with self.assertRaisesRegex(ValidationError, "duplicate source URL"): validate_map(v)

    def test_future_source(self):
        v = self.mutate(); v["sources"][0]["observed_at_utc"] = "2026-09-17T00:52:01Z"
        with self.assertRaisesRegex(ValidationError, "observed after generation"): validate_map(v)

    def test_bool_priority(self):
        v = self.mutate(); v["opportunities"][0]["priority"] = True
        with self.assertRaisesRegex(ValidationError, "priority"): validate_map(v)

    def test_summary_drift(self):
        v = self.mutate(); v["summary"]["opportunity_count"] = 19
        with self.assertRaisesRegex(ValidationError, "summary does not match"): validate_map(v)

    def test_duplicate_json_key(self):
        p = HERE / "_dup.json"
        try:
            p.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "duplicate JSON key"): load_map(p)
        finally:
            p.unlink(missing_ok=True)

    def test_nan_json(self):
        p = HERE / "_nan.json"
        try:
            p.write_text('{"a":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "non-finite"): load_map(p)
        finally:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
