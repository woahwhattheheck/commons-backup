from __future__ import annotations

import json
import unittest

from .core import (
    AuditError,
    ConflictError,
    DataError,
    PermissionDenied,
    ResidentStore,
    StaleWriteError,
    canonical_bytes,
    compile_migration,
    strict_json_loads,
)
from .demo import build_demo_receipt, synthetic_rows


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_key_rejected(self):
        with self.assertRaises(DataError):
            strict_json_loads('{"a":1,"a":2}')

    def test_nonfinite_rejected(self):
        with self.assertRaises(DataError):
            strict_json_loads('{"x":NaN}')

    def test_lone_surrogate_rejected(self):
        with self.assertRaises(DataError):
            strict_json_loads('"\\ud800"')

    def test_canonical_is_order_independent(self):
        self.assertEqual(canonical_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')


class MigrationTests(unittest.TestCase):
    def test_clean_plan(self):
        plan = compile_migration(synthetic_rows())
        self.assertEqual(plan.status, "NO_CONFLICTS")
        self.assertEqual(len(plan.records), 2)
        self.assertEqual(plan.source_rows, 3)

    def test_row_order_does_not_change_digest(self):
        rows = synthetic_rows()
        self.assertEqual(compile_migration(rows).plan_digest, compile_migration(reversed(rows)).plan_digest)

    def test_conflict_is_explicit_and_blocks_resident(self):
        rows = synthetic_rows()
        rows.append({"source": "other.csv", "row": 1, "record": {"resident_id": "R001", "program": "Surgery"}})
        plan = compile_migration(rows)
        self.assertEqual(plan.status, "CONFLICTS_PRESENT")
        self.assertEqual(plan.conflicts[0]["field"], "program")
        self.assertEqual([r["resident_id"] for r in plan.records], ["R002"])

    def test_bad_source_shape_rejected(self):
        with self.assertRaises(DataError):
            compile_migration([{"source": "x", "row": 1, "record": {"resident_id": "R001"}, "extra": True}])

    def test_missing_required_after_merge_rejected(self):
        with self.assertRaises(DataError):
            compile_migration([{"source": "x", "row": 1, "record": {"resident_id": "R001", "program": "FM"}}])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.rows = synthetic_rows()
        self.plan = compile_migration(self.rows)
        self.store = ResidentStore(self.rows)
        self.store.apply_migration(self.plan)

    def test_apply_conflicted_plan_rejected(self):
        rows = synthetic_rows()
        rows.append({"source": "other", "row": 1, "record": {"resident_id": "R001", "program": "Surgery"}})
        store = ResidentStore(rows)
        with self.assertRaises(ConflictError):
            store.apply_migration(compile_migration(rows))

    def test_unbound_store_rejects_plan(self):
        with self.assertRaises(DataError):
            ResidentStore().apply_migration(self.plan)

    def test_non_admin_migration_rejected(self):
        with self.assertRaises(PermissionDenied):
            ResidentStore(self.rows).apply_migration(self.plan, actor_role="coordinator")

    def test_second_initial_migration_rejected(self):
        with self.assertRaises(ConflictError):
            self.store.apply_migration(self.plan)

    def test_resident_self_only_own(self):
        own = self.store.view("R001", role="resident_self", self_resident_id="R001")
        self.assertEqual(own["resident"]["resident_id"], "R001")
        with self.assertRaises(PermissionDenied):
            self.store.view("R002", role="resident_self", self_resident_id="R001")

    def test_auditor_view_has_no_direct_identifiers(self):
        view = self.store.view("R001", role="auditor")["resident"]
        for forbidden in ("resident_id", "first_name", "last_name", "email"):
            self.assertNotIn(forbidden, view)

    def test_program_director_cannot_read_notes(self):
        self.assertNotIn("coordinator_notes", self.store.view("R001", role="program_director")["resident"])

    def test_stale_write_rejected(self):
        self.store.update("R001", expected_version=1, patch={"pgy_level": 3}, actor_role="program_director")
        with self.assertRaises(StaleWriteError):
            self.store.update("R001", expected_version=1, patch={"pgy_level": 4}, actor_role="program_director")

    def test_role_escalation_rejected(self):
        with self.assertRaises(PermissionDenied):
            self.store.update("R001", expected_version=1, patch={"email": "new@example.test"}, actor_role="program_director")

    def test_resident_cannot_write(self):
        with self.assertRaises(PermissionDenied):
            self.store.update("R001", expected_version=1, patch={"email": "new@example.test"}, actor_role="resident_self")

    def test_resident_id_immutable(self):
        with self.assertRaises(DataError):
            self.store.update("R001", expected_version=1, patch={"resident_id": "R999"}, actor_role="admin")

    def test_noop_rejected(self):
        with self.assertRaises(DataError):
            self.store.update("R001", expected_version=1, patch={"program": "Family Medicine"}, actor_role="admin")

    def test_update_advances_version_and_audit(self):
        result = self.store.update("R002", expected_version=1, patch={"license_status": "CURRENT"}, actor_role="coordinator")
        self.assertEqual(result["version"], 2)
        self.assertEqual(self.store.view("R002", role="admin")["version"], 2)
        self.assertTrue(self.store.verify_audit())

    def test_audit_tamper_rejected(self):
        events = list(self.store.audit_events(role="auditor"))
        events[0]["resident_id"] = "R999"
        with self.assertRaises(AuditError):
            self.store.verify_audit(events)

    def test_audit_reorder_rejected(self):
        events = list(self.store.audit_events(role="auditor"))
        events.reverse()
        with self.assertRaises(AuditError):
            self.store.verify_audit(events)

    def test_audit_permission(self):
        with self.assertRaises(PermissionDenied):
            self.store.audit_events(role="coordinator")

    def test_analytics_is_aggregate_only(self):
        export = self.store.analytics_export(role="auditor")
        encoded = json.dumps(export)
        self.assertEqual(export["record_count"], 2)
        self.assertNotIn("Avery", encoded)
        self.assertNotIn("example.test", encoded)
        self.assertNotIn("R001", encoded)

    def test_analytics_role_gate(self):
        with self.assertRaises(PermissionDenied):
            self.store.analytics_export(role="resident_self")

    def test_receipt_is_deterministic_for_same_operations(self):
        other = ResidentStore(self.rows)
        other.apply_migration(self.plan)
        self.assertEqual(self.store.receipt(), other.receipt())

    def test_invalid_date_order_rejected(self):
        with self.assertRaises(DataError):
            self.store.update("R001", expected_version=1, patch={"expected_end_date": "2024-01-01"}, actor_role="admin")


class DemoTests(unittest.TestCase):
    def test_demo_is_deterministic(self):
        self.assertEqual(build_demo_receipt(), build_demo_receipt())

    def test_demo_truth_ceiling(self):
        receipt = build_demo_receipt()
        self.assertFalse(receipt["final_receipt"]["clinical_decision_support"])
        self.assertFalse(receipt["final_receipt"]["live_osu_data_used"])
        self.assertEqual(receipt["qualification"]["status"], "TEAMING_REQUIRED")
        self.assertFalse(receipt["qualification"]["submission_authorized"])


if __name__ == "__main__":
    unittest.main()
