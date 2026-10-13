import copy
from pathlib import Path
import contextlib
import io
import unittest

import cli
from qualifier import (
    compile_qualification,
    normalized_source_sha256,
    verify_current_qualification,
)
from test_qualifier import AS_OF, complete_packet, public_packet


class CurrentAuthorityTests(unittest.TestCase):
    def test_incomplete_packet_cannot_self_close_on_untrusted_deadline(self):
        packet = public_packet()
        packet["closeAt"] = "2026-09-13T10:45:00Z"
        out = compile_qualification(packet, as_of=AS_OF)
        self.assertEqual(out["receipt"]["disposition"], "HOLD_RAW_PACKET_REQUIRED")
        self.assertIn("DEADLINE_NOT_BOUND_TO_CONTROLLING_SOURCE", out["receipt"]["reasons"])

    def test_incomplete_packet_stays_hold_even_with_exact_self_content_tamper(self):
        packet = public_packet()
        packet["closeAt"] = "2026-09-13T10:45:00Z"
        trusted = normalized_source_sha256(packet, as_of=AS_OF)
        out = compile_qualification(packet, as_of=AS_OF, expected_source_packet_sha256=trusted)
        self.assertEqual(out["receipt"]["disposition"], "HOLD_RAW_PACKET_REQUIRED")

    def test_retained_trusted_packet_ages_to_stale_hold(self):
        packet = complete_packet()
        trusted = normalized_source_sha256(packet, as_of=AS_OF)
        first = compile_qualification(packet, as_of=AS_OF, expected_source_packet_sha256=trusted)
        self.assertEqual(first["receipt"]["disposition"], "PRIME_READY_FOR_OWNER_REVIEW")
        later = compile_qualification(
            packet,
            as_of="2026-09-15T10:50:01Z",
            expected_source_packet_sha256=trusted,
        )
        self.assertEqual(later["receipt"]["disposition"], "HOLD_PACKAGE_INVENTORY_STALE")
        self.assertEqual(later["receipt"]["reasons"], ["ADDENDA_CHECK_EXCEEDS_24H_POLICY"])

    def test_current_verifier_detects_aged_authority(self):
        packet = complete_packet()
        trusted = normalized_source_sha256(packet, as_of=AS_OF)
        receipt = compile_qualification(
            packet,
            as_of=AS_OF,
            expected_source_packet_sha256=trusted,
        )["receipt"]
        self.assertTrue(
            verify_current_qualification(
                packet,
                receipt,
                current_as_of="2026-09-13T11:00:00Z",
                expected_source_packet_sha256=trusted,
            )
        )
        self.assertFalse(
            verify_current_qualification(
                packet,
                receipt,
                current_as_of="2026-09-15T10:50:01Z",
                expected_source_packet_sha256=trusted,
            )
        )

    def test_current_verifier_rejects_time_before_receipt(self):
        packet = public_packet()
        receipt = compile_qualification(packet, as_of=AS_OF)["receipt"]
        self.assertFalse(
            verify_current_qualification(
                packet,
                receipt,
                current_as_of="2026-09-13T10:49:59Z",
            )
        )

    def test_production_cli_has_no_caller_as_of(self):
        sink = io.StringIO()
        with contextlib.redirect_stderr(sink):
            with self.assertRaises(SystemExit):
                cli.parser().parse_args([
                    "compile", "--source", "source.json", "--out", "out.json",
                    "--as-of", AS_OF,
                ])
            with self.assertRaises(SystemExit):
                cli.parser().parse_args([
                    "verify", "--source", "source.json", "--receipt", "receipt.json",
                    "--as-of", AS_OF,
                ])

    def test_tampering_deadline_changes_trusted_digest(self):
        packet = complete_packet()
        trusted = normalized_source_sha256(packet, as_of=AS_OF)
        tampered = copy.deepcopy(packet)
        tampered["closeAt"] = "2026-09-14T00:00:00Z"
        self.assertNotEqual(trusted, normalized_source_sha256(tampered, as_of=AS_OF))
        out = compile_qualification(tampered, as_of=AS_OF, expected_source_packet_sha256=trusted)
        self.assertEqual(out["receipt"]["disposition"], "HOLD_SOURCE_PACKET_TRUST_ROOT_MISMATCH")

    def test_hosted_workflow_and_docs_have_no_caller_as_of(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/fsu-itn-6769-4.yml").read_text(encoding="utf-8")
        docs = Path(__file__).with_name("QUALIFICATION.md").read_text(encoding="utf-8")
        self.assertNotIn("--as-of", workflow)
        self.assertNotIn("--as-of", docs)
        self.assertIn("VERIFIED_CURRENT", workflow)
        self.assertIn("VERIFIED_CURRENT", docs)


if __name__ == "__main__":
    unittest.main()
