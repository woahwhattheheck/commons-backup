from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path

try:
    from .engine import (
        CutoverError,
        canonical_json_bytes,
        canonical_sha256,
        compile_cutover,
        load_json_bytes,
        render_markdown,
        verify_report,
        write_new_text,
    )
    from .synthetic_acceptance import make_acceptance, run_acceptance
except ImportError:
    from engine import (
        CutoverError,
        canonical_json_bytes,
        canonical_sha256,
        compile_cutover,
        load_json_bytes,
        render_markdown,
        verify_report,
        write_new_text,
    )
    from synthetic_acceptance import make_acceptance, run_acceptance

AS_OF = "2026-09-13T14:30:00Z"
CAPTURED = "2026-09-13T14:25:00Z"
FRESH = "2026-09-13T14:15:00Z"
EVIDENCE = "a" * 64


def row(item: str = "item-1", batch: str = "batch-1", site: str = "site-1", updated: str = FRESH, **updates):
    value = {
        "item_id": item,
        "batch_id": batch,
        "site_id": site,
        "process_revision": "proc-r1",
        "quality_master_revision": "qm-r1",
        "inspection_evidence_sha256": EVIDENCE,
        "disposition": "SYNTHETIC-ACCEPTED",
        "last_updated_utc": updated,
    }
    value.update(updates)
    return value


def rows_sha(rows):
    ordered = sorted(rows, key=lambda r: (r["item_id"], r["batch_id"], r["site_id"], canonical_sha256(r)))
    return canonical_sha256(ordered)


def snap(role: str, sid: str, rows, *, generation: str = "gen-1", schema: str = "quality-master-cutover-v1", captured: str = CAPTURED):
    return {
        "snapshot_id": sid,
        "system_role": role,
        "schema_revision": schema,
        "release_generation": generation,
        "captured_at_utc": captured,
        "complete_export": True,
        "rows_sha256": rows_sha(rows),
        "rows": rows,
    }


class FrozenAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.target, cls.policy = make_acceptance(AS_OF)
        cls.report = compile_cutover(cls.source, cls.target, cls.policy, as_of=AS_OF)

    def test_exact_2000_distribution(self):
        self.assertEqual(self.report["summary"]["source_record_count"], 2000)
        self.assertEqual(
            self.report["summary"]["counts"],
            {
                "CONFLICT": 60,
                "DUPLICATE_KEY": 40,
                "MISSING_TARGET": 50,
                "READY": 1800,
                "STALE_TARGET": 50,
            },
        )
        self.assertEqual(sum(self.report["summary"]["counts"].values()), 2000)
        self.assertEqual(self.report["summary"]["state"], "HOLD_FOR_RECONCILIATION")

    def test_three_runs_same_receipt(self):
        receipts = [run_acceptance(AS_OF)["receipt_sha256"] for _ in range(3)]
        self.assertEqual(len(set(receipts)), 1)

    def test_order_invariant(self):
        source = copy.deepcopy(self.source)
        target = copy.deepcopy(self.target)
        source["rows"].reverse()
        target["rows"].reverse()
        rebuilt = compile_cutover(source, target, self.policy, as_of=AS_OF)
        self.assertEqual(canonical_json_bytes(rebuilt), canonical_json_bytes(self.report))

    def test_verifier_and_markdown_deterministic(self):
        self.assertTrue(verify_report(self.report)["verified"])
        self.assertEqual(render_markdown(self.report), render_markdown(copy.deepcopy(self.report)))


class ClassificationTests(unittest.TestCase):
    def test_all_ready_can_clear(self):
        a = row()
        report = compile_cutover(
            snap("SOURCE_CURRENT", "src-1", [a]),
            snap("TARGET_CUTOVER", "tgt-1", [copy.deepcopy(a)]),
            {"max_target_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["summary"]["state"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(report["results"][0]["classification"], "READY")

    def test_missing_target(self):
        a = row()
        report = compile_cutover(
            snap("SOURCE_CURRENT", "src-1", [a]),
            snap("TARGET_CUTOVER", "tgt-1", []),
            {"max_target_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "MISSING_TARGET")

    def test_source_and_target_duplicates_are_fail_closed(self):
        a = row()
        report = compile_cutover(
            snap("SOURCE_CURRENT", "src-1", [a, copy.deepcopy(a)]),
            snap("TARGET_CUTOVER", "tgt-1", [copy.deepcopy(a)]),
            {"max_target_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "DUPLICATE_KEY")
        report = compile_cutover(
            snap("SOURCE_CURRENT", "src-2", [a]),
            snap("TARGET_CUTOVER", "tgt-2", [copy.deepcopy(a), copy.deepcopy(a)]),
            {"max_target_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "DUPLICATE_KEY")

    def test_conflict_precedes_staleness(self):
        source_row = row(updated="2026-09-13T10:00:00Z")
        target_row = row(updated="2026-09-13T10:00:00Z", quality_master_revision="qm-r2")
        report = compile_cutover(
            snap("SOURCE_CURRENT", "src-1", [source_row]),
            snap("TARGET_CUTOVER", "tgt-1", [target_row]),
            {"max_target_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "CONFLICT")

    def test_exact_stale_boundary(self):
        boundary = row(updated="2026-09-13T11:30:00Z")
        report = compile_cutover(
            snap("SOURCE_CURRENT", "src-1", [boundary]),
            snap("TARGET_CUTOVER", "tgt-1", [copy.deepcopy(boundary)]),
            {"max_target_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "READY")
        stale = row(updated="2026-09-13T11:29:00Z")
        report = compile_cutover(
            snap("SOURCE_CURRENT", "src-2", [stale]),
            snap("TARGET_CUTOVER", "tgt-2", [copy.deepcopy(stale)]),
            {"max_target_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "STALE_TARGET")

    def test_fresh_timestamp_difference_is_conflict(self):
        source_row = row(updated="2026-09-13T14:15:00Z")
        target_row = row(updated="2026-09-13T14:14:00Z")
        report = compile_cutover(
            snap("SOURCE_CURRENT", "src-1", [source_row]),
            snap("TARGET_CUTOVER", "tgt-1", [target_row]),
            {"max_target_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "CONFLICT")
        self.assertEqual(report["results"][0]["field_diffs"][0]["field"], "last_updated_utc")

    def test_target_only_blocks_clear(self):
        a = row()
        extra = row(item="item-2", batch="batch-2")
        report = compile_cutover(
            snap("SOURCE_CURRENT", "src-1", [a]),
            snap("TARGET_CUTOVER", "tgt-1", [copy.deepcopy(a), extra]),
            {"max_target_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["summary"]["counts"]["READY"], 1)
        self.assertEqual(report["summary"]["target_only_key_count"], 1)
        self.assertEqual(report["summary"]["state"], "HOLD_FOR_RECONCILIATION")


class CustodyAndStrictnessTests(unittest.TestCase):
    def test_changed_release_generation_fails(self):
        a = row()
        with self.assertRaises(CutoverError):
            compile_cutover(
                snap("SOURCE_CURRENT", "src-1", [a], generation="gen-1"),
                snap("TARGET_CUTOVER", "tgt-1", [copy.deepcopy(a)], generation="gen-2"),
                {"max_target_age_minutes": 180},
                as_of=AS_OF,
            )

    def test_same_snapshot_identity_fails(self):
        a = row()
        with self.assertRaises(CutoverError):
            compile_cutover(
                snap("SOURCE_CURRENT", "same", [a]),
                snap("TARGET_CUTOVER", "same", [copy.deepcopy(a)]),
                {"max_target_age_minutes": 180},
                as_of=AS_OF,
            )

    def test_rows_digest_drift_fails(self):
        a = row()
        source = snap("SOURCE_CURRENT", "src-1", [a])
        source["rows_sha256"] = "0" * 64
        with self.assertRaises(CutoverError):
            compile_cutover(
                source,
                snap("TARGET_CUTOVER", "tgt-1", [copy.deepcopy(a)]),
                {"max_target_age_minutes": 180},
                as_of=AS_OF,
            )

    def test_incomplete_export_and_schema_mismatch_fail(self):
        a = row()
        source = snap("SOURCE_CURRENT", "src-1", [a])
        source["complete_export"] = False
        with self.assertRaises(CutoverError):
            compile_cutover(source, snap("TARGET_CUTOVER", "tgt-1", [copy.deepcopy(a)]), {"max_target_age_minutes": 180}, as_of=AS_OF)
        with self.assertRaises(CutoverError):
            compile_cutover(
                snap("SOURCE_CURRENT", "src-2", [a]),
                snap("TARGET_CUTOVER", "tgt-2", [copy.deepcopy(a)], schema="quality-master-cutover-v2"),
                {"max_target_age_minutes": 180},
                as_of=AS_OF,
            )

    def test_duplicate_json_keys_and_nonfinite_fail(self):
        with self.assertRaises(CutoverError):
            load_json_bytes(b'{"a":1,"a":1}')
        with self.assertRaises(CutoverError):
            load_json_bytes(b'{"a":NaN}')

    def test_bool_int_alias_unknown_policy_and_unknown_row_key_fail(self):
        a = row()
        source = snap("SOURCE_CURRENT", "src-1", [a])
        target = snap("TARGET_CUTOVER", "tgt-1", [copy.deepcopy(a)])
        with self.assertRaises(CutoverError):
            compile_cutover(source, target, {"max_target_age_minutes": True}, as_of=AS_OF)
        with self.assertRaises(CutoverError):
            compile_cutover(source, target, {"max_target_age_minutes": 180, "x": 1}, as_of=AS_OF)
        bad = row()
        bad["extra"] = "x"
        with self.assertRaises(CutoverError):
            compile_cutover(snap("SOURCE_CURRENT", "src-b", [bad]), target, {"max_target_age_minutes": 180}, as_of=AS_OF)

    def test_future_and_timezone_alias_fail(self):
        future = row(updated="2026-09-13T14:31:00Z")
        with self.assertRaises(CutoverError):
            compile_cutover(
                snap("SOURCE_CURRENT", "src-1", [future]),
                snap("TARGET_CUTOVER", "tgt-1", [copy.deepcopy(future)]),
                {"max_target_age_minutes": 180},
                as_of=AS_OF,
            )
        alias = row(updated="2026-09-13T14:15:00+00:00")
        with self.assertRaises(CutoverError):
            compile_cutover(
                snap("SOURCE_CURRENT", "src-2", [alias]),
                snap("TARGET_CUTOVER", "tgt-2", [copy.deepcopy(alias)]),
                {"max_target_age_minutes": 180},
                as_of=AS_OF,
            )


class IntegrityAndIOTests(unittest.TestCase):
    def test_receipt_and_resealed_snapshot_tamper_fail(self):
        report = run_acceptance(AS_OF)
        tampered = copy.deepcopy(report)
        tampered["summary"]["counts"]["READY"] += 1
        with self.assertRaises(CutoverError):
            verify_report(tampered)
        tampered = copy.deepcopy(report)
        tampered["source"]["rows"][0]["quality_master_revision"] = "qm-altered"
        plain = {k: tampered[k] for k in tampered if k != "receipt_sha256"}
        tampered["receipt_sha256"] = canonical_sha256(plain)
        with self.assertRaises(CutoverError):
            verify_report(tampered)

    def test_create_exclusive_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            out = base / "out.txt"
            write_new_text(out, "one")
            with self.assertRaises(CutoverError):
                write_new_text(out, "two")
            target = base / "target.txt"
            target.write_text("safe")
            link = base / "link.txt"
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(CutoverError):
                write_new_text(link, "overwrite")
            self.assertEqual(target.read_text(), "safe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
