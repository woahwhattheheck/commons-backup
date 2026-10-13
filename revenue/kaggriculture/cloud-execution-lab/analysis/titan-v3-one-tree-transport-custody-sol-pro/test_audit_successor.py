from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import audit_successor as successor
import audit_transport as core
from test_audit_transport import packet_fixture, strict_dump


def make_claim(blob: bytes, package: dict) -> dict:
    claim = {
        "schema": successor.CLAIM_SCHEMA,
        "file_id": "FNEWOBJECT",
        "transport": {
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
            "regular_files": 13,
        },
        "package": copy.deepcopy(package),
        "publication_claim": {
            "channel_id": "CNEW",
            "thread_ts": "1.2",
            "message_ts": "1.3",
        },
    }
    claim["claim_sha256"] = successor.claim_digest(claim)
    return claim


class SuccessorClaimTests(unittest.TestCase):
    def test_new_object_passes_only_its_own_sealed_claim(self):
        blob, package = packet_fixture()
        claim = make_claim(blob, package)
        before = (
            core.EXPECTED_FILE_ID,
            core.EXPECTED_TRANSPORT_SHA256,
            core.EXPECTED_TRANSPORT_BYTES,
            core.EXPECTED_TRANSPORT_FILES,
            dict(core.PUBLICATION_CLAIM),
        )
        report = successor.audit_successor(blob, claim)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["file_id"], "FNEWOBJECT")
        self.assertEqual(report["external_claim_sha256"], claim["claim_sha256"])
        core.verify_seal(report)
        after = (
            core.EXPECTED_FILE_ID,
            core.EXPECTED_TRANSPORT_SHA256,
            core.EXPECTED_TRANSPORT_BYTES,
            core.EXPECTED_TRANSPORT_FILES,
            dict(core.PUBLICATION_CLAIM),
        )
        self.assertEqual(after, before)

    def test_package_disagreement_is_hold_not_pass(self):
        blob, package = packet_fixture()
        claim = make_claim(blob, package)
        claim["package"]["base"]["sha256"] = "9" * 64
        claim["claim_sha256"] = successor.claim_digest(claim)
        report = successor.audit_successor(blob, claim)
        self.assertEqual(report["verdict"], "HOLD_STALE_REPIN")
        self.assertEqual([row["path"] for row in report["mismatches"]], ["base.sha256"])

    def test_claim_tamper_is_invalid_before_packet_parse(self):
        blob, package = packet_fixture()
        claim = make_claim(blob, package)
        claim["transport"]["bytes"] += 1
        with self.assertRaisesRegex(core.AuditError, "seal mismatch"):
            successor.audit_successor(b"not a tar", claim)

    def test_observed_file_id_must_match_claim(self):
        blob, package = packet_fixture()
        claim = make_claim(blob, package)
        with self.assertRaisesRegex(core.AuditError, "unexpected Slack file id"):
            successor.audit_successor(blob, claim, observed_file_id="FOTHER")

    def test_cli_writes_sealed_pass_report(self):
        blob, package = packet_fixture()
        claim = make_claim(blob, package)
        with tempfile.TemporaryDirectory() as td:
            packet_path = Path(td, "packet.tar.gz")
            claim_path = Path(td, "claim.json")
            report_path = Path(td, "report.json")
            packet_path.write_bytes(blob)
            claim_path.write_bytes(strict_dump(claim))
            status = successor.main([
                "--packet", str(packet_path),
                "--claim-profile", str(claim_path),
                "--output", str(report_path),
            ])
            self.assertEqual(status, 0)
            report = core.strict_json(report_path.read_bytes(), "report")
            self.assertEqual(report["verdict"], "PASS")
            self.assertEqual(report["external_claim_sha256"], claim["claim_sha256"])
            core.verify_seal(report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
