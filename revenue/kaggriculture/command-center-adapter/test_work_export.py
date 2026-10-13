import copy
import json
from pathlib import Path
import unittest

from native_export import build_adapter
from work_export import build_work_items, activity_freshness, load_catalog

HERE = Path(__file__).resolve().parent


class WorkExportTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.fleet = json.loads((HERE / "fleet.json").read_text())
        self.vm = json.loads((HERE / "local-vm.json").read_text())

    def test_full_board_and_existing_session_references(self):
        items = build_work_items(self.catalog)
        self.assertEqual({x["lane"] for x in items if x["lane"]},
                         {f"T{i:02}" for i in range(1, 16)})
        self.assertTrue(all(x["owner"]["coordination_ref"] and x["session_ref"] for x in items))
        t15 = next(x for x in items if x["lane"] == "T15")
        self.assertEqual(t15["session_id"], "gpt-t11-vm")
        self.assertTrue(t15["session_ref"].endswith("6a9f137c-2da8-83e9-a6aa-b1c214a182ff"))

    def test_activity_never_refreshes_hardware(self):
        doc = build_adapter(self.fleet, self.vm, generated_at="2026-09-08T12:00:00Z",
                            work_catalog=self.catalog)
        sessions = {x["id"]: x for x in doc["sessions"]}
        self.assertEqual(sessions["gpt-t14-vm"]["observed_at"], self.vm["observed_at"])
        self.assertEqual(doc["resources"], [self.vm])
        self.assertEqual(len(sessions), 5)
        self.assertIn("T15", sessions["gpt-t11-vm"]["label"])
        self.assertIn("claude-titan-vm", sessions)
        self.assertIn("gpt-titan-vm", sessions)
        self.assertEqual(doc["work_items"], self.catalog["work_items"])

    def test_regeneration_and_fetch_time_do_not_refresh_old_activity(self):
        items = build_work_items(self.catalog)
        record = copy.deepcopy(next(x for x in items if x["lane"] == "T01"))
        old = record["latest_activity_at"]
        record["observed_at"] = "2026-09-08T12:00:00Z"
        result = activity_freshness(record, as_of="2026-09-08T12:00:00Z")
        self.assertEqual(result["state"], "stale")
        self.assertEqual(record["latest_activity_at"], old)

    def test_unknown_gemini_completion_is_separate_from_owner_report(self):
        gemini = next(x for x in build_work_items(self.catalog)
                      if x["id"] == "titan-gemini-research")
        self.assertEqual(gemini["reported_operation"]["completed_requests"], 4)
        self.assertIsNone(gemini["provider_completion"]["status"])
        self.assertIsNone(gemini["provider_completion"]["completed_at"])
        self.assertIsNone(gemini["session_id"])
        self.assertEqual(gemini["session_ref_kind"], "shared_equipment_route")
        self.assertEqual(activity_freshness(gemini, as_of="2026-09-08T12:00:00Z")["state"], "unknown")

    def test_landing_selection_hosting_and_report_time_are_independent(self):
        items = {x["id"]: x for x in build_work_items(self.catalog)}
        seller = items["titan-gpt-sell"]
        self.assertEqual(seller["landed"]["state"], "landed")
        self.assertEqual(seller["selected"]["state"], "not_selected")
        self.assertEqual(seller["hosted"]["state"], "not_uploaded")
        self.assertEqual(seller["landed"]["completed_at"], "2026-09-07T21:19:52Z")
        service = items["titan-t04"]
        self.assertIsNotNone(service["landed"]["observed_at"])
        self.assertIsNone(service["landed"]["completed_at"])
        self.assertIsNone(items["titan-t09"]["landed"]["state"])
        self.assertIsNone(items["titan-t09"]["provider_completion"]["status"])

    def test_detached_export_and_dated_provenance(self):
        before = copy.deepcopy(self.catalog)
        result = build_work_items(self.catalog)
        result[0]["owner"]["label"] = "changed"
        self.assertEqual(self.catalog, before)
        bad = copy.deepcopy(self.catalog)
        bad["work_items"][0]["latest_activity_source"] = None
        with self.assertRaises(ValueError):
            build_work_items(bad)


if __name__ == "__main__":
    unittest.main()

