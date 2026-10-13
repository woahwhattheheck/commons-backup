from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from thompson_canton_cmt import (
    ThompsonCantonGate,
    build_registry,
    canonical_json,
    load_fixture,
    named_human,
    sha256_text,
    summarize,
    verify_manifest,
)

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "thompson_100_jobs.json"
MANIFEST = HERE / "fixtures" / "manifest.json"


class ThompsonCantonGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = verify_manifest(FIXTURE, MANIFEST)
        cls.jobs = load_fixture(FIXTURE)

    def _run(self):
        gate = ThompsonCantonGate()
        results = gate.process_many(copy.deepcopy(self.jobs))
        return gate, results

    def test_01_manifest_and_expanded_fixture_are_hash_bound(self) -> None:
        self.assertEqual(100, self.manifest["fixture_count"])
        self.assertEqual(100, len(self.jobs))
        self.assertEqual(
            self.manifest["expanded_fixture_sha256"],
            sha256_text(canonical_json(self.jobs)),
        )
        self.assertFalse(self.manifest["run_execution_enabled"])
        self.assertTrue(self.manifest["synthetic_only"])

    def test_02_exact_80_scheduled_20_hold_truth(self) -> None:
        gate, results = self._run()
        summary = summarize(results)
        self.assertEqual({"SCHEDULED": 80, "HOLD": 20}, summary["states"])
        self.assertEqual(self.manifest["expected_hold_codes"], summary["hold_codes"])
        self.assertEqual(80, len(gate.state.scheduled))
        self.assertEqual(20, len(gate.state.holds))

    def test_03_every_scheduled_job_matches_golden_eligibility_and_unique_slot(self) -> None:
        gate, _ = self._run()
        registry = build_registry()
        self.assertEqual(80, len({item["job_id"] for item in gate.state.scheduled}))
        self.assertEqual(80, len({item["schedule_key"] for item in gate.state.scheduled}))
        for item in gate.state.scheduled:
            route = registry[item["material_class"]]
            self.assertEqual(route["scope_id"], item["scope_id"])
            self.assertEqual(route["method_authority"], item["method_authority"])
            self.assertEqual(route["method_code"], item["method_code"])
            self.assertEqual(route["method_revision"], item["method_revision"])
            self.assertEqual(route["technician_id"], item["technician_id"])
            self.assertEqual(route["qualification_id"], item["qualification_id"])
            self.assertEqual(route["equipment_id"], item["equipment_id"])

    def test_04_no_scheduled_job_runs_and_run_path_is_disabled(self) -> None:
        gate, _ = self._run()
        self.assertTrue(all(item["run_state"] == "NOT_RUN" for item in gate.state.scheduled))
        self.assertTrue(all(item["state"] == "NOT_RUN" for item in gate.state.result_stubs))
        with self.assertRaises(PermissionError):
            gate.run_job(gate.state.scheduled[0]["job_id"])

    def test_05_unknown_method_scope_fails_closed_before_schedule(self) -> None:
        gate = ThompsonCantonGate()
        probe = copy.deepcopy(self.jobs[0])
        probe["submission_id"] = "PROBE-UNKNOWN-METHOD"
        probe["job_id"] = "PROBE-UNKNOWN-METHOD"
        probe["material_class"] = "unknown-material"
        before = len(gate.state.scheduled)
        result = gate.process(probe)
        self.assertEqual(("HOLD", "METHOD_INELIGIBLE"), (result["state"], result["code"]))
        self.assertEqual(before, len(gate.state.scheduled))

    def test_06_exact_retry_is_zero_add_and_all_golden_digests_hold(self) -> None:
        gate, first = self._run()
        self.assertEqual({"SCHEDULED": 80, "HOLD": 20}, summarize(first)["states"])
        counts_before = (
            len(gate.state.scheduled), len(gate.state.holds), len(gate.state.events),
            len(gate.state.result_stubs), len(gate.state.staged_reports),
        )
        audit_before = gate.state.digest()
        replay = gate.process_many(copy.deepcopy(self.jobs))
        counts_after = (
            len(gate.state.scheduled), len(gate.state.holds), len(gate.state.events),
            len(gate.state.result_stubs), len(gate.state.staged_reports),
        )
        self.assertEqual({"IDEMPOTENT": 100}, summarize(replay)["states"])
        self.assertEqual(counts_before, counts_after)
        self.assertEqual(audit_before, gate.state.digest())
        self.assertEqual(self.manifest["expected_worklist_sha256"], gate.state.worklist_digest())
        self.assertEqual(self.manifest["expected_result_sha256"], gate.state.result_digest())
        self.assertEqual(self.manifest["expected_report_sha256"], gate.state.report_digest())
        self.assertEqual(self.manifest["expected_audit_sha256"], gate.state.digest())

    def test_07_same_submission_changed_content_fails_closed_without_state_mutation(self) -> None:
        gate = ThompsonCantonGate()
        original = copy.deepcopy(self.jobs[0])
        self.assertEqual("SCHEDULED", gate.process(original)["state"])
        before = gate.state.digest()
        changed = copy.deepcopy(original)
        changed["method_revision"] = "CHANGED"
        result = gate.process(changed)
        self.assertEqual(("HOLD", "REPLAY_PAYLOAD_CONFLICT"), (result["state"], result["code"]))
        self.assertEqual(before, gate.state.digest())

    def test_08_schedule_collision_fails_closed(self) -> None:
        gate = ThompsonCantonGate()
        first = copy.deepcopy(self.jobs[0])
        self.assertEqual("SCHEDULED", gate.process(first)["state"])
        probe = copy.deepcopy(first)
        probe["submission_id"] = "PROBE-SLOT-COLLISION"
        probe["job_id"] = "PROBE-SLOT-COLLISION"
        result = gate.process(probe)
        self.assertEqual(("HOLD", "SCHEDULE_COLLISION"), (result["state"], result["code"]))
        self.assertEqual(1, len(gate.state.scheduled))

    def test_09_human_report_release_is_copy_only_and_unsent(self) -> None:
        gate, _ = self._run()
        job_id = gate.state.scheduled[0]["job_id"]
        before = copy.deepcopy(gate.state.staged_reports[job_id])
        released = gate.release_report(job_id, "Jordan Rivera")
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", released["state"])
        self.assertEqual("Jordan Rivera", released["reviewer"])
        self.assertFalse(released["sent"])
        self.assertEqual(before, gate.state.staged_reports[job_id])

    def test_10_reserved_and_nonhuman_reviewers_are_rejected_without_mutation(self) -> None:
        gate, _ = self._run()
        job_id = gate.state.scheduled[0]["job_id"]
        before = gate.state.digest()
        for reviewer in [
            "Auto Reviewer", "System Operator", "AI Reviewer", "service account",
            "workflow agent", "Jordan Bot", "Automation Service", "Madonna",
            "12 34", "1234 5678", "Jordan 12", "1234 Rivera",
        ]:
            with self.subTest(reviewer=reviewer):
                self.assertFalse(named_human(reviewer))
                with self.assertRaises(PermissionError):
                    gate.release_report(job_id, reviewer)
                self.assertEqual(before, gate.state.digest())
        self.assertTrue(named_human("Jordan Rivera"))

    def test_11_automatic_report_release_is_disabled(self) -> None:
        gate, _ = self._run()
        with self.assertRaises(PermissionError):
            gate.automatic_release(gate.state.scheduled[0]["job_id"])

    def test_12_fixture_is_not_mutated_by_processing(self) -> None:
        jobs = copy.deepcopy(self.jobs)
        frozen = canonical_json(jobs)
        gate = ThompsonCantonGate()
        gate.process_many(jobs)
        self.assertEqual(frozen, canonical_json(jobs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
