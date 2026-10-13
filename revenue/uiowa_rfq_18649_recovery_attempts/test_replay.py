"""Independent acceptance cases for the serial-attempt timing contract."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

import example
import replay as subject


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.p = example.packet()
        self.i = self.p["incidents"][0]
        self.a = self.i["attempts"][-1]

    def result(self):
        return subject.replay(self.p)["incidents"][0]

    def unknown(self):
        self.assertIsNone(self.result()["incident_detection_to_verified_minutes"])
        self.assertEqual(self.result()["target_comparison"], "not_measured")

    def test_failed_rollback_does_not_reset_original_clock(self):
        r = self.result()
        self.assertEqual(r["incident_detection_to_verified_minutes"], 43)
        self.assertEqual(r["attempts"][-1]["attempt_to_verified_minutes"], 30)
        self.assertEqual(r["attempts"][-1]["execution_minutes"], 15)
        self.assertEqual(r["target_comparison"], "exceeded_target")

    def test_configuration_requires_business_not_data(self):
        self.i["change_type"] = "configuration"
        self.a["checks"].pop()
        self.assertEqual(self.result()["incident_detection_to_verified_minutes"], 32)

    def test_migration_health_is_not_data_recovery(self):
        self.a["checks"].pop()
        self.unknown()

    def test_fictional_incomplete_packet(self):
        r = subject.replay(example.incomplete_packet())["incidents"][0]
        self.assertIsNone(r["incident_detection_to_verified_minutes"])

    def test_unknown_detection_not_inferred_from_attempt(self):
        self.i["detected_at"] = None
        self.unknown()

    def test_missing_detection_record(self):
        self.i["detection_refs"] = []
        self.unknown()

    def test_partial_history_not_inferred_complete(self):
        for flag in (False, None):
            self.i["history_complete"] = flag
            self.unknown()

    def test_tabletop_not_measured_recovery(self):
        self.i["context"] = "tabletop"
        self.unknown()
        self.assertEqual(self.result()["status"], "TABLETOP_TIMING_ONLY")

    def test_production_context_preserved_not_authenticated(self):
        self.i["context"] = "production_event"
        self.p["synthetic"] = False
        self.assertEqual(self.result()["context"], "production_event")
        report = subject.replay(self.p)
        self.assertIn("NOT INDEPENDENTLY VERIFIED", subject.render(report))

    def test_missing_attempt_record(self):
        self.i["attempts"][0]["record_refs"] = []
        self.unknown()

    def test_runbook_cannot_replace_execution_record(self):
        self.p["evidence"][1]["kind"] = "procedure"
        self.unknown()

    def test_statement_cannot_replace_check(self):
        self.p["evidence"][-1]["kind"] = "statement"
        self.unknown()

    def test_missing_reference(self):
        self.a["record_refs"] = ["NOT-PRESENT"]
        self.unknown()

    def test_cross_incident_reference(self):
        self.p["evidence"][-1]["incident_id"] = "OTHER"
        self.unknown()

    def test_cross_attempt_reference(self):
        self.p["evidence"][-1]["attempt_id"] = "A1"
        self.unknown()

    def test_future_record(self):
        self.p["evidence"][-1]["observed_at"] = "2026-09-20T00:00:00Z"
        self.unknown()

    def test_good_ref_does_not_hide_bad_ref(self):
        self.a["checks"][-1]["evidence_refs"].append("MISSING")
        self.unknown()

    def test_reversed_attempts(self):
        self.i["attempts"].reverse()
        self.unknown()

    def test_overlapping_attempts(self):
        self.a["started_at"] = "2026-09-18T11:09:00Z"
        self.unknown()

    def test_missing_previous_finish(self):
        self.i["attempts"][0]["finished_at"] = None
        self.unknown()

    def test_future_attempt(self):
        self.a["finished_at"] = "2026-09-20T00:00:00Z"
        self.unknown()

    def test_future_detection(self):
        self.i["detected_at"] = "2026-09-20T00:00:00Z"
        self.unknown()

    def test_check_before_attempt_completion(self):
        self.a["checks"][-1]["observed_at"] = "2026-09-18T11:29:00Z"
        self.unknown()

    def test_future_check(self):
        self.a["checks"][-1]["observed_at"] = "2026-09-20T00:00:00Z"
        self.unknown()

    def test_later_failed_check_revokes_previous_pass(self):
        c = deepcopy(self.a["checks"][-1])
        c.update(id="LATER", result="failed", observed_at="2026-09-18T11:46:00Z")
        self.a["checks"].append(c)
        self.unknown()

    def test_later_supported_pass_can_resolve_earlier_failure(self):
        c = deepcopy(self.a["checks"][-1])
        c.update(id="EARLIER", result="failed", observed_at="2026-09-18T11:40:00Z")
        self.a["checks"].append(c)
        self.assertEqual(self.result()["incident_detection_to_verified_minutes"], 43)

    def test_same_time_conflicting_checks(self):
        c = deepcopy(self.a["checks"][-1])
        c.update(id="CONFLICT", result="failed")
        self.a["checks"].append(c)
        self.unknown()

    def test_unknown_time_check_cannot_be_sorted_away(self):
        c = deepcopy(self.a["checks"][-1])
        c.update(id="UNDATED", result="failed", observed_at=None)
        self.a["checks"].append(c)
        self.unknown()

    def test_declared_extra_scope_cannot_be_ignored(self):
        c = deepcopy(self.a["checks"][-1])
        c.update(id="EXTRA", scope="downstream_delivery", result="unknown")
        self.a["checks"].append(c)
        self.unknown()

    def test_failed_final_attempt_cannot_be_green(self):
        self.a["outcome"] = "failed"
        self.unknown()

    def test_no_attempts_unknown(self):
        self.i["attempts"] = []
        self.unknown()

    def test_target_boundary_uses_unrounded_elapsed(self):
        self.i["target_minutes"] = 43
        self.assertEqual(self.result()["target_comparison"], "within_target")
        self.a["checks"][-1]["observed_at"] = "2026-09-18T11:45:00.000001Z"
        self.assertEqual(self.result()["target_comparison"], "exceeded_target")

    def test_target_missing_not_zero(self):
        self.i["target_minutes"] = None
        self.assertEqual(self.result()["target_comparison"], "not_defined")

    def test_offset_equivalence(self):
        self.i["detected_at"] = "2026-09-18T07:02:00-04:00"
        self.assertEqual(self.result()["incident_detection_to_verified_minutes"], 43)

    def test_invalid_targets(self):
        for value in (True, -1, 0, float("nan"), float("inf"), 10**400):
            self.i["target_minutes"] = value
            with self.subTest(value=str(value)), self.assertRaises(subject.InputError):
                self.result()

    def test_naive_timestamp(self):
        self.i["detected_at"] = "2026-09-18T11:02:00"
        with self.assertRaises(subject.InputError):
            self.result()

    def test_duplicate_reference(self):
        self.a["record_refs"] *= 2
        with self.assertRaises(subject.InputError):
            self.result()

    def test_duplicate_identifier(self):
        self.p["evidence"].append(deepcopy(self.p["evidence"][0]))
        with self.assertRaises(subject.InputError):
            self.result()

    def test_duplicate_json_key(self):
        with self.assertRaises(subject.InputError):
            subject.loads('{"schema_version":1,"schema_version":2}')

    def test_nonfinite_json_constant(self):
        with self.assertRaises(subject.InputError):
            subject.loads('{"x":NaN}')

    def test_unexpected_field(self):
        self.a["ready"] = True
        with self.assertRaises(subject.InputError):
            self.result()

    def test_hash_deterministic_and_inputs_not_mutated(self):
        before = deepcopy(self.p)
        first = subject.replay(self.p)
        self.assertEqual(first, subject.replay(self.p))
        self.assertEqual(before, self.p)
        first["evidence"][0]["excerpt"] = "changed"
        self.assertEqual(before, self.p)
        self.i["target_minutes"] = 40
        self.assertNotEqual(first["input_sha256"], subject.replay(self.p)["input_sha256"])

    def test_markdown_is_literal_and_has_banner(self):
        self.p["evidence"][0]["excerpt"] = '<img src=x> [click](bad) | café'
        content = subject.render(subject.replay(self.p))
        self.assertIn("SYNTHETIC REHEARSAL", content)
        self.assertIn("&lt;img", content)
        self.assertIn("\\| café", content)
        self.assertNotIn("<img", content)

    def test_cli_formats_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dest = Path(temp)/"packet.json", Path(temp)/"report.md"
            src.write_text(json.dumps(self.p))
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(subject.main([str(src)]), 0)
            self.assertEqual(json.loads(out.getvalue())["packet_id"], self.p["packet_id"])
            self.assertEqual(subject.main([str(src), "--format", "markdown", "--output", str(dest)]), 0)
            saved = dest.read_bytes()
            with redirect_stderr(StringIO()):
                self.assertEqual(subject.main([str(src), "--output", str(dest)]), 2)
                self.assertEqual(subject.main([str(src), "--output", str(src)]), 2)
            self.assertEqual(dest.read_bytes(), saved)
            self.assertEqual(json.loads(src.read_text()), self.p)

    def test_cli_invalid_input_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dest = Path(temp)/"bad.json", Path(temp)/"out.json"
            for content in ("{", " " * (subject.LIMIT + 1)):
                src.write_text(content)
                with redirect_stderr(StringIO()):
                    self.assertEqual(subject.main([str(src), "--output", str(dest)]), 2)
                self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
