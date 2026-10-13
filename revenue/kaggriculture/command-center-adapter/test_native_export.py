import copy
import json
from pathlib import Path
import unittest

from native_export import build_adapter

HERE = Path(__file__).resolve().parent


class NativeExportTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((HERE / "fleet.json").read_text())
        self.vm = json.loads((HERE / "local-vm.json").read_text())

    def test_existing_session_ids_and_actual_vm_binding(self):
        result = build_adapter(self.catalog, self.vm, generated_at="2026-09-08T00:00:00Z")
        sessions = {item["id"]: item for item in result["sessions"]}
        self.assertIn("claude-titan-vm", sessions)
        self.assertIn("gpt-titan-vm", sessions)
        self.assertIsNone(sessions["claude-titan-vm"]["cpu"])
        self.assertIsNone(sessions["gpt-titan-vm"]["cpu"])
        t14 = sessions["gpt-t14-vm"]
        self.assertEqual(t14["cpu"], self.vm["data"]["cpu_logical"])
        self.assertEqual(t14["ram_gib"], self.vm["data"]["memory_total_bytes"] / 2**30)
        self.assertEqual(t14["observed_at"], self.vm["observed_at"])
        self.assertEqual(result["resources"][0]["data"]["cpu_cgroup_quota"], 8)
        self.assertEqual(result["resources"][0]["data"]["memory_cgroup_limit_bytes"], 20 * 2**30)
        self.assertTrue(all(item["model"] is None and item["gpu"] is None for item in sessions.values()))

    def test_unrelated_vm_measurement_is_not_attached_to_a_session(self):
        other = copy.deepcopy(self.vm)
        other["subject_id"] = "unrelated-runtime"
        result = build_adapter(self.catalog, other, generated_at="2026-09-08T00:00:00Z")
        self.assertTrue(all(item["cpu"] is None and item["ram_gib"] is None for item in result["sessions"]))
        self.assertEqual(result["resources"][0]["subject_id"], "unrelated-runtime")

    def test_regeneration_does_not_refresh_measurement_time(self):
        document = json.loads((HERE / "adapter.json").read_text())
        regenerated = build_adapter(self.catalog, self.vm, generated_at=document["generated_at"])
        self.assertEqual(document, regenerated)
        later = build_adapter(self.catalog, self.vm, generated_at="2026-09-08T00:00:00Z")
        old_sessions = {item["id"]: item for item in document["sessions"]}
        self.assertEqual(later["sessions"], list(old_sessions.values()))


if __name__ == "__main__":
    unittest.main()
