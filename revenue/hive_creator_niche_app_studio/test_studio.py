from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from studio import CreatorConfig, StudioError, StudioStore, canonical_json_bytes, load_config, strict_json_loads, write_exclusive


def config_obj(**overrides):
    obj = {
        "schema_version": "creator-niche-app-studio/v1",
        "creator_id": "kilnkit_creator",
        "app_id": "kilnkit_class_planner",
        "app_name": "KilnKit Class Planner",
        "creator_label": "Ceramics educator / creator",
        "audience_label": "Ceramics teachers",
        "promise": "Plan consumables and shared tools from expected attendance.",
        "support_route": "creator-managed support route",
        "mvp_sprint_price_cents": 300000,
        "workflow": "attendance_supply_planner/v1",
        "limits": {"max_classes": 12, "max_items": 128, "max_saved_plans": 64},
    }
    obj.update(overrides)
    return obj


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cfg_path = self.root / "creator.json"
        cfg_path.write_bytes(canonical_json_bytes(config_obj()))
        self.cfg, self.sha = load_config(cfg_path)
        self.store = StudioStore(self.root / "app.sqlite3", self.cfg, self.sha)

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def seed(self):
        self.store.upsert_class("ceramics_a", "Ceramics A", 35, 28)
        self.store.upsert_class("ceramics_b", "Ceramics B", 30, 26)
        self.store.upsert_item("clay_bag", "Clay bag", "per_attendee_consumable", units_per_attendee=2, package_size=25)
        self.store.upsert_item("banding_wheel", "Banding wheel", "per_class_shared", units_per_class=4, package_size=1)
        self.store.upsert_item("texture_roller", "Texture roller", "program_shared", program_units=8, package_size=4)

    def test_actual_attendance_drives_consumables_only(self):
        self.seed(); p = self.store.compute_plan(); rows = {r["item_id"]: r for r in p["supply_plan"]}
        self.assertEqual(p["summary"], {"class_count": 2, "rostered_total": 65, "expected_total": 54, "attendance_gap": 11, "item_count": 3})
        self.assertEqual(rows["clay_bag"]["needed_units"], 108)
        self.assertEqual(rows["clay_bag"]["packages_to_prepare"], 5)
        self.assertEqual(rows["banding_wheel"]["needed_units"], 8)
        self.assertEqual(rows["texture_roller"]["needed_units"], 8)

    def test_changing_expected_does_not_scale_shared_tools(self):
        self.seed(); first = {r["item_id"]: r for r in self.store.compute_plan()["supply_plan"]}
        self.store.upsert_class("ceramics_a", "Ceramics A", 35, 20)
        second = {r["item_id"]: r for r in self.store.compute_plan()["supply_plan"]}
        self.assertNotEqual(first["clay_bag"]["needed_units"], second["clay_bag"]["needed_units"])
        self.assertEqual(first["banding_wheel"]["needed_units"], second["banding_wheel"]["needed_units"])
        self.assertEqual(first["texture_roller"]["needed_units"], second["texture_roller"]["needed_units"])

    def test_expected_cannot_exceed_roster(self):
        with self.assertRaises(StudioError): self.store.upsert_class("x", "X", 10, 11)

    def test_mode_requires_matching_quantity(self):
        with self.assertRaises(StudioError): self.store.upsert_item("x", "X", "per_class_shared", units_per_class=0)
        with self.assertRaises(StudioError): self.store.upsert_item("x", "X", "program_shared", program_units=0)

    def test_limits_are_enforced(self):
        tiny = CreatorConfig.from_obj(config_obj(limits={"max_classes": 1, "max_items": 1, "max_saved_plans": 1}))
        other = StudioStore(self.root / "tiny.sqlite3", tiny, "a"*64)
        try:
            other.upsert_class("a", "A", 1, 1)
            with self.assertRaises(StudioError): other.upsert_class("b", "B", 1, 1)
            other.upsert_item("a", "A", "program_shared", program_units=1)
            with self.assertRaises(StudioError): other.upsert_item("b", "B", "program_shared", program_units=1)
        finally: other.close()

    def test_saved_plan_idempotent_but_changed_retry_rejected(self):
        self.seed(); p1 = self.store.save_plan("week1", now="2026-09-13T16:00:00Z"); p2 = self.store.save_plan("week1", now="2026-09-13T16:01:00Z")
        self.assertEqual(p1, p2)
        self.store.upsert_class("ceramics_a", "Ceramics A", 35, 27)
        with self.assertRaises(StudioError): self.store.save_plan("week1")

    def test_config_generation_is_pinned_to_workspace(self):
        self.store.close()
        changed = CreatorConfig.from_obj(config_obj(app_name="Renamed"))
        with self.assertRaises(StudioError): StudioStore(self.root / "app.sqlite3", changed, "b"*64)
        self.store = StudioStore(self.root / "app.sqlite3", self.cfg, self.sha)

    def test_csv_neutralizes_formula_cells(self):
        self.store.upsert_class("a", "A", 1, 1)
        self.store.upsert_item("danger", "=SUM(A1:A2)", "program_shared", program_units=1, notes="@cmd")
        csv_bytes = self.store.export_csv(self.store.compute_plan())
        self.assertIn(b"'=SUM", csv_bytes); self.assertIn(b"'@cmd", csv_bytes)

    def test_support_packet_is_non_sending(self):
        raw = self.store.create_support_packet("Need help", "How do I model a kiln shelf?")
        obj = strict_json_loads(raw)
        self.assertIs(obj["send_authority"], False)
        self.assertEqual(obj["support_route"], self.cfg.support_route)

    def test_strict_json_rejects_duplicate_and_nonfinite(self):
        with self.assertRaises(StudioError): strict_json_loads(b'{"a":1,"a":2}')
        with self.assertRaises(StudioError): strict_json_loads(b'{"a":NaN}')

    def test_bool_is_not_int_in_limits_and_prices(self):
        with self.assertRaises(StudioError): CreatorConfig.from_obj(config_obj(mvp_sprint_price_cents=True))
        bad = config_obj(); bad["limits"]["max_items"] = True
        with self.assertRaises(StudioError): CreatorConfig.from_obj(bad)

    def test_unknown_config_key_rejected(self):
        bad = config_obj(); bad["mystery"] = "x"
        with self.assertRaises(StudioError): CreatorConfig.from_obj(bad)

    def test_config_symlink_rejected(self):
        real = self.root / "real.json"; real.write_bytes(canonical_json_bytes(config_obj()))
        link = self.root / "link.json"; link.symlink_to(real)
        with self.assertRaises(StudioError): load_config(link)

    def test_output_is_deterministic_for_same_state(self):
        self.seed(); a = canonical_json_bytes(self.store.compute_plan()); b = canonical_json_bytes(self.store.compute_plan()); self.assertEqual(a, b)

    def test_write_exclusive_never_overwrites(self):
        p = self.root / "out.json"; write_exclusive(p, b"one")
        with self.assertRaises(StudioError): write_exclusive(p, b"two")
        self.assertEqual(p.read_bytes(), b"one")

    def test_reopen_preserves_state(self):
        self.seed(); before = self.store.compute_plan(); self.store.close(); self.store = StudioStore(self.root / "app.sqlite3", self.cfg, self.sha); self.assertEqual(before, self.store.compute_plan())

    def test_order_is_stable(self):
        self.store.upsert_class("z", "Z", 3, 2); self.store.upsert_class("a", "A", 2, 1)
        self.store.upsert_item("z", "Z", "program_shared", program_units=1); self.store.upsert_item("a", "A", "program_shared", program_units=1)
        p = self.store.compute_plan(); self.assertEqual([c["class_id"] for c in p["classes"]], ["a", "z"]); self.assertEqual([r["item_id"] for r in p["supply_plan"]], ["a", "z"])

    def test_plan_requires_classes_and_items(self):
        with self.assertRaises(StudioError): self.store.compute_plan()
        self.store.upsert_class("a", "A", 1, 1)
        with self.assertRaises(StudioError): self.store.compute_plan()

    def test_safe_ids(self):
        with self.assertRaises(StudioError): self.store.upsert_class("../x", "X", 1, 1)
        with self.assertRaises(StudioError): self.store.upsert_item("A B", "X", "program_shared", program_units=1)


if __name__ == "__main__": unittest.main()
