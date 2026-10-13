import copy
import json
import tempfile
import unittest
from pathlib import Path

import family_schedule as fs
import panel_diversity as pd


def base_panel():
    return {
        "schema": pd.PANEL_SCHEMA,
        "expected_labels": 6,
        "opponents": [
            {"id":"a1","kind":"archetype","family":"A","source_id":"src-A","status":"resolved","rank":1},
            {"id":"a2","kind":"archetype","family":"A","source_id":"src-A","status":"resolved","rank":2},
            {"id":"a3","kind":"archetype","family":"A","source_id":"src-A","status":"resolved","rank":3},
            {"id":"b1","kind":"real_policy","family":"B","source_id":"src-B1","status":"resolved","rank":4},
            {"id":"b2","kind":"real_policy","family":"B","source_id":"src-B2","status":"resolved","rank":5},
            {"id":"m","kind":"mirror","family":"M","source_id":"src-M","status":"resolved"},
        ],
    }


class FamilyScheduleTests(unittest.TestCase):
    def test_equal_budget_per_family_despite_label_multiplicity(self):
        report = fs.plan(base_panel(), [7, 3], 2)
        counts = {row["family"]: row["cells"] for row in report["families"]}
        self.assertEqual(counts, {"A": 8, "B": 8, "M": 8})
        self.assertEqual(report["coverage"]["cells"], 24)
        self.assertEqual(report["coverage"]["cells_per_family"], 8)

    def test_both_seats_and_sorted_seed_order(self):
        report = fs.plan(base_panel(), [99, 1], 1)
        self.assertEqual(report["parameters"]["seeds"], [1, 99])
        by_family = [c for c in report["cells"] if c["family"] == "A"]
        self.assertEqual([(c["seed"], c["seat"]) for c in by_family], [(1,0),(1,1),(99,0),(99,1)])

    def test_round_robin_full_label_coverage_at_max_multiplicity(self):
        report = fs.plan(base_panel(), [1], 3)
        self.assertTrue(report["coverage"]["all_resolved_labels_seen"])
        self.assertEqual(report["coverage"]["cycles_for_full_label_coverage"], 3)
        fam_a = next(row for row in report["families"] if row["family"] == "A")
        self.assertEqual(fam_a["scheduled_labels"], ["a1", "a2", "a3"])

    def test_short_schedule_reports_partial_label_coverage(self):
        report = fs.plan(base_panel(), [1], 1)
        self.assertFalse(report["coverage"]["all_resolved_labels_seen"])
        self.assertEqual(report["coverage"]["resolved_labels_scheduled"], 3)
        self.assertEqual(report["coverage"]["resolved_labels_total"], 6)

    def test_rotation_offset_advances_alias_choice(self):
        p = base_panel()
        r0 = fs.plan(p, [1], 1, rotation_offset=0)
        r1 = fs.plan(p, [1], 1, rotation_offset=1)
        a0 = next(c for c in r0["cells"] if c["family"] == "A")
        a1 = next(c for c in r1["cells"] if c["family"] == "A")
        self.assertEqual(a0["opponent_id"], "a1")
        self.assertEqual(a1["opponent_id"], "a2")

    def test_input_opponent_order_does_not_change_schedule_or_panel_digest(self):
        p1 = base_panel()
        p2 = base_panel()
        p2["opponents"] = list(reversed(p2["opponents"]))
        r1 = fs.plan(p1, [5, 2], 2)
        r2 = fs.plan(p2, [2, 5], 2)
        self.assertEqual(r1["panel_identity_sha256"], r2["panel_identity_sha256"])
        self.assertEqual(r1["schedule_sha256"], r2["schedule_sha256"])
        self.assertEqual(r1["cells"], r2["cells"])

    def test_rank_changes_digest_and_schedule_alias_order(self):
        p1 = base_panel()
        p2 = copy.deepcopy(p1)
        p2["opponents"][0]["rank"] = 9
        r1 = fs.plan(p1, [1], 1)
        r2 = fs.plan(p2, [1], 1)
        self.assertNotEqual(r1["panel_identity_sha256"], r2["panel_identity_sha256"])
        a1 = next(c for c in r1["cells"] if c["family"] == "A")
        a2 = next(c for c in r2["cells"] if c["family"] == "A")
        self.assertEqual(a1["opponent_id"], "a1")
        self.assertEqual(a2["opponent_id"], "a2")

    def test_incomplete_panel_fails_closed_by_default(self):
        p = base_panel()
        p["opponents"][-1] = {"id":"missing","kind":"unknown","family":None,"source_id":None,"status":"unresolved"}
        with self.assertRaises(fs.IncompletePanelError):
            fs.plan(p, [1], 1)

    def test_preview_incomplete_is_explicit_non_authoritative(self):
        p = base_panel()
        p["opponents"][-1] = {"id":"missing","kind":"unknown","family":None,"source_id":None,"status":"unresolved"}
        report = fs.plan(p, [1], 1, preview_incomplete=True)
        self.assertFalse(report["authoritative"])
        self.assertEqual(report["panel_status"]["unresolved_labels"], ["missing"])
        self.assertNotIn("missing", {c["opponent_id"] for c in report["cells"]})

    def test_missing_expected_label_fails_closed(self):
        p = base_panel()
        p["opponents"].pop()
        with self.assertRaises(fs.IncompletePanelError):
            fs.plan(p, [1], 1)

    def test_duplicate_seed_rejected(self):
        with self.assertRaises(pd.DataError):
            fs.plan(base_panel(), [1, 1], 1)

    def test_bool_seed_rejected(self):
        with self.assertRaises(pd.DataError):
            fs.plan(base_panel(), [True], 1)

    def test_zero_or_bool_cycles_rejected(self):
        for bad in (0, True):
            with self.subTest(bad=bad):
                with self.assertRaises(pd.DataError):
                    fs.plan(base_panel(), [1], bad)

    def test_negative_or_bool_rotation_rejected(self):
        for bad in (-1, True):
            with self.subTest(bad=bad):
                with self.assertRaises(pd.DataError):
                    fs.plan(base_panel(), [1], 1, rotation_offset=bad)

    def test_cell_ids_unique_and_schedule_bound(self):
        report = fs.plan(base_panel(), [1, 2], 2)
        ids = [c["cell_id"] for c in report["cells"]]
        self.assertEqual(len(ids), len(set(ids)))
        changed = fs.plan(base_panel(), [1, 2], 2, rotation_offset=1)
        self.assertNotEqual(report["schedule_sha256"], changed["schedule_sha256"])

    def test_same_family_distinct_sources_rotate_without_extra_family_budget(self):
        report = fs.plan(base_panel(), [1], 2)
        fam_b = next(row for row in report["families"] if row["family"] == "B")
        self.assertEqual(fam_b["sources"], ["src-B1", "src-B2"])
        self.assertEqual(fam_b["scheduled_sources"], ["src-B1", "src-B2"])
        self.assertEqual(fam_b["cells"], 4)

    def test_cli_incomplete_exit_three_and_preview_zero(self):
        p = base_panel()
        p["opponents"][-1] = {"id":"missing","kind":"unknown","family":None,"source_id":None,"status":"unresolved"}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "panel.json"
            out = Path(td) / "schedule.json"
            path.write_text(json.dumps(p), encoding="utf-8")
            self.assertEqual(fs.main([str(path), "--seed", "1", "--cycles", "1"]), 3)
            self.assertEqual(fs.main([str(path), "--seed", "1", "--cycles", "1", "--preview-incomplete", "--output", str(out)]), 0)
            parsed = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(parsed["authoritative"])


if __name__ == "__main__":
    unittest.main()
