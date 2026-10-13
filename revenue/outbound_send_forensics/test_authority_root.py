import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import revenue.outbound_send_forensics.audit as audit
from revenue.outbound_connector_lease.key import compile_document

TEST_KEY = bytes.fromhex("11" * 32)
FIXED_ROOT = Path("/etc/commons/outbound-send-forensics/authority-key.json")


def _mac(payload):
    return hmac.new(TEST_KEY, audit._canonical_bytes(payload), hashlib.sha256).hexdigest()


def _forged_document():
    seam = {
        "schema": "outbound-connector-lease/v1",
        "buyer_scope": "example.com",
        "opportunity": {
            "kind": "external",
            "authority": "issuer.example",
            "id": "rfp-04254",
        },
    }
    compiled = compile_document(seam)
    send = {
        "provider": "gmail",
        "event_id": "attacker-selected-event",
        "sent_at": "2026-09-14T01:20:00Z",
        "status": "sent",
        "receipt_sha256": "a" * 64,
    }
    _, send_at = audit._timestamp(send["sent_at"], "send.sent_at")
    normalized_send = {
        **send,
        "provider": send["provider"].casefold(),
        "event_id": send["event_id"].casefold(),
        "sent_at": send_at,
    }
    send["attestation_hmac_sha256"] = _mac(
        audit._send_attestation_payload(normalized_send, compiled["seam_sha256"])
    )

    lease = {
        "repository_full_name": audit.CANONICAL_LEASE_REPOSITORY,
        "branch": compiled["branch"],
        "created_at": "2026-09-14T01:19:00Z",
        "result": "created",
        "base_sha": "c" * 40,
        "receipt_sha256": "b" * 64,
    }
    _, created_at = audit._timestamp(lease["created_at"], "lease.created_at")
    normalized_lease = {
        **lease,
        "repository_full_name": lease["repository_full_name"].casefold(),
        "created_at": created_at,
    }
    lease["attestation_hmac_sha256"] = _mac(
        audit._lease_attestation_payload(normalized_lease)
    )
    return {
        "schema": audit.INPUT_SCHEMA,
        "records": [
            {
                "record_id": "attacker-home",
                "seam": seam,
                "send": send,
                "lease_create": lease,
            }
        ],
    }


class AuthorityRootHostileTests(unittest.TestCase):
    def test_production_root_is_absolute_and_not_home_derived(self):
        self.assertEqual(audit.HOST_AUTHORITY_KEY_PATH, FIXED_ROOT)
        self.assertTrue(audit.HOST_AUTHORITY_KEY_PATH.is_absolute())

    def test_alternate_home_attacker_key_cannot_mint_current_authority(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            attacker_home = td / "claimant-home"
            attacker_key = (
                attacker_home
                / ".config"
                / "commons"
                / "outbound-send-forensics"
                / "authority-key.json"
            )
            attacker_key.parent.mkdir(parents=True)
            attacker_key.write_text(
                json.dumps(
                    {
                        "schema": audit.AUTHORITY_KEY_SCHEMA,
                        "key_hex": TEST_KEY.hex(),
                    }
                ),
                encoding="utf-8",
            )
            if os.name == "posix":
                os.chmod(attacker_key, 0o600)

            evidence = td / "forged.json"
            evidence.write_text(json.dumps(_forged_document()), encoding="utf-8")
            env = os.environ.copy()
            env["HOME"] = str(attacker_home)
            env["USERPROFILE"] = str(attacker_home)
            repo_root = Path(__file__).resolve().parents[2]
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "revenue.outbound_send_forensics.audit",
                    str(evidence),
                ],
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )

            if completed.returncode == 2:
                self.assertIn("HOLD:", completed.stderr)
                self.assertNotIn(str(attacker_key), completed.stderr)
                return

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            receipt = result["receipts"][0]
            self.assertEqual(receipt["classification"], audit.CLASS_UNTRUSTED)
            self.assertFalse(receipt["send_authority_authenticated"])
            self.assertFalse(receipt["lease_authority_authenticated"])


if __name__ == "__main__":
    unittest.main()
