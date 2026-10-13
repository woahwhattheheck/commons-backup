import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.runtime_provenance.runtime_registry import RegistryError, canonical_json, registry_digest, verify_registry
from tools.runtime_provenance._test_fixtures import *  # noqa: F403

class RuntimeRegistryTests(unittest.TestCase):
    def assessment(self, payload):
        return verify_registry(payload, now=NOW)["records"][0]

    def test_happy_deployment_proven(self):
        result = verify_registry(registry(), now=NOW)
        self.assertEqual(result["deployment_proven_runtime_ids"], ["muse.slack.production"])
        self.assertTrue(result["records"][0]["deployment_proven"])
        self.assertEqual(result["records"][0]["effective_lifecycle"], "DEPLOYMENT_PROVEN")
        self.assertFalse(result["external_send_authorized"])
        self.assertFalse(result["deployment_mutation_authorized"])

    def test_repo_merge_alone_never_proves_deployment(self):
        rec = proven_record()
        rec["evidence"] = [{
            "kind": "REPO_MERGE",
            "ref": "github:merge/123",
            "observed_at": EVIDENCE_AT,
            "generation": GEN,
        }]
        result = self.assessment(registry(rec))
        self.assertFalse(result["deployment_proven"])
        self.assertEqual(result["effective_lifecycle"], "UNKNOWN")
        self.assertIn("NO_DEPLOYMENT_EVIDENCE", result["reasons"])
        self.assertIn("NO_BLACK_BOX_EVIDENCE", result["reasons"])

    def test_stale_probe_fails_closed_to_stale(self):
        rec = proven_record()
        rec["probe"]["observed_at"] = "2026-09-13T07:45:00Z"
        rec["evidence"][1]["observed_at"] = "2026-09-13T07:45:00Z"
        result = self.assessment(registry(rec))
        self.assertFalse(result["deployment_proven"])
        self.assertEqual(result["effective_lifecycle"], "STALE")
        self.assertIn("STALE_PROBE", result["reasons"])

    def test_generation_mismatch_fails_closed(self):
        rec = proven_record()
        rec["probe"]["generation"] = "deploy:other"
        result = self.assessment(registry(rec))
        self.assertFalse(result["deployment_proven"])
        self.assertIn("PROBE_GENERATION_MISMATCH", result["reasons"])

    def test_unknown_config_fails_closed(self):
        rec = proven_record()
        rec["config_location"] = "UNKNOWN"
        result = self.assessment(registry(rec))
        self.assertFalse(result["deployment_proven"])
        self.assertIn("UNKNOWN_CONFIG_LOCATION", result["reasons"])

    def test_future_evidence_fails_closed(self):
        rec = proven_record()
        rec["evidence_at"] = "2026-09-15T09:00:00Z"
        result = self.assessment(registry(rec))
        self.assertFalse(result["deployment_proven"])
        self.assertIn("FUTURE_EVIDENCE_TIME", result["reasons"])

    def test_secret_like_value_is_rejected(self):
        rec = proven_record()
        rec["runtime_surface"] = "service:" + "xo" + "xb-123456789012-abcdefghijklmnop"
        with self.assertRaises(RegistryError):
            verify_registry(registry(rec), now=NOW)

    def test_secret_like_key_is_rejected(self):
        rec = proven_record()
        rec["provider_ids"] = {"api_token": "not-even-a-real-secret"}
        with self.assertRaises(RegistryError):
            verify_registry(registry(rec), now=NOW)

    def test_secret_like_query_parameter_is_rejected(self):
        rec = proven_record()
        rec["config_location"] = "https://runtime.invalid/config?token=abcd1234"
        with self.assertRaises(RegistryError):
            verify_registry(registry(rec), now=NOW)

    def test_unhashable_authority_surface_is_cleanly_rejected(self):
        rec = proven_record()
        rec["authority_surfaces"] = [{"bad": "shape"}]
        with self.assertRaises(RegistryError):
            verify_registry(registry(rec), now=NOW)

    def test_unknown_seed_is_valid_but_not_deployment_proven(self):
        rec = proven_record()
        rec.update({
            "custodian": "UNKNOWN",
            "runtime_surface": "UNKNOWN",
            "config_location": "UNKNOWN",
            "deployed_generation": "UNKNOWN",
            "source_commitment": {"kind": "UNKNOWN", "value": "UNKNOWN"},
            "config_commitment": {"kind": "UNKNOWN", "value": "UNKNOWN"},
            "trigger": {"mechanism": "UNKNOWN", "cadence": "UNKNOWN"},
            "authority_surfaces": ["UNKNOWN"],
            "decision_contract": "UNKNOWN",
            "deployment_at": "UNKNOWN",
            "evidence_at": "UNKNOWN",
            "probe": {
                "suite": "UNKNOWN",
                "generation": "UNKNOWN",
                "observed_at": None,
                "result": "UNKNOWN",
            },
            "lifecycle": "UNKNOWN",
            "evidence": [],
        })
        result = self.assessment(registry(rec))
        self.assertFalse(result["deployment_proven"])
        self.assertEqual(result["effective_lifecycle"], "UNKNOWN")

    def test_source_bound_does_not_imply_deployed(self):
        rec = proven_record()
        rec["lifecycle"] = "SOURCE_BOUND"
        rec["deployed_generation"] = "UNKNOWN"
        rec["deployment_at"] = "UNKNOWN"
        rec["evidence_at"] = "UNKNOWN"
        rec["probe"] = {
            "suite": "UNKNOWN",
            "generation": "UNKNOWN",
            "observed_at": None,
            "result": "UNKNOWN",
        }
        rec["authority_surfaces"] = ["UNKNOWN"]
        rec["trigger"] = {"mechanism": "UNKNOWN", "cadence": "UNKNOWN"}
        rec["decision_contract"] = "UNKNOWN"
        rec["evidence"] = [{
            "kind": "SOURCE_COMMIT",
            "ref": "github:commit/example",
            "observed_at": EVIDENCE_AT,
            "generation": "source:abc",
        }]
        result = self.assessment(registry(rec))
        self.assertEqual(result["effective_lifecycle"], "SOURCE_BOUND")
        self.assertFalse(result["deployment_proven"])

    def test_unknown_evidence_reference_is_rejected(self):
        rec = proven_record()
        rec["evidence"][0]["ref"] = "UNKNOWN"
        with self.assertRaises(RegistryError):
            verify_registry(registry(rec), now=NOW)

    def test_unknown_provider_identity_is_rejected(self):
        rec = proven_record()
        rec["provider_ids"] = {"slack_user_id": "UNKNOWN"}
        with self.assertRaises(RegistryError):
            verify_registry(registry(rec), now=NOW)

    def test_predeployment_black_box_evidence_fails_closed(self):
        rec = proven_record()
        rec["evidence"][1]["observed_at"] = "2026-09-15T06:59:00Z"
        result = self.assessment(registry(rec))
        self.assertFalse(result["deployment_proven"])
        self.assertIn("BLACK_BOX_EVIDENCE_PREDATES_DEPLOYMENT", result["reasons"])

    def test_duplicate_runtime_id_is_rejected(self):
        payload = registry()
        payload["records"].append(copy.deepcopy(payload["records"][0]))
        with self.assertRaises(RegistryError):
            verify_registry(payload, now=NOW)

    def test_digest_is_canonical(self):
        payload = registry()
        reordered = json.loads(json.dumps(payload, sort_keys=True))
        self.assertEqual(registry_digest(payload), registry_digest(reordered))
        self.assertEqual(canonical_json(payload), canonical_json(reordered))

    def test_cli_runs_under_optimized_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(registry()), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-O", "-m", "tools.runtime_provenance.runtime_registry", "verify", str(path), "--now", NOW_TEXT],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            parsed = json.loads(proc.stdout)
            self.assertEqual(parsed["deployment_proven_runtime_ids"], ["muse.slack.production"])


if __name__ == "__main__":
    unittest.main()