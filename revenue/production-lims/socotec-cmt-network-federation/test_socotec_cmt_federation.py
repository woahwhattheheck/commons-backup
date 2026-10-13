from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from socotec_cmt_federation import (
    SocotecCmtFederation,
    allowed_transfer,
    build_registry,
    canonical_json,
    expected_transfer_ticket,
    legacy_payload_digest,
    load_fixture,
    named_human,
    sha256_text,
    summarize,
    verify_manifest,
)

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "socotec_500_jobs.json"
MANIFEST = HERE / "fixtures" / "manifest.json"


class SocotecCmtFederationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = verify_manifest(FIXTURE, MANIFEST)
        cls.jobs = load_fixture(FIXTURE)

    def test_01_manifest_and_fixture_contract(self) -> None:
        self.assertEqual(500, self.manifest["fixture_count"])
        self.assertEqual(25, self.manifest["namespace_count"])
        self.assertEqual(500, len(self.jobs))
        self.assertEqual(
            self.manifest["expanded_fixture_sha256"],
            sha256_text(canonical_json(self.jobs)),
        )
        self.assertEqual(
            {
                "CAPACITY_EXCEEDED": 16,
                "DUPLICATE_JOB_ID": 16,
                "EQUIPMENT_UNAVAILABLE": 17,
                "METHOD_VERSION_MISMATCH": 17,
                "QUALIFICATION_INVALID": 17,
                "SCOPE_MISMATCH": 17,
            },
            self.manifest["expected_hold_codes"],
        )

    def _run(self):
        federation = SocotecCmtFederation()
        results = federation.process_many(self.jobs)
        return federation, results

    def test_02_exact_400_ready_100_hold_truth(self) -> None:
        federation, results = self._run()
        summary = summarize(results)
        self.assertEqual({"READY": 400, "HOLD": 100}, summary["states"])
        self.assertEqual(self.manifest["expected_hold_codes"], summary["hold_codes"])
        self.assertEqual(400, len(federation.state.accessions))
        self.assertEqual(100, len(federation.state.holds))

    def test_03_ready_routes_match_golden_namespace_personnel_method_once(self) -> None:
        federation, results = self._run()
        jobs_by_submission = {job["submission_id"]: job for job in self.jobs}
        registry = build_registry()
        ready_results = [result for result in results if result["state"] == "READY"]
        self.assertEqual(400, len(ready_results))
        self.assertEqual(400, len({result["job_id"] for result in ready_results}))
        for accession in federation.state.accessions:
            source_job = jobs_by_submission[federation.state.ready_job_ids[accession["job_id"]]]
            route = registry[source_job["service_code"]]
            self.assertEqual(source_job["expected_route_namespace"], accession["route_namespace"])
            self.assertEqual(route["personnel_id"], accession["personnel_id"])
            self.assertEqual(route["method_code"], accession["method_code"])
            self.assertEqual(route["method_version"], accession["method_version"])

    def test_04_namespace_and_transfer_safety(self) -> None:
        federation, _ = self._run()
        self.assertEqual(400, len(federation.state.ready_job_ids))
        self.assertTrue(all(item["transfer_authorized"] for item in federation.state.accessions))
        namespace_job_pairs = {(item["route_namespace"], item["job_id"]) for item in federation.state.accessions}
        self.assertEqual(400, len(namespace_job_pairs))

        probe = copy.deepcopy(self.jobs[0])
        probe["submission_id"] = "PROBE-UNAUTHORIZED-TRANSFER"
        probe["job_id"] = "PROBE-UNAUTHORIZED-TRANSFER"
        probe["origin_namespace"] = "SOC-13"
        probe["transfer_ticket"] = "not-authorized"
        probe["legacy_payload"]["job_id"] = probe["job_id"]
        probe["legacy_payload"]["source_namespace"] = probe["origin_namespace"]
        probe["legacy_payload_sha256"] = legacy_payload_digest(probe["legacy_payload"])
        result = federation.process(probe)
        self.assertEqual(("HOLD", "UNAUTHORIZED_TRANSFER"), (result["state"], result["code"]))

        self.assertTrue(allowed_transfer("SOC-25", "SOC-01"))
        malformed_origins = ("FAKE-25", "SOC-025", "SOC-00", "SOC-26", "25")
        for index, bad_origin in enumerate(malformed_origins, start=1):
            with self.subTest(bad_origin=bad_origin):
                self.assertFalse(allowed_transfer(bad_origin, "SOC-01"))
                malformed = copy.deepcopy(self.jobs[0])
                malformed["submission_id"] = f"PROBE-MALFORMED-NAMESPACE-{index}"
                malformed["job_id"] = f"PROBE-MALFORMED-NAMESPACE-{index}"
                malformed["origin_namespace"] = bad_origin
                malformed["transfer_ticket"] = expected_transfer_ticket(
                    bad_origin, malformed["expected_route_namespace"], malformed["job_id"]
                )
                malformed["legacy_payload"]["job_id"] = malformed["job_id"]
                malformed["legacy_payload"]["source_namespace"] = bad_origin
                malformed["legacy_payload_sha256"] = legacy_payload_digest(malformed["legacy_payload"])
                result = federation.process(malformed)
                self.assertEqual(("HOLD", "UNAUTHORIZED_TRANSFER"), (result["state"], result["code"]))

    def test_05_mock_legacy_payload_hashes_reconcile_read_only(self) -> None:
        federation, _ = self._run()
        original_payloads = [copy.deepcopy(job["legacy_payload"]) for job in self.jobs]
        for accession in federation.state.accessions:
            self.assertEqual(64, len(accession["legacy_payload_sha256"]))
        self.assertEqual(original_payloads, [job["legacy_payload"] for job in self.jobs])

    def test_06_replay_is_zero_add_and_audit_hash_stable(self) -> None:
        federation, first = self._run()
        self.assertEqual({"READY": 400, "HOLD": 100}, summarize(first)["states"])
        before = federation.state.digest()
        counts_before = (
            len(federation.state.accessions), len(federation.state.holds),
            len(federation.state.events), len(federation.state.staged_reports),
        )
        replay = federation.process_many(self.jobs)
        self.assertEqual({"IDEMPOTENT": 500}, summarize(replay)["states"])
        self.assertEqual(counts_before, (
            len(federation.state.accessions), len(federation.state.holds),
            len(federation.state.events), len(federation.state.staged_reports),
        ))
        self.assertEqual(before, federation.state.digest())
        self.assertEqual(self.manifest["expected_audit_sha256"], before)

    def test_07_same_submission_changed_content_fails_closed_without_state_mutation(self) -> None:
        federation = SocotecCmtFederation()
        original = copy.deepcopy(self.jobs[0])
        first = federation.process(original)
        self.assertEqual("READY", first["state"])
        before = federation.state.digest()
        changed = copy.deepcopy(original)
        changed["capacity_position"] = 999
        result = federation.process(changed)
        self.assertEqual(("HOLD", "REPLAY_PAYLOAD_CONFLICT"), (result["state"], result["code"]))
        self.assertEqual(before, federation.state.digest())

    def test_08_legacy_payload_tamper_fails_closed(self) -> None:
        federation = SocotecCmtFederation()
        probe = copy.deepcopy(self.jobs[1])
        probe["submission_id"] = "PROBE-PAYLOAD-TAMPER"
        probe["job_id"] = "PROBE-PAYLOAD-TAMPER"
        probe["legacy_payload"]["job_id"] = probe["job_id"]
        # Intentionally leave the signed payload digest stale.
        result = federation.process(probe)
        self.assertEqual(("HOLD", "LEGACY_PAYLOAD_HASH_MISMATCH"), (result["state"], result["code"]))
        self.assertEqual(0, len(federation.state.accessions))

    def test_09_human_release_is_copy_only_unsent_and_does_not_mutate_staged_report(self) -> None:
        federation, _ = self._run()
        job_id = federation.state.accessions[0]["job_id"]
        before = copy.deepcopy(federation.state.staged_reports[job_id])
        released = federation.release_report(job_id, "Jordan Rivera")
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", released["state"])
        self.assertEqual("Jordan Rivera", released["reviewer"])
        self.assertFalse(released["sent"])
        self.assertEqual(before, federation.state.staged_reports[job_id])

    def test_10_reserved_automation_identities_and_one_token_names_are_rejected(self) -> None:
        federation, _ = self._run()
        job_id = federation.state.accessions[0]["job_id"]
        rejected = [
            "auto reviewer", "System Reviewer", "bot operator", "Automation Service",
            "Jordan System", "AI Reviewer", "workflow agent", "service account", "Madonna",
            "12 34", "1234 5678", "Jordan 12", "1234 Rivera",
        ]
        for reviewer in rejected:
            with self.subTest(reviewer=reviewer):
                self.assertFalse(named_human(reviewer))
                with self.assertRaises(PermissionError):
                    federation.release_report(job_id, reviewer)
        self.assertTrue(named_human("Jordan Rivera"))

    def test_11_automatic_release_disabled(self) -> None:
        federation, _ = self._run()
        job_id = federation.state.accessions[0]["job_id"]
        with self.assertRaises(PermissionError):
            federation.automatic_release(job_id)

    def test_12_fixture_does_not_mutate_during_processing(self) -> None:
        jobs = copy.deepcopy(self.jobs)
        frozen = json.dumps(jobs, sort_keys=True, separators=(",", ":"))
        federation = SocotecCmtFederation()
        federation.process_many(jobs)
        self.assertEqual(frozen, json.dumps(jobs, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
