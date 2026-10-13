"""Run with: python -m unittest discover -s revenue/uiowa_rfq_18649_recovery -v"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("quartz17_recovery", ROOT / "recovery.py")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads((ROOT / "example.json").read_text(encoding="utf-8"))
        self.cfg, self.mig = self.packet["scenarios"]
        self.run = self.cfg["attempts"][0]

    def report(self, sid="CFG-01"):
        return next(s for s in recovery.assess(self.packet)["scenarios"] if s["id"] == sid)

    def test_example(self):
        report = recovery.assess(self.packet)
        self.assertEqual(report["counts"], {"scenarios": 2, "evidence_supported": 1})
        run = self.report()["attempts"][0]
        self.assertEqual(run["minutes"], {"detect": 2.0, "decide_after_detection": 2.0,
                         "execute": 7.0, "failure_to_completion": 12.0, "failure_to_verified_recovery": 15.0})
        self.assertEqual(run["target_result"], "met")

    def test_migration_needs_data_not_just_service(self):
        run = self.report("MIG-01")["attempts"][0]
        self.assertEqual(run["verification"], {"data": "unknown", "service": "pass"})
        self.assertIsNone(run["minutes"]["failure_to_verified_recovery"])
        self.assertEqual(run["target_result"], "unknown")

    def test_supplied_data_followup_completes_migration(self):
        self.mig["attempts"][0]["verification"][1]["result"] = "pass"
        next(e for e in self.packet["evidence"] if e["id"] == "MIG-01-DATA")["available"] = True
        self.assertEqual(self.report("MIG-01")["state"], "evidence_supported")
        self.assertEqual(self.report("MIG-01")["attempts"][0]["minutes"]["failure_to_verified_recovery"], 37.0)

    def test_removed_data_check_does_not_remove_requirement(self):
        self.mig["attempts"][0]["verification"].pop()
        self.assertEqual(self.report("MIG-01")["attempts"][0]["verification"]["data"], "unknown")

    def test_tabletop_is_never_execution(self):
        self.run["mode"] = "tabletop"
        self.assertEqual(self.report()["state"], "discussion_only")
        self.assertEqual(self.report()["attempts"][0]["demonstration"], "discussion_only")
        self.assertIsNone(self.report()["attempts"][0]["minutes"]["failure_to_verified_recovery"])

    def test_procedure_only(self):
        self.cfg["attempts"] = []
        self.assertEqual(self.report()["state"], "documented_only")

    def test_missing_procedure(self):
        self.cfg["procedure_refs"] = []
        self.assertEqual(self.report()["state"], "gaps_in_supplied_records")

    def test_missing_decision_owner(self):
        self.cfg["decision"]["owner_role"] = None
        self.assertFalse(self.report()["decision_supported"])

    def test_rollback_compatibility_is_not_assumed(self):
        for compatible in (False, None):
            with self.subTest(compatible=compatible):
                self.cfg["decision"]["rollback_compatible"] = compatible
                self.assertFalse(self.report()["decision_supported"])
                self.assertNotEqual(self.report()["state"], "evidence_supported")

    def test_strategy_changed_since_rehearsal(self):
        self.cfg["decision"]["strategy"] = "forward_repair"
        self.assertEqual(self.report()["attempts"][0]["demonstration"], "unverified")

    def test_undecided(self):
        self.cfg["decision"]["strategy"] = "undecided"
        self.assertFalse(self.report()["decision_supported"])

    def test_references_must_be_real_available_and_correct_kind_scope(self):
        original = self.run["evidence_refs"][:]
        for ref in ("NOT-PRESENT", "CFG-01-PROC", "MIG-01-RUN", "MIG-01-DATA"):
            with self.subTest(ref=ref):
                self.run["evidence_refs"] = [ref]
                self.assertEqual(self.report()["attempts"][0]["demonstration"], "unverified")
        self.run["evidence_refs"] = original

    def test_evidence_record_cannot_predate_execution_completion(self):
        next(e for e in self.packet["evidence"] if e["id"] == "CFG-01-RUN")["recorded_at"] = "2026-09-18T10:11:00Z"
        self.assertEqual(self.report()["attempts"][0]["demonstration"], "unverified")

    def test_future_evidence_cannot_support_case(self):
        self.packet["evidence"][0]["recorded_at"] = "2027-01-01T00:00:00Z"
        self.assertFalse(self.report()["procedure_supported"])

    def test_missing_times_are_not_zero(self):
        self.run["times"]["detected"] = None
        run = self.report()["attempts"][0]
        self.assertIsNone(run["minutes"]["detect"])
        self.assertIsNone(run["minutes"]["decide_after_detection"])
        self.assertEqual(run["demonstration"], "unverified")

    def test_bad_chronology_suppresses_durations(self):
        self.run["times"]["start"] = "2026-09-18T10:20:00Z"
        run = self.report()["attempts"][0]
        self.assertTrue(all(v is None for v in run["minutes"].values()))
        self.assertIn("invalid_execution_chronology", run["issues"])

    def test_future_execution(self):
        self.packet["as_of"] = "2026-09-18T10:01:00Z"
        self.assertEqual(self.report()["attempts"][0]["demonstration"], "unverified")

    def test_verification_before_completion(self):
        self.run["verification"][0]["at"] = "2026-09-18T10:10:00Z"
        self.assertEqual(self.report()["attempts"][0]["verification"]["service"], "unknown")

    def test_undated_verification_is_not_silently_ignored(self):
        check = copy.deepcopy(self.run["verification"][0])
        check["at"] = None
        self.run["verification"].append(check)
        self.assertEqual(self.report()["attempts"][0]["verification"]["service"], "unknown")

    def test_conflicting_same_time_verification(self):
        check = copy.deepcopy(self.run["verification"][0])
        check["result"] = "fail"
        self.run["verification"].append(check)
        run = self.report()["attempts"][0]
        self.assertIn("conflicting_verification:service", run["issues"])
        self.assertEqual(run["demonstration"], "unverified")

    def test_earlier_failure_can_be_resolved_by_later_observed_pass(self):
        check = copy.deepcopy(self.run["verification"][0])
        check.update(result="fail", at="2026-09-18T10:13:00Z")
        self.run["verification"].append(check)
        self.assertEqual(self.report()["state"], "evidence_supported")

    def test_unexpected_data_failure_not_ignored_for_configuration(self):
        check = copy.deepcopy(self.run["verification"][0])
        check.update(aspect="data", result="fail")
        self.run["verification"].append(check)
        self.assertEqual(self.report()["attempts"][0]["demonstration"], "unverified")

    def test_newer_failure_overrides_old_success(self):
        newer = copy.deepcopy(self.run)
        newer["id"] = "CFG-01-R2"
        newer["times"] = {k: v.replace("2026-09-18", "2026-09-19") for k, v in newer["times"].items()}
        newer["verification"] = []
        self.cfg["attempts"].append(newer)
        self.assertEqual(self.report()["latest_execution_id"], "CFG-01-R2")
        self.assertEqual(self.report()["state"], "gaps_in_supplied_records")

    def test_unknown_or_ambiguous_latest_attempt(self):
        other = copy.deepcopy(self.run)
        other["id"] = "CFG-01-R2"
        self.cfg["attempts"].append(other)
        self.assertIn("ambiguous_latest_execution", self.report()["issues"])
        other["times"]["failure"] = None
        self.assertIn("latest_execution_order_unknown", self.report()["issues"])

    def test_stale_exercise(self):
        self.packet["as_of"] = "2027-01-01T00:00:00Z"
        self.assertIn("exercise_older_than_declared_window", self.report()["attempts"][0]["issues"])

    def test_target_measured_through_verification_not_command_end(self):
        self.cfg["target_minutes"] = 14
        self.assertEqual(self.report()["attempts"][0]["target_result"], "missed")
        self.cfg["target_minutes"] = None
        self.assertEqual(self.report()["attempts"][0]["target_result"], "not_set")

    def test_timezone_offsets_are_normalized(self):
        self.run["times"]["failure"] = "2026-09-18T06:00:00-04:00"
        self.assertEqual(self.report()["attempts"][0]["minutes"]["detect"], 2)

    def test_naive_timestamp_rejected(self):
        self.run["times"]["failure"] = "2026-09-18T10:00:00"
        with self.assertRaises(ValueError):
            self.report()

    def test_unknown_field_rejected(self):
        self.cfg["production_credentials"] = "never accepted"
        with self.assertRaises(ValueError):
            self.report()

    def test_bad_types_and_numbers_rejected(self):
        for value in (True, False, 0, -1, "20", float("nan"), float("inf"), [], {}):
            with self.subTest(value=value):
                self.cfg["target_minutes"] = value
                with self.assertRaises(ValueError):
                    self.report()

    def test_duplicate_ids_and_references_rejected(self):
        self.packet["evidence"].append(copy.deepcopy(self.packet["evidence"][0]))
        with self.assertRaises(ValueError):
            self.report()
        self.packet["evidence"].pop()
        self.cfg["procedure_refs"] *= 2
        with self.assertRaises(ValueError):
            self.report()

    def test_pure_and_deterministic_under_record_reordering(self):
        before = copy.deepcopy(self.packet)
        expected = recovery.assess(self.packet)
        self.assertEqual(self.packet, before)
        self.packet["scenarios"].reverse()
        self.packet["evidence"].reverse()
        self.assertEqual(recovery.assess(self.packet), expected)

    def test_markdown_escapes_markup_and_marks_synthetic(self):
        self.cfg["title"] = "<script>bad</script>|line\nnext"
        report = recovery.markdown(recovery.assess(self.packet))
        self.assertNotIn("<script>", report)
        self.assertIn("\\|", report)
        self.assertIn("SYNTHETIC EXERCISE", report)

    def test_large_integer_target_does_not_overflow(self):
        self.cfg["target_minutes"] = 10 ** 400
        self.assertEqual(self.report()["attempts"][0]["target_result"], "met")

    def test_invalid_offset_minute_is_rejected(self):
        self.run["times"]["failure"] = "2026-09-18T10:00:00+00:60"
        with self.assertRaises(ValueError):
            self.report()

    def test_freshness_comparison_is_not_rounded(self):
        self.packet["max_exercise_age_days"] = 1
        self.packet["as_of"] = "2026-09-19T10:12:00.001Z"
        self.assertIn("exercise_older_than_declared_window", self.report()["attempts"][0]["issues"])

    def test_target_comparison_is_not_rounded(self):
        self.run["verification"][0]["at"] = "2026-09-18T10:15:00.000001Z"
        next(e for e in self.packet["evidence"] if e["id"] == "CFG-01-SERVICE")["recorded_at"] = "2026-09-18T10:15:01Z"
        self.cfg["target_minutes"] = 15
        self.assertEqual(self.report()["attempts"][0]["target_result"], "missed")

    def test_utc_normalization_outside_supported_calendar_is_rejected(self):
        for value in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
            with self.subTest(value=value):
                self.run["times"]["failure"] = value
                with self.assertRaisesRegex(ValueError, "invalid timestamp"):
                    self.report()

    def test_cli_calendar_overflow_has_validation_exit_not_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "input.json"
            for value in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
                self.packet["as_of"] = value
                path.write_text(json.dumps(self.packet))
                result = self.cli(path)
                self.assertEqual(result.returncode, 2)
                self.assertIn("invalid timestamp", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def cli(self, *args):
        return subprocess.run([sys.executable, *(["-O"] if sys.flags.optimize else []),
                               str(ROOT / "recovery.py"), *map(str, args)],
                              text=True, capture_output=True, timeout=10)

    def test_cli_json_and_gap_exit(self):
        result = self.cli(ROOT / "example.json", "--format", "json", "--fail-on-gaps")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["counts"]["evidence_supported"], 1)

    def test_cli_rejects_duplicate_keys_and_nonfinite_constants(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            for raw in ('{"schema":1,"schema":2}', '{"number":NaN}'):
                path.write_text(raw)
                result = self.cli(path)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_cli_refuses_to_overwrite_input_or_hardlink(self):
        with tempfile.TemporaryDirectory() as d:
            src, alias = Path(d) / "input.json", Path(d) / "alias.json"
            data = json.dumps(self.packet)
            src.write_text(data)
            os.link(src, alias)
            for target in (src, alias):
                result = self.cli(src, "--output", target)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(src.read_text(), data)

    def test_cli_atomic_output(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "report.json"
            result = self.cli(ROOT / "example.json", "--output", output, "--format", "json")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(output.read_text())["counts"]["scenarios"], 2)
            self.assertFalse(list(Path(d).glob(".recovery-*")))

    def test_cli_rejects_oversized_input(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "big.json"
            path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
            result = self.cli(path)
            self.assertEqual(result.returncode, 2)
            self.assertIn("exceeds 2 MiB", result.stderr)

    def test_cli_invalid_shape_and_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            for raw in (b"[]", b"null", b'"text"', b"\xff"):
                path.write_bytes(raw)
                result = self.cli(path)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
