from __future__ import annotations

import copy
import inspect
import unittest

from .core import DataError, MigrationPlan, ResidentStore, compile_migration, digest
from .demo import synthetic_rows


class HardeningTests(unittest.TestCase):
    def test_impossible_calendar_date_rejected(self):
        rows = synthetic_rows()
        store = ResidentStore(rows)
        store.apply_migration(compile_migration(rows))
        with self.assertRaises(DataError):
            store.update(
                "R001",
                expected_version=1,
                patch={"expected_end_date": "2028-99-99"},
                actor_role="admin",
            )

    def test_forged_plan_digest_rejected(self):
        rows = synthetic_rows()
        plan = compile_migration(rows)
        forged = MigrationPlan(plan.records, (), plan.source_rows, "0" * 64)
        with self.assertRaises(DataError):
            ResidentStore(rows).apply_migration(forged)

    def test_forged_noncanonical_plan_record_rejected(self):
        rows = synthetic_rows()
        plan = compile_migration(rows)
        records = [dict(item) for item in plan.records]
        records[0]["email"] = records[0]["email"].upper()
        body = {"records": records, "conflicts": [], "source_rows": plan.source_rows}
        forged = MigrationPlan(tuple(records), (), plan.source_rows, digest(body))
        with self.assertRaises(DataError):
            ResidentStore(rows).apply_migration(forged)

    def test_correct_digest_cannot_erase_retained_source_conflict(self):
        # Exact predecessor from SOURCE/AUTHORITY review: authoritative rows
        # contain an A/B conflict on R001.program, but the caller hand-builds a
        # clean A-side result, erases conflicts, and correctly recomputes the
        # public plan digest.  Self-consistency is not migration authority.
        clean_rows = synthetic_rows()
        clean_plan = compile_migration(clean_rows)
        conflicting_rows = synthetic_rows()
        conflicting_rows.append({
            "source": "source_b.csv",
            "row": 1,
            "record": {"resident_id": "R001", "program": "Surgery"},
        })
        authoritative_plan = compile_migration(conflicting_rows)
        self.assertEqual(authoritative_plan.status, "CONFLICTS_PRESENT")
        self.assertEqual(authoritative_plan.conflicts[0]["field"], "program")

        forged_records = tuple(dict(record) for record in clean_plan.records)
        forged_body = {
            "records": list(forged_records),
            "conflicts": [],
            "source_rows": len(conflicting_rows),
        }
        forged = MigrationPlan(
            records=forged_records,
            conflicts=(),
            source_rows=len(conflicting_rows),
            plan_digest=digest(forged_body),
        )
        self.assertEqual(digest(forged_body), forged.plan_digest)
        self.assertEqual(forged.status, "NO_CONFLICTS")

        store = ResidentStore(conflicting_rows)
        with self.assertRaisesRegex(DataError, "does not match retained source generation"):
            store.apply_migration(forged)

    def test_equal_plan_cannot_select_alternate_source_generation(self):
        # Provenance-only mutation: same records/count, different source/row labels.
        source_a = synthetic_rows()
        source_b = copy.deepcopy(source_a)
        source_b[0]["source"] = "alternate_roster.csv"
        source_b[0]["row"] = 99
        plan_a = compile_migration(source_a)
        plan_b = compile_migration(source_b)
        self.assertEqual(plan_a, plan_b)
        self.assertEqual(plan_a.plan_digest, plan_b.plan_digest)
        self.assertNotEqual(source_a[0]["source"], source_b[0]["source"])

        store = ResidentStore(source_a)
        with self.assertRaises(TypeError):
            store.apply_migration(plan_a, source_generation=source_b)
        store.apply_migration(plan_a)
        self.assertEqual(store.receipt()["record_count"], 2)

    def test_audit_and_receipt_reject_caller_source_selection(self):
        rows = synthetic_rows()
        store = ResidentStore(rows)
        store.apply_migration(compile_migration(rows))
        self.assertNotIn("source_generation", inspect.signature(store.verify_audit).parameters)
        self.assertNotIn("source_generation", inspect.signature(store.receipt).parameters)
        self.assertNotIn("source_generation", inspect.signature(store.apply_migration).parameters)
        with self.assertRaises(TypeError):
            store.verify_audit(source_generation=["truthy-but-unbound"])
        with self.assertRaises(TypeError):
            store.receipt(source_generation=["truthy-but-unbound"])


if __name__ == "__main__":
    unittest.main()
