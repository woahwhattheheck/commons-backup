import json
from pathlib import Path
import subprocess
import sys
import unittest

import adapter

NOW = "2026-09-07T21:00:00Z"
HERE = Path(__file__).resolve().parent


class AdapterTests(unittest.TestCase):
    def record(self, *, observed="2026-09-07T20:59:00Z", recorded=NOW,
               data=None, provider=None, source=None):
        return adapter.make_record("operation", "op-1", data or {},
                                   observed_at=observed, recorded_at=recorded,
                                   provider=provider, source=source)

    def test_stale_arrival_cannot_replace_newer_observation(self):
        current = self.record(data={"reported_status": "running"})
        delayed = self.record(observed="2026-09-07T18:00:00Z",
                              recorded="2026-09-07T21:30:00Z",
                              data={"reported_status": "requested"})
        entity = adapter.snapshot([current, delayed], as_of=NOW)["entities"][0]
        self.assertEqual(entity["latest"]["data"]["reported_status"], "running")
        self.assertEqual(len(entity["observations"]), 2)
        self.assertEqual(adapter.freshness(delayed, as_of=NOW, max_age_seconds=60)["state"], "stale")

    def test_unknown_time_remains_unknown_and_does_not_override(self):
        unknown = self.record(observed=None, data={"reported_status": "succeeded"})
        current = self.record(data={"reported_status": "running"})
        entity = adapter.snapshot([current, unknown], as_of=NOW)["entities"][0]
        self.assertEqual(entity["latest"]["record_id"], current["record_id"])
        self.assertEqual(adapter.freshness(unknown, as_of=NOW, max_age_seconds=60),
                         {"state": "unknown", "age_seconds": None})

    def test_partial_and_full_acknowledgments_do_not_imply_completion(self):
        data = {"expected_parts": ["source", "artifact"],
                "acknowledgments": [{"part_id": "source", "status": "accepted"}]}
        result = adapter.operation_summary(self.record(data=data))
        self.assertEqual(result["acknowledgment_coverage"], "partial")
        self.assertEqual(result["missing_parts"], ["artifact"])
        self.assertEqual(result["provider_completion"], "unknown")
        data["acknowledgments"].append({"part_id": "artifact", "status": "accepted"})
        result = adapter.operation_summary(self.record(data=data))
        self.assertEqual(result["acknowledgment_coverage"], "complete")
        self.assertEqual(result["provider_completion"], "unknown")

    def test_unknown_acknowledgment_total_stays_unknown(self):
        result = adapter.operation_summary(self.record(data={
            "expected_parts": None,
            "acknowledgments": [{"part_id": "source", "status": "accepted"}]}))
        self.assertEqual(result["acknowledgment_coverage"], "unknown")
        self.assertIsNone(result["missing_parts"])

    def test_board_report_is_preserved_separately_from_provider_completion(self):
        result = adapter.operation_summary(self.record(
            data={"reported_status": "succeeded"}, source={"kind": "board"},
            provider={"operation_id": "op-1", "status": "succeeded",
                      "receipt_ref": "provider:operation/op-1"}))
        self.assertEqual(result["reported_status"], "succeeded")
        self.assertEqual(result["provider_completion"], "unknown")

    def test_explicit_provider_outcome_and_unknown_completion_time(self):
        provider = {"operation_id": "op-1", "status": "succeeded",
                    "receipt_ref": "provider:operation/op-1"}
        result = adapter.operation_summary(self.record(
            source={"kind": "provider_response"}, provider=provider))
        self.assertEqual(result["provider_completion"], "succeeded")
        self.assertFalse(result["completion_time_known"])
        provider["completed_at"] = "2026-09-07T20:58:00Z"
        result = adapter.operation_summary(self.record(
            source={"kind": "provider_response"}, provider=provider))
        self.assertEqual(result["provider_completed_at"], provider["completed_at"])
        self.assertTrue(result["completion_time_known"])

    def test_other_operation_receipt_or_missing_receipt_is_not_completion(self):
        for provider in ({"operation_id": "op-2", "status": "succeeded", "receipt_ref": "r2"},
                         {"operation_id": "op-1", "status": "succeeded"}):
            result = adapter.operation_summary(self.record(
                source={"kind": "provider_response"}, provider=provider))
            self.assertEqual(result["provider_completion"], "unknown")

    def test_completion_time_after_observation_remains_uncertain(self):
        result = adapter.operation_summary(self.record(
            source={"kind": "provider_response"}, provider={
                "operation_id": "op-1", "status": "succeeded",
                "receipt_ref": "provider:operation/op-1", "completed_at": "2026-09-08T00:00:00Z"}))
        self.assertEqual(result["provider_completion"], "unknown")
        self.assertFalse(result["completion_time_consistent"])

    def test_equal_time_conflict_is_ambiguous_in_both_input_orders(self):
        a = self.record(data={"reported_status": "running"})
        b = self.record(data={"reported_status": "failed"})
        for records in ([a, b], [b, a]):
            entity = adapter.snapshot(records, as_of=NOW)["entities"][0]
            self.assertEqual(entity["selection"], "ambiguous")
            self.assertIsNone(entity["latest"])
            self.assertIsNone(entity["operation"])

    def test_future_observation_does_not_replace_present_observation(self):
        current = self.record()
        future = self.record(observed="2026-09-08T00:00:00Z")
        entity = adapter.snapshot([future, current], as_of=NOW)["entities"][0]
        self.assertEqual(entity["latest"]["record_id"], current["record_id"])
        self.assertEqual(adapter.freshness(future, as_of=NOW, max_age_seconds=60)["state"], "future")

    def test_reingestion_dedupes_without_refreshing_evidence_time(self):
        a = self.record()
        b = self.record(recorded="2026-09-08T00:00:00Z")
        entity = adapter.snapshot([a, b], as_of=NOW)["entities"][0]
        self.assertEqual(a["record_id"], b["record_id"])
        self.assertEqual(len(entity["observations"]), 1)
        self.assertEqual(entity["freshness"]["age_seconds"], 60)

    def test_catalog_preserves_unresolved_integration_and_known_session_urls(self):
        records = adapter.catalog_records(json.loads((HERE / "fleet.json").read_text()), recorded_at=NOW)
        by_id = {r["subject_id"]: r for r in records}
        native = by_id["01a07d24-eeb7-7211-97dd-0956000bbb4f"]
        self.assertIsNone(native["data"]["url"])
        self.assertEqual(native["data"]["import_path"], "integrations.command_center.core.CommandCenter")
        self.assertIsNone(native["provider"]["status"])
        self.assertEqual(by_id["gpt-sell"]["data"]["url"],
                         "https://chatgpt.com/c/6a9ef70e-0f6c-83ea-ae06-e5093d51b5c7")
        self.assertEqual(by_id["01a07d73-a79b-7d33-8451-0c1acbc2f000"]["data"]["url"],
                         "https://chatgpt.com/c/6a9f1774-69dc-83e9-a065-88f61de7f0a4")
        self.assertEqual(by_id["titan-project-strategy"]["data"]["url"],
                         "https://chatgpt.com/g/g-p-6a9f15847f708191aff9765e562b65aa/project")
        self.assertEqual(by_id["t14-policy-portfolio"]["data"]["source_commit"],
                         "e987ed4eec0c27223de7432a8bce88ff7e062697")
        self.assertTrue(all(r["observed_at"] is None for r in records))

    def test_local_vm_cli_emits_actual_measurement(self):
        run = subprocess.run([sys.executable, str(HERE / "adapter.py"), "local-vm",
                              "--vm-id", "test-current-runtime", "--directory", str(HERE)],
                             check=True, capture_output=True, text=True)
        record = json.loads(run.stdout)
        self.assertEqual(record["source"]["kind"], "local_measurement")
        self.assertGreater(record["data"]["disk_total_bytes"], 0)
        self.assertIsNone(record["data"]["network_egress"])
        self.assertIsNone(record["provider"]["status"])
        self.assertIsNotNone(record["observed_at"])


if __name__ == "__main__":
    unittest.main()
