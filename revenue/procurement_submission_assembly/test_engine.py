from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from revenue.procurement_submission_assembly import engine


NOW = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


def packet_template() -> dict:
    return {
        "contract_version": engine.CONTRACT_VERSION,
        "opportunity": {
            "opportunity_id": "DEMO-001",
            "buyer": "Example Public Buyer",
            "solicitation_id": "RFP-001",
            "source_generation": 1,
        },
        "sources": [
            {
                "source_id": "rfp-v1",
                "generation": 1,
                "sha256": "1" * 64,
                "source_class": "OFFICIAL",
                "section": "Submission Instructions",
                "observed_at_utc": "2026-09-16T12:00:00Z",
            }
        ],
        "deadlines": [
            {
                "deadline_id": "deadline-v1",
                "at": "2099-10-01T15:00:00-04:00",
                "source_id": "rfp-v1",
                "source_section": "Key Dates",
                "generation": 1,
            }
        ],
        "requirements": [
            {
                "requirement_id": "technical-v1",
                "slot_id": "technical-volume",
                "generation": 1,
                "source_id": "rfp-v1",
                "source_section": "4.2 Technical Volume",
                "requirement_class": "REQUIRED",
                "delivery_kind": "FILE",
                "order": 1,
                "filename_rule": "Technical Volume.pdf",
                "format": "PDF",
                "page_limit": 12,
                "size_limit_bytes": 100000,
                "signature_requirement": "NONE",
                "attachment_class": "TECHNICAL",
                "portal_field": None,
            },
            {
                "requirement_id": "cover-v1",
                "slot_id": "signed-cover",
                "generation": 1,
                "source_id": "rfp-v1",
                "source_section": "3.1 Cover",
                "requirement_class": "OPTIONAL",
                "delivery_kind": "FILE",
                "order": 0,
                "filename_rule": None,
                "format": "PDF",
                "page_limit": 1,
                "size_limit_bytes": None,
                "signature_requirement": "SIGNATORY_AUTHORITY",
                "attachment_class": "COVER",
                "portal_field": None,
            },
        ],
        "artifacts": [
            {
                "slot_id": "technical-volume",
                "kind": "FILE",
                "path": "Technical Volume.pdf",
                "built_for_generation": 1,
            }
        ],
    }


class AssemblyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.artifacts = self.root / "artifacts"
        self.output = self.root / "out"
        self.artifacts.mkdir()
        self.output.mkdir()
        (self.artifacts / "Technical Volume.pdf").write_bytes(b"synthetic technical bytes\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def compile(self, packet: dict | None = None) -> dict:
        return engine.compile_packet(packet or packet_template(), str(self.artifacts), _now=NOW)

    def test_ready_binds_exact_candidate_bytes_and_requires_human_checks(self) -> None:
        receipt = self.compile()
        self.assertEqual(receipt["status"], engine.ASSEMBLY_READY_FOR_OWNER_REVIEW)
        evidence = {row["slot_id"]: row for row in receipt["artifact_evidence"]}
        tech = evidence["technical-volume"]
        self.assertEqual(tech["candidate_state"], "PRESENT")
        self.assertEqual(
            tech["candidate_sha256"],
            engine._sha256((self.artifacts / "Technical Volume.pdf").read_bytes()),
        )
        cover = evidence["signed-cover"]
        self.assertEqual(cover["candidate_state"], "MISSING")
        self.assertIn("SIGNATURE_AUTHORITY_OWNER_REVIEW", cover["human_checks"])
        self.assertFalse(receipt["authority"]["signature_or_certification_authorized"])
        self.assertFalse(receipt["authority"]["external_submission_authorized"])

    def test_missing_required_artifact_holds(self) -> None:
        (self.artifacts / "Technical Volume.pdf").unlink()
        receipt = self.compile()
        self.assertEqual(receipt["status"], engine.HOLD_MISSING_REQUIRED_ARTIFACT)
        self.assertEqual(receipt["missing_required_slots"][0]["reason"], "UNREADABLE")

    def test_deadline_passed_overrides_complete_assembly(self) -> None:
        packet = packet_template()
        packet["deadlines"][0]["at"] = "2026-09-17T08:59:59Z"
        receipt = self.compile(packet)
        self.assertEqual(receipt["status"], engine.HOLD_DEADLINE_PASSED)

    def test_latest_generation_supersedes_old_requirement_and_deadline(self) -> None:
        packet = packet_template()
        packet["opportunity"]["source_generation"] = 2
        packet["sources"].append(
            {
                "source_id": "amendment-1",
                "generation": 2,
                "sha256": "2" * 64,
                "source_class": "OFFICIAL",
                "section": "Amendment 1",
                "observed_at_utc": "2026-09-17T01:00:00Z",
            }
        )
        packet["deadlines"].append(
            {
                "deadline_id": "deadline-v2",
                "at": "2099-10-08T15:00:00-04:00",
                "source_id": "amendment-1",
                "source_section": "A1.2",
                "generation": 2,
            }
        )
        changed = copy.deepcopy(packet["requirements"][0])
        changed.update(
            {
                "requirement_id": "technical-v2",
                "generation": 2,
                "source_id": "amendment-1",
                "source_section": "A1.3",
                "format": "DOCX",
            }
        )
        packet["requirements"].append(changed)
        packet["artifacts"][0]["built_for_generation"] = 2
        receipt = self.compile(packet)
        active = {row["slot_id"]: row for row in receipt["active_requirements"]}
        self.assertEqual(active["technical-volume"]["format"], "DOCX")
        self.assertEqual(receipt["active_deadline"]["deadline_id"], "deadline-v2")
        self.assertEqual(receipt["status"], engine.ASSEMBLY_READY_FOR_OWNER_REVIEW)

    def test_same_generation_duplicate_slot_is_source_conflict(self) -> None:
        packet = packet_template()
        duplicate = copy.deepcopy(packet["requirements"][0])
        duplicate["requirement_id"] = "technical-conflict"
        duplicate["format"] = "DOCX"
        packet["requirements"].append(duplicate)
        receipt = self.compile(packet)
        self.assertEqual(receipt["status"], engine.HOLD_SOURCE_CONFLICT)
        self.assertEqual(receipt["source_conflicts"][0]["kind"], "DUPLICATE_REQUIRED_SLOT_GENERATION")

    def test_same_generation_duplicate_deadline_is_source_conflict(self) -> None:
        packet = packet_template()
        duplicate = copy.deepcopy(packet["deadlines"][0])
        duplicate["deadline_id"] = "deadline-conflict"
        duplicate["at"] = "2099-11-01T15:00:00-04:00"
        packet["deadlines"].append(duplicate)
        receipt = self.compile(packet)
        self.assertEqual(receipt["status"], engine.HOLD_SOURCE_CONFLICT)

    def test_stale_candidate_generation_cannot_be_ready(self) -> None:
        packet = packet_template()
        packet["opportunity"]["source_generation"] = 2
        packet["sources"].append(
            {
                "source_id": "amendment-1",
                "generation": 2,
                "sha256": "2" * 64,
                "source_class": "OFFICIAL",
                "section": "Amendment 1",
                "observed_at_utc": "2026-09-17T01:00:00Z",
            }
        )
        receipt = self.compile(packet)
        self.assertEqual(receipt["status"], engine.HOLD_MISSING_REQUIRED_ARTIFACT)
        self.assertEqual(receipt["missing_required_slots"][0]["reason"], "STALE_GENERATION")

    def test_size_limit_is_machine_checked(self) -> None:
        packet = packet_template()
        packet["requirements"][0]["size_limit_bytes"] = 2
        receipt = self.compile(packet)
        self.assertEqual(receipt["status"], engine.HOLD_MISSING_REQUIRED_ARTIFACT)
        self.assertEqual(receipt["missing_required_slots"][0]["reason"], "SIZE_LIMIT_EXCEEDED")

    def test_form_value_is_digest_only_in_receipt(self) -> None:
        packet = packet_template()
        packet["requirements"][0]["delivery_kind"] = "FORM_VALUE"
        packet["requirements"][0]["filename_rule"] = None
        packet["requirements"][0]["format"] = None
        packet["requirements"][0]["page_limit"] = None
        packet["requirements"][0]["size_limit_bytes"] = None
        packet["requirements"][0]["portal_field"] = "vendor_name"
        packet["artifacts"][0] = {
            "slot_id": "technical-volume",
            "kind": "FORM_VALUE",
            "value": "Sensitive but bounded owner value",
            "built_for_generation": 1,
        }
        receipt = self.compile(packet)
        rendered = engine._canonical_json_bytes(receipt)
        self.assertNotIn(b"Sensitive but bounded owner value", rendered)
        evidence = {row["slot_id"]: row for row in receipt["artifact_evidence"]}
        self.assertEqual(evidence["technical-volume"]["candidate_state"], "PRESENT")
        self.assertIn("PORTAL_FIELD_OWNER_REVIEW", evidence["technical-volume"]["human_checks"])

    def test_symlink_artifact_fails_closed(self) -> None:
        target = self.artifacts / "real.pdf"
        target.write_bytes(b"real")
        (self.artifacts / "Technical Volume.pdf").unlink()
        try:
            os.symlink(target.name, self.artifacts / "Technical Volume.pdf")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        receipt = self.compile()
        self.assertEqual(receipt["status"], engine.HOLD_MISSING_REQUIRED_ARTIFACT)
        self.assertEqual(receipt["missing_required_slots"][0]["reason"], "UNREADABLE")

    def test_symlink_ancestor_fails_closed(self) -> None:
        real = self.root / "real-dir"
        real.mkdir()
        (real / "nested.pdf").write_bytes(b"x")
        link = self.artifacts / "linked"
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        packet = packet_template()
        packet["artifacts"][0]["path"] = "linked/nested.pdf"
        receipt = self.compile(packet)
        self.assertEqual(receipt["status"], engine.HOLD_MISSING_REQUIRED_ARTIFACT)

    def test_duplicate_json_key_rejected(self) -> None:
        with self.assertRaises(engine.AssemblyError):
            engine.strict_json_loads(b'{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self) -> None:
        with self.assertRaises(engine.AssemblyError):
            engine.strict_json_loads(b'{"a":NaN}')

    def test_bool_as_integer_rejected(self) -> None:
        packet = packet_template()
        packet["opportunity"]["source_generation"] = True
        with self.assertRaises(engine.AssemblyError):
            self.compile(packet)

    def test_unknown_top_level_key_rejected(self) -> None:
        packet = packet_template()
        packet["submit_now"] = True
        with self.assertRaises(engine.AssemblyError):
            self.compile(packet)

    def test_fifo_without_writer_fails_closed_without_blocking(self) -> None:
        target = self.artifacts / "Technical Volume.pdf"
        target.unlink()
        os.mkfifo(target)
        receipt = self.compile()
        self.assertEqual(receipt["status"], engine.HOLD_MISSING_REQUIRED_ARTIFACT)
        self.assertEqual(receipt["missing_required_slots"][0]["reason"], "UNREADABLE")

    def test_unknown_candidate_slot_rejected(self) -> None:
        packet = packet_template()
        packet["artifacts"].append(
            {
                "slot_id": "invented-slot",
                "kind": "FORM_VALUE",
                "value": "x",
                "built_for_generation": 1,
            }
        )
        with self.assertRaises(engine.AssemblyError):
            self.compile(packet)

    def test_publish_is_create_exclusive_and_rolls_back_reservations(self) -> None:
        receipt = self.compile()
        result = engine.publish_bundle(receipt, str(self.output), stem="demo")
        self.assertEqual(set(result), {"demo.assembly.json", "demo.checklist.md", "demo.missing.json"})
        with self.assertRaises(FileExistsError):
            engine.publish_bundle(receipt, str(self.output), stem="demo")
        self.assertTrue((self.output / "demo.assembly.json").is_file())

    def test_verify_recompiles_semantics_and_detects_candidate_tamper(self) -> None:
        packet = packet_template()
        packet_path = self.root / "packet.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        # Public compilation owns the verifier clock.  The far-future fixture keeps
        # the deadline open while allowing the public verifier path to be exercised.
        receipt = engine.compile_packet(packet, str(self.artifacts))
        engine.publish_bundle(receipt, str(self.output), stem="demo")
        engine.verify_bundle(str(packet_path), str(self.artifacts), str(self.output), stem="demo")
        (self.artifacts / "Technical Volume.pdf").write_bytes(b"tampered\n")
        with self.assertRaises(engine.AssemblyError):
            engine.verify_bundle(str(packet_path), str(self.artifacts), str(self.output), stem="demo")

    def test_receipt_is_order_invariant(self) -> None:
        packet = packet_template()
        baseline = self.compile(packet)
        shuffled = copy.deepcopy(packet)
        shuffled["requirements"] = list(reversed(shuffled["requirements"]))
        shuffled["sources"] = list(reversed(shuffled["sources"]))
        again = self.compile(shuffled)
        self.assertEqual(engine._canonical_json_bytes(baseline), engine._canonical_json_bytes(again))


if __name__ == "__main__":
    unittest.main()
