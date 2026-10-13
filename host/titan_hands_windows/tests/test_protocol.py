from __future__ import annotations

import unittest

from host.titan_hands_windows.protocol import DeltaTracker, ProtocolError


class DeltaTrackerTests(unittest.TestCase):
    def test_full_then_minimal_delta(self):
        tracker = DeltaTracker()
        first = tracker.observe(
            {
                "nodes": [
                    {"id": "b", "role": "Button", "name": "Save", "actions": ["invoke"]},
                    {"id": "w", "role": "Window", "name": "Editor"},
                ],
                "focus_id": "b",
            }
        )
        self.assertTrue(first["full"])
        self.assertEqual([node["id"] for node in first["added"]], ["b", "w"])

        second = tracker.observe(
            {
                "nodes": [
                    {"id": "b", "role": "Button", "name": "Saved", "actions": ["invoke"]},
                    {"id": "n", "role": "Text", "name": "Complete"},
                ],
                "focus_id": "b",
            }
        )
        self.assertFalse(second["full"])
        self.assertEqual([node["id"] for node in second["added"]], ["n"])
        self.assertEqual([node["id"] for node in second["updated"]], ["b"])
        self.assertEqual(second["removed"], ["w"])
        self.assertFalse(second["meta_changed"])

    def test_order_does_not_change_digest(self):
        a = DeltaTracker().observe({"nodes": [{"id": "x", "states": ["b", "a"]}]})
        b = DeltaTracker().observe({"nodes": [{"id": "x", "states": ["a", "b"]}]})
        self.assertEqual(a["state_digest"], b["state_digest"])

    def test_current_nodes_track_latest_snapshot(self):
        tracker = DeltaTracker()
        tracker.observe({"nodes": [{"id": "x", "name": "one"}], "focus_id": "x"})
        self.assertEqual(tracker.current_nodes()["x"]["name"], "one")
        self.assertEqual(tracker.current_meta()["focus_id"], "x")

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(ProtocolError):
            DeltaTracker().observe({"nodes": [{"id": "x"}, {"id": "x"}]})


if __name__ == "__main__":
    unittest.main()
