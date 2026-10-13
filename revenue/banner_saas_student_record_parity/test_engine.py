from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    from .engine import (
        ParityError,
        canonical_json_bytes,
        canonical_sha256,
        compile_parity,
        load_json_bytes,
        render_markdown,
        verify_report,
        write_new_text,
    )
    from .synthetic_acceptance import make_acceptance, run_acceptance
except ImportError:
    from engine import (
        ParityError,
        canonical_json_bytes,
        canonical_sha256,
        compile_parity,
        load_json_bytes,
        render_markdown,
        verify_report,
        write_new_text,
    )
    from synthetic_acceptance import make_acceptance, run_acceptance

AS_OF = "2026-09-13T14:00:00Z"
CAPTURED = "2026-09-13T13:55:00Z"
FRESH = "2026-09-13T13:50:00Z"


def rec(student: str = "student-1", term: str = "2026FA", sync: str = FRESH, **updates):
    row = {
        "student_id": student,
        "term": term,
        "program": "PROGRAM-A",
        "enrollment_status": "ACTIVE",
        "holds": [],
        "advisor": "advisor-a",
        "last_sync_utc": sync,
    }
    row.update(updates)
    return row


def rows_sha(rows):
    ordered = sorted(rows, key=lambda r: (r["student_id"], r["term"], canonical_sha256(r)))
    return canonical_sha256(ordered)


def snap(role: str, sid: str, rows, captured: str = CAPTURED):
    return {
        "snapshot_id": sid,
        "system_role": role,
        "schema_revision": "student-parity-v1",
        "captured_at_utc": captured,
        "complete_export": True,
        "rows_sha256": rows_sha(rows),
        "rows": rows,
    }


class FrozenAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.target, cls.policy = make_acceptance(AS_OF)
        cls.report = compile_parity(cls.source, cls.target, cls.policy, as_of=AS_OF)

    def test_exact_2000_distribution(self):
        self.assertEqual(self.report["summary"]["source_record_count"], 2000)
        self.assertEqual(
            self.report["summary"]["counts"],
            {
                "DUPLICATE_ID": 25,
                "FIELD_MISMATCH": 35,
                "MISSING_TARGET": 40,
                "PARITY_OK": 1850,
                "STALE_SYNC": 50,
            },
        )
        self.assertEqual(sum(self.report["summary"]["counts"].values()), 2000)
        self.assertEqual(self.report["summary"]["state"], "RECONCILIATION_REQUIRED")

    def test_three_runs_have_identical_receipt(self):
        receipts = [run_acceptance(AS_OF)["receipt_sha256"] for _ in range(3)]
        self.assertEqual(len(set(receipts)), 1)

    def test_order_invariance(self):
        source = copy.deepcopy(self.source)
        target = copy.deepcopy(self.target)
        source["rows"].reverse()
        target["rows"].reverse()
        reordered = compile_parity(source, target, self.policy, as_of=AS_OF)
        self.assertEqual(canonical_json_bytes(reordered), canonical_json_bytes(self.report))

    def test_verifier_and_markdown_are_deterministic(self):
        verified = verify_report(self.report)
        self.assertTrue(verified["verified"])
        self.assertEqual(render_markdown(self.report), render_markdown(copy.deepcopy(self.report)))

    def test_zero_parity_possible_with_missing_id_or_term(self):
        source = copy.deepcopy(self.source)
        del source["rows"][0]["student_id"]
        source["rows_sha256"] = "0" * 64
        with self.assertRaises(ParityError):
            compile_parity(source, self.target, self.policy, as_of=AS_OF)
        source = copy.deepcopy(self.source)
        del source["rows"][0]["term"]
        source["rows_sha256"] = "0" * 64
        with self.assertRaises(ParityError):
            compile_parity(source, self.target, self.policy, as_of=AS_OF)


class ClassificationTests(unittest.TestCase):
    def test_target_duplicate_is_duplicate_id(self):
        row = rec()
        source = snap("SOURCE_BANNER", "source-a", [row])
        target = snap("TARGET_SAAS", "target-a", [copy.deepcopy(row), copy.deepcopy(row)])
        report = compile_parity(source, target, {"max_sync_age_minutes": 120}, as_of=AS_OF)
        self.assertEqual(report["results"][0]["classification"], "DUPLICATE_ID")
        self.assertEqual(report["results"][0]["target_occurrences"], 2)

    def test_source_duplicate_is_duplicate_id(self):
        row = rec()
        source = snap("SOURCE_BANNER", "source-a", [row, copy.deepcopy(row)])
        target = snap("TARGET_SAAS", "target-a", [copy.deepcopy(row)])
        report = compile_parity(source, target, {"max_sync_age_minutes": 120}, as_of=AS_OF)
        self.assertEqual(report["results"][0]["classification"], "DUPLICATE_ID")
        self.assertEqual(report["results"][0]["source_occurrences"], 2)

    def test_business_mismatch_precedes_stale(self):
        source_row = rec()
        target_row = rec(sync="2026-09-13T10:00:00Z", program="PROGRAM-B")
        report = compile_parity(
            snap("SOURCE_BANNER", "source-a", [source_row]),
            snap("TARGET_SAAS", "target-a", [target_row]),
            {"max_sync_age_minutes": 120},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "FIELD_MISMATCH")
        self.assertEqual(report["results"][0]["field_diffs"][0]["field"], "program")

    def test_exact_staleness_boundary(self):
        boundary = "2026-09-13T12:00:00Z"
        row = rec(sync=boundary)
        report = compile_parity(
            snap("SOURCE_BANNER", "source-a", [row]),
            snap("TARGET_SAAS", "target-a", [copy.deepcopy(row)]),
            {"max_sync_age_minutes": 120},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "PARITY_OK")
        stale_row = rec(sync="2026-09-13T11:59:00Z")
        report = compile_parity(
            snap("SOURCE_BANNER", "source-b", [stale_row]),
            snap("TARGET_SAAS", "target-b", [copy.deepcopy(stale_row)]),
            {"max_sync_age_minutes": 120},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "STALE_SYNC")

    def test_fresh_last_sync_mismatch_is_field_mismatch(self):
        source_row = rec(sync="2026-09-13T13:50:00Z")
        target_row = rec(sync="2026-09-13T13:49:00Z")
        report = compile_parity(
            snap("SOURCE_BANNER", "source-a", [source_row]),
            snap("TARGET_SAAS", "target-a", [target_row]),
            {"max_sync_age_minutes": 120},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "FIELD_MISMATCH")
        self.assertEqual(report["results"][0]["field_diffs"][0]["field"], "last_sync_utc")

    def test_target_only_key_prevents_clear_state(self):
        row = rec()
        extra = rec(student="student-2")
        report = compile_parity(
            snap("SOURCE_BANNER", "source-a", [row]),
            snap("TARGET_SAAS", "target-a", [copy.deepcopy(row), extra]),
            {"max_sync_age_minutes": 120},
            as_of=AS_OF,
        )
        self.assertEqual(report["summary"]["counts"]["PARITY_OK"], 1)
        self.assertEqual(report["summary"]["target_only_key_count"], 1)
        self.assertEqual(report["summary"]["state"], "RECONCILIATION_REQUIRED")


class StrictInputTests(unittest.TestCase):
    def test_duplicate_json_key_and_nonfinite_fail(self):
        with self.assertRaises(ParityError):
            load_json_bytes(b'{"a":1,"a":1}')
        with self.assertRaises(ParityError):
            load_json_bytes(b'{"a":NaN}')

    def test_bool_int_alias_and_unknown_policy_fail(self):
        row = rec()
        source = snap("SOURCE_BANNER", "source-a", [row])
        target = snap("TARGET_SAAS", "target-a", [copy.deepcopy(row)])
        with self.assertRaises(ParityError):
            compile_parity(source, target, {"max_sync_age_minutes": True}, as_of=AS_OF)
        with self.assertRaises(ParityError):
            compile_parity(source, target, {"max_sync_age_minutes": 120, "x": 1}, as_of=AS_OF)

    def test_timezone_alias_future_and_unknown_record_key_fail(self):
        row = rec(sync="2026-09-13T14:01:00Z")
        with self.assertRaises(ParityError):
            snap_src = snap("SOURCE_BANNER", "source-a", [row])
            snap_tgt = snap("TARGET_SAAS", "target-a", [copy.deepcopy(row)])
            compile_parity(snap_src, snap_tgt, {"max_sync_age_minutes": 120}, as_of=AS_OF)
        row = rec(sync="2026-09-13T13:50:00+00:00")
        with self.assertRaises(ParityError):
            compile_parity(
                snap("SOURCE_BANNER", "source-b", [row]),
                snap("TARGET_SAAS", "target-b", [copy.deepcopy(row)]),
                {"max_sync_age_minutes": 120},
                as_of=AS_OF,
            )
        row = rec()
        row["extra"] = "x"
        with self.assertRaises(ParityError):
            compile_parity(
                snap("SOURCE_BANNER", "source-c", [row]),
                snap("TARGET_SAAS", "target-c", [copy.deepcopy(row)]),
                {"max_sync_age_minutes": 120},
                as_of=AS_OF,
            )

    def test_rows_digest_and_snapshot_identity_must_bind(self):
        row = rec()
        source = snap("SOURCE_BANNER", "source-a", [row])
        target = snap("TARGET_SAAS", "target-a", [copy.deepcopy(row)])
        source["rows_sha256"] = "0" * 64
        with self.assertRaises(ParityError):
            compile_parity(source, target, {"max_sync_age_minutes": 120}, as_of=AS_OF)
        source = snap("SOURCE_BANNER", "same", [row])
        target = snap("TARGET_SAAS", "same", [copy.deepcopy(row)])
        with self.assertRaises(ParityError):
            compile_parity(source, target, {"max_sync_age_minutes": 120}, as_of=AS_OF)

    def test_incomplete_export_and_schema_mismatch_fail(self):
        row = rec()
        source = snap("SOURCE_BANNER", "source-a", [row])
        target = snap("TARGET_SAAS", "target-a", [copy.deepcopy(row)])
        source["complete_export"] = False
        with self.assertRaises(ParityError):
            compile_parity(source, target, {"max_sync_age_minutes": 120}, as_of=AS_OF)
        source = snap("SOURCE_BANNER", "source-a", [row])
        target = snap("TARGET_SAAS", "target-a", [copy.deepcopy(row)])
        target["schema_revision"] = "student-parity-v2"
        with self.assertRaises(ParityError):
            compile_parity(source, target, {"max_sync_age_minutes": 120}, as_of=AS_OF)


class IntegrityAndIOTests(unittest.TestCase):
    def test_receipt_tamper_and_resealed_input_tamper_fail(self):
        report = run_acceptance(AS_OF)
        tampered = copy.deepcopy(report)
        tampered["summary"]["counts"]["PARITY_OK"] += 1
        with self.assertRaises(ParityError):
            verify_report(tampered)
        tampered = copy.deepcopy(report)
        tampered["source"]["rows"][0]["program"] = "ALTERED"
        without = {k: tampered[k] for k in tampered if k != "receipt_sha256"}
        tampered["receipt_sha256"] = canonical_sha256(without)
        with self.assertRaises(ParityError):
            verify_report(tampered)

    def test_create_exclusive_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            out = base / "out.txt"
            write_new_text(out, "one")
            self.assertEqual(out.read_text(), "one")
            with self.assertRaises(ParityError):
                write_new_text(out, "two")
            target = base / "target.txt"
            target.write_text("safe")
            link = base / "link.txt"
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(ParityError):
                write_new_text(link, "overwrite")
            self.assertEqual(target.read_text(), "safe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
