from __future__ import annotations
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import review_register as rr
from make_examples import event, example, handoff

HERE = Path(__file__).resolve().parent


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.packet = example()

    def reject(self, snippet=None):
        with self.assertRaises(rr.ValidationError) as got:
            rr.compile_cycle(self.packet)
        if snippet:
            self.assertIn(snippet, str(got.exception))

    def test_complete_synthetic_cycle(self):
        output = rr.compile_cycle(self.packet)
        self.assertEqual(output["summary"]["status_counts"], {"RESOLVED": 2, "UNRESOLVED": 1, "REJECTED": 1})
        self.assertEqual(output["summary"]["follow_up_comment_ids"], ["C-001", "C-003"])
        self.assertEqual(output["summary"]["stale_resolution_comment_ids"], ["C-001"])
        self.assertEqual(output["comments"][1]["evidence_delta"], {"added": ["E-RELEASE-v2"], "removed": ["E-RELEASE-v1"]})
        self.assertEqual(output["authority"], rr.AUTHORITY)

    def test_deterministic_and_input_unchanged(self):
        original = deepcopy(self.packet)
        first = rr.compile_cycle(self.packet)
        self.assertEqual(rr.canonical(first), rr.canonical(rr.compile_cycle(self.packet)))
        self.assertEqual(self.packet, original)
        digest = first.pop("receipt_sha256")
        self.assertEqual(rr.sha(first), digest)

    def test_outputs_do_not_alias_original_input(self):
        output = rr.compile_cycle(self.packet)
        output["comments"][0]["events"][0]["rationale"] = "modified downstream"
        self.assertNotEqual(self.packet["comments"][0]["events"][0]["rationale"], "modified downstream")

    def test_duplicate_comment(self):
        self.packet["comments"].append(deepcopy(self.packet["comments"][0]))
        self.reject("duplicate comment")

    def test_duplicate_evidence(self):
        self.packet["evidence"].append(deepcopy(self.packet["evidence"][0]))
        self.reject("duplicate evidence")

    def test_duplicate_report(self):
        self.packet["reports"].append(deepcopy(self.packet["reports"][0]))
        self.reject("duplicate report")

    def test_duplicate_finding(self):
        self.packet["reports"][0]["findings"].append(deepcopy(self.packet["reports"][0]["findings"][0]))
        self.reject("duplicate finding")

    def test_missing_evidence(self):
        self.packet["reports"][0]["findings"][0]["evidence_refs"].append("E-NOT-PRESENT")
        self.reject("unresolved reference")

    def test_duplicate_evidence_reference(self):
        self.packet["reports"][0]["findings"][0]["evidence_refs"].append("E-POLICY-v1")
        self.reject("duplicate reference")

    def test_lineage_gap(self):
        self.packet["reports"][1]["supersedes"] = "missing"
        self.reject("linear supersedes")

    def test_finding_id_cannot_move_cell(self):
        self.packet["reports"][1]["findings"][0]["cell"]["group"] = "IAM"
        self.reject("cannot move")

    def test_unknown_original_finding(self):
        self.packet["comments"][0]["finding_id"] = "MISSING"
        self.reject("does not resolve")

    def test_deleted_result_finding(self):
        self.packet["reports"][1]["findings"] = []
        self.reject("resulting finding")

    def test_invalid_receipt(self):
        self.packet["reports"][0]["receipt_sha256"] = "abc"
        self.reject("SHA-256")

    def test_state_cannot_jump_open_to_resolved(self):
        events = self.packet["comments"][0]["events"]
        events[1]["state"] = "RESOLVED"
        events[1]["resulting_report_version"] = "draft-v2"
        self.reject("invalid transition")

    def test_accepted_is_not_resolved(self):
        self.packet["comments"][0]["events"].pop()
        row = rr.compile_cycle(self.packet)["comments"][0]
        self.assertEqual(row["status"], "ACCEPTED")
        self.assertTrue(row["needs_follow_up"])
        self.assertIsNone(row["resulting_report_version"])

    def test_wording_cannot_hide_evidence_change(self):
        self.packet["comments"][1]["kind"] = "WORDING"
        self.reject("evidence changed under")

    def test_wording_requires_edit(self):
        self.packet["reports"][1]["findings"][0]["statement"] = self.packet["reports"][0]["findings"][0]["statement"]
        self.reject("actual statement edit")

    def test_evidence_change_requires_explicit_revision(self):
        self.packet["comments"][0]["kind"] = "EVIDENCE_CHANGE"
        self.reject("explicit evidence version change")

    def test_timezone_required(self):
        self.packet["comments"][0]["events"][0]["at"] = "2026-01-01T12:00:00"
        self.reject("timezone")

    def test_reversed_event_time(self):
        self.packet["comments"][0]["events"][1]["at"] = "2025-01-01T12:00:00Z"
        self.reject("backwards")

    def test_boolean_event_sequence_rejected(self):
        self.packet["comments"][0]["events"][0]["sequence"] = True
        self.reject("sequence")

    def test_missing_event_sequence_rejected(self):
        self.packet["comments"][0]["events"][1]["sequence"] = 3
        self.reject("sequence")

    def test_nonresolved_cannot_bind_report(self):
        self.packet["comments"][0]["events"][0]["resulting_report_version"] = "draft-v2"
        self.reject("only RESOLVED")

    def test_question_can_resolve_without_changed_report(self):
        comment = self.packet["comments"][2]
        comment["events"] = [event(1, "OPEN", "Question recorded."), event(2, "ACCEPTED", "Clarification sufficient."),
                             event(3, "RESOLVED", "Source wording already states the limit.", "draft-v1")]
        row = rr.compile_cycle(self.packet)["comments"][2]
        self.assertFalse(row["stale_resolution"])
        self.assertFalse(row["needs_follow_up"])

    def test_reopen_resolved_clears_applied_binding(self):
        self.packet["comments"][0]["events"].append(event(4, "OPEN", "Revisit the scope statement."))
        row = rr.compile_cycle(self.packet)["comments"][0]
        self.assertIsNone(row["resulting_report_version"])
        self.assertEqual(row["evidence_delta"], {"added": [], "removed": []})
        self.assertEqual(len(row["events"]), 4)

    def test_reordered_refs_do_not_make_resolution_stale(self):
        self.packet["comments"] = [self.packet["comments"][0]]
        latest = deepcopy(self.packet["reports"][1])
        latest.update(version="draft-v3", supersedes="draft-v2")
        latest["findings"][0]["evidence_refs"].reverse()
        self.packet["reports"][2] = latest
        self.assertFalse(rr.compile_cycle(self.packet)["comments"][0]["stale_resolution"])

    def test_later_deleted_finding_needs_revisit(self):
        self.packet["comments"] = [self.packet["comments"][0]]
        self.packet["reports"][2]["findings"] = []
        row = rr.compile_cycle(self.packet)["comments"][0]
        self.assertTrue(row["stale_resolution"])
        self.assertFalse(row["target_finding_present"])

    def test_unknown_fields_are_not_silently_ignored(self):
        self.packet["approved"] = True
        self.reject("unknown fields")

    def test_synthetic_must_be_boolean(self):
        self.packet["synthetic"] = 1
        self.reject("boolean")

    def test_enum_types_have_clear_errors(self):
        for target, key in ((self.packet["comments"][0], "kind"),
                            (self.packet["reports"][0]["findings"][0]["cell"], "group")):
            old = target[key]
            target[key] = []
            self.reject()
            target[key] = old

    def test_csv_formula_text_is_escaped(self):
        self.packet["comments"][0]["comment"] = " =1+2"
        row = next(csv.DictReader(io.StringIO(rr.csv_text(rr.compile_cycle(self.packet)))))
        self.assertEqual(row["comment"], "' =1+2")

    def test_markdown_keeps_comment_text_inert(self):
        self.packet["comments"][0]["comment"] = "<script>text</script> ![image](https://example.invalid/a)"
        output = rr.markdown(rr.compile_cycle(self.packet))
        self.assertNotIn("<script>", output)
        self.assertNotIn("![image]", output)
        self.assertIn("&lt;script&gt;", output)

    def test_empty_review_cycle_is_explicit(self):
        self.packet["comments"] = []
        output = rr.compile_cycle(self.packet)
        self.assertEqual(output["summary"]["comment_count"], 0)
        self.assertEqual(output["status"], "DRAFT_NON_AUTHORITATIVE")

    def test_applied_report_cannot_move_backwards_after_reopening(self):
        comment = self.packet["comments"][2]
        comment["events"] = [event(1, "OPEN", "Clarification requested."),
            event(2, "ACCEPTED", "Clarification agreed."),
            event(3, "RESOLVED", "Bound to current draft.", "draft-v3"),
            event(4, "OPEN", "Revisit question."),
            event(5, "ACCEPTED", "Revised clarification agreed."),
            event(6, "RESOLVED", "Attempted older binding.", "draft-v2")]
        self.reject("moves backwards")

    def test_private_output_is_labeled(self):
        self.packet["synthetic"] = False
        self.assertIn("PRIVATE INPUT", rr.markdown(rr.compile_cycle(self.packet)))


class IntakeTests(unittest.TestCase):
    def test_existing_workbench_shape(self):
        output = rr.handoff_intake(handoff(), "Fictional reviewer")
        self.assertEqual(len(output["comments"]), 2)
        self.assertTrue(all(c["finding_id"] is None and c["kind"] is None for c in output["comments"]))
        self.assertEqual(output["authority"], rr.AUTHORITY)

    def test_no_duplicate_cell(self):
        value = handoff()
        value["cell_notes"][-1] = value["cell_notes"][0]
        with self.assertRaisesRegex(rr.ValidationError, "duplicate assessment"):
            rr.handoff_intake(value, "Reviewer")

    def test_all_twelve_cells_required(self):
        value = handoff()
        value["cell_notes"].pop()
        with self.assertRaisesRegex(rr.ValidationError, "all 12"):
            rr.handoff_intake(value, "Reviewer")

    def test_authority_flags_must_be_literal_false(self):
        for flag in rr.AUTHORITY:
            for invalid in (True, 0, "false", None):
                value = handoff()
                value["authority"][flag] = invalid
                with self.assertRaises(rr.ValidationError):
                    rr.handoff_intake(value, "Reviewer")

    def test_unknown_disposition_rejected(self):
        for invalid in ("APPROVED", []):
            value = handoff()
            value["cell_notes"][0]["disposition"] = invalid
            with self.assertRaises(rr.ValidationError):
                rr.handoff_intake(value, "Reviewer")

    def test_multiple_reviewers_keep_distinct_ids(self):
        left = rr.handoff_intake(handoff(), "A")
        right = rr.handoff_intake(handoff(), "B")
        self.assertTrue(set(c["intake_id"] for c in left["comments"]).isdisjoint(c["intake_id"] for c in right["comments"]))

    def test_synthetic_and_nondemo_intake_do_not_share_ids(self):
        value = handoff()
        original = rr.handoff_intake(value, "Reviewer")
        value["synthetic_demo"] = False
        changed = rr.handoff_intake(value, "Reviewer")
        self.assertNotEqual(original["comments"][0]["intake_id"], changed["comments"][0]["intake_id"])

    def test_receipt_movement_changes_intake_binding(self):
        value = handoff()
        old = rr.handoff_intake(value, "A")
        value["report_receipt_sha256"] = "e" * 64
        new = rr.handoff_intake(value, "A")
        self.assertNotEqual(old["comments"][0]["intake_id"], new["comments"][0]["intake_id"])


class FilesAndCliTests(unittest.TestCase):
    def test_strict_json_rejections(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}', '[]', '{', '{"a":1.5}'):
                path.write_text(text)
                with self.assertRaises(rr.ValidationError):
                    rr.strict_load(path)

    def test_example_source_locators_and_hashes_resolve(self):
        packet = json.loads((HERE / "examples" / "synthetic-review-cycle.json").read_text())
        for record in packet["evidence"]:
            path, locator = record["source_locator"].split("#")
            raw = (HERE / path).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
            self.assertEqual(locator, "L3-L4")
            self.assertGreaterEqual(len(raw.decode().splitlines()), 4)

    def test_byte_limit(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "big.json"
            path.write_bytes(b" " * (rr.MAX_BYTES + 1))
            with self.assertRaisesRegex(rr.ValidationError, "exceeds"):
                rr.strict_load(path)

    def test_unpaired_surrogate(self):
        packet = example()
        packet["comments"][0]["comment"] = "\ud800"
        with self.assertRaisesRegex(rr.ValidationError, "surrogate"):
            rr.compile_cycle(packet)

    def test_compile_cli_and_hash_readback(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            source = parent / "packet.json"
            source.write_text(json.dumps(example()))
            output = parent / "export"
            command = [sys.executable, str(HERE / "review_register.py"), "compile", str(source), "--out", str(output)]
            run = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)
            manifest = json.loads((output / "manifest.json").read_text())
            for name, expected in manifest["files"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
            before = (output / "response.json").read_bytes()
            again = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(again.returncode, 2)
            self.assertEqual((output / "response.json").read_bytes(), before)

    def test_handoff_cli(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            source, target = parent / "handoff.json", parent / "intake.json"
            source.write_text(json.dumps(handoff()))
            code = rr.main(["handoff-intake", str(source), "--reviewer", "Fictional reviewer", "--out", str(target)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(target.read_text())["report_receipt_sha256"], "d" * 64)


if __name__ == "__main__":
    unittest.main()
