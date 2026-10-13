from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path

try:
    from .engine import (
        TransferError,
        canonical_json_bytes,
        canonical_sha256,
        load_json_bytes,
        write_new_text,
    )
    from .historical import (
        compile_transfer as _historical_compile,
        render_markdown as _historical_render,
        seal_existing_decision as _historical_seal,
        verify_report as _historical_verify,
    )
    from .synthetic_acceptance import (
        make_acceptance,
        run_acceptance as _run_acceptance_envelope,
    )
except ImportError:
    from engine import (
        TransferError,
        canonical_json_bytes,
        canonical_sha256,
        load_json_bytes,
        write_new_text,
    )
    from historical import (
        compile_transfer as _historical_compile,
        render_markdown as _historical_render,
        seal_existing_decision as _historical_seal,
        verify_report as _historical_verify,
    )
    from synthetic_acceptance import (
        make_acceptance,
        run_acceptance as _run_acceptance_envelope,
    )

# Compatibility helpers for the frozen predecessor classifier corpus.  These
# exist only in this test module; the supported package/current module never
# exposes caller-selected time as current authority.
def compile_transfer(source, receiving, policy, *, as_of):
    return _historical_compile(source, receiving, policy, as_of=as_of)["decision"]


def verify_report(report):
    return _historical_verify(_historical_seal(report))


def render_markdown(report):
    return _historical_render(_historical_seal(report))


def run_acceptance(as_of):
    return _run_acceptance_envelope(as_of)["decision"]


AS_OF = "2026-09-13T15:00:00Z"
CAPTURED = "2026-09-13T14:55:00Z"
FRESH = "2026-09-13T14:45:00Z"
HASH = "a" * 64


def row(updated: str = FRESH, **updates):
    value = {
        "project_id": "project-1",
        "molecule_id": "molecule-1",
        "batch_id": "batch-1",
        "site_id": "chicago",
        "receiving_site_id": "rankweil",
        "process_version": "process-v1",
        "method_version": "method-v1",
        "container_configuration": "synthetic-container-a",
        "equipment_id": "equipment-rankweil-1",
        "equipment_calibration_sha256": HASH,
        "operator_qualification_sha256": "b" * 64,
        "qc_inspection_sha256": "c" * 64,
        "microbiology_evidence_sha256": "d" * 64,
        "storage_condition": "synthetic-controlled-2-8C",
        "transfer_evidence_sha256": "e" * 64,
        "release_evidence_sha256": "f" * 64,
        "last_updated_utc": updated,
    }
    value.update(updates)
    return value


def rows_sha(rows):
    ordered = sorted(
        rows,
        key=lambda r: (
            r["project_id"],
            r["molecule_id"],
            r["batch_id"],
            r["site_id"],
            canonical_sha256(r),
        ),
    )
    return canonical_sha256(ordered)


def snap(
    role: str,
    sid: str,
    rows,
    *,
    generation: str = "gen-1",
    schema: str = "clinical-fill-tech-transfer-v1",
    captured: str = CAPTURED,
):
    return {
        "snapshot_id": sid,
        "system_role": role,
        "schema_revision": schema,
        "transfer_generation": generation,
        "captured_at_utc": captured,
        "complete_export": True,
        "rows_sha256": rows_sha(rows),
        "rows": rows,
    }


class FrozenAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.receiving, cls.policy = make_acceptance(AS_OF)
        cls.report = compile_transfer(
            cls.source, cls.receiving, cls.policy, as_of=AS_OF
        )

    def test_exact_144_distribution(self):
        counts = self.report["summary"]["counts"]
        self.assertEqual(self.report["summary"]["source_packet_count"], 144)
        self.assertEqual(sum(counts.values()), 144)
        self.assertEqual(counts["TRANSFER_READY"], 120)
        self.assertEqual(counts["METHOD_OR_VERSION_MISMATCH"], 4)
        self.assertEqual(counts["LOT_OR_RELEASE_GAP"], 4)
        self.assertEqual(counts["CONTAINER_OR_BATCH_CONFIG_MISMATCH"], 4)
        self.assertEqual(counts["EQUIPMENT_OR_CALIBRATION_GAP"], 4)
        self.assertEqual(counts["OPERATOR_QUALIFICATION_GAP"], 4)
        self.assertEqual(counts["MICROBIOLOGY_OR_INSPECTION_GAP"], 4)
        for name in (
            "STALE_EVIDENCE",
            "DUPLICATE_PACKET",
            "MISSING_RECEIVING_PACKET",
            "TRANSFER_CONFLICT",
        ):
            self.assertEqual(counts[name], 0)

    def test_all_24_holds_have_field_commitments(self):
        holds = [
            r for r in self.report["results"] if r["classification"] != "TRANSFER_READY"
        ]
        self.assertEqual(len(holds), 24)
        for item in holds:
            self.assertTrue(item["field_diffs"])
            for diff in item["field_diffs"]:
                self.assertIn("field", diff)
                self.assertRegex(diff["source_value_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(diff["receiving_value_sha256"], r"^[0-9a-f]{64}$")

    def test_three_runs_same_receipt(self):
        receipts = [run_acceptance(AS_OF)["receipt_sha256"] for _ in range(3)]
        self.assertEqual(len(set(receipts)), 1)

    def test_order_invariant(self):
        source = copy.deepcopy(self.source)
        receiving = copy.deepcopy(self.receiving)
        source["rows"].reverse()
        receiving["rows"].reverse()
        rebuilt = compile_transfer(source, receiving, self.policy, as_of=AS_OF)
        self.assertEqual(
            canonical_json_bytes(rebuilt), canonical_json_bytes(self.report)
        )

    def test_verifier_and_markdown_deterministic(self):
        self.assertTrue(verify_report(self.report)["verified"])
        self.assertEqual(
            render_markdown(self.report), render_markdown(copy.deepcopy(self.report))
        )


class ClassificationTests(unittest.TestCase):
    def compile_one(self, source_row=None, receiving_row=None, policy=None):
        source_row = row() if source_row is None else source_row
        receiving_row = (
            copy.deepcopy(source_row) if receiving_row is None else receiving_row
        )
        return compile_transfer(
            snap("SOURCE_SITE", "src-1", [source_row]),
            snap("RECEIVING_SITE", "recv-1", [receiving_row]),
            policy or {"max_evidence_age_minutes": 180},
            as_of=AS_OF,
        )

    def test_all_ready_can_clear(self):
        report = self.compile_one()
        self.assertEqual(report["results"][0]["classification"], "TRANSFER_READY")
        self.assertEqual(
            report["summary"]["state"], "TRANSFER_READY_FOR_OWNER_REVIEW"
        )

    def test_named_family_precedence(self):
        source_row = row()
        receiving_row = row(method_version="method-v2", release_evidence_sha256=None)
        report = self.compile_one(source_row, receiving_row)
        self.assertEqual(
            report["results"][0]["classification"], "METHOD_OR_VERSION_MISMATCH"
        )

    def test_each_named_family(self):
        cases = [
            ({"process_version": "process-v2"}, "METHOD_OR_VERSION_MISMATCH"),
            ({"transfer_evidence_sha256": None}, "LOT_OR_RELEASE_GAP"),
            (
                {"container_configuration": "different"},
                "CONTAINER_OR_BATCH_CONFIG_MISMATCH",
            ),
            (
                {"equipment_calibration_sha256": None},
                "EQUIPMENT_OR_CALIBRATION_GAP",
            ),
            (
                {"operator_qualification_sha256": None},
                "OPERATOR_QUALIFICATION_GAP",
            ),
            (
                {"qc_inspection_sha256": None},
                "MICROBIOLOGY_OR_INSPECTION_GAP",
            ),
        ]
        for updates, expected in cases:
            with self.subTest(expected=expected):
                report = self.compile_one(row(), row(**updates))
                self.assertEqual(report["results"][0]["classification"], expected)

    def test_duplicate_and_missing(self):
        a = row()
        report = compile_transfer(
            snap("SOURCE_SITE", "src-1", [a, copy.deepcopy(a)]),
            snap("RECEIVING_SITE", "recv-1", [copy.deepcopy(a)]),
            {"max_evidence_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["results"][0]["classification"], "DUPLICATE_PACKET")
        report = compile_transfer(
            snap("SOURCE_SITE", "src-2", [a]),
            snap("RECEIVING_SITE", "recv-2", []),
            {"max_evidence_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(
            report["results"][0]["classification"], "MISSING_RECEIVING_PACKET"
        )

    def test_generic_conflict_and_target_only(self):
        source_row = row()
        receiving_row = row(storage_condition="synthetic-frozen")
        report = self.compile_one(source_row, receiving_row)
        self.assertEqual(
            report["results"][0]["classification"], "TRANSFER_CONFLICT"
        )
        extra = row(batch_id="batch-2")
        report = compile_transfer(
            snap("SOURCE_SITE", "src-3", [source_row]),
            snap(
                "RECEIVING_SITE",
                "recv-3",
                [copy.deepcopy(source_row), extra],
            ),
            {"max_evidence_age_minutes": 180},
            as_of=AS_OF,
        )
        self.assertEqual(report["summary"]["receiving_only_key_count"], 1)
        self.assertEqual(
            report["summary"]["state"], "HOLD_FOR_OWNER_RECONCILIATION"
        )

    def test_exact_stale_boundary(self):
        boundary = row(updated="2026-09-13T12:00:00Z")
        report = self.compile_one(
            boundary,
            copy.deepcopy(boundary),
            {"max_evidence_age_minutes": 180},
        )
        self.assertEqual(report["results"][0]["classification"], "TRANSFER_READY")
        stale = row(updated="2026-09-13T11:59:00Z")
        report = self.compile_one(
            stale,
            copy.deepcopy(stale),
            {"max_evidence_age_minutes": 180},
        )
        self.assertEqual(report["results"][0]["classification"], "STALE_EVIDENCE")


class CustodyAndStrictnessTests(unittest.TestCase):
    def test_generation_schema_identity_and_roles_fail_closed(self):
        a = row()
        with self.assertRaises(TransferError):
            compile_transfer(
                snap("SOURCE_SITE", "src", [a], generation="g1"),
                snap(
                    "RECEIVING_SITE",
                    "recv",
                    [copy.deepcopy(a)],
                    generation="g2",
                ),
                {"max_evidence_age_minutes": 180},
                as_of=AS_OF,
            )
        with self.assertRaises(TransferError):
            compile_transfer(
                snap("SOURCE_SITE", "src", [a]),
                snap(
                    "RECEIVING_SITE", "recv", [copy.deepcopy(a)], schema="v2"
                ),
                {"max_evidence_age_minutes": 180},
                as_of=AS_OF,
            )
        with self.assertRaises(TransferError):
            compile_transfer(
                snap("SOURCE_SITE", "same", [a]),
                snap("RECEIVING_SITE", "same", [copy.deepcopy(a)]),
                {"max_evidence_age_minutes": 180},
                as_of=AS_OF,
            )
        with self.assertRaises(TransferError):
            compile_transfer(
                snap("RECEIVING_SITE", "src", [a]),
                snap("RECEIVING_SITE", "recv", [copy.deepcopy(a)]),
                {"max_evidence_age_minutes": 180},
                as_of=AS_OF,
            )

    def test_rows_digest_and_incomplete_export_fail(self):
        a = row()
        source = snap("SOURCE_SITE", "src", [a])
        source["rows_sha256"] = "0" * 64
        with self.assertRaises(TransferError):
            compile_transfer(
                source,
                snap("RECEIVING_SITE", "recv", [copy.deepcopy(a)]),
                {"max_evidence_age_minutes": 180},
                as_of=AS_OF,
            )
        source = snap("SOURCE_SITE", "src2", [a])
        source["complete_export"] = False
        with self.assertRaises(TransferError):
            compile_transfer(
                source,
                snap("RECEIVING_SITE", "recv2", [copy.deepcopy(a)]),
                {"max_evidence_age_minutes": 180},
                as_of=AS_OF,
            )

    def test_duplicate_json_nonfinite_bool_int_unknown_fields_fail(self):
        with self.assertRaises(TransferError):
            load_json_bytes(b'{"a":1,"a":1}')
        with self.assertRaises(TransferError):
            load_json_bytes(b'{"a":NaN}')
        a = row()
        source = snap("SOURCE_SITE", "src", [a])
        recv = snap("RECEIVING_SITE", "recv", [copy.deepcopy(a)])
        with self.assertRaises(TransferError):
            compile_transfer(
                source,
                recv,
                {"max_evidence_age_minutes": True},
                as_of=AS_OF,
            )
        bad = row()
        bad["extra"] = "x"
        with self.assertRaises(TransferError):
            compile_transfer(
                snap("SOURCE_SITE", "src2", [bad]),
                recv,
                {"max_evidence_age_minutes": 180},
                as_of=AS_OF,
            )

    def test_future_timezone_alias_malformed_hash_and_same_site_fail(self):
        for bad in [
            row(updated="2026-09-13T15:01:00Z"),
            row(updated="2026-09-13T14:45:00+00:00"),
            row(equipment_calibration_sha256="not-a-hash"),
            row(receiving_site_id="chicago"),
        ]:
            with self.subTest(bad=bad.get("last_updated_utc")):
                with self.assertRaises(TransferError):
                    compile_transfer(
                        snap("SOURCE_SITE", "src", [bad]),
                        snap("RECEIVING_SITE", "recv", [copy.deepcopy(bad)]),
                        {"max_evidence_age_minutes": 180},
                        as_of=AS_OF,
                    )


class IntegrityAndIOTests(unittest.TestCase):
    def test_receipt_and_resealed_snapshot_tamper_fail(self):
        report = run_acceptance(AS_OF)
        tampered = copy.deepcopy(report)
        tampered["summary"]["counts"]["TRANSFER_READY"] += 1
        with self.assertRaises(TransferError):
            verify_report(tampered)
        tampered = copy.deepcopy(report)
        tampered["source"]["rows"][0]["method_version"] = "altered"
        plain = {k: tampered[k] for k in tampered if k != "receipt_sha256"}
        tampered["receipt_sha256"] = canonical_sha256(plain)
        with self.assertRaises(TransferError):
            verify_report(tampered)

    def test_create_exclusive_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            out = base / "out.txt"
            write_new_text(out, "one")
            with self.assertRaises(TransferError):
                write_new_text(out, "two")
            target = base / "target.txt"
            target.write_text("safe")
            link = base / "link.txt"
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(TransferError):
                write_new_text(link, "overwrite")
            self.assertEqual(target.read_text(), "safe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
