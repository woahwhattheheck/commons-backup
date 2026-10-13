"""Namespace and explicit-migration regressions; all inputs are fictional."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import migrate_register as mr
import review_register as rr
from make_examples import example, handoff

HERE = Path(__file__).resolve().parent


def legacy():
    packet = example()
    packet["schema"] = mr.LEGACY_SCHEMA
    return packet


def patch_cycle():
    # Exact root contract from ORRERY review.py blob 9bf19ae0c022c936e0591a171fa4496f1cb6b282,
    # apply_cycle. This is a synthetic negative fixture, not an executed canonical cycle.
    return {"schema": mr.LEGACY_SCHEMA, "id": "SYNTHETIC-CYCLE", "base_document_sha256": "a" * 64,
            "base_report_receipt_sha256": "b" * 64, "target_report_receipt_sha256": "c" * 64,
            "new_version": "synthetic-v2", "comments": []}


class NamespaceTests(unittest.TestCase):
    def test_namespace_is_distinct_from_canonical_cycle(self):
        self.assertEqual(rr.SCHEMA, "uiowa-rfq18649-review-register/v1")
        self.assertNotEqual(rr.SCHEMA, mr.LEGACY_SCHEMA)

    def test_current_generator_uses_register_schema(self):
        self.assertEqual(example()["schema"], rr.SCHEMA)
        self.assertEqual(rr.compile_cycle(example())["summary"]["comment_count"], 4)

    def test_compile_never_silently_accepts_old_name(self):
        with self.assertRaisesRegex(rr.ValidationError, "packet.schema"):
            rr.compile_cycle(legacy())

    def test_canonical_patch_cycle_rejected_as_not_register(self):
        with self.assertRaisesRegex(rr.ValidationError, "canonical patch-cycle"):
            mr.migrate(patch_cycle())
        with self.assertRaises(rr.ValidationError):
            rr.compile_cycle(patch_cycle())

    def test_hybrid_envelope_rejected(self):
        p = legacy()
        p["base_document_sha256"] = "0" * 64
        with self.assertRaisesRegex(rr.ValidationError, "unknown fields"):
            mr.migrate(p)

    def test_unknown_name_not_guessed_from_shape(self):
        p = legacy()
        p["schema"] = "unknown/v9"
        with self.assertRaisesRegex(rr.ValidationError, "requires legacy"):
            mr.migrate(p)

    def test_current_register_not_migrated_again(self):
        with self.assertRaisesRegex(rr.ValidationError, "compile directly"):
            mr.migrate(example())

    def test_wrong_input_types_have_named_diagnoses(self):
        for value in (None, [], "", 0, True):
            with self.subTest(value=value), self.assertRaises(rr.ValidationError):
                mr.migrate(value)

    def test_missing_register_sections_rejected(self):
        for key in mr.REGISTER_FIELDS:
            p = legacy()
            del p[key]
            with self.subTest(key=key), self.assertRaises(rr.ValidationError):
                mr.migrate(p)

    def test_missing_evidence_reference_rejected(self):
        p = legacy()
        p["reports"][0]["findings"][0]["evidence_refs"].append("MISSING")
        with self.assertRaisesRegex(rr.ValidationError, "unresolved reference"):
            mr.migrate(p)

    def test_bad_event_history_rejected(self):
        p = legacy()
        p["comments"][0]["events"][1]["sequence"] = True
        with self.assertRaisesRegex(rr.ValidationError, "consecutive integers"):
            mr.migrate(p)

    def test_invalid_wording_resolution_not_repaired(self):
        p = legacy()
        p["comments"][1]["kind"] = "WORDING"
        with self.assertRaisesRegex(rr.ValidationError, "WORDING-only"):
            mr.migrate(p)


class MigrationMeaningTests(unittest.TestCase):
    def test_only_schema_changes_and_source_is_immutable(self):
        source = legacy()
        before = rr.canonical(source)
        target, receipt = mr.migrate(source)
        self.assertEqual(rr.canonical(source), before)
        self.assertEqual([k for k in source if source[k] != target[k]], ["schema"])
        self.assertEqual(receipt["changed_fields"], ["schema"])

    def test_nested_output_does_not_alias_source(self):
        source = legacy()
        before = rr.canonical(source)
        target, receipt = mr.migrate(source)
        target["comments"][0]["events"][0]["rationale"] = "Changed externally"
        receipt["report_receipts_preserved"][0] = "f" * 64
        self.assertEqual(rr.canonical(source), before)

    def test_unicode_and_multiline_comments_remain_exact(self):
        source = legacy()
        note = "=FORMULA()\r\n分析 – café\t😀"
        source["comments"][0]["comment"] = note
        target, _ = mr.migrate(source)
        self.assertEqual(target["comments"][0]["comment"], note)

    def test_report_receipts_and_source_locators_unchanged(self):
        source = legacy()
        target, receipt = mr.migrate(source)
        self.assertEqual(source["reports"], target["reports"])
        self.assertEqual(source["evidence"], target["evidence"])
        self.assertEqual(receipt["report_receipts_preserved"], [r["receipt_sha256"] for r in source["reports"]])

    def test_packet_digest_rebound_and_no_authority_promoted(self):
        source = legacy()
        target, receipt = mr.migrate(source)
        self.assertEqual(receipt["source_packet_sha256"], rr.sha(source))
        self.assertEqual(receipt["target_packet_sha256"], rr.sha(target))
        self.assertNotEqual(receipt["source_packet_sha256"], receipt["target_packet_sha256"])
        response = rr.compile_cycle(target)
        self.assertEqual(receipt["target_response_receipt_sha256"], response["receipt_sha256"])
        self.assertTrue(all(v is False for v in receipt["authority"].values()))
        self.assertEqual(response["authority"], rr.AUTHORITY)

    def test_disagreement_and_stale_resolution_survive(self):
        target, _ = mr.migrate(legacy())
        summary = rr.compile_cycle(target)["summary"]
        self.assertEqual(summary["status_counts"], {"REJECTED": 1, "RESOLVED": 2, "UNRESOLVED": 1})
        self.assertEqual(summary["stale_resolution_comment_ids"], ["C-001"])
        self.assertEqual(summary["follow_up_comment_ids"], ["C-001", "C-003"])

    def test_private_marker_not_promoted_to_synthetic(self):
        source = legacy()
        source["synthetic"] = False
        target, receipt = mr.migrate(source)
        self.assertIs(target["synthetic"], False)
        self.assertIs(receipt["synthetic"], False)
        self.assertIn("PRIVATE INPUT", rr.markdown(rr.compile_cycle(target)))

    def test_handoff_intake_contract_unchanged(self):
        result = rr.handoff_intake(handoff(), "Fictional reviewer")
        self.assertEqual(result["schema"], "uiowa-rfq18649-review-intake-draft/v1")
        self.assertEqual(result["report_receipt_sha256"], "d" * 64)
        self.assertTrue(all(c["finding_id"] is None for c in result["comments"]))

    def test_recomputation_verifies_valid_migration(self):
        source = legacy()
        target, receipt = mr.migrate(source)
        mr.verify(source, target, receipt)
        self.assertEqual((target, receipt), mr.migrate(source))

    def test_resealed_changed_target_rejected(self):
        source = legacy()
        target, receipt = mr.migrate(source)
        target["comments"][0]["comment"] = "Fabricated replacement"
        receipt["target_packet_sha256"] = rr.sha(target)
        receipt["receipt_sha256"] = rr.sha({k: v for k, v in receipt.items() if k != "receipt_sha256"})
        with self.assertRaisesRegex(rr.ValidationError, "source-bound"):
            mr.verify(source, target, receipt)

    def test_resealed_changed_receipt_rejected(self):
        source = legacy()
        target, receipt = mr.migrate(source)
        receipt["authority"]["prime_approved"] = True
        receipt["receipt_sha256"] = rr.sha({k: v for k, v in receipt.items() if k != "receipt_sha256"})
        with self.assertRaisesRegex(rr.ValidationError, "source-bound"):
            mr.verify(source, target, receipt)


class FilesAndCliTests(unittest.TestCase):
    def source(self, root, packet=None):
        p = root / "legacy.json"
        p.write_bytes(mr.encoded(legacy() if packet is None else packet))
        return p

    def test_source_untouched_output_hashes_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self.source(root)
            before = source.read_bytes()
            dest = root / "result"
            mr.write_bundle(source, dest)
            self.assertEqual(source.read_bytes(), before)
            manifest = rr.strict_load(dest / "manifest.json")
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256((dest / name).read_bytes()).hexdigest(), digest)
            mr.verify(rr.strict_load(source), rr.strict_load(dest / "register.json"), rr.strict_load(dest / "migration.json"))

    def test_existing_destination_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, dest = self.source(root), root / "result"
            dest.mkdir()
            sentinel = dest / "register.json"
            sentinel.write_text("KEEP")
            with self.assertRaises(FileExistsError):
                mr.write_bundle(source, dest)
            self.assertEqual(sentinel.read_text(), "KEEP")
            self.assertEqual([p.name for p in dest.iterdir()], ["register.json"])

    def test_output_cannot_replace_input(self):
        with tempfile.TemporaryDirectory() as td:
            source = self.source(Path(td))
            before = source.read_bytes()
            with self.assertRaises(FileExistsError):
                mr.write_bundle(source, source)
            self.assertEqual(source.read_bytes(), before)

    def test_invalid_input_creates_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, dest = self.source(root, patch_cycle()), root / "result"
            with self.assertRaises(rr.ValidationError):
                mr.write_bundle(source, dest)
            self.assertFalse(dest.exists())

    def test_duplicate_json_key_not_silently_rewritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, dest = root / "bad.json", root / "result"
            source.write_text('{"schema":"one","schema":"two"}')
            with self.assertRaisesRegex(rr.ValidationError, "duplicate JSON key"):
                mr.write_bundle(source, dest)
            self.assertFalse(dest.exists())

    def test_io_failure_keeps_source_and_has_no_complete_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, dest = self.source(root), root / "result"
            before = source.read_bytes()
            original_open = Path.open
            def fail_second(path, *args, **kwargs):
                if path == dest / "migration.json":
                    raise OSError("simulated disk failure")
                return original_open(path, *args, **kwargs)
            with mock.patch.object(Path, "open", fail_second), self.assertRaises(OSError):
                mr.write_bundle(source, dest)
            self.assertEqual(source.read_bytes(), before)
            self.assertTrue((dest / "register.json").exists())
            self.assertFalse((dest / "manifest.json").exists())

    def test_cli_normal_and_explicit_optimized_are_identical(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self.source(root)
            snapshots = []
            for optimized in (False, True):
                prefix = [sys.executable] + (["-O"] if optimized else [])
                dest = root / ("optimized" if optimized else "normal")
                cmd = prefix + [str(HERE / "migrate_register.py"), "migrate", str(source), "--out", str(dest)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("NAMESPACE_MIGRATED", result.stdout)
                verify = subprocess.run(prefix + [str(HERE / "migrate_register.py"), "verify", str(source),
                    str(dest / "register.json"), str(dest / "migration.json")], capture_output=True, text=True, timeout=20)
                self.assertEqual(verify.returncode, 0, verify.stderr)
                snapshots.append({p.name: p.read_bytes() for p in dest.iterdir()})
                again = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                self.assertEqual(again.returncode, 2)
            self.assertEqual(snapshots[0], snapshots[1])


if __name__ == "__main__":
    unittest.main()
