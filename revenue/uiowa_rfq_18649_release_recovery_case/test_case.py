"""Integration regressions execute the three real sibling implementations."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("release_recovery_case", HERE / "case.py")
case = importlib.util.module_from_spec(spec)
spec.loader.exec_module(case)


def change(packet, eid):
    return next(e for e in packet["events"] if e["id"] == eid)


class IntegratedCaseTests(unittest.TestCase):
    def test_real_engines_byte_binding(self):
        _, bindings = case.load_components()
        self.assertEqual(len(bindings), 3)
        for binding in bindings.values():
            self.assertEqual(binding["git_blob"], binding["tested_git_blob"])

    def test_verified_clock_includes_failed_attempt_and_waits(self):
        report = case.run(case.fixture())
        summary = report["summary"]
        self.assertEqual(summary["release_linked_recovery_minutes"], 27)
        self.assertEqual(summary["verified_source_event_ids"], ["E_BEHAVIOR", "E_HEALTH"])
        attempts = report["outputs"]["recovery"]["incidents"][0]["attempts"]
        self.assertIsNone(attempts[0]["verified_at"])
        self.assertEqual(attempts[0]["execution_minutes"], 4)
        self.assertEqual(attempts[1]["attempt_to_verified_minutes"], 12)
        self.assertNotEqual(summary["release_linked_recovery_minutes"], 12)

    def test_environment_difference_then_alignment(self):
        summary = case.run(case.fixture())["summary"]
        self.assertEqual(summary["environment_at_detection"], "UNEXPLAINED_DIFFERENCE")
        self.assertEqual(summary["environment_at_as_of"], "ALIGNED")

    def test_restart_is_not_behavior_verification(self):
        summary = case.run(case.fixture("restart_only"))["summary"]
        self.assertEqual(summary["environment_at_as_of"], "ALIGNED")
        self.assertIsNone(summary["native_detection_to_verified_minutes"])
        self.assertEqual(summary["verified_source_event_ids"], [])

    def test_failed_final_check_does_not_restore(self):
        summary = case.run(case.fixture("failed_verification"))["summary"]
        self.assertIsNone(summary["verified_at"])
        self.assertIsNone(summary["release_linked_recovery_minutes"])

    def test_foreign_artifact_check_cannot_be_borrowed(self):
        summary = case.run(case.fixture("foreign_artifact"))["summary"]
        self.assertEqual(summary["excluded_events"], [{"event_id": "E_BEHAVIOR", "reason": "FOREIGN_ARTIFACT"}])
        self.assertIsNone(summary["release_linked_recovery_minutes"])

    def test_foreign_release_check_cannot_be_borrowed(self):
        packet = case.fixture()
        change(packet, "E_BEHAVIOR")["release_id"] = "OTHER_RELEASE"
        summary = case.run(packet)["summary"]
        self.assertEqual(summary["excluded_events"][0]["reason"], "FOREIGN_RELEASE")
        self.assertIsNone(summary["release_linked_recovery_minutes"])

    def test_incomplete_history_never_invents_elapsed_time(self):
        summary = case.run(case.fixture("incomplete_history"))["summary"]
        self.assertIsNone(summary["native_detection_to_verified_minutes"])

    def test_missing_deployment_preserves_native_but_not_joined_claim(self):
        summary = case.run(case.fixture("missing_deployment"))["summary"]
        self.assertEqual(summary["native_detection_to_verified_minutes"], 27)
        self.assertEqual(summary["provenance_status"], "GAPS")
        self.assertIsNone(summary["release_linked_recovery_minutes"])
        self.assertIn("MISSING_RELEASE_TIMELINE_EVENT", summary["join_issues"])

    def test_future_verification_preserved_but_not_consumed(self):
        report = case.run(case.fixture("future_verification"))
        self.assertIsNone(report["summary"]["native_detection_to_verified_minutes"])
        self.assertEqual(report["summary"]["excluded_events"][0]["reason"], "AFTER_AS_OF")
        self.assertIn("E_BEHAVIOR", [s["event_id"] for s in report["source_bindings"]])
        self.assertNotIn("E_BEHAVIOR", [e["id"] for e in report["inputs"]["recovery"]["evidence"]])

    def test_artifact_bytes_are_really_hashed(self):
        packet = case.fixture()
        packet["artifact"]["content"] += "changed\n"
        report = case.run(packet)
        self.assertEqual(report["summary"]["provenance_status"], "CONTRADICTORY_RECORDS")
        self.assertIsNone(report["summary"]["release_linked_recovery_minutes"])
        self.assertTrue(any(c["code"] == "VALUE_MISMATCH" and c["path"].endswith(".local_bytes") for c in report["outputs"]["provenance"]["checks"]))

    def test_version_mismatch_not_hidden(self):
        packet = case.fixture()
        change(packet, "E_DEPLOY")["data"]["observed_version"] = "different"
        self.assertEqual(case.run(packet)["summary"]["provenance_status"], "CONTRADICTORY_RECORDS")

    def test_detection_before_release_does_not_make_a_join(self):
        packet = case.fixture()
        change(packet, "E_DETECT")["at"] = "2026-09-18T08:59:00Z"
        summary = case.run(packet)["summary"]
        self.assertEqual(summary["native_detection_to_verified_minutes"], 33)
        self.assertIn("RELEASE_TIMELINE_CONTRADICTION", summary["join_issues"])
        self.assertIsNone(summary["release_linked_recovery_minutes"])

    def test_timezone_offsets_compare_as_instants(self):
        packet = case.fixture()
        change(packet, "E_DETECT")["at"] = "2026-09-18T05:05:00-04:00"
        self.assertEqual(case.run(packet)["summary"]["release_linked_recovery_minutes"], 27)

    def test_latest_failed_verification_wins(self):
        packet = case.fixture()
        e = deepcopy(change(packet, "E_BEHAVIOR"))
        e.update(id="E_LATER_FAILED", at="2026-09-18T09:33:00Z")
        e["data"]["result"] = "failed"
        packet["events"].append(e)
        self.assertIsNone(case.run(packet)["summary"]["verified_at"])

    def test_conflicting_final_checks_do_not_select_convenient_record(self):
        packet = case.fixture()
        e = deepcopy(change(packet, "E_BEHAVIOR"))
        e["id"] = "E_CONFLICT"
        e["data"]["result"] = "failed"
        packet["events"].append(e)
        self.assertIsNone(case.run(packet)["summary"]["verified_at"])

    def test_conflicting_same_time_environment_is_rejected(self):
        packet = case.fixture()
        e = deepcopy(change(packet, "E_CONFIG_FIXED"))
        e["id"] = "E_CONFLICT"
        e["data"]["value"] = True
        packet["events"].append(e)
        with self.assertRaisesRegex(ValueError, "conflicting simultaneous"):
            case.run(packet)

    def test_orphan_verification_named_and_join_not_established(self):
        packet = case.fixture()
        e = deepcopy(change(packet, "E_BEHAVIOR"))
        e["id"] = "E_ORPHAN"
        e["data"]["attempt_id"] = "ABSENT"
        packet["events"].append(e)
        summary = case.run(packet)["summary"]
        self.assertEqual(summary["orphan_check_ids"], ["E_ORPHAN"])
        self.assertIsNone(summary["release_linked_recovery_minutes"])

    def test_missing_approval_is_gap_not_malformed(self):
        packet = case.fixture()
        packet["events"] = [e for e in packet["events"] if e["kind"] != "approval"]
        self.assertEqual(case.run(packet)["summary"]["provenance_status"], "GAPS")

    def test_missing_detection_never_guesses_start(self):
        packet = case.fixture()
        packet["events"] = [e for e in packet["events"] if e["kind"] != "detection"]
        summary = case.run(packet)["summary"]
        self.assertIsNone(summary["detected_at"])
        self.assertIsNone(summary["native_detection_to_verified_minutes"])

    def test_source_ids_locators_and_timestamps_preserved(self):
        packet = case.fixture()
        report = case.run(packet)
        indexed = {e["id"]: e for e in packet["events"]}
        for source in report["source_bindings"]:
            original = indexed[source["event_id"]]
            self.assertEqual(source["observed_at"], original["at"])
            self.assertEqual(source["artifact_id"], original["artifact_id"])
        for e in report["outputs"]["recovery"]["evidence"]:
            self.assertEqual(e["observed_at"], indexed[e["id"]]["at"])
        for report_name in ("environment_at_detection", "environment_at_as_of"):
            for e in report["outputs"][report_name]["evidence_register"]:
                self.assertEqual(e["locator"], "synthetic://CASE109/events/" + e["id"])

    def test_determinism_and_no_input_mutation(self):
        packet = case.fixture()
        before = deepcopy(packet)
        first, second = case.run(packet), case.run(packet)
        self.assertEqual(first, second)
        self.assertEqual(packet, before)

    def test_shuffled_events_keep_semantic_results(self):
        packet = case.fixture()
        first = case.run(packet)
        packet["events"].reverse()
        second = case.run(packet)
        self.assertEqual(first["outputs"], second["outputs"])
        self.assertEqual(first["summary"], second["summary"])
        self.assertNotEqual(first["input_sha256"], second["input_sha256"])

    def test_extensions_retained(self):
        packet = case.fixture()
        packet["extensions"] = {"unknown_measure": None, "literal": "=not-a-command"}
        self.assertEqual(case.run(packet)["extensions"], packet["extensions"])

    def test_duplicate_id_rejected(self):
        packet = case.fixture()
        packet["events"].append(deepcopy(packet["events"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate event"):
            case.run(packet)

    def test_ambiguous_detection_rejected(self):
        packet = case.fixture()
        e = deepcopy(change(packet, "E_DETECT"))
        e["id"] = "E_OTHER_DETECTION"
        packet["events"].append(e)
        with self.assertRaisesRegex(ValueError, "ambiguous detection"):
            case.run(packet)

    def test_non_synthetic_packet_rejected(self):
        packet = case.fixture()
        packet["synthetic"] = False
        with self.assertRaisesRegex(ValueError, "synthetic"):
            case.run(packet)

    def test_naive_timestamp_rejected(self):
        packet = case.fixture()
        packet["events"][0]["at"] = "2026-09-18T08:40:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            case.run(packet)

    def test_json_duplicate_keys_nonfinite_and_size_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.json"
            for text in ('{"x":1,"x":2}', '{"x":NaN}', ' ' * (2 * 1024 * 1024 + 1)):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    case.load(path)

    def test_cli_exports_real_native_packets_and_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "case"
            command = [sys.executable, str(HERE / "case.py"), "--output", str(destination)]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            manifest = json.loads((destination / "SHA256SUMS.json").read_text())
            self.assertEqual(len(manifest), 12)
            for name, sha in manifest.items():
                self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), sha)
            summary = json.loads(proc.stdout)
            self.assertEqual(summary["release_linked_recovery_minutes"], 27)
            self.assertEqual(case.run(case.load(destination / "ledger.json"))["summary"], summary)
            again = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(again.returncode, 2)
            self.assertIn("exists", again.stderr)

    def test_every_named_scenario_executes_actual_engines(self):
        summaries = {name: case.run(case.fixture(name))["summary"] for name in case.SCENARIOS}
        self.assertEqual(len(summaries), 7)
        self.assertEqual(summaries["verified"]["release_linked_recovery_minutes"], 27)
        for name in case.SCENARIOS[1:]:
            self.assertIsNone(summaries[name]["release_linked_recovery_minutes"], name)


if __name__ == "__main__":
    unittest.main()
