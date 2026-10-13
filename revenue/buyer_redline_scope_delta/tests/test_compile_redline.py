import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
FIXTURE = PKG / "fixtures" / "requote.synthetic.json"
SPEC = importlib.util.spec_from_file_location("redline", PKG / "compile_redline.py")
redline = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(redline)

def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))

class RedlineCompilerTests(unittest.TestCase):
    def test_fixture_requires_requote(self):
        result, packet, receipt = redline.compile_case(fixture())
        self.assertEqual(receipt["decision"], "REQUOTE_REQUIRED")
        self.assertIn("scope", packet.lower())
        self.assertEqual(result["truth_state"], redline.TRUTH_STATE)

    def test_no_delta_is_acceptable_but_not_acceptance(self):
        raw = fixture()
        raw["counter"] = copy.deepcopy(raw["baseline"])
        raw["counter"]["document_id"] = "COUNTER-SAME"
        raw["counter"]["generation"] = "counter-same-v1"
        raw["counter"]["baseline_generation"] = raw["baseline"]["generation"]
        _, packet, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "ACCEPTABLE_AS_WRITTEN")
        self.assertIn("does not accept or sign", packet)

    def test_ip_change_requires_legal_review(self):
        raw = fixture()
        raw["counter"]["clauses"].append({
            "id":"C-IP","logical_key":"ip","category":"IP",
            "text":"Buyer receives exclusive ownership of all background IP.",
            "terms":{},"buyer_visible":True,
        })
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "LEGAL_REVIEW_REQUIRED")

    def test_unlimited_liability_requires_legal_review(self):
        raw = fixture()
        raw["counter"]["clauses"].append({
            "id":"C-LIAB","logical_key":"liability","category":"LIABILITY_WARRANTY",
            "text":"Supplier liability is unlimited.",
            "terms":{"cap_type":"UNLIMITED"},"buyer_visible":True,
        })
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "LEGAL_REVIEW_REQUIRED")

    def test_deleted_acceptance_is_owner_review_without_other_commercial_change(self):
        raw = fixture()
        raw["counter"]["clauses"] = [
            copy.deepcopy(c) for c in raw["baseline"]["clauses"]
            if c["category"] != "ACCEPTANCE"
        ]
        raw["counter"]["price_total_minor"] = raw["baseline"]["price_total_minor"]
        raw["counter"]["payment_days"] = raw["baseline"]["payment_days"]
        raw["counter"]["currency"] = raw["baseline"]["currency"]
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "OWNER_REVIEW")

    def test_currency_drift_requires_requote(self):
        raw = fixture()
        raw["counter"] = copy.deepcopy(raw["baseline"])
        raw["counter"]["document_id"] = "COUNTER-CURRENCY"
        raw["counter"]["generation"] = "counter-currency-v1"
        raw["counter"]["baseline_generation"] = raw["baseline"]["generation"]
        raw["counter"]["currency"] = "EUR"
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "REQUOTE_REQUIRED")

    def test_wider_payment_terms_require_requote(self):
        raw = fixture()
        raw["counter"] = copy.deepcopy(raw["baseline"])
        raw["counter"]["document_id"] = "COUNTER-NET60"
        raw["counter"]["generation"] = "counter-net60-v1"
        raw["counter"]["baseline_generation"] = raw["baseline"]["generation"]
        raw["counter"]["payment_days"] = 60
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "REQUOTE_REQUIRED")

    def test_scope_expansion_without_price_change_requires_requote(self):
        raw = fixture()
        raw["counter"] = copy.deepcopy(raw["baseline"])
        raw["counter"]["document_id"] = "COUNTER-SCOPE"
        raw["counter"]["generation"] = "counter-scope-v1"
        raw["counter"]["baseline_generation"] = raw["baseline"]["generation"]
        raw["counter"]["clauses"].append({
            "id":"C-SCOPE-EXTRA","logical_key":"scope.extra","category":"SCOPE",
            "text":"Add a second deployment environment at no stated price change.",
            "terms":{"environment_count":2},"buyer_visible":True,
        })
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "REQUOTE_REQUIRED")

    def test_stale_baseline_generation_holds(self):
        raw = fixture()
        raw["counter"]["baseline_generation"] = "old-baseline-v0"
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "HOLD_CONTRADICTION")

    def test_conflicting_logical_keys_hold(self):
        raw = fixture()
        duplicate = copy.deepcopy(raw["counter"]["clauses"][0])
        duplicate["id"] = "C-SCOPE-DUP"
        duplicate["text"] = "Conflicting scope variant."
        raw["counter"]["clauses"].append(duplicate)
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "HOLD_CONTRADICTION")
        self.assertGreater(receipt["hold_count"], 0)

    def test_header_clause_currency_conflict_holds(self):
        raw = fixture()
        raw["counter"]["clauses"].append({
            "id":"C-PRICE","logical_key":"price.currency","category":"PRICE_PAYMENT",
            "text":"Price payable in EUR.","terms":{"currency":"EUR"},"buyer_visible":True,
        })
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "HOLD_CONTRADICTION")

    def test_category_change_same_logical_key_holds(self):
        raw = fixture()
        for c in raw["counter"]["clauses"]:
            if c["logical_key"] == "scope.primary":
                c["category"] = "TERMINATION"
                break
        _, _, receipt = redline.compile_case(raw)
        self.assertEqual(receipt["decision"], "HOLD_CONTRADICTION")

    def test_non_proposed_truth_state_rejected(self):
        raw = fixture()
        raw["counter"]["truth_state"] = "ACCEPTED"
        with self.assertRaises(redline.InputError):
            redline.compile_case(raw)

    def test_bool_money_rejected(self):
        raw = fixture()
        raw["counter"]["price_total_minor"] = True
        with self.assertRaises(redline.InputError):
            redline.compile_case(raw)

    def test_path_traversal_rejected(self):
        raw = fixture()
        raw["counter"]["source"] = "../../secret"
        with self.assertRaises(redline.InputError):
            redline.compile_case(raw)

    def test_url_userinfo_rejected(self):
        raw = fixture()
        raw["counter"]["source"] = "https://user:token@example.com/counter"
        with self.assertRaises(redline.InputError):
            redline.compile_case(raw)

    def test_unicode_normalization_is_not_silently_collapsed(self):
        raw = fixture()
        raw["counter"] = copy.deepcopy(raw["baseline"])
        raw["counter"]["document_id"] = "COUNTER-UNICODE"
        raw["counter"]["generation"] = "counter-unicode-v1"
        raw["counter"]["baseline_generation"] = raw["baseline"]["generation"]
        raw["baseline"]["clauses"][0]["text"] = "café"
        raw["counter"]["clauses"][0]["text"] = "cafe\u0301"
        _, _, receipt = redline.compile_case(raw)
        self.assertNotEqual(receipt["decision"], "ACCEPTABLE_AS_WRITTEN")

    def test_duplicate_json_key_rejected_by_cli_loader(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            with self.assertRaises(redline.InputError):
                redline.load_json_strict(p)

    def test_nan_rejected_by_cli_loader(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text('{"x":NaN}', encoding="utf-8")
            with self.assertRaises(redline.InputError):
                redline.load_json_strict(p)

    def test_compile_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            out = td / "out"
            self.assertEqual(redline.compile_to_dir(FIXTURE, out), 0)
            self.assertEqual(redline.verify(FIXTURE, out/"packet.md", out/"receipt.json"), 0)
            (out/"packet.md").write_text("tampered\n", encoding="utf-8")
            self.assertEqual(redline.verify(FIXTURE, out/"packet.md", out/"receipt.json"), 1)

    def test_fail_on_hold_exit_code(self):
        raw = fixture()
        raw["counter"]["baseline_generation"] = "wrong"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "case.json"
            inp.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(redline.compile_to_dir(inp, td/"out", fail_on_hold=True), 2)

    def test_optimized_python_cli(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            out = td/"out"
            c = subprocess.run([
                sys.executable, "-O", str(PKG/"compile_redline.py"), "compile",
                "--input", str(FIXTURE), "--out-dir", str(out)
            ], capture_output=True, text=True)
            self.assertEqual(c.returncode, 0, c.stderr)
            v = subprocess.run([
                sys.executable, "-O", str(PKG/"compile_redline.py"), "verify",
                "--input", str(FIXTURE), "--packet", str(out/"packet.md"),
                "--receipt", str(out/"receipt.json")
            ], capture_output=True, text=True)
            self.assertEqual(v.returncode, 0, v.stderr)
            self.assertIn("VERIFY_OK", v.stdout)

if __name__ == "__main__":
    unittest.main()
