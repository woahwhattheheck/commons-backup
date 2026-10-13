import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from rail import RailError, receipt_for, reconcile, verify_receipt

FIXTURE = json.loads((HERE / "fixtures" / "acceptance.json").read_text())

class RailTests(unittest.TestCase):
    def test_acceptance_fixture_reconciles_exactly(self):
        manifest = reconcile(FIXTURE)
        self.assertEqual(manifest["award_count"], 6)
        self.assertEqual(manifest["net_disbursed_cents"], 43750000)
        self.assertEqual(manifest["totals"]["program"], {"CAPACITY_BUILDING": 3000000, "COMMUNITY_PRIORITY": 40750000})
        self.assertEqual(manifest["review_holds"], [{"award_id":"CP-003","milestone_id":"MS-003","owner_role":"Foundation grant operations reviewer","reason":"PAST_DUE_MILESTONE"}])

    def test_order_invariant(self):
        expected = reconcile(FIXTURE)
        shuffled = copy.deepcopy(FIXTURE)
        random.Random(913).shuffle(shuffled["events"])
        self.assertEqual(reconcile(shuffled), expected)

    def test_identical_retry_does_not_change_state(self):
        retried = copy.deepcopy(FIXTURE)
        retried["events"].extend(copy.deepcopy(FIXTURE["events"][:4]))
        self.assertEqual(reconcile(retried), reconcile(FIXTURE))

    def test_conflicting_retry_fails_closed(self):
        bad = copy.deepcopy(FIXTURE)
        row = copy.deepcopy(bad["events"][0]); row["authorized_cents"] += 1
        bad["events"].append(row)
        with self.assertRaisesRegex(RailError, "conflicting duplicate event_id"):
            reconcile(bad)

    def test_unknown_reference_fails_closed(self):
        bad = copy.deepcopy(FIXTURE)
        next(x for x in bad["events"] if x["type"] == "disbursement")["award_id"] = "NOPE"
        with self.assertRaisesRegex(RailError, "unknown award"):
            reconcile(bad)

    def test_disbursement_cannot_exceed_authority(self):
        bad = copy.deepcopy(FIXTURE)
        next(x for x in bad["events"] if x.get("disbursement_id") == "PAY-001")["amount_cents"] = 12000001
        with self.assertRaisesRegex(RailError, "exceed final authorized"):
            reconcile(bad)

    def test_return_cannot_exceed_disbursement(self):
        bad = copy.deepcopy(FIXTURE)
        next(x for x in bad["events"] if x["type"] == "return")["amount_cents"] = 10000001
        with self.assertRaisesRegex(RailError, "returns exceed disbursement"):
            reconcile(bad)

    def test_pii_fields_rejected(self):
        bad = copy.deepcopy(FIXTURE)
        bad["events"][0]["beneficiary_name"] = "Forbidden Person"
        with self.assertRaisesRegex(RailError, "PII field forbidden"):
            reconcile(bad)

    def test_float_money_rejected(self):
        bad = copy.deepcopy(FIXTURE)
        bad["events"][0]["authorized_cents"] = 1.25
        with self.assertRaisesRegex(RailError, "integer cents"):
            reconcile(bad)

    def test_noncontiguous_amendments_rejected(self):
        bad = copy.deepcopy(FIXTURE)
        next(x for x in bad["events"] if x["type"] == "amendment")["version"] = 2
        with self.assertRaisesRegex(RailError, "contiguous"):
            reconcile(bad)

    def test_satisfied_without_evidence_routes_named_review(self):
        bad = copy.deepcopy(FIXTURE)
        bad["events"] = [x for x in bad["events"] if x.get("evidence_id") != "EV-001"]
        holds = reconcile(bad)["review_holds"]
        self.assertIn({"award_id":"CP-001","milestone_id":"MS-001","owner_role":"Foundation grant operations reviewer","reason":"SATISFIED_WITHOUT_REQUIRED_EVIDENCE"}, holds)

    def test_receipt_detects_manifest_tamper(self):
        manifest = reconcile(FIXTURE)
        receipt = receipt_for(manifest)
        self.assertTrue(verify_receipt(manifest, receipt))
        tampered = copy.deepcopy(manifest); tampered["net_disbursed_cents"] += 1
        with self.assertRaisesRegex(RailError, "manifest hash mismatch"):
            verify_receipt(tampered, receipt)

    def test_authority_is_explicitly_false(self):
        manifest = reconcile(FIXTURE)
        self.assertEqual(set(manifest["authority"].values()), {False})

    def test_cli_build_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "manifest.json"; receipt = Path(td) / "receipt.json"
            built = subprocess.run([sys.executable, str(HERE / "rail.py"), "build", str(HERE / "fixtures" / "acceptance.json"), "--manifest", str(manifest), "--receipt", str(receipt)], text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            checked = subprocess.run([sys.executable, str(HERE / "rail.py"), "verify", str(manifest), str(receipt)], text=True, capture_output=True)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual(json.loads(checked.stdout), {"ok": True})

    def test_optimized_mode_keeps_fail_closed_validation(self):
        code = "import json,sys; sys.path.insert(0,sys.argv[1]); from rail import reconcile,RailError; p=json.load(open(sys.argv[2])); p['events'][0]['authorized_cents']=1.5;\ntry: reconcile(p)\nexcept RailError: raise SystemExit(0)\nraise SystemExit(9)"
        run = subprocess.run([sys.executable, "-O", "-c", code, str(HERE), str(HERE / "fixtures" / "acceptance.json")])
        self.assertEqual(run.returncode, 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
