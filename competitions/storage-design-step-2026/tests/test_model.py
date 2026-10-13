import json
import unittest
from decimal import Decimal
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "model"))
from production_model import ModelError, compare, parse_scenario


def fixture(name):
    return json.loads((HERE / "model" / name).read_text(encoding="utf-8"))


class ProductionModelTests(unittest.TestCase):
    def test_synthetic_comparison_is_exact_and_reduces_exposure(self):
        result = compare(
            parse_scenario(fixture("example_baseline.synthetic.json")),
            parse_scenario(fixture("example_candidate.synthetic.json")),
        )
        self.assertEqual(result["baseline"]["conversion_cost_usd"], "11194.00")
        self.assertEqual(result["candidate"]["conversion_cost_usd"], "10142.00")
        self.assertEqual(result["delta"]["conversion_cost_usd"], "-1052.00")
        self.assertEqual(result["delta"]["conversion_cost_reduction_pct"], "9.40")
        self.assertLess(Decimal(result["candidate"]["single_source_value_pct"]), Decimal(result["baseline"]["single_source_value_pct"]))
        self.assertIn("Synthetic scenario only", result["truth_boundary"])

    def test_evidence_authority_is_typed_bound_and_comparable(self):
        baseline = fixture("example_baseline.synthetic.json")
        candidate = fixture("example_candidate.synthetic.json")
        baseline["authority"] = candidate["authority"] = "QUOTE_BACKED"
        baseline["evidence_ref"] = "quote-set:reference-stack:2026-09"
        candidate["evidence_ref"] = "quote-set:ferroframe:2026-09"
        result = compare(parse_scenario(baseline), parse_scenario(candidate))
        self.assertEqual(result["baseline"]["authority"], "QUOTE_BACKED")
        self.assertIn("does not authenticate", result["truth_boundary"])

        candidate["authority"] = "PURCHASE_EVIDENCE"
        with self.assertRaises(ModelError):
            compare(parse_scenario(baseline), parse_scenario(candidate))

    def test_rejects_money_float_bool_aliases_and_bad_authority_binding(self):
        raw = fixture("example_baseline.synthetic.json")
        raw["components"][0]["unit_cost_usd"] = 2.5
        with self.assertRaises(ModelError):
            parse_scenario(raw)

        raw = fixture("example_baseline.synthetic.json")
        raw["components"][0]["quantity"] = True
        with self.assertRaises(ModelError):
            parse_scenario(raw)

        raw = fixture("example_baseline.synthetic.json")
        raw["authority"] = "QUOTE_BACKED"
        with self.assertRaises(ModelError):
            parse_scenario(raw)

        raw = fixture("example_baseline.synthetic.json")
        raw["authority"] = "UNVERIFIED"
        with self.assertRaises(ModelError):
            parse_scenario(raw)

    def test_rejects_duplicate_component_identity_and_rating_mismatch(self):
        raw = fixture("example_baseline.synthetic.json")
        raw["components"][1]["name"] = raw["components"][0]["name"].upper()
        with self.assertRaises(ModelError):
            parse_scenario(raw)

        baseline = parse_scenario(fixture("example_baseline.synthetic.json"))
        raw = fixture("example_candidate.synthetic.json")
        raw["energy_kwh"] = "120"
        with self.assertRaises(ModelError):
            compare(baseline, parse_scenario(raw))


if __name__ == "__main__":
    unittest.main()
