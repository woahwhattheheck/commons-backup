from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import native_handoff as nh
import review_register as rr
from make_examples import handoff

HERE = Path(__file__).resolve().parent


def native():
    value = handoff()
    # Source spelling is grounded in workshare_constants.py, not the UI demo.
    for note in value["cell_notes"]:
        if note["dimension"] == "software_development":
            note["dimension"] = "software"
            note["analyst_note"] = "Fictional native software-cell follow-up."
    return value


class NativeHandoffTests(unittest.TestCase):
    def test_native_software_preserved(self):
        source = native()
        result = nh.convert(source, "Reviewer")
        rows = [row for row in result["comments"] if row["cell"]["dimension"] == "software"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["register_cell"]["dimension"] == "software_development" for row in rows))
        self.assertEqual(result["source_handoff"], source)
        self.assertEqual(result["source_handoff_sha256"], rr.sha(source))
        self.assertEqual(result["dimension_translation"], [{"input": "software", "register": "software_development"}])

    def test_legacy_vocabulary_needs_no_translation(self):
        source = handoff()
        result = nh.convert(source, "Reviewer")
        self.assertEqual(result["input_dimension_vocabulary"], "software_development")
        self.assertEqual(result["dimension_translation"], [])
        self.assertEqual(len(result["comments"]), 2)
        self.assertTrue(all(row["cell"] == row["register_cell"] for row in result["comments"]))

    def test_original_legacy_entrypoint_unchanged(self):
        self.assertEqual(len(rr.handoff_intake(handoff(), "Reviewer")["comments"]), 2)
        with self.assertRaises(rr.ValidationError):
            rr.handoff_intake(native(), "Reviewer")

    def test_mixed_vocabulary_rejected(self):
        value = native()
        next(n for n in value["cell_notes"] if n["dimension"] == "software")["dimension"] = "software_development"
        with self.assertRaisesRegex(rr.ValidationError, "mixed"):
            nh.convert(value, "Reviewer")

    def test_missing_and_duplicate_cells_rejected(self):
        for duplicate in (False, True):
            value = native()
            value["cell_notes"].pop()
            if duplicate:
                value["cell_notes"].append(deepcopy(value["cell_notes"][0]))
            with self.assertRaises(rr.ValidationError):
                nh.convert(value, "Reviewer")

    def test_unknown_spelling_is_not_guessed(self):
        value = native()
        value["cell_notes"][0]["dimension"] = "Software"
        with self.assertRaises(rr.ValidationError):
            nh.convert(value, "Reviewer")

    def test_authority_cannot_be_promoted(self):
        for key in rr.AUTHORITY:
            for invalid in (True, 0, None, "false"):
                value = native()
                value["authority"][key] = invalid
                with self.assertRaises(rr.ValidationError):
                    nh.convert(value, "Reviewer")
        self.assertEqual(nh.convert(native(), "Reviewer")["authority"], rr.AUTHORITY)

    def test_no_invented_finding_or_kind(self):
        result = nh.convert(native(), "Reviewer")
        self.assertTrue(all(row["finding_id"] is None and row["kind"] is None for row in result["comments"]))
        self.assertTrue(all(row["status"] == "OPEN_INTAKE_NOT_A_FINDING" for row in result["comments"]))

    def test_no_input_mutation_or_output_alias(self):
        source = native()
        before = deepcopy(source)
        result = nh.convert(source, "Reviewer")
        self.assertEqual(source, before)
        result["source_handoff"]["cell_notes"][0]["analyst_note"] = "downstream edit"
        self.assertEqual(source, before)

    def test_deterministic_recompute_and_digest(self):
        source = native()
        result = nh.convert(source, "Reviewer")
        self.assertEqual(result, nh.convert(source, "Reviewer"))
        nh.verify(source, "Reviewer", result)
        digest = result.pop("receipt_sha256")
        self.assertEqual(digest, rr.sha(result))

    def test_resealed_fabrication_fails_recompute(self):
        source = native()
        result = nh.convert(source, "Reviewer")
        result["comments"][0]["finding_id"] = "fabricated"
        result.pop("receipt_sha256")
        result["receipt_sha256"] = rr.sha(result)
        with self.assertRaisesRegex(rr.ValidationError, "recomputed"):
            nh.verify(source, "Reviewer", result)

    def test_wrong_reviewer_or_source_receipt_fails(self):
        source = native()
        result = nh.convert(source, "Reviewer")
        with self.assertRaises(rr.ValidationError):
            nh.verify(source, "Other reviewer", result)
        source["report_receipt_sha256"] = "e" * 64
        with self.assertRaises(rr.ValidationError):
            nh.verify(source, "Reviewer", result)

    def test_original_vocabulary_part_of_comment_identity(self):
        source = native()
        legacy = deepcopy(source)
        for note in legacy["cell_notes"]:
            if note["dimension"] == "software":
                note["dimension"] = "software_development"
        a = nh.convert(source, "Reviewer")
        b = nh.convert(legacy, "Reviewer")
        a_ids = {r["intake_id"] for r in a["comments"] if r["cell"]["dimension"] == "software"}
        b_ids = {r["intake_id"] for r in b["comments"] if r["cell"]["dimension"] == "software_development"}
        self.assertTrue(a_ids.isdisjoint(b_ids))

    def test_order_changes_source_binding_not_comment_ids(self):
        source = native()
        result = nh.convert(source, "Reviewer")
        source["cell_notes"].reverse()
        reordered = nh.convert(source, "Reviewer")
        self.assertEqual(result["comments"], reordered["comments"])
        self.assertNotEqual(result["source_handoff_sha256"], reordered["source_handoff_sha256"])

    def test_unicode_multiline_and_status_are_preserved(self):
        source = native()
        note = source["cell_notes"][0]
        note["analyst_note"] = "Fictional café\n=plain text \U0001f642"
        note["compiler_status"] = "HOLD_CONFLICTING_EVIDENCE"
        result = nh.convert(source, "Reviewer")
        row = next(r for r in result["comments"] if r["cell"] == {"group": note["group"], "dimension": note["dimension"]})
        self.assertEqual(row["analyst_note"], note["analyst_note"])
        self.assertEqual(row["compiler_status"], note["compiler_status"])

    def test_all_unreviewed_retains_twelve_original_notes(self):
        source = native()
        for note in source["cell_notes"]:
            note.update(analyst_note="", disposition="UNREVIEWED")
        result = nh.convert(source, "Reviewer")
        self.assertEqual(result["comments"], [])
        self.assertEqual(len(result["source_handoff"]["cell_notes"]), 12)

    def test_bad_shapes_fail_cleanly(self):
        for value in ([], {}, {"cell_notes": [None]}, {"cell_notes": [{"dimension": []}]}):
            with self.assertRaises(rr.ValidationError):
                nh.convert(value, "Reviewer")

    def test_unknown_envelope_field_not_dropped(self):
        source = native()
        source["extra_context"] = "must not be discarded silently"
        with self.assertRaises(rr.ValidationError):
            nh.convert(source, "Reviewer")

    def test_real_optimized_cli_convert_verify_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, target = root / "source.json", root / "intake.json"
            source.write_text(json.dumps(native()), encoding="utf-8")
            prefix = [sys.executable, "-O", str(HERE / "native_handoff.py")]
            convert = prefix + ["convert", str(source), "--reviewer", "Reviewer", "--out", str(target)]
            run = subprocess.run(convert, capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)
            before = target.read_bytes()
            check = prefix + ["verify", str(source), str(target), "--reviewer", "Reviewer"]
            run = subprocess.run(check, capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("SOURCE_BOUND_DRAFT_INTAKE_VERIFIED", run.stdout)
            run = subprocess.run(convert, capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(before, target.read_bytes())

    def test_invalid_input_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, target = root / "bad.json", root / "intake.json"
            source.write_text('{"cell_notes":[],"cell_notes":[]}', encoding="utf-8")
            run = subprocess.run([sys.executable, str(HERE / "native_handoff.py"), "convert", str(source),
                                  "--reviewer", "Reviewer", "--out", str(target)], capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 2)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
