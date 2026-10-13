from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from revenue.numih_ai_sad_admission_readiness import cli
from revenue.numih_ai_sad_admission_readiness.compiler import (
    BOUND_COVERAGE,
    ValidationError,
    compile_packet,
    loads_strict,
    render_markdown,
    verify_result,
)


EXAMPLES = Path(__file__).parents[1] / "examples"


def packet() -> dict:
    return json.loads((EXAMPLES / "fictional_partner_packet.json").read_text())


def bundle() -> dict:
    return json.loads((EXAMPLES / "fictional_evidence_bundle.json").read_text())


def semantic(result: dict) -> dict:
    clone = copy.deepcopy(result)
    clone.pop("receipt", None)
    return clone


def evidence_row(value: dict, evidence_id: str) -> dict:
    return next(row for row in value["evidence"] if row["id"] == evidence_id)


def artifact(value: dict, evidence_id: str) -> dict:
    return next(row for row in value["artifacts"] if row["evidence_id"] == evidence_id)


class ReadinessTests(unittest.TestCase):
    def test_complete_retained_bundle_packet(self):
        p = packet()
        b = bundle()
        result = compile_packet(p, b)
        self.assertEqual(result["packet_state"], "PACKET_REVIEW_READY")
        self.assertEqual(result["rubric"]["retained_evidence_coverage_points"], 100)
        self.assertTrue(result["evidence_bundle"]["root_sha256"])
        self.assertEqual(result["evidence_authority_queue"], [])
        self.assertEqual(result["dce"]["currentness"], "CURRENTNESS_UNVERIFIED")
        self.assertEqual(
            result["external_submission_state"], "HOLD_CURRENTNESS_AND_OWNER_ACTIONS"
        )
        self.assertTrue(all(value is False for value in result["authority"].values()))
        self.assertTrue(verify_result(p, result, b))

    def test_packet_metadata_alone_cannot_mint_readiness(self):
        result = compile_packet(packet())
        self.assertEqual(result["packet_state"], "INCOMPLETE_EVIDENCE")
        self.assertEqual(result["rubric"]["retained_evidence_coverage_points"], 0)
        self.assertEqual(len(result["evidence_authority_queue"]), 16)
        self.assertTrue(
            all(
                row["state"] == "SOURCE_BUNDLE_MISSING"
                for row in result["evidence_authority_queue"]
            )
        )
        self.assertFalse(result["partners"][0]["capacity_composable"])

    def test_nonexistent_locator_and_invented_hash_do_not_count(self):
        p = packet()
        row = evidence_row(p, "e1")
        row["source"] = {
            "locator": "nonexistent://invented",
            "generation": "invented-generation",
            "sha256": "f" * 64,
        }
        result = compile_packet(p, bundle())
        self.assertEqual(result["packet_state"], "INCOMPLETE_EVIDENCE")
        self.assertLess(result["rubric"]["retained_evidence_coverage_points"], 100)
        queued = next(
            item
            for item in result["evidence_authority_queue"]
            if item["evidence_id"] == "e1"
        )
        self.assertEqual(queued["state"], "SOURCE_BINDING_MISMATCH")
        self.assertEqual(
            queued["mismatched_fields"], ["generation", "locator", "sha256"]
        )

    def test_bundle_content_sha_is_recomputed(self):
        b = bundle()
        item = artifact(b, "e1")
        item["content_b64"] = base64.b64encode(b"foreign bytes").decode("ascii")
        item["byte_length"] = len(b"foreign bytes")
        with self.assertRaisesRegex(ValidationError, "sha256 does not match"):
            compile_packet(packet(), b)

    def test_bundle_byte_length_is_recomputed(self):
        b = bundle()
        artifact(b, "e1")["byte_length"] += 1
        with self.assertRaisesRegex(ValidationError, "byte_length does not match"):
            compile_packet(packet(), b)

    def test_bundle_identity_mismatch_does_not_count(self):
        b = bundle()
        artifact(b, "e1")["party_id"] = "partner"
        result = compile_packet(packet(), b)
        queued = next(
            row
            for row in result["evidence_authority_queue"]
            if row["evidence_id"] == "e1"
        )
        self.assertEqual(queued["state"], "SOURCE_BINDING_MISMATCH")
        self.assertEqual(queued["mismatched_fields"], ["party_id"])
        self.assertEqual(result["packet_state"], "INCOMPLETE_EVIDENCE")

    def test_duplicate_bundle_evidence_id_rejected(self):
        b = bundle()
        b["artifacts"].append(copy.deepcopy(b["artifacts"][0]))
        with self.assertRaisesRegex(ValidationError, "duplicate bundle evidence id"):
            compile_packet(packet(), b)

    def test_invalid_bundle_base64_rejected(self):
        b = bundle()
        artifact(b, "e1")["content_b64"] = "not***base64"
        with self.assertRaisesRegex(ValidationError, "canonical base64"):
            compile_packet(packet(), b)

    def test_missing_retained_partner_commitment_blocks_composition(self):
        b = bundle()
        b["artifacts"] = [
            item for item in b["artifacts"] if item["evidence_id"] != "e6"
        ]
        result = compile_packet(packet(), b)
        self.assertFalse(result["partners"][0]["capacity_composable"])
        dimension = next(
            value
            for value in result["rubric"]["dimensions"]
            if value["dimension"] == "recent_ai_references"
        )
        self.assertEqual(
            dimension["rows"][0]["coverage"], "PARTNER_COMMITMENT_MISSING"
        )
        self.assertEqual(result["packet_state"], "INCOMPLETE_EVIDENCE")

    def test_cross_party_commitment_rejected(self):
        p = packet()
        p["partners"].append(
            {
                "id": "other",
                "display_name": "Other",
                "commitment_evidence_id": "e6",
            }
        )
        with self.assertRaisesRegex(ValidationError, "cross-party"):
            compile_packet(p, bundle())

    def test_applicant_only_transplant_rejected(self):
        p = packet()
        evidence_row(p, "e1")["party_id"] = "partner"
        with self.assertRaisesRegex(ValidationError, "must belong to applicant"):
            compile_packet(p, bundle())

    def test_category_gap_holds(self):
        p = packet()
        p["evidence"] = [row for row in p["evidence"] if row["kind"] != "category_fit_4"]
        result = compile_packet(p, bundle())
        category = next(row for row in result["categories"] if row["category"] == 4)
        self.assertEqual(category["state"], "HOLD")
        self.assertEqual(result["packet_state"], "INCOMPLETE_EVIDENCE")

    def test_original_fr_language_mismatch_rejected(self):
        p = packet()
        evidence_row(p, "e7")["language"] = "en"
        with self.assertRaisesRegex(ValidationError, "ORIGINAL_FR requires language=fr"):
            compile_packet(p, bundle())

    def test_french_working_translation_stays_queued(self):
        p = packet()
        evidence_row(p, "e7")["translation_status"] = "WORKING_TRANSLATION"
        result = compile_packet(p, bundle())
        self.assertEqual(result["translation_queue"][0]["evidence_id"], "e7")
        self.assertEqual(result["packet_state"], "INCOMPLETE_EVIDENCE")

    def test_non_french_certified_translation_can_clear_queue(self):
        p = packet()
        row = evidence_row(p, "e7")
        row["language"] = "en"
        row["translation_status"] = "CERTIFIED_TRANSLATION"
        result = compile_packet(p, bundle())
        self.assertEqual(result["translation_queue"], [])
        self.assertEqual(result["packet_state"], "PACKET_REVIEW_READY")

    def test_claimed_unverified_does_not_count(self):
        p = packet()
        row = evidence_row(p, "e12")
        row["status"] = "CLAIMED_UNVERIFIED"
        row.pop("source")
        result = compile_packet(p, bundle())
        self.assertLess(result["rubric"]["retained_evidence_coverage_points"], 100)
        self.assertEqual(result["packet_state"], "INCOMPLETE_EVIDENCE")

    def test_currentness_self_assertion_rejected(self):
        p = packet()
        p["dce"]["current"] = True
        with self.assertRaisesRegex(ValidationError, "unknown fields"):
            compile_packet(p, bundle())

    def test_bool_int_alias_rejected(self):
        p = packet()
        p["categories"] = [True]
        with self.assertRaisesRegex(ValidationError, "integer"):
            compile_packet(p, bundle())

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
            loads_strict('{"x":1,"x":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(ValidationError, "non-finite"):
            loads_strict('{"x":NaN}')

    def test_duplicate_evidence_rejected(self):
        p = packet()
        p["evidence"][1]["id"] = p["evidence"][0]["id"]
        with self.assertRaisesRegex(ValidationError, "duplicate evidence id"):
            compile_packet(p, bundle())

    def test_unknown_category_rejected(self):
        p = packet()
        p["categories"] = [5]
        with self.assertRaisesRegex(ValidationError, "1..4"):
            compile_packet(p, bundle())

    def test_semantic_order_invariance(self):
        p1, b1 = packet(), bundle()
        p2, b2 = copy.deepcopy(p1), copy.deepcopy(b1)
        p2["evidence"].reverse()
        p2["categories"].reverse()
        b2["artifacts"].reverse()
        self.assertEqual(semantic(compile_packet(p1, b1)), semantic(compile_packet(p2, b2)))

    def test_result_tamper_detected(self):
        p, b = packet(), bundle()
        result = compile_packet(p, b)
        result["authority"]["payment"] = True
        self.assertFalse(verify_result(p, result, b))

    def test_bundle_generation_tamper_detected(self):
        p, b = packet(), bundle()
        result = compile_packet(p, b)
        b2 = copy.deepcopy(b)
        b2["generation"] = "different-bundle-generation"
        self.assertFalse(verify_result(p, result, b2))

    def test_markdown_truth_labels(self):
        markdown = render_markdown(compile_packet(packet(), bundle()))
        self.assertIn("not a sponsor score", markdown)
        self.assertIn("exact retained bundle bytes", markdown)
        self.assertIn("authority fields are `false`", markdown)

    def test_initial_symlink_input_rejected(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            link = root / "input.json"
            target.write_text('{"safe":true}', encoding="utf-8")
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            with self.assertRaisesRegex(SystemExit, "cannot safely open"):
                cli._read_retained(link)

    def test_path_swap_to_symlink_after_open_cannot_redirect_fd(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input.json"
            foreign = root / "foreign.json"
            path.write_text('{"generation":"original"}', encoding="utf-8")
            foreign.write_text('{"generation":"foreign"}', encoding="utf-8")
            real_open = cli.os.open
            swapped = False

            def open_then_swap(value, flags, mode=0o777):
                nonlocal swapped
                fd = real_open(value, flags, mode)
                if Path(value) == path and not swapped:
                    swapped = True
                    path.unlink()
                    path.symlink_to(foreign)
                return fd

            with mock.patch.object(cli.os, "open", side_effect=open_then_swap):
                text = cli._read_retained(path)
            self.assertEqual(json.loads(text)["generation"], "original")
            self.assertTrue(path.is_symlink())

    def test_path_swap_to_oversized_generation_after_open_cannot_redirect_fd(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input.json"
            path.write_text('{"generation":"original"}', encoding="utf-8")
            real_open = cli.os.open
            swapped = False

            def open_then_swap(value, flags, mode=0o777):
                nonlocal swapped
                fd = real_open(value, flags, mode)
                if Path(value) == path and not swapped:
                    swapped = True
                    path.unlink()
                    path.write_bytes(b"x" * 4096)
                return fd

            with mock.patch.object(cli.os, "open", side_effect=open_then_swap):
                text = cli._read_retained(path, limit=128)
            self.assertEqual(json.loads(text)["generation"], "original")
            self.assertGreater(path.stat().st_size, 128)

    def test_initial_oversized_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b"x" * 129)
            with self.assertRaisesRegex(SystemExit, "regular file"):
                cli._read_retained(path, limit=128)

    def test_cli_writes_complete_proof_from_two_retained_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_out = root / "result.json"
            markdown_out = root / "result.md"
            rc = cli.main(
                [
                    str(EXAMPLES / "fictional_partner_packet.json"),
                    "--evidence-bundle",
                    str(EXAMPLES / "fictional_evidence_bundle.json"),
                    "--json-out",
                    str(json_out),
                    "--markdown-out",
                    str(markdown_out),
                ]
            )
            self.assertEqual(rc, 0)
            result = json.loads(json_out.read_text(encoding="utf-8"))
            self.assertEqual(result["packet_state"], "PACKET_REVIEW_READY")
            self.assertIn("not a sponsor score", markdown_out.read_text(encoding="utf-8"))

    def test_cli_requires_evidence_bundle(self):
        with self.assertRaises(SystemExit) as caught:
            cli.main([str(EXAMPLES / "fictional_partner_packet.json")])
        self.assertEqual(caught.exception.code, 2)

    def test_create_exclusive_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                cli._write_new(path, "replacement")
            self.assertEqual(path.read_text(encoding="utf-8"), "existing")

    def test_valid_bundle_entry_sha_matches_retained_content(self):
        b = bundle()
        item = artifact(b, "e1")
        content = base64.b64decode(item["content_b64"], validate=True)
        self.assertEqual(hashlib.sha256(content).hexdigest(), item["sha256"])
        self.assertEqual(len(content), item["byte_length"])

    def test_coverage_rows_are_truth_labeled_retained_bytes(self):
        result = compile_packet(packet(), bundle())
        rows = [
            row
            for dimension in result["rubric"]["dimensions"]
            for row in dimension["rows"]
        ]
        self.assertTrue(rows)
        self.assertTrue(all(row["coverage"] == BOUND_COVERAGE for row in rows))
        self.assertNotIn("EVIDENCED", {row["coverage"] for row in rows})


if __name__ == "__main__":
    unittest.main()
