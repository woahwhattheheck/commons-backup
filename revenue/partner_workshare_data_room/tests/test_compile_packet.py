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
FIXTURE = PKG / "fixtures" / "opportunity.synthetic.json"
SPEC = importlib.util.spec_from_file_location("compile_packet", PKG / "compile_packet.py")
cp = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(cp)


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class WorksharePacketTests(unittest.TestCase):
    def test_fixture_is_owner_review_ready(self):
        doc, packet, receipt = cp.compile_document(load_fixture())
        self.assertEqual(receipt["status"], "OWNER_REVIEW_READY")
        self.assertEqual(receipt["hold_count"], 0)
        self.assertIn("PROPOSED_NOT_ACCEPTED", packet)
        self.assertIn("not partner acceptance", packet.lower())
        self.assertEqual(doc["truth_ceiling"], cp.TRUTH_CEILING)

    def test_semantic_permutations_are_deterministic(self):
        a = load_fixture()
        b = copy.deepcopy(a)
        for key in (
            "parties", "evidence_receipts", "claims", "capability_slices", "workshare",
            "security_access_requirements", "delivery_proof_refs", "pricing_basis",
            "exclusions", "assumptions",
        ):
            b[key].reverse()
        for ws in b["workshare"]:
            ws["allocations"].reverse()
            ws["responsibilities"].reverse()
            ws["evidence_ids"].reverse()
        b["acceptance"]["questions"].reverse()
        for claim in b["claims"]:
            claim["evidence_ids"].reverse()
        _, packet_a, receipt_a = cp.compile_document(a)
        _, packet_b, receipt_b = cp.compile_document(b)
        self.assertEqual(packet_a, packet_b)
        self.assertEqual(receipt_a, receipt_b)

    def test_stale_verified_evidence_holds_instead_of_escalating(self):
        raw = load_fixture()
        raw["evidence_receipts"][0]["valid_through"] = "2026-09-15T00:00:00Z"
        _, _, receipt = cp.compile_document(raw)
        self.assertEqual(receipt["status"], "HOLD")
        codes = {h["code"] for h in receipt["holds"]}
        self.assertIn("UNSUPPORTED_CLAIM", codes)
        self.assertIn("CAPABILITY_EVIDENCE_HOLD", codes)

    def test_conflicting_evidence_holds(self):
        raw = load_fixture()
        raw["evidence_receipts"][1]["status"] = "CONFLICTING"
        _, _, receipt = cp.compile_document(raw)
        self.assertEqual(receipt["status"], "HOLD")
        self.assertTrue(any(h["ref"] == "CL-PARTNER-1" for h in receipt["holds"]))

    def test_missing_sensitive_evidence_holds(self):
        raw = load_fixture()
        raw["claims"][0]["evidence_ids"] = []
        _, _, receipt = cp.compile_document(raw)
        self.assertEqual(receipt["status"], "HOLD")
        self.assertTrue(any(h["ref"] == "CL-TJL-1" for h in receipt["holds"]))

    def test_partner_relationship_claim_is_rejected(self):
        raw = load_fixture()
        raw["claims"].append({
            "id": "CL-BAD-REL",
            "subject_party_id": "PARTNER-A",
            "category": "PARTNER_RELATIONSHIP",
            "text": "Partner accepted the relationship.",
            "evidence_ids": ["EV-PARTNER-CAP"],
        })
        with self.assertRaises(cp.InputError):
            cp.compile_document(raw)

    def test_relationship_state_cannot_exceed_truth_ceiling(self):
        raw = load_fixture()
        raw["parties"][1]["relationship_state"] = "ACCEPTED"
        with self.assertRaises(cp.InputError):
            cp.compile_document(raw)

    def test_numeric_pricing_is_rejected(self):
        raw = load_fixture()
        raw["pricing_basis"][0]["amount"] = 25000
        raw["pricing_basis"][0]["currency"] = "USD"
        with self.assertRaises(cp.InputError):
            cp.compile_document(raw)

    def test_acceptance_state_is_never_inferred(self):
        raw = load_fixture()
        raw["acceptance"]["state"] = "ACCEPTED"
        with self.assertRaises(cp.InputError):
            cp.compile_document(raw)

    def test_traversal_delivery_proof_is_rejected(self):
        raw = load_fixture()
        raw["delivery_proof_refs"][0]["path"] = "../../secrets.txt"
        with self.assertRaises(cp.InputError):
            cp.compile_document(raw)

    def test_https_userinfo_source_is_rejected(self):
        raw = load_fixture()
        raw["evidence_receipts"][0]["source"] = "https://user:token@example.com/private"
        with self.assertRaises(cp.InputError):
            cp.compile_document(raw)

    def test_allocations_must_sum_to_100_percent(self):
        raw = load_fixture()
        raw["workshare"][0]["allocations"][0]["basis_points"] = 7499
        with self.assertRaises(cp.InputError):
            cp.compile_document(raw)

    def test_duplicate_ids_are_rejected(self):
        raw = load_fixture()
        raw["parties"][1]["id"] = "TJL"
        with self.assertRaises(cp.InputError):
            cp.compile_document(raw)

    def test_required_security_without_security_receipt_holds(self):
        raw = load_fixture()
        raw["security_access_requirements"][0]["evidence_ids"] = ["EV-PARTNER-CAP"]
        _, _, receipt = cp.compile_document(raw)
        self.assertEqual(receipt["status"], "HOLD")
        self.assertTrue(any(h["code"] == "SECURITY_ACCESS_HOLD" for h in receipt["holds"]))

    def test_compile_verify_and_tamper_detection(self):
        raw = load_fixture()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "input.json"
            out = td / "out"
            inp.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(cp.compile_to_dir(inp, out), 0)
            self.assertEqual(cp.verify_artifacts(inp, out / "packet.md", out / "receipt.json"), 0)
            (out / "packet.md").write_text("tampered\n", encoding="utf-8")
            self.assertEqual(cp.verify_artifacts(inp, out / "packet.md", out / "receipt.json"), 1)

    def test_fail_on_hold_exit_code(self):
        raw = load_fixture()
        raw["claims"][0]["evidence_ids"] = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "input.json"
            inp.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(cp.compile_to_dir(inp, td / "out", fail_on_hold=True), 2)

    def test_local_fixture_refs_match_hashes(self):
        raw = load_fixture()
        local_refs = [
            (raw["opportunity"]["source"], raw["opportunity"]["source_sha256"]),
            (raw["evidence_receipts"][0]["source"], raw["evidence_receipts"][0]["source_sha256"]),
            (raw["delivery_proof_refs"][0]["path"], raw["delivery_proof_refs"][0]["sha256"]),
        ]
        import hashlib
        for rel, expected in local_refs:
            data = (PKG / rel).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, rel)

    def test_optimized_python_keeps_guards_and_verifier(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            out = td / "out"
            compile_cmd = [
                sys.executable, "-O", str(PKG / "compile_packet.py"), "compile",
                "--input", str(FIXTURE), "--out-dir", str(out), "--fail-on-hold",
            ]
            result = subprocess.run(compile_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            verify_cmd = [
                sys.executable, "-O", str(PKG / "compile_packet.py"), "verify",
                "--input", str(FIXTURE), "--packet", str(out / "packet.md"),
                "--receipt", str(out / "receipt.json"),
            ]
            verify = subprocess.run(verify_cmd, capture_output=True, text=True, check=False)
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertIn("VERIFY_OK", verify.stdout)


if __name__ == "__main__":
    unittest.main()
