import copy, json, unittest
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("readiness", ROOT / "shipaton" / "readiness.py")
readiness = importlib.util.module_from_spec(spec); spec.loader.exec_module(readiness)

class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "shipaton" / "manifest.json").read_text())
        self.witness = {
            "authority": "external-provider-observation",
            "package": "com.tokenjunkielabs.proofpocket",
            "version_code": 1,
            "observed_at_utc": "2026-09-30T20:00:00Z",
            "revenuecat_account_verified": True,
            "revenuecat_product_offering_verified": True,
            "store_developer_account_verified": True,
            "store_publication_verified": True,
            "public_store_url": "https://play.google.com/store/apps/details?id=com.tokenjunkielabs.proofpocket",
            "demo_video_url": "https://example.com/demo",
            "screenshot_evidence": "sha256:abc",
            "devpost_submission_verified": True,
        }

    def test_current_manifest_fails_closed(self):
        result = readiness.compile_readiness(self.manifest, None)
        self.assertEqual("HOLD_EXTERNAL_AUTHORITY", result["status"])
        self.assertFalse(result["ready_authorized"])

    def test_fully_populated_local_witness_cannot_clear(self):
        result = readiness.compile_readiness(self.manifest, self.witness)
        self.assertEqual("HOLD_EXTERNAL_AUTHORITY", result["status"])
        self.assertFalse(result["ready_authorized"])
        self.assertTrue(any("SELF_ASSERTED" in x for x in result["reasons"]))

    def test_authority_label_cannot_upgrade(self):
        witness = copy.deepcopy(self.witness)
        witness["authority"] = "external-provider-observation"
        self.assertFalse(readiness.compile_readiness(self.manifest, witness)["ready_authorized"])

    def test_source_cannot_self_assert_ready(self):
        manifest = copy.deepcopy(self.manifest); manifest["submission_ready"] = True
        result = readiness.compile_readiness(manifest, self.witness)
        self.assertFalse(result["ready_authorized"])
        self.assertTrue(any("may not self-assert" in x for x in result["reasons"]))

    def test_identity_drift_stays_hold(self):
        witness = copy.deepcopy(self.witness); witness["package"] = "com.attacker.other"
        result = readiness.compile_readiness(self.manifest, witness)
        self.assertFalse(result["ready_authorized"])
        self.assertTrue(any("identity drift" in x for x in result["reasons"]))

    def test_future_after_deadline_stays_hold(self):
        witness = copy.deepcopy(self.witness); witness["observed_at_utc"] = "2026-10-01T07:00:00Z"
        result = readiness.compile_readiness(self.manifest, witness)
        self.assertFalse(result["ready_authorized"])
        self.assertTrue(any("after competition deadline" in x for x in result["reasons"]))

    def test_missing_gate_stays_hold(self):
        witness = copy.deepcopy(self.witness); witness["store_publication_verified"] = False
        result = readiness.compile_readiness(self.manifest, witness)
        self.assertFalse(result["ready_authorized"])

    def test_deterministic_identity(self):
        a = readiness.compile_readiness(self.manifest, None)["identity_sha256"]
        b = readiness.compile_readiness(json.loads(json.dumps(self.manifest, sort_keys=True)), None)["identity_sha256"]
        self.assertEqual(a, b)

    def test_witness_digest_is_deterministic_but_non_authorizing(self):
        a = readiness.compile_readiness(self.manifest, self.witness)
        b = readiness.compile_readiness(self.manifest, json.loads(json.dumps(self.witness, sort_keys=True)))
        self.assertEqual(a["self_asserted_witness_sha256"], b["self_asserted_witness_sha256"])
        self.assertFalse(a["ready_authorized"])
        self.assertFalse(b["ready_authorized"])

if __name__ == "__main__": unittest.main()
