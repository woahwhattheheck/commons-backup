import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gate", ROOT / "gate.py")
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def load(self, name):
        return json.loads((ROOT / "fixtures" / name).read_text())

    def test_clean_batch_passes(self):
        decision = gate.evaluate(self.load("pass_batch.json"))
        self.assertEqual("PASS", decision["status"])
        self.assertEqual([], decision["reason_codes"])
        self.assertTrue(decision["mass_balance"]["checked"])
        self.assertEqual("0", decision["mass_balance"]["variance_liters"])

    def test_missing_handoff_owner_holds_with_stable_code(self):
        decision = gate.evaluate(self.load("hold_missing_owner.json"))
        self.assertEqual("HOLD", decision["status"])
        self.assertIn("HANDOFF_OWNER_MISSING", [r["code"] for r in decision["reason_codes"]])

    def test_mass_imbalance_holds(self):
        decision = gate.evaluate(self.load("hold_mass_balance.json"))
        self.assertEqual("HOLD", decision["status"])
        self.assertIn("MASS_BALANCE_OUT_OF_TOLERANCE", [r["code"] for r in decision["reason_codes"]])

    def test_out_of_order_handoff_holds(self):
        batch = self.load("pass_batch.json")
        batch["handoffs"][2]["timestamp"] = "2026-08-31T16:05:00Z"
        decision = gate.evaluate(batch)
        self.assertIn("HANDOFF_SEQUENCE_INVALID", [r["code"] for r in decision["reason_codes"]])

    def test_deterministic_decision_and_pdf(self):
        batch = self.load("pass_batch.json")
        first = gate.evaluate(batch)
        second = gate.evaluate(batch)
        self.assertEqual(gate.canonical_json(first), gate.canonical_json(second))
        self.assertEqual(gate.render_pdf(first), gate.render_pdf(second))
        self.assertTrue(gate.render_pdf(first).startswith(b"%PDF-1.4"))

    def test_cli_writer_names_outputs_and_emits_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path, pdf_path, decision = gate.run(ROOT / "fixtures" / "pass_batch.json", Path(tmp))
            self.assertEqual("PASS", decision["status"])
            self.assertTrue(json_path.exists())
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
